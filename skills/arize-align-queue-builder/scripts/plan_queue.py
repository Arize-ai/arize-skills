#!/usr/bin/env python3
"""Plan an annotation queue for aligning one Arize evaluator. Read-only.

Pulls candidate records from a project, grouped by the label the evaluator
already stored on them, and picks a balanced, deduplicated set sized so the
finished queue should clear the arize-align-evaluator gates. Writes:

  plan.md              Summary to show the user before anything is created
  plan.json            Every picked record with its stored labels
  record_sources.json  Every picked record as SPAN sources of at most 7 days each
  record_sources.create.json, record_sources.add_N.json
                       The same sources in batches of 2: pass the first to
                       `ax annotation-queues create`, the rest to `add-records`
  config_values.json   Proposed categorical label values for the annotation config

Standard library only (Python 3.9+). Creates nothing in Arize.

Example:
  plan_queue.py --space SPACE --project PROJECT --evaluator EVALUATOR \\
    --root-filter "attributes.is_copilot_root_span = 'true'" --out-dir plan/
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

# Keep in step with the arize-align-evaluator gates.
TARGET_GOLD = 10
MIN_PER_CLASS = 3
EXPECTED_EXCLUSION = 0.30


# Arize limits.
PAGE = 500  # spans per export call
SOURCE_MAX_DAYS = 7  # time range of one queue record source
SOURCES_PER_CALL = 2  # record sources per create/add-records call
CONFIG_NAME_MAX = 40  # annotation config name length


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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", required=True)
    p.add_argument("--project", required=True, help="Project name or ID the evaluator's task scores")
    p.add_argument("--evaluator", required=True, help="Evaluator name or ID")
    p.add_argument("--out-dir", required=True)
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
    p.add_argument("--target-gold", type=int, default=TARGET_GOLD)
    p.add_argument("--min-per-class", type=int, default=MIN_PER_CLASS)
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
    p.add_argument("--exclude-queue", nargs="*", default=[], help="Skip units already in these queues")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--ax", default="ax")
    a = p.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out_dir, exist_ok=True)

    ev = run_ax(a.ax, ["evaluators", "get", a.evaluator, "--space", a.space, "-o", "json"])
    tc = (ev.get("version") or {}).get("template_config") or {}
    tname = a.eval_name or tc.get("name")
    if not tname:
        sys.exit("Evaluator has no template_config.name; this script supports template evaluators only.")
    gran = (tc.get("data_granularity") or "SPAN").upper()
    column = f"{GRANULARITY_PREFIX.get(gran, 'eval')}.{tname}.label"
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

    def candidates(filt, label):
        """One candidate per unit not already used, keeping the unit's earliest matching span."""
        cands, dup = {}, 0
        for s in export_slices(with_root(filt)):
            attrs, ctx = s.get("attributes") or {}, s.get("context") or {}
            evals = {e.get("name"): e for e in s.get("evaluations") or []}
            row = {
                "session_id": attrs.get("session.id"),
                "trace_id": ctx.get("trace_id"),
                "span_id": ctx.get("span_id"),
                "span_name": s.get("name"),
                "start_time": s.get("start_time"),
                "stored_label": (evals.get(tname) or {}).get("label", label),
                "stored_explanation": (evals.get(tname) or {}).get("explanation"),
                "compare_label": (evals.get(a.compare_eval) or {}).get("label") if a.compare_eval else None,
                "probe_label": (evals.get(probe_name) or {}).get("label") if probe_name else None,
            }
            unit = row[unit_key]
            if not unit or str(unit) in used:
                dup += 1
            elif unit not in cands or row["start_time"] < cands[unit]["start_time"]:
                cands[unit] = row
        return list(cands.values()), dup

    def take(chosen, tag, label, quota, pool, dup, **extra):
        for c in chosen:
            c["sampled_as"] = tag(c)
            used.add(str(c[unit_key]))
        picks.extend(chosen)
        summary.append({"label": label, "pool_units": pool, "quota": quota, "picked": len(chosen),
                        "provider_disagreements": sum(1 for c in chosen if c.get("disagree")),
                        "span_names": len({c["span_name"] for c in chosen}), "skipped_dupes_or_excluded": dup,
                        "shortfall": max(0, quota - len(chosen)), **extra})

    picks, summary, used = [], [], set(excluded_units)
    decisive_picked = 0
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
        take(chosen, lambda c, l=label: l, label, quota, len(items), dup)
        if label not in na:
            decisive_picked += len(chosen)

    # Scope probes: units this evaluator called not applicable that another evaluator graded decisively.
    probe = None
    if a.na_probe_eval and a.na_probe_count:
        na_label = next((l for l in choices if l in na), "not_applicable")
        probe_col = (a.na_probe_eval if "." in a.na_probe_eval
                     else f"{GRANULARITY_PREFIX.get(gran, 'eval')}.{a.na_probe_eval}") + ".label"
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

    # Record sources, split to Arize's limits: at most SOURCE_MAX_DAYS each, SOURCES_PER_CALL per call.
    def z(t):
        return t.isoformat().replace("+00:00", "Z")

    timed = sorted((parse_time(c["start_time"]), c) for c in picks if parse_time(c["start_time"]))
    groups = []
    for t, c in timed:
        if groups and t - groups[-1][0][0] <= timedelta(days=SOURCE_MAX_DAYS) - timedelta(minutes=10):
            groups[-1].append((t, c))
        else:
            groups.append([(t, c)])
    sources = [{"record_type": "SPAN", "project_id": project["id"],
                "start_time": z(g[0][0] - timedelta(minutes=5)), "end_time": z(g[-1][0] + timedelta(minutes=5)),
                "span_ids": [c["span_id"] for _, c in g]} for g in groups]
    batches = [sources[i:i + SOURCES_PER_CALL] for i in range(0, len(sources), SOURCES_PER_CALL)]
    config_values = list(dict.fromkeys(choices + [l for l in a.not_applicable if l not in choices] + UNSCORABLE))
    config_name = f"{(tc.get('name') or tname)[:CONFIG_NAME_MAX - 5]}-gold"

    with open(os.path.join(a.out_dir, "plan.json"), "w") as f:
        json.dump({"evaluator": ev.get("name"), "evaluator_id": ev.get("id"), "version_id": (ev.get("version") or {}).get("id"),
                   "column": column, "granularity": gran, "project_id": project["id"], "per_label_quota": per,
                   "config_name": config_name, "summary": summary, "records": picks}, f, indent=1)
    for old in os.listdir(a.out_dir):
        if old.startswith("record_sources."):
            os.remove(os.path.join(a.out_dir, old))
    with open(os.path.join(a.out_dir, "record_sources.json"), "w") as f:
        json.dump(sources, f, indent=1)
    for i, b in enumerate(batches):
        with open(os.path.join(a.out_dir, "record_sources.create.json" if i == 0 else f"record_sources.add_{i}.json"), "w") as f:
            json.dump(b, f, indent=1)
    with open(os.path.join(a.out_dir, "config_values.json"), "w") as f:
        json.dump(config_values, f, indent=1)

    expected_gold = decisive_picked * (1 - a.expected_exclusion)
    window = f"{a.start_time} → {a.end_time or 'now'}" if a.start_time else f"last {a.days} days"
    excluded = f"{len(excluded_units)} IDs from existing queues excluded" if excluded_units else "no existing queues excluded"
    out = [
        f"# Queue plan for `{ev.get('name')}`\n",
        "Nothing has been created. Review, then approve or adjust.\n",
        f"- Evaluator version `{(ev.get('version') or {}).get('id')}`, granularity `{gran}`, stored column `{column}`",
        f"- Project `{project.get('name')}`, {window}" + (f", root filter `{a.root_filter}`" if a.root_filter else ""),
        f"- One record per {unit_key.replace('_id', '')}; {excluded}",
        f"- Per-label quota {per}: max({a.min_per_class}, {a.target_gold}/{k}) / (1 − {a.expected_exclusion:.0%} expected exclusions)\n",
        "| Stored label | Candidates | Picked | Provider disagreements | Distinct entry points | Shortfall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        out.append(f"| `{s['label']}` | {s['pool_units']} | {s['picked']} | {s['provider_disagreements']} | "
                   f"{s['span_names']} | {s['shortfall'] or ''} |")
    out += [
        "",
        f"**Total records: {len(picks)}.** If humans exclude {a.expected_exclusion:.0%} of the decisive picks, "
        f"about {expected_gold:.0f} gold records remain (target {a.target_gold}).\n",
        f"Proposed annotation config: `{config_name}` with values {config_values}\n",
        "Caveats:",
        "- Records were stratified by the evaluator's own stored label, so the sample over-represents rare labels "
        "relative to production. Report agreement per label, not as one production-wide rate.",
        "- Stored labels choose which records are included; labelers must not see them (say so in the queue instructions).",
    ]
    if probe:
        out.append(f"- {probe['picked']} scope probes: stored `not applicable` here, graded {probe['probe_labels']} by "
                   f"`{a.na_probe_eval}`. If humans label them decisively, the scope rule is too strict. They are left "
                   "out of the expected gold count.")
    if empty_slices:
        out.append(f"- No values for an eval column in: {', '.join(sorted(empty_slices))}. Those periods "
                   "contributed no candidates (nothing was scored there, or it is not indexed yet).")
    out.append(f"- Record sources: {len(sources)} of at most {SOURCE_MAX_DAYS} days. Create the queue with "
               "`--record-sources record_sources.create.json`"
               + (", then run `add-records` with each `record_sources.add_*.json`." if len(batches) > 1 else "."))
    short = [s for s in summary if s["shortfall"]]
    if short:
        out.append("- Not enough candidates for: " + ", ".join(f"`{s['label']}` (short {s['shortfall']})" for s in short)
                   + ". Widen `--days`, or accept fewer and note it.")
    print("\n".join(out))
    with open(os.path.join(a.out_dir, "plan.md"), "w") as f:
        f.write("\n".join(out) + "\n")

if __name__ == "__main__":
    main()
