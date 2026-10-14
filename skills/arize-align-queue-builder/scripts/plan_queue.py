#!/usr/bin/env python3
"""Plan annotation queues for aligning one Arize evaluator, or their ongoing intake.

Builds two streams of records from a project:

  random    A uniform sample of the units the evaluator scored, drawn with a known probability and
            never filtered on its labels. This is the measurement set: agreement, the human ceiling
            and the evaluator's VALIDATED verdict come from it. It goes in its own calibration queue.
  targeted  Records picked to find the evaluator's failures: a balanced quota per stored label
            (provider disagreements first), judge-independent signals (--signal), not-applicable
            checks and scope probes. Use them for failure finding and dev/few-shot examples.

Every record carries a routing_reason (random, label_stratum, provider_disagreement, na_check,
scope_probe, signal:NAME) and the instructions version it was queued under. Writes:

  plan.md              Summary to show the user before anything is created
  plan.json            Every picked record, its stored labels and stream, and each stratum's
                       production count and selection rate (for `report --plan`)
  record_sources.*     The targeted records as SPAN sources of at most 7 days, in batches of 2:
                       pass record_sources.create.json to `ax annotation-queues create` and each
                       record_sources.add_N.json to `add-records`
  random_sources.*     The random stream, split the same way, for the calibration queue
  config_values.json   Proposed categorical label values for the annotation config

Intake (--intake plan.json --queue QUEUE [--random-queue QUEUE --random N]): sample only the units
that arrived since the last run, with the same strata and settings, into a new directory beside
plan.json (intake-N/). Each run's strata are counted and stored separately, so the weighting stays
exact. Without --execute this is a dry run. With --execute it adds the records to the queues and
appends them, the strata and the new cursor to plan.json; run it on a schedule for continuous intake.

Standard library only (Python 3.9+). Creates nothing in Arize, except `--intake --execute`.

Example:
  plan_queue.py --space SPACE --project PROJECT --evaluator EVALUATOR \\
    --root-filter "attributes.is_copilot_root_span = 'true'" --out-dir plan/
  plan_queue.py --space SPACE --intake plan/plan.json --queue QUEUE --per-label 2 --execute
"""

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}
UNSCORABLE = ["cannot_judge"]

# Sizing modes. "discovery" is enough to start: error analysis on the random stream (30+ traces read by a
# human) and a first alignment pass. It is not a measurement. "validation" puts 30 gold records per label in
# each of dev and test after the evaluator report's 15/42.5/42.5 split (30 / 0.425 ≈ 71 per label), and a
# 100-record random stream for agreement, human-human agreement and the alternative annotator test.
SIZING = {"discovery": {"target_gold": 10, "min_per_class": 3, "random": 30},
          "validation": {"target_gold": 142, "min_per_class": 71, "random": 100}}
MODE_ALIASES = {"directional": "discovery"}  # the old name for discovery
EXPECTED_EXCLUSION = 0.30

# Routing reasons. Only RANDOM records are a measurement sample.
RANDOM, LABEL, DISAGREE, NA_CHECK, PROBE = "random", "label_stratum", "provider_disagreement", "na_check", "scope_probe"

# Arize limits.
PAGE = 500  # spans per export call
SOURCE_MAX_DAYS = 7  # time range of one queue record source
SOURCES_PER_CALL = 2  # record sources per create/add-records call
CONFIG_NAME_MAX = 40  # annotation config name length

# Settings saved in plan.json so each intake run samples the way the first plan did.
CARRIED = ("root_filter", "eval_name", "compare_eval", "max_disagreement_share", "mode", "expected_exclusion",
           "labels", "not_applicable", "na_count", "pool", "slices", "signal", "signal_count", "instructions_version")
SETTLE_HOURS = 2  # leave time for evaluator tasks to score the newest units before an intake counts them


class ColumnMissing(Exception):
    """An eval column the filter references has no values in the requested period (or is not indexed yet)."""


def run_ax(ax, args, allow_empty=False, retries=5):
    for attempt in range(retries + 1):
        proc = subprocess.run([ax] + args, capture_output=True, text=True)
        out, msg = proc.stdout.strip(), proc.stderr + proc.stdout
        if proc.returncode == 0 and out:
            break
        if ("429" in msg or "Too Many Requests" in msg) and attempt < retries:
            time.sleep(2 ** attempt)
            continue
        if allow_empty and "No spans found" in msg:
            return []
        missing = re.search(r'column\s+"([^"]*eval\.[^"]+)"\s+does not exist', msg)
        if missing:
            raise ColumnMissing(missing.group(1))
        sys.exit(f"ax {' '.join(args)} failed:\n{msg.strip()[:800]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        sys.exit(f"ax {' '.join(args)} did not return JSON. Run `ax --version` and upgrade if it is old.\n"
                 f"{proc.stderr.strip()[:500]}")


def quote(v):
    return "'" + str(v).replace("'", "''") + "'"


def parse_time(v):
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def z(t):
    return t.isoformat().replace("+00:00", "Z")


def queue_units(ax, space, queue):
    """Session, trace, and span IDs already in an existing queue."""
    q = run_ax(ax, ["annotation-queues", "get", queue, "--space", space, "-o", "json"])
    seen, cursor = set(), None
    while True:
        args = ["annotation-queues", "list-records", q["id"], "--limit", "100", "-o", "json"]
        if cursor:
            args += ["--cursor", cursor]
        page = run_ax(ax, args)
        for r in page.get("records", []):
            d = r.get("data") or {}
            for k in ("attributes.session.id", "context.trace_id", "context.span_id"):
                if d.get(k):
                    seen.add(str(d[k]))
        pag = page.get("pagination") or {}
        cursor = pag.get("next_cursor")
        if not pag.get("has_more") or not cursor:
            return seen


def export_units(ax, project_id, space, filt, lo, hi, unit_key, min_span=timedelta(minutes=30)):
    """Every distinct unit matching filt in [lo, hi), with its earliest matching span, splitting any period
    that fills an export page. Returns (units, lower_bound). A period where the eval column has no values
    counts as empty."""
    def fetch(lo, hi):
        try:
            page = run_ax(ax, ["spans", "export", project_id, "--space", space, "--filter", filt,
                               "--start-time", lo.isoformat(), "--end-time", hi.isoformat(),
                               "-l", str(PAGE), "--stdout"], allow_empty=True)
        except ColumnMissing:
            return {}, False
        if len(page) < PAGE or hi - lo <= min_span:
            found = {}
            for s in page:
                u = unit_of(s, unit_key)
                if u is not None and (u not in found or s.get("start_time", "") < found[u].get("start_time", "")):
                    found[u] = s
            return found, len(page) >= PAGE
        mid = lo + (hi - lo) / 2
        (a, t1), (b, t2) = fetch(lo, mid), fetch(mid, hi)
        for u, s in b.items():
            if u not in a or s.get("start_time", "") < a[u].get("start_time", ""):
                a[u] = s
        return a, t1 or t2
    return fetch(lo, hi)


def count_units(ax, project_id, space, filt, lo, hi, unit_key):
    units, capped = export_units(ax, project_id, space, filt, lo, hi, unit_key)
    return len(units), capped


def unit_of(span, unit_key):
    if unit_key == "session_id":
        return (span.get("attributes") or {}).get("session.id")
    return (span.get("context") or {}).get(unit_key)


def spread_pick(items, n, rng):
    """Pick n items, round-robin across span names so no one entry point dominates."""
    groups = defaultdict(list)
    for it in items:
        groups[it["span_name"]].append(it)
    for g in groups.values():
        rng.shuffle(g)
    order = sorted(groups, key=lambda k: -len(groups[k]))
    picked = []
    while len(picked) < n and any(groups.values()):
        for k in order:
            if groups[k] and len(picked) < n:
                picked.append(groups[k].pop())
    return picked


def parse_signal(v):
    name, sep, filt = v.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not filt.strip():
        raise argparse.ArgumentTypeError("use NAME=FILTER, e.g. thumbs_down=\"attributes.feedback = 'down'\"")
    return [name, filt.strip()]


def split_sources(recs, project_id):
    """SPAN record sources of at most SOURCE_MAX_DAYS each, in batches of SOURCES_PER_CALL."""
    timed = sorted(((parse_time(c["start_time"]), c) for c in recs if parse_time(c["start_time"])), key=lambda tc: tc[0])
    groups = []
    for t, c in timed:
        if groups and t - groups[-1][0][0] <= timedelta(days=SOURCE_MAX_DAYS) - timedelta(minutes=10):
            groups[-1].append((t, c))
        else:
            groups.append([(t, c)])
    sources = [{"record_type": "SPAN", "project_id": project_id,
                "start_time": z(g[0][0] - timedelta(minutes=5)), "end_time": z(g[-1][0] + timedelta(minutes=5)),
                "span_ids": [c["span_id"] for _, c in g]} for g in groups]
    return sources, [sources[i:i + SOURCES_PER_CALL] for i in range(0, len(sources), SOURCES_PER_CALL)]


def write_sources(out_dir, prefix, sources, batches, adding):
    """Write PREFIX.json and its batch files; an intake adds to existing queues, so every batch is add_N."""
    with open(os.path.join(out_dir, f"{prefix}.json"), "w") as f:
        json.dump(sources, f, indent=1)
    files = []
    for i, b in enumerate(batches):
        files.append(os.path.join(out_dir, f"{prefix}.create.json" if i == 0 and not adding
                                  else f"{prefix}.add_{i + (1 if adding else 0)}.json"))
        with open(files[-1], "w") as f:
            json.dump(b, f, indent=1)
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", required=True)
    p.add_argument("--project", help="Project name or ID the evaluator's task scores")
    p.add_argument("--evaluator", help="Evaluator name or ID")
    p.add_argument("--out-dir", help="Where to write the plan (intake: default intake-N/ beside the plan)")
    p.add_argument("--root-filter", help="Filter selecting one span per unit, e.g. the root span of each turn")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--start-time", help="ISO 8601 window start; overrides --days (use with --end-time)")
    p.add_argument("--end-time", help="ISO 8601 window end (default now)")
    p.add_argument("--eval-name", help="Sample from this stored output instead of the evaluator's own, "
                                       "e.g. a backfill candidate's template name")
    p.add_argument("--pool", type=int, default=200, help="Max spans to export per stored label")
    p.add_argument("--slices", type=int, default=4,
                   help="Split the window into this many time slices and draw the pool evenly from each")
    p.add_argument("--max-disagreement-share", type=float, default=0.4,
                   help="Cap on the share of each label's picks taken from provider disagreements")
    p.add_argument("--mode", choices=sorted(SIZING) + sorted(MODE_ALIASES), default="discovery",
                   help="discovery: enough to start (error analysis, a first alignment pass); "
                        "validation: 30 gold per label in each of dev and test, and a 100-record random stream")
    p.add_argument("--random", type=int,
                   help="Records in the random measurement stream (default: 30 discovery, 100 validation; "
                        "intake: 0 unless --random-queue is set). 0 turns it off")
    p.add_argument("--target-gold", type=int, help="Override the mode's target gold records")
    p.add_argument("--min-per-class", type=int, help="Override the mode's minimum gold records per label")
    p.add_argument("--skip-population", action="store_true",
                   help="Don't count each stratum's production units (no production-weighted estimates later)")
    p.add_argument("--expected-exclusion", type=float, default=EXPECTED_EXCLUSION,
                   help="Expected share of records humans will mark not applicable or cannot judge")
    p.add_argument("--per-label", type=int, help="Override the computed per-label quota")
    p.add_argument("--labels", nargs="*", help="Only sample these stored labels (for topping up a queue)")
    p.add_argument("--not-applicable", nargs="*", default=["not_applicable"])
    p.add_argument("--na-count", type=int, default=2, help="Records to include whose stored label is not applicable")
    p.add_argument("--na-probe-eval", help="Another evaluator's template name, or PREFIX.TEMPLATE (e.g. eval.NAME) when "
                   "its granularity differs from this evaluator's. Adds --na-probe-count records this evaluator called "
                   "not applicable but that one graded decisively, to test the scope rule")
    p.add_argument("--na-probe-count", type=int, default=5)
    p.add_argument("--compare-eval", help="Another evaluator's template name (e.g. a provider copy); "
                                          "records where it disagrees are picked first")
    p.add_argument("--signal", type=parse_signal, action="append", default=[], metavar="NAME=FILTER",
                   help="A judge-independent targeting signal, e.g. user thumbs-down or a high-severity topic, as a "
                        "span filter. Adds --signal-count records matching it. Repeatable")
    p.add_argument("--signal-count", type=int, default=5)
    p.add_argument("--instructions-version", help="Version line of the queue instructions, stored on each record "
                                                  "so labels made under older definitions can be found")
    p.add_argument("--exclude-queue", nargs="*", default=[], help="Skip units already in these queues")
    p.add_argument("--intake", metavar="PLAN_JSON",
                   help="Sample units that arrived since this plan's last run, for the queue in --queue")
    p.add_argument("--queue", help="intake: the queue the plan's targeted records went into")
    p.add_argument("--random-queue", help="intake: the calibration queue for the random stream")
    p.add_argument("--settle-hours", type=float, default=SETTLE_HOURS,
                   help="intake: leave out the newest hours, which evaluators may not have scored yet")
    p.add_argument("--execute", action="store_true",
                   help="intake: add the records to the queues and record the run in the plan")
    p.add_argument("--seed", type=int, help="Random seed (default 0; intake: the run number)")
    p.add_argument("--ax", default="ax")
    a = p.parse_args()
    base = None
    if a.intake:
        if not a.queue:
            p.error("--intake needs --queue")
        if a.random and not a.random_queue:
            p.error("--random in an intake needs --random-queue, the calibration queue")
        if a.random_queue and not a.random:
            p.error("--random-queue needs --random N, the random records per run")
        with open(a.intake) as f:
            base = json.load(f)
        if not base.get("window"):
            sys.exit(f"{a.intake} has no window or settings; re-plan with a current plan_queue.py before intake.")
        for k, v in (base.get("settings") or {}).items():
            if getattr(a, k, None) == p.get_default(k):
                setattr(a, k, v)
        a.evaluator, a.project = a.evaluator or base["evaluator_id"], a.project or base["project_id"]
        a.na_probe_eval = None
        a.exclude_queue = list(dict.fromkeys(a.exclude_queue + [q for q in (a.queue, a.random_queue) if q]))
        a.per_label = a.per_label or base.get("per_label_quota")
        a.random = a.random or 0
        run_id = f"intake-{len(base.get('intakes') or []) + 1}"
        a.out_dir = a.out_dir or os.path.join(os.path.dirname(os.path.abspath(a.intake)), run_id)
        if a.seed is None:
            a.seed = len(base.get("intakes") or []) + 1
    elif a.execute or a.queue or a.random_queue:
        p.error("--execute, --queue and --random-queue go with --intake")
    elif not (a.project and a.evaluator and a.out_dir):
        p.error("--project, --evaluator and --out-dir are required")
    a.mode = MODE_ALIASES.get(a.mode, a.mode)
    if a.random is None:
        a.random = SIZING[a.mode]["random"]
    a.target_gold = a.target_gold or SIZING[a.mode]["target_gold"]
    a.min_per_class = a.min_per_class or SIZING[a.mode]["min_per_class"]
    rng = random.Random(a.seed or 0)
    os.makedirs(a.out_dir, exist_ok=True)

    ev = run_ax(a.ax, ["evaluators", "get", a.evaluator, "--space", a.space, "-o", "json"])
    tc = (ev.get("version") or {}).get("template_config") or {}
    tname = a.eval_name or tc.get("name")
    if not tname:
        sys.exit("Evaluator has no template_config.name; this script supports template evaluators only.")
    if base and (ev.get("version") or {}).get("id") != base.get("version_id"):
        sys.exit(f"The evaluator's version is now {(ev.get('version') or {}).get('id')}, not the plan's "
                 f"{base.get('version_id')}. Labels from a new version measure a different evaluator: plan a new "
                 "queue for it instead of adding to this one.")
    gran = (tc.get("data_granularity") or "SPAN").upper()
    prefix = GRANULARITY_PREFIX.get(gran, "eval")
    column = f"{prefix}.{tname}.label"
    choices = list((tc.get("classification_choices") or {}).keys())
    na = set(a.not_applicable)
    wanted = a.labels or choices
    unit_key = {"SESSION": "session_id", "TRACE": "trace_id"}.get(gran, "span_id")

    project = run_ax(a.ax, ["projects", "get", a.project, "--space", a.space, "-o", "json"])
    excluded_units = set()
    for q in a.exclude_queue:
        excluded_units |= queue_units(a.ax, a.space, q)

    k = len([c for c in wanted if c not in na]) or 1
    per = a.per_label or math.ceil(max(a.min_per_class, a.target_gold / k) / (1 - a.expected_exclusion))

    end = parse_time(a.end_time) if a.end_time else datetime.now(timezone.utc)
    start = parse_time(a.start_time) if a.start_time else end - timedelta(days=a.days)
    if base:
        start = parse_time(base.get("intake_cursor") or base["window"]["end"])
        if not a.end_time:
            end -= timedelta(hours=a.settle_hours)
        if end <= start:
            print(f"Nothing to take in: the plan already covers up to {start.isoformat()}.")
            return
    step = (end - start) / a.slices
    empty_slices = set()

    def with_root(filt):
        return f"({a.root_filter}) AND {filt}" if a.root_filter else filt

    def export_slices(filt):
        """Draw evenly across the window; a single export returns only the newest spans. A slice where an eval
        column has no values counts as empty."""
        spans, missing = [], 0
        for i in range(a.slices):
            hi, lo = end - step * i, end - step * (i + 1)
            try:
                spans += run_ax(a.ax, ["spans", "export", project["id"], "--space", a.space, "--filter", filt,
                                       "--start-time", lo.isoformat(), "--end-time", hi.isoformat(),
                                       "-l", str(min(PAGE, math.ceil(a.pool / a.slices))), "--stdout"],
                                allow_empty=True)
            except ColumnMissing:
                missing += 1
                empty_slices.add(f"{lo.date().isoformat()} → {hi.date().isoformat()}")
        if missing == a.slices:
            sys.exit(f"No part of the window has values for the eval column in `{filt}`. Check the template name "
                     "(`--eval-name`, `--na-probe-eval`), the window, and that the evaluator has run; a new column "
                     "can take 20+ minutes to become queryable.")
        return spans

    probe_name = (a.na_probe_eval or "").split(".")[-1] or None

    def row_of(s, label=None):
        attrs, ctx = s.get("attributes") or {}, s.get("context") or {}
        evals = {e.get("name"): e for e in s.get("evaluations") or []}
        return {
            "session_id": attrs.get("session.id"),
            "trace_id": ctx.get("trace_id"),
            "span_id": ctx.get("span_id"),
            "span_name": s.get("name"),
            "start_time": s.get("start_time"),
            "stored_label": (evals.get(tname) or {}).get("label", label),
            "stored_explanation": (evals.get(tname) or {}).get("explanation"),
            "compare_label": (evals.get(a.compare_eval) or {}).get("label") if a.compare_eval else None,
            "probe_label": (evals.get(probe_name) or {}).get("label") if probe_name else None,
            "instructions_version": a.instructions_version,
        }

    def candidates(filt, label):
        """One candidate per unit not already used, keeping the unit's earliest matching span."""
        cands, dup = {}, 0
        for s in export_slices(with_root(filt)):
            row = row_of(s, label)
            unit = row[unit_key]
            if not unit or str(unit) in used:
                dup += 1
            elif unit not in cands or row["start_time"] < cands[unit]["start_time"]:
                cands[unit] = row
        return list(cands.values()), dup

    def take(chosen, tag, label, quota, pool, dup, **extra):
        for c in chosen:
            c["sampled_as"] = tag(c)
            c.setdefault("stratum", f"probe:{label}")
            c.setdefault("routing_reason", PROBE)
            c["stream"] = "random" if c["routing_reason"] == RANDOM else "targeted"
            used.add(str(c[unit_key]))
        picks.extend(chosen)
        summary.append({"label": label, "pool_units": pool, "quota": quota, "picked": len(chosen),
                        "provider_disagreements": sum(1 for c in chosen if c.get("disagree")),
                        "span_names": len({c["span_name"] for c in chosen}), "skipped_dupes_or_excluded": dup,
                        "shortfall": max(0, quota - len(chosen)), **extra})

    picks, summary, strata, used = [], [], [], set(excluded_units)

    # Random stream first: a uniform draw from every scored unit not already queued, so its selection
    # probability is known exactly and nothing about the evaluator's labels decides who is in it.
    rand = None
    if a.random:
        units, lower = export_units(a.ax, project["id"], a.space, with_root(f"{column} IS NOT NULL"),
                                    start, end, unit_key)
        frame = sorted(u for u in units if str(u) not in used)
        chosen = [row_of(units[u]) for u in rng.sample(frame, min(a.random, len(frame)))]
        for c in chosen:
            c["stratum"], c["routing_reason"] = "random", RANDOM
        take(chosen, lambda c: "random", "random", a.random, len(frame), len(units) - len(frame))
        rand = summary.pop()
        strata.append({"stratum": "random", "stream": "random", "label": None, "subgroup": "all",
                       "population": len(units), "frame": len(frame), "population_lower_bound": lower,
                       "population_estimated": False, "picked": len(chosen),
                       "selection_rate": len(chosen) / len(frame) if frame else None})

    # Judge-independent signals (user feedback, severity): targeted, never weighted.
    for name, filt in a.signal:
        items, dup = candidates(f"({filt}) AND {column} IS NOT NULL", None)
        chosen = spread_pick(items, a.signal_count, rng)
        for c in chosen:
            c["stratum"] = c["routing_reason"] = f"signal:{name}"
        take(chosen, lambda c, n=name: f"signal: {n}", f"signal: {name}", a.signal_count, len(items), dup)

    decisive_picked = 0
    cmp_col = f"{prefix}.{a.compare_eval}.label" if a.compare_eval else None
    for label in wanted:
        items, dup = candidates(f"{column} = {quote(label)}", label)
        quota = a.na_count if label in na else per
        disagree, rest = [], []
        for i in items:
            i["disagree"] = bool(i["compare_label"] and i["compare_label"] != i["stored_label"])
            (disagree if i["disagree"] else rest).append(i)
        chosen = spread_pick(disagree, int(quota * a.max_disagreement_share), rng)
        chosen += spread_pick(rest, quota - len(chosen), rng)
        if len(chosen) < quota:
            # Not enough other candidates; fall back to the remaining disagreements.
            ids = {c["span_id"] for c in chosen}
            chosen += spread_pick([d for d in disagree if d["span_id"] not in ids], quota - len(chosen), rng)
        # Strata: the stored label, split by provider agreement when a comparison copy is given. Disagreements
        # are oversampled, so they are their own stratum and get their own weight.
        for c in chosen:
            c["stratum"] = label if not a.compare_eval else f"{label}|{'disagree' if c['disagree'] else 'agree'}"
            c["routing_reason"] = DISAGREE if c["disagree"] else NA_CHECK if label in na else LABEL
        take(chosen, lambda c, l=label: l, label, quota, len(items), dup)
        population, lower = (None, False) if a.skip_population else count_units(
            a.ax, project["id"], a.space, with_root(f"{column} = {quote(label)}"), start, end, unit_key)
        if not a.compare_eval:
            pops = {"all": population}
        elif population is None:
            pops = {"disagree": None, "agree": None}
        else:
            # Count disagreements in full: an estimated population is not a known selection probability.
            dis, dis_lower = count_units(
                a.ax, project["id"], a.space,
                with_root(f"{column} = {quote(label)} AND {cmp_col} IS NOT NULL AND {cmp_col} != {quote(label)}"),
                start, end, unit_key)
            pops, lower = {"disagree": dis, "agree": population - dis}, lower or dis_lower
        for sub, pop in pops.items():
            name = label if sub == "all" else f"{label}|{sub}"
            picked = sum(1 for c in chosen if c["stratum"] == name)
            strata.append({"stratum": name, "stream": "targeted", "label": label, "subgroup": sub,
                           "population": pop, "population_lower_bound": lower, "population_estimated": False,
                           "picked": picked, "selection_rate": picked / pop if pop else None})
        if label not in na:
            decisive_picked += len(chosen)

    # Scope probes: units this evaluator called not applicable that another evaluator graded decisively.
    probe = None
    if a.na_probe_eval and a.na_probe_count:
        na_label = next((l for l in choices if l in na), "not_applicable")
        probe_col = (a.na_probe_eval if "." in a.na_probe_eval else f"{prefix}.{a.na_probe_eval}") + ".label"
        items, dup = candidates(f"{column} = {quote(na_label)} AND {probe_col} IS NOT NULL", na_label)
        by_probe = defaultdict(list)
        for i in items:
            if i["probe_label"] and i["probe_label"] not in na:
                by_probe[i["probe_label"]].append(i)
        # Spread across the other evaluator's labels first (rarest first), then entry points.
        n, chosen = a.na_probe_count, []
        share = math.ceil(n / max(1, len(by_probe)))
        for lbl in sorted(by_probe, key=lambda k: len(by_probe[k])):
            chosen += spread_pick(by_probe[lbl], min(share, n - len(chosen)), rng)
        if len(chosen) < n:
            ids = {c["span_id"] for c in chosen}
            chosen += spread_pick([i for g in by_probe.values() for i in g if i["span_id"] not in ids], n - len(chosen), rng)
        pool = sum(len(g) for g in by_probe.values())
        take(chosen, lambda c: f"{na_label} (probe: {a.na_probe_eval}={c['probe_label']})",
             f"{na_label} probe vs {a.na_probe_eval}", n, pool, dup,
             probe_labels=dict(Counter(c["probe_label"] for c in chosen)))
        probe = summary[-1]

    # An intake run's units are a new period, so its strata are counted and weighted on their own.
    if base:
        for x in picks + strata:
            x["stratum"] += f"@{run_id}"
        for st in strata:
            st["intake"] = run_id

    targeted = [c for c in picks if c["stream"] == "targeted"]
    randoms = [c for c in picks if c["stream"] == "random"]
    sources, batches = split_sources(targeted, project["id"])
    r_sources, r_batches = split_sources(randoms, project["id"])
    config_values = list(dict.fromkeys(choices + [l for l in a.not_applicable if l not in choices] + UNSCORABLE))
    stem = tc.get("name") or tname
    config_name = f"{stem[:CONFIG_NAME_MAX - 5]}-gold"
    critique_name = f"{stem[:CONFIG_NAME_MAX - 9]}-critique"

    run_plan = {"evaluator": ev.get("name"), "evaluator_id": ev.get("id"), "version_id": (ev.get("version") or {}).get("id"),
                "column": column, "granularity": gran, "project_id": project["id"], "per_label_quota": per,
                "config_name": config_name, "critique_config_name": critique_name, "mode": a.mode,
                "window": {"start": z(start), "end": z(end)}, "settings": {k: getattr(a, k) for k in CARRIED},
                "summary": summary, "random_stream": rand, "strata": strata, "records": picks}
    with open(os.path.join(a.out_dir, "plan.json"), "w") as f:
        json.dump(run_plan, f, indent=1)
    for old in os.listdir(a.out_dir):
        if old.startswith(("record_sources.", "random_sources.")):
            os.remove(os.path.join(a.out_dir, old))
    files = write_sources(a.out_dir, "record_sources", sources, batches, bool(base))
    r_files = write_sources(a.out_dir, "random_sources", r_sources, r_batches, bool(base)) if randoms else []
    with open(os.path.join(a.out_dir, "config_values.json"), "w") as f:
        json.dump(config_values, f, indent=1)

    expected_gold = decisive_picked * (1 - a.expected_exclusion)
    window = f"{a.start_time} → {a.end_time or 'now'}" if a.start_time else f"last {a.days} days"
    excluded = f"{len(excluded_units)} IDs from existing queues excluded" if excluded_units else "no existing queues excluded"
    title = (f"# Intake {run_id} for queue `{a.queue}` (`{ev.get('name')}`)\n" if base
             else f"# Queue plan for `{ev.get('name')}`\n")
    out = [
        title,
        "Records were added to the queue; the result is at the end.\n" if a.execute
        else "Nothing has been created. Review, then approve or adjust.\n",
        f"- Evaluator version `{(ev.get('version') or {}).get('id')}`, granularity `{gran}`, stored column `{column}`",
        f"- Project `{project.get('name')}`, {window}" + (f", root filter `{a.root_filter}`" if a.root_filter else ""),
        f"- One record per {unit_key.replace('_id', '')}; {excluded}",
        f"- Sizing mode `{a.mode}`: per-label quota {per} = max({a.min_per_class}, {a.target_gold}/{k}) / "
        f"(1 − {a.expected_exclusion:.0%} expected exclusions), about {per * (1 - a.expected_exclusion):.1f} gold "
        "records per label" + (" (enough to start aligning, not to validate; use `--mode validation` for that)"
                                if a.mode == "discovery" else "") + "\n",
    ]
    if rand:
        rate = f"{rand['picked'] / rand['pool_units']:.1%}" if rand["pool_units"] else "—"
        out.append(f"**Random stream (measurement): {rand['picked']} records**, drawn uniformly from {rand['pool_units']} "
                   f"scored units not already queued ({rate}), with no filter on the evaluator's labels. Agreement, the "
                   "human ceiling and the VALIDATED verdict come from these. They go in a separate calibration queue "
                   "(`random_sources.*.json`)"
                   + (". Assign it to 3 or more annotators (`ALL`) for human-human agreement." if a.mode == "validation"
                      else ". In discovery mode, an expert reads and open-codes them before the rubric is settled.")
                   + (f" Short {rand['shortfall']}: the window has too few scored units." if rand["shortfall"] else "")
                   + "\n")
    else:
        out.append("**No random stream** (`--random 0`). Nothing in this plan can be used to measure agreement; "
                   "the records only find failures.\n")
    out += ["**Targeted stream (failure finding):**\n",
            "| Picked as | Candidates | Picked | Provider disagreements | Distinct entry points | Shortfall |",
            "|---|---:|---:|---:|---:|---:|"]
    for s in summary:
        out.append(f"| `{s['label']}` | {s['pool_units']} | {s['picked']} | {s['provider_disagreements']} | "
                   f"{s['span_names']} | {s['shortfall'] or ''} |")
    if strata and not a.skip_population:
        out += ["", "Strata (`report --plan plan.json`):\n",
                "| Stratum | Stream | Production units | Picked | Selection rate |", "|---|---|---:|---:|---:|"]
        for st in strata:
            pop = "—" if st["population"] is None else f"{st['population']}{'+' if st['population_lower_bound'] else ''}"
            r = "—" if not st["selection_rate"] else f"{st['selection_rate']:.1%}"
            out.append(f"| `{st['stratum']}` | {st['stream']} | {pop} | {st['picked']} | {r} |")
    out += [
        "",
        f"**Total records: {len(picks)}** ({len(randoms)} random, {len(targeted)} targeted). If humans exclude "
        f"{a.expected_exclusion:.0%} of the decisive targeted picks, about {expected_gold:.0f} gold records remain "
        f"(target {a.target_gold}).\n",
        f"Proposed annotation configs: `{config_name}` with values {config_values}, and `{critique_name}` "
        "(free text) for the critique the instructions require with every label.\n",
        "Caveats:",
        "- Targeted records were chosen using the evaluator's own labels and other signals, so they over-represent "
        "rare labels and hard cases. Use them to find failures and for dev and few-shot examples; take agreement from "
        "the random stream. Agreement within a stored label is that label's precision, not recall.",
        "- Labelers must not see evaluator output. ax can't hide it: after creating each queue, set its Annotator "
        "Columns in the Arize UI to leave out every eval column, then open a record as an annotator to check.",
        "- Ask annotators to stop after about 100 records per sitting; missed defects rise with fatigue.",
    ]
    if a.signal:
        out.append("- Signals " + ", ".join(f"`{n}`" for n, _ in a.signal) + " pick records by span filters that don't "
                   "depend on the evaluator. They are targeted and never weighted.")
    if probe:
        out.append(f"- {probe['picked']} scope probes: stored `not applicable` here, graded {probe['probe_labels']} by "
                   f"`{a.na_probe_eval}`. If humans label them decisively, the scope rule is too strict. They are left "
                   "out of the expected gold count.")
    if not a.instructions_version:
        out.append("- No `--instructions-version` given. Pass the instructions' version line so labels made under "
                   "older definitions can be found after an edit.")
    if empty_slices:
        out.append(f"- No values for an eval column in: {', '.join(sorted(empty_slices))}. Those periods "
                   "contributed no candidates (nothing was scored there, or it is not indexed yet).")
    if base:
        out.append(f"- Intake: only units that started in this window and are not in the queues; the newest "
                   f"{a.settle_hours:g} hours are left for the next run. Its strata are tagged `@{run_id}`.")
    else:
        out.append(f"- Record sources: {len(sources)} targeted and {len(r_sources)} random, each at most "
                   f"{SOURCE_MAX_DAYS} days. Create each queue with its `*.create.json`, then run `add-records` "
                   "with each of its `*.add_*.json`.")
    short = [s for s in summary if s["shortfall"]]
    if short:
        out.append("- Not enough candidates for: " + ", ".join(f"`{s['label']}` (short {s['shortfall']})" for s in short)
                   + (". Later intake runs add more as new units arrive." if base
                      else ". Widen `--days`, or accept fewer and note it."))
    if base and a.execute:
        out += ["", record_intake(a, base, run_id, run_plan,
                                  [(a.queue, batches, files), (a.random_queue, r_batches, r_files)])]
    print("\n".join(out))
    with open(os.path.join(a.out_dir, "plan.md"), "w") as f:
        f.write("\n".join(out) + "\n")


def record_intake(a, base, run_id, run_plan, targets):
    """Add an intake run's records to its queues, then append what was added to the plan.

    A failed batch stops the run; the records already added are still recorded (with their strata's
    picked counts and rates reduced to match), and the cursor still moves, so no period is counted twice."""
    added, failed = set(), None
    for queue, batches, files in targets:
        for b, path in zip(batches, files):
            if failed:
                break
            proc = subprocess.run([a.ax, "annotation-queues", "add-records", queue, "--space", a.space,
                                   "--record-sources", path, "-o", "json"], capture_output=True, text=True)
            if proc.returncode != 0:
                failed = (path, (proc.stderr + proc.stdout).strip()[:500])
                break
            added |= {sid for src in b for sid in src["span_ids"]}
    records = [r for r in run_plan["records"] if r["span_id"] in added]
    for st in run_plan["strata"]:
        st["picked"] = sum(1 for r in records if r["stratum"] == st["stratum"])
        denom = st.get("frame", st["population"])
        st["selection_rate"] = st["picked"] / denom if denom else None
    base["records"] = (base.get("records") or []) + records
    base["strata"] = (base.get("strata") or []) + run_plan["strata"]
    base.setdefault("intakes", []).append({
        "id": run_id, "queue": a.queue, "random_queue": a.random_queue, "window": run_plan["window"],
        "picked": len(records), "planned": len(run_plan["records"]), "summary": run_plan["summary"],
        "random_stream": run_plan["random_stream"],
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "failed": failed and failed[1]})
    base["intake_cursor"] = run_plan["window"]["end"]
    tmp = a.intake + ".tmp"
    with open(tmp, "w") as f:
        json.dump(base, f, indent=1)
    os.replace(tmp, a.intake)
    if failed:
        return (f"**Added {len(records)} of {len(run_plan['records'])} records, then `add-records` failed on "
                f"`{os.path.basename(failed[0])}`:** {failed[1]}\nThe added records and the window are recorded in "
                "the plan; the rest of this window is skipped.")
    queues = " and ".join(f"`{q}`" for q in (a.queue, a.random_queue) if q)
    return f"**Added {len(records)} records to {queues} and recorded {run_id} in `{a.intake}`.**"


if __name__ == "__main__":
    main()
