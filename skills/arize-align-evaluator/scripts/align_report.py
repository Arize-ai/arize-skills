#!/usr/bin/env python3
"""Pre-alignment report for an Arize evaluator against human ground truth.

Two subcommands, standard library only (Python 3.9+):

  fetch   Read-only. Calls `ax` to save a queue, all of its records (every
          page), and an evaluator to a directory. With --count-turns, also
          counts each session's turns so `report` can flag stale stored outputs.
  report  Joins the saved files and prints a Markdown pre-alignment report:
          queue/evaluator fit, label coverage, annotator agreement, quality
          gates, and human-vs-evaluator agreement on the gold subset.
          Writes nothing to Arize.

  compare Read-only. Compares two `report --json-out` files from the same gold
          set (before and after a change): agreement with intervals, records
          that flipped each way, and the shift in the evaluator's label mix.

Examples:
  align_report.py fetch --space SPACE --queue QUEUE --evaluator EVALUATOR --out-dir align/
  align_report.py report --dir align/ --json-out align/report.json > align/report.md
  align_report.py compare align/baseline.json align/candidate_v2.json
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations

GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}
DEFAULT_NOT_APPLICABLE = ["not_applicable"]
DEFAULT_UNSCORABLE = ["cannot_judge", "unclear"]

# Gate defaults; see references/research.md for where each comes from. Clearing every gate makes the
# queue DIRECTIONAL: enough to start aligning, not to claim alignment. VALIDATED also needs the class
# sizes below, because at 10 gold records a 90% agreement has a 95% interval of about 60-98%.
# A single annotator is allowed; agreement is gated only when records overlap.
MIN_GOLD_USABLE = 10
MIN_GOLD_EXPLORATORY = 5
MIN_PER_CLASS = 3
MIN_GOLD_VALIDATED = 50
MIN_PER_CLASS_VALIDATED = 30
MAX_EXCLUDED_RATE = 0.30
MIN_JOIN_RATE = 0.90
MIN_KAPPA = 0.60
# When one label holds this share of an annotator pair's votes, κ is low even at high raw agreement
# (the kappa paradox), so the gate also accepts Gwet's AC1.
SKEW_SHARE = 0.80
MIN_SHARED_FOR_KAPPA = 20
SPLIT = {"train": 0.15, "dev": 0.425}  # the rest is test, scored once at the end


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def run_ax(ax, args, json_flag=True, retries=5):
    for attempt in range(retries + 1):
        proc = subprocess.run([ax] + args + (["-o", "json"] if json_flag else []), capture_output=True, text=True)
        if proc.returncode == 0:
            break
        msg = proc.stderr + proc.stdout
        if ("429" in msg or "Too Many Requests" in msg) and attempt < retries:
            time.sleep(2 ** attempt)
            continue
        if "No spans found" in msg:
            return []
        sys.exit(f"ax {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    if not json_flag and not proc.stdout.strip():
        return []  # spans export prints nothing when no spans match
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(
            f"ax {' '.join(args)} did not return JSON. This is usually an outdated CLI "
            f"that cannot parse the API response; run `ax --version` and upgrade.\n"
            f"{proc.stderr.strip()[:500]}"
        )


def cmd_fetch(a):
    os.makedirs(a.out_dir, exist_ok=True)
    queue = run_ax(a.ax, ["annotation-queues", "get", a.queue, "--space", a.space])
    records, cursor = [], None
    while True:
        args = ["annotation-queues", "list-records", queue["id"], "--limit", "100"]
        if cursor:
            args += ["--cursor", cursor]
        page = run_ax(a.ax, args)
        records.extend(page.get("records", []))
        pag = page.get("pagination") or {}
        cursor = pag.get("next_cursor")
        if not pag.get("has_more") or not cursor:
            break
    evaluator = run_ax(a.ax, ["evaluators", "get", a.evaluator, "--space", a.space])
    for name, obj in (("queue", queue), ("records", records), ("evaluator", evaluator)):
        with open(os.path.join(a.out_dir, f"{name}.json"), "w") as f:
            json.dump(obj, f, indent=1)
    print(f"Saved queue '{queue['name']}', {len(records)} records, and evaluator "
          f"'{evaluator['name']}' to {a.out_dir}")
    turns_path = os.path.join(a.out_dir, "turns.json")
    if os.path.exists(turns_path):
        os.remove(turns_path)  # counts belong to the records just fetched
    if a.count_turns:
        if LAST_TURN_MARKER not in ((evaluator.get("version") or {}).get("template_config") or {}).get("template", ""):
            print(f"Skipping --count-turns: the template has no {LAST_TURN_MARKER} marker, so stored results "
                  "don't say how many turns the judge saw.")
            return
        turns = count_turns(a, records)
        with open(turns_path, "w") as f:
            json.dump(turns, f, indent=1)
        print(f"Counted turns for {len(turns)} sessions (turns.json)")


# Templates that ask the judge to name the highest turn it saw, e.g. "LAST_TURN_CHECK: Turn 7". Without the
# marker, a "Turn N" in an explanation is only the decisive turn, so staleness can't be read from it.
LAST_TURN_MARKER = "LAST_TURN_CHECK"
SESSIONS_PER_EXPORT = 50


def last_turn_seen(explanation):
    """The highest turn the judge says it saw, or None when the explanation doesn't say."""
    m = re.search(LAST_TURN_MARKER + r"\D{0,40}?(\d+)", explanation or "", re.I)
    return int(m.group(1)) if m else None


def count_turns(a, records):
    """Root spans (turns) per session, for records whose stored result can be checked for staleness."""
    if not a.project:
        sys.exit("--count-turns needs --project")
    first = {}
    for r in records:
        d = r.get("data") or {}
        sid, t = d.get("attributes.session.id"), parse_ms(d.get("start_time"))
        if sid and t and (sid not in first or t < first[sid]):
            first[sid] = t
    turns, todo = {}, sorted(first, key=first.get)

    def export(batch):
        ids = ", ".join("'" + str(x).replace("'", "''") + "'" for x in batch)
        spans = run_ax(a.ax, ["spans", "export", a.project, "--space", a.space,
                              "--filter", f"({a.count_turns}) AND attributes.session.id IN ({ids})",
                              "--start-time", (first[batch[0]] - timedelta(hours=1)).isoformat(),
                              "--end-time", (first[batch[-1]] + timedelta(days=3)).isoformat(),
                              "-l", "500", "--stdout"], json_flag=False)
        if len(spans) >= 500 and len(batch) > 1:
            # Page cap hit; split so no session's count is truncated.
            export(batch[:len(batch) // 2])
            export(batch[len(batch) // 2:])
            return
        if len(spans) >= 500:
            print(f"Warning: session {batch[0]} has 500+ turns matching the root filter; its count is a lower bound.")
        counts = Counter((sp.get("attributes") or {}).get("session.id") for sp in spans)
        turns.update({sid: counts.get(sid, 0) for sid in batch})

    for i in range(0, len(todo), SESSIONS_PER_EXPORT):
        export(todo[i:i + SESSIONS_PER_EXPORT])
    return turns


# ---------------------------------------------------------------------------
# report helpers
# ---------------------------------------------------------------------------

def load(path):
    with open(path) as f:
        return json.load(f)


def config_of(c):
    # The API wraps each config as a oneOf; the CLI exposes it as actual_instance.
    return c.get("actual_instance", c)


def short_email(email):
    return email.split("@")[0] if email else "(unattributed)"


def cohen_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for x, y in pairs if x == y) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def gwet_ac1(pairs):
    """Gwet's AC1 for two raters; stable when one label dominates, where κ collapses."""
    n = len(pairs)
    if n == 0:
        return None
    labels = {x for p in pairs for x in p}
    q = max(2, len(labels))
    po = sum(1 for x, y in pairs if x == y) / n
    share = Counter(x for p in pairs for x in p)
    pe = sum((share[k] / (2 * n)) * (1 - share[k] / (2 * n)) for k in labels) / (q - 1)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def pabak(pairs):
    """Prevalence- and bias-adjusted κ: (q·p_o − 1) / (q − 1)."""
    if not pairs:
        return None
    q = max(2, len({x for p in pairs for x in p}))
    po = sum(1 for x, y in pairs if x == y) / len(pairs)
    return (q * po - 1) / (q - 1)


def wilson(x, n, z=1.96):
    """95% Wilson score interval for a proportion, as (low, high)."""
    if not n:
        return None
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def pct(x, n):
    return f"{x}/{n} ({100 * x / n:.0f}%)" if n else f"{x}/0"


def pct_ci(x, n):
    """Count, percentage and 95% interval, e.g. '9/10 (90%, 95% CI 60–98%)'."""
    if not n:
        return f"{x}/0"
    lo, hi = wilson(x, n)
    return f"{x}/{n} ({100 * x / n:.0f}%, 95% CI {100 * lo:.0f}–{100 * hi:.0f}%)"


def split_of(record_id, label, counts):
    """Stable train/dev/test assignment: a record's rank within its human label, by hash of its ID."""
    ranked = counts[label]
    i = ranked.index(record_id)
    n = len(ranked)
    n_train = int(n * SPLIT["train"])
    n_dev = int(round(n * SPLIT["dev"]))
    return "train" if i < n_train else "dev" if i < n_train + n_dev else "test"


def stable_order(ids):
    return sorted(ids, key=lambda r: hashlib.sha256(str(r).encode()).hexdigest())


def parse_ms(v):
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_iso(v):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def clip(s, n=160):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def build(a):
    queue = load(os.path.join(a.dir, "queue.json"))
    records = load(os.path.join(a.dir, "records.json"))
    evaluator = load(os.path.join(a.dir, "evaluator.json"))
    adjudications = load(a.adjudications) if a.adjudications else {}
    turns_path = os.path.join(a.dir, "turns.json")
    turns = load(turns_path) if os.path.exists(turns_path) else {}

    version = evaluator.get("version") or {}
    tc = version.get("template_config") or {}
    choices = list((tc.get("classification_choices") or {}).keys())
    granularity = (tc.get("data_granularity") or "SPAN").upper()
    eval_column = a.eval_column or f"{GRANULARITY_PREFIX.get(granularity, 'eval')}.{tc.get('name')}"

    configs = [config_of(c) for c in queue.get("annotation_configs", [])]
    if a.config:
        config = next((c for c in configs if c.get("name") == a.config), None)
        if not config:
            sys.exit(f"Queue has no annotation config named {a.config!r}; it has {[c.get('name') for c in configs]}")
    elif len(configs) == 1:
        config = configs[0]
    else:
        sys.exit(f"Queue has {len(configs)} annotation configs; pass --config with one of {[c.get('name') for c in configs]}")
    config_name = config.get("name")
    rubric = [v.get("label") for v in config.get("values") or [] if v.get("label")]

    na = set(a.not_applicable)
    unscorable = set(a.unscorable)
    assigned = [u.get("email") for u in queue.get("annotators", [])]

    rows, other_configs, unattributed_only = [], Counter(), 0
    completion = defaultdict(Counter)
    levels_used, self_conflicts = Counter(), 0
    for r in records:
        data = r.get("data") or {}
        votes, unattributed, conflicted = {}, [], False
        # A queue can store labels at span, trace, or session level depending on its config.
        for level in ("annotations", "trace_annotations", "session_annotations"):
            for ann in r.get(level) or []:
                if ann.get("name") != config_name:
                    other_configs[ann.get("name")] += 1
                    continue
                levels_used[level] += 1
                who = (ann.get("annotator") or {}).get("email")
                if not who:
                    unattributed.append(ann.get("label"))
                elif who in votes and votes[who] != ann.get("label"):
                    conflicted = True
                else:
                    votes[who] = ann.get("label")
        if conflicted:
            # The same annotator left different labels at different levels; no single vote stands.
            self_conflicts += 1
            votes = {}
        if not votes and unattributed and not conflicted:
            # Annotations applied outside the queue carry no annotator; keep one as a single vote.
            votes["(unattributed)"] = unattributed[0]
            unattributed_only += 1
        for u in r.get("assigned_users") or []:
            completion[(u.get("user") or {}).get("email")][u.get("completion_status")] += 1
        stored = next((e for e in r.get("evaluations") or [] if e.get("name") == eval_column), None)
        # A stored result whose last turn seen is lower than the session's turn count was likely scored mid-session.
        n_turns = turns.get(data.get("attributes.session.id"))
        seen = last_turn_seen((stored or {}).get("explanation"))
        stale = bool(n_turns and seen and seen < n_turns)
        rows.append({
            "record_id": r.get("id"),
            "granularity": r.get("granularity"),
            "session_id": data.get("attributes.session.id"),
            "trace_id": data.get("context.trace_id"),
            "span_id": data.get("context.span_id"),
            "start_time": parse_ms(data.get("start_time")),
            "votes": votes,
            "stored": stored,
            "stale": stale,
        })

    # Resolve each record to a gold label (or a reason it has none).
    for row in rows:
        labels = set(row["votes"].values())
        adj = adjudications.get(row["record_id"])
        if adj:
            row["consensus"], row["status"] = adj, "adjudicated"
        elif not labels:
            row["consensus"], row["status"] = None, "unlabeled"
        elif len(labels) > 1:
            row["consensus"], row["status"] = None, "disputed"
        else:
            row["consensus"] = labels.pop()
            row["status"] = "single" if len(row["votes"]) == 1 else "agreed"
        c = row["consensus"]
        if c is None:
            row["bucket"] = row["status"]
        elif c in na:
            row["bucket"] = "not_applicable"
        elif c in unscorable:
            row["bucket"] = "unscorable"
        elif choices and c not in choices:
            row["bucket"] = "off_rubric"
        else:
            row["bucket"] = "gold"

    # Annotator agreement over records with at least two attributed votes.
    annotators = sorted({w for row in rows for w in row["votes"] if w != "(unattributed)"})
    iaa = []
    for x, y in combinations(annotators, 2):
        pairs = [(row["votes"][x], row["votes"][y]) for row in rows if x in row["votes"] and y in row["votes"]]
        if pairs:
            top = Counter(v for p in pairs for v in p).most_common(1)[0][1] / (2 * len(pairs))
            kappa, ac1 = cohen_kappa(pairs), gwet_ac1(pairs)
            skewed = top >= SKEW_SHARE
            iaa.append({"a": x, "b": y, "n": len(pairs), "agree": sum(1 for p, q in pairs if p == q),
                        "kappa": kappa, "ac1": ac1, "pabak": pabak(pairs), "majority_share": top,
                        "skewed": skewed,
                        "ok": kappa >= MIN_KAPPA or (skewed and ac1 is not None and ac1 >= MIN_KAPPA)})
    multi = [row for row in rows if len(row["votes"]) >= 2]
    disputed = [row for row in rows if row["status"] == "disputed"]

    # Join and coverage.
    n = len(rows)
    joined = [row for row in rows if row["session_id"] or granularity != "SESSION"]
    session_counts = Counter(row["session_id"] for row in rows if row["session_id"])
    dup_sessions = {s: c for s, c in session_counts.items() if c > 1}
    with_stored = [row for row in rows if row["stored"]]
    created = parse_iso(version.get("created_at"))
    older = [row for row in rows if created and row["start_time"] and row["start_time"] < created]

    # Human vs evaluator.
    gold = [row for row in rows if row["bucket"] == "gold"]
    gold_scored = [row for row in gold if row["stored"]]
    confusion = Counter((row["consensus"], row["stored"].get("label")) for row in gold_scored)
    per_label = {}
    for lbl in sorted({row["consensus"] for row in gold_scored}):
        tp = confusion[(lbl, lbl)]
        fp = sum(c for (h, e), c in confusion.items() if e == lbl and h != lbl)
        fn = sum(c for (h, e), c in confusion.items() if h == lbl and e != lbl)
        per_label[lbl] = {"precision": tp / (tp + fp) if tp + fp else None,
                          "recall": tp / (tp + fn) if tp + fn else None, "support": tp + fn,
                          "tp": tp, "predicted": tp + fp}
    agree = sum(c for (h, e), c in confusion.items() if h == e)
    # Mean recall over the human labels: the TPR/TNR average for a binary judge, robust to class imbalance.
    recalls = [m["recall"] for m in per_label.values() if m["recall"] is not None]
    balanced = sum(recalls) / len(recalls) if recalls else None

    # Held-out split of the gold records, by human label, stable across runs.
    by_label = defaultdict(list)
    for row in gold:
        by_label[row["consensus"]].append(row["record_id"])
    ranked = {lbl: stable_order(ids) for lbl, ids in by_label.items()}
    for row in rows:
        row["split"] = split_of(row["record_id"], row["consensus"], ranked) if row["bucket"] == "gold" else None
    split_counts = {s: Counter(row["consensus"] for row in gold if row["split"] == s) for s in ("train", "dev", "test")}

    weighted = weight_by_plan(load(a.plan), rows, gold_scored) if getattr(a, "plan", None) else None
    na_rows = [row for row in rows if row["bucket"] == "not_applicable" and row["stored"]]
    applicability = Counter(row["stored"].get("label") for row in na_rows)

    # Fit checks.
    vote_labels = Counter(v for row in rows for v in row["votes"].values())
    fit = []
    if (rows and rows[0]["granularity"] or "").upper() != granularity:
        fit.append(f"Queue records are `{rows[0]['granularity'] if rows else '?'}` but the evaluator scores "
                   f"`{granularity}`. Each record must map to exactly one {granularity.lower()}; "
                   f"verify the evaluator's input (e.g. `{{conversation}}`) is the full {granularity.lower()} the labeler saw.")
    missing_in_rubric = [c for c in choices if c not in rubric]
    if missing_in_rubric:
        fit.append(f"Evaluator choices missing from the human rubric: {missing_in_rubric}. Humans cannot produce these labels.")
    extra = [l for l in rubric if l not in choices and l not in na | unscorable]
    if extra:
        fit.append(f"Human rubric labels the evaluator cannot output: {extra}. Records with these labels are excluded as off-rubric.")
    unseen = [c for c in choices if c not in vote_labels and c not in na]
    if unseen:
        fit.append(f"Evaluator classes with zero human examples: {unseen}. The queue cannot test whether the evaluator produces them correctly.")
    template = tc.get("template") or ""
    if "{turn_data}" in template:
        fit.append("The evaluator template reads `{turn_data}` (per-turn data from the task's query mappings), not the "
                   "whole session. If humans judged the whole session, the two sides graded different inputs.")
    decisive = [c for c in choices if c not in na]
    instructions = queue.get("instructions") or ""
    undefined = [c for c in decisive
                 if not re.search(r"(?<![\w-])" + r"[_ ]".join(map(re.escape, re.split(r"[_ ]", c))) + r"(?![\w-])",
                                  instructions, re.I)]
    if undefined:
        fit.append(f"Queue instructions never mention {len(undefined)} of {len(decisive)} evaluator labels ({undefined}), "
                   "and annotation configs carry no label definitions. If labelers saw label names only, expect "
                   "disagreements about what a label means (Phase 4 step 2 compares the definitions).")
    if other_configs:
        fit.append("Records also carry labels from other annotation configs "
                   + ", ".join(f"`{k}` ({v})" for k, v in other_configs.most_common())
                   + f". They were ignored; only `{config_name}` is used.")
    if levels_used:
        fit.append(f"`{config_name}` labels were read from: "
                   + ", ".join(f"`{k}` ({v})" for k, v in levels_used.most_common()) + ".")
    if self_conflicts:
        fit.append(f"{self_conflicts} record(s) have one annotator giving different labels at different levels; "
                   "they are treated as unlabeled until resolved.")
    if unattributed_only:
        fit.append(f"{unattributed_only} record(s) have only unattributed `{config_name}` labels (applied outside the queue).")

    # Gates.
    gold_classes = Counter(row["consensus"] for row in gold)
    excluded = sum(1 for row in rows if row["bucket"] in ("not_applicable", "unscorable", "off_rubric"))
    labeled = sum(1 for row in rows if row["bucket"] != "unlabeled")
    gates = [
        ("Gold records (applicable, decisive, resolved)", len(gold) >= MIN_GOLD_USABLE,
         f"{len(gold)} (need ≥{MIN_GOLD_USABLE})"),
        (f"≥2 gold classes with ≥{MIN_PER_CLASS} each", sum(1 for c in gold_classes.values() if c >= MIN_PER_CLASS) >= 2,
         ", ".join(f"{k}={v}" for k, v in gold_classes.most_common()) or "none"),
        ("Excluded rate (not applicable + unscorable + off-rubric)",
         labeled > 0 and excluded / labeled <= MAX_EXCLUDED_RATE, f"{pct(excluded, labeled)} (max {MAX_EXCLUDED_RATE:.0%})"),
        ("Join to evaluator unit", n > 0 and len(joined) / n >= MIN_JOIN_RATE and not dup_sessions,
         f"{pct(len(joined), n)} with a session ID; {len(dup_sessions)} duplicated session(s)"),
        ("Stored evaluator output on gold records", bool(gold) and len(gold_scored) / len(gold) >= MIN_JOIN_RATE,
         pct(len(gold_scored), len(gold))),
        (f"Annotator agreement κ ≥ {MIN_KAPPA}, or AC1 ≥ {MIN_KAPPA} when one label holds ≥{SKEW_SHARE:.0%} "
         "(when records have 2+ votes)",
         all(p["ok"] for p in iaa),
         "; ".join(f"{short_email(p['a'])}/{short_email(p['b'])} κ={p['kappa']:.2f}"
                   + (f", AC1={p['ac1']:.2f} (top label {p['majority_share']:.0%})" if p["skewed"] else "")
                   + f" on {p['n']}" for p in iaa)
         or "single annotator; not measured"),
        ("No unresolved disputes", not disputed, f"{len(disputed)} disputed"),
    ]
    mismatches = [row for row in rows if row["stored"] and row["consensus"] and row["stored"].get("label") != row["consensus"]]
    stale = [row for row in rows if row["stale"]]
    big_classes = [c for c, k in gold_classes.items() if k >= MIN_PER_CLASS_VALIDATED]
    small_classes = sorted(c for c in gold_classes if c not in big_classes)
    if all(ok for _, ok, _ in gates):
        validated = len(gold) >= MIN_GOLD_VALIDATED and len(big_classes) >= 2
        verdict = "VALIDATED" if validated else "DIRECTIONAL"
    elif len(gold) >= MIN_GOLD_EXPLORATORY and len(gold_classes) >= 2:
        verdict = "EXPLORATORY"
    else:
        verdict = "NOT USABLE"

    return {
        "queue": queue, "evaluator": evaluator, "version": version, "tc": tc, "choices": choices,
        "granularity": granularity, "eval_column": eval_column, "config_name": config_name, "rubric": rubric,
        "assigned": assigned, "completion": completion, "rows": rows, "vote_labels": vote_labels,
        "iaa": iaa, "multi": multi, "disputed": disputed, "dup_sessions": dup_sessions,
        "with_stored": with_stored, "older": older, "gold": gold, "gold_scored": gold_scored,
        "confusion": confusion, "per_label": per_label, "agree": agree, "na_rows": na_rows,
        "applicability": applicability, "fit": fit, "gates": gates, "verdict": verdict,
        "gold_classes": gold_classes, "annotators": annotators, "mismatches": mismatches, "stale": stale,
        "turns_fetched": bool(turns), "marker": LAST_TURN_MARKER in template,
        "balanced": balanced, "split_counts": split_counts, "weighted": weighted, "small_classes": small_classes,
    }


def weight_by_plan(plan, rows, gold_scored):
    """Production-weighted agreement and per-label recall, from the queue builder's strata.

    The queue oversamples rare stored labels and provider disagreements, so raw agreement on it is
    not a production rate. Each stratum's gold records stand in for its production units (strata
    without gold are reported as uncovered). Assumes exclusions are random within a stratum."""
    strata = {s["stratum"]: s for s in plan.get("strata") or [] if s.get("population")}
    if not strata:
        return {"error": "plan.json has no strata with production counts (re-plan with a current plan_queue.py)"}
    by_span = {r.get("span_id"): r.get("stratum") for r in plan.get("records") or []}
    groups = defaultdict(list)
    for row in gold_scored:
        h = by_span.get(row["span_id"])
        if h in strata:
            groups[h].append(row)
    covered = {h: s["population"] for h, s in strata.items() if groups.get(h)}
    total = sum(s["population"] for s in strata.values())
    if not covered:
        return {"error": "no gold record maps to a plan stratum (check the plan and queue match)"}
    pop = sum(covered.values())
    agree = sum(n * sum(1 for r in groups[h] if r["stored"].get("label") == r["consensus"]) / len(groups[h])
                for h, n in covered.items()) / pop
    recall = {}
    for lbl in sorted({r["consensus"] for g in groups.values() for r in g}):
        has = sum(n * sum(1 for r in groups[h] if r["consensus"] == lbl) / len(groups[h]) for h, n in covered.items())
        hit = sum(n * sum(1 for r in groups[h] if r["consensus"] == lbl and r["stored"].get("label") == lbl)
                  / len(groups[h]) for h, n in covered.items())
        recall[lbl] = hit / has if has else None
    return {"agreement": agree, "recall": recall, "covered_share": pop / total if total else None,
            "uncovered": sorted(h for h in strata if h not in covered),
            "lower_bound": any(s.get("population_lower_bound") for s in strata.values())}


VERDICT_MEANING = {
    "VALIDATED": "Every gate passes and two or more classes have enough gold records to support an agreement claim.",
    "DIRECTIONAL": "Every gate passes, so it is enough to start aligning, but too small to confirm a target.",
    "EXPLORATORY": "Some gates fail; disagreements show patterns worth investigating, nothing more.",
    "NOT USABLE": "Too few gold records or classes; fix the queue before reading agreement.",
}


def render(r):
    q, ev, v, tc = r["queue"], r["evaluator"], r["version"], r["tc"]
    rows, out = r["rows"], []
    w = out.append
    w(f"# Pre-alignment report: `{ev.get('name')}` vs queue \"{q.get('name')}\"\n")
    w(f"**Verdict: {r['verdict']}.** {VERDICT_MEANING[r['verdict']]} "
      "No evaluator, task, or queue was changed to produce this report.\n")
    if r["verdict"] == "DIRECTIONAL" and r["small_classes"]:
        w(f"Classes with fewer than {MIN_PER_CLASS_VALIDATED} gold records, where agreement is not validated: "
          f"{r['small_classes']}.\n")

    w("## What is being compared\n")
    w(f"- Queue `{q.get('id')}`: {len(rows)} records, annotation config `{r['config_name']}`")
    w(f"- Queue instructions: {clip(q.get('instructions'), 400) or '(none)'}")
    w(f"- Evaluator `{ev.get('id')}`, current version `{v.get('id')}` created {v.get('created_at')} "
      f"(\"{clip(v.get('commit_message'), 120)}\")")
    w(f"- Evaluator granularity `{r['granularity']}`, model `{(tc.get('llm_config') or {}).get('model_name')}`, "
      f"output column `{r['eval_column']}`")
    w(f"- Evaluator choices: {r['choices']}")
    w(f"- Human rubric: {r['rubric']}\n")

    w("## Fit between queue and evaluator\n")
    for f in r["fit"] or ["No structural mismatches found."]:
        w(f"- {f}")
    w("")

    w("## Labeling coverage\n")
    w("| Annotator | Completed | Pending | Votes cast |")
    w("|---|---:|---:|---:|")
    vote_by = Counter(who for row in rows for who in row["votes"])
    for who in sorted(set(r["assigned"]) | set(r["completion"]) | set(vote_by)):
        c = r["completion"].get(who, Counter())
        w(f"| {short_email(who)} | {c.get('COMPLETED', 0)} | {sum(c.values()) - c.get('COMPLETED', 0)} | {vote_by.get(who, 0)} |")
    w("")
    w("Human label distribution (one row per record, after consensus):\n")
    buckets = Counter(row["bucket"] for row in rows)
    labels = Counter(row["consensus"] for row in rows if row["consensus"])
    w("| Label | Records | Bucket |")
    w("|---|---:|---|")
    for lbl, c in labels.most_common():
        b = next(row["bucket"] for row in rows if row["consensus"] == lbl)
        w(f"| `{lbl}` | {c} | {b} |")
    for b in ("unlabeled", "disputed"):
        if buckets.get(b):
            w(f"| — | {buckets[b]} | {b} |")
    w("")

    w("## Annotator agreement\n")
    if not r["multi"]:
        w("No record has two or more votes, so human-human agreement cannot be measured. "
          "Every gold label rests on a single annotator; say so when quoting results.\n")
    else:
        for p in r["iaa"]:
            w(f"- {short_email(p['a'])} vs {short_email(p['b'])}: {pct_ci(p['agree'], p['n'])} agree, "
              f"Cohen's κ = {p['kappa']:.2f}, AC1 = {p['ac1']:.2f}, PABAK = {p['pabak']:.2f}; "
              f"most common label {p['majority_share']:.0%} of votes")
            if p["skewed"]:
                w(f"  - One label holds ≥{SKEW_SHARE:.0%} of the votes, so κ understates agreement (the kappa "
                  "paradox). The gate accepts AC1 for this pair.")
            if p["n"] < MIN_SHARED_FOR_KAPPA:
                w(f"  - Only {p['n']} shared records; κ from fewer than {MIN_SHARED_FOR_KAPPA} is noisy. "
                  "Treat this as a rough check.")
        if r["disputed"]:
            w("\nDisputed records (excluded from gold until adjudicated):\n")
            w("| Record | Session | Votes |")
            w("|---|---|---|")
            for row in r["disputed"]:
                w(f"| `{row['record_id']}` | {row['session_id']} | "
                  + ", ".join(f"{short_email(k)}=`{x}`" for k, x in row["votes"].items()) + " |")
        w("")

    w("## Quality gates\n")
    w("| Gate | Pass | Value |")
    w("|---|:---:|---|")
    for name, ok, val in r["gates"]:
        w(f"| {name} | {'✅' if ok else '❌'} | {val} |")
    w("")

    w("## Stored evaluator output\n")
    w(f"- `{r['eval_column']}` present on {pct(len(r['with_stored']), len(rows))} records.")
    if r["older"]:
        w(f"- {len(r['older'])} record(s) started before the current version was created. Stored outputs carry no version ID, "
          "so these may have been scored by an older version. A fresh run of the current version is needed before any "
          "agreement number is quoted as the baseline.")
    if r["stale"]:
        w(f"- {len(r['stale'])} stored result(s) say the judge saw fewer turns than the session has "
          f"(`{LAST_TURN_MARKER}`), so they were likely scored before the session ended. A hint, not proof: "
          "re-run the current version before relying on their disagreements.")
    elif r["marker"] and not r["turns_fetched"]:
        w(f"- The template reports `{LAST_TURN_MARKER}`; run `fetch --count-turns` to check for results scored mid-session.")
    if r["dup_sessions"]:
        w(f"- Sessions appearing on more than one record: {r['dup_sessions']}.")
    w("")

    if r["na_rows"]:
        w("### Records humans marked not applicable\n")
        w("Evaluator output on these records (`not_applicable` is correct if the evaluator offers it):\n")
        for lbl, c in r["applicability"].most_common():
            w(f"- `{lbl}`: {c}")
        w("")

    w("## Human vs evaluator on gold records\n")
    gs = r["gold_scored"]
    if not gs:
        w("No gold record has a stored evaluator output, so agreement cannot be computed from stored results.\n")
    else:
        w("Per human label, the share the evaluator caught (recall; TPR and TNR for a binary evaluator):\n")
        for lbl, m in r["per_label"].items():
            w(f"- `{lbl}`: {pct_ci(m['tp'], m['support'])}")
        if r["balanced"] is not None:
            w(f"- Balanced accuracy (mean of the above): {100 * r['balanced']:.0f}%")
        w("")
        w(f"Exact agreement: {pct_ci(r['agree'], len(gs))}. "
          + ("Evidence of alignment on this gold set." if r["verdict"] == "VALIDATED"
             else "Directional only: the interval is too wide to confirm a target." if r["verdict"] == "DIRECTIONAL"
             else "Descriptive only.")
          + " The queue may oversample rare labels, so this is not a production-wide rate"
          + (" (see the weighted estimate below).\n" if r["weighted"] else ".\n"))
        w("| Human \\ Evaluator | " + " | ".join(f"`{c}`" for c in r["choices"]) + " |")
        w("|---|" + "---:|" * len(r["choices"]))
        for h in sorted({row["consensus"] for row in gs}):
            w(f"| `{h}` | " + " | ".join(str(r["confusion"].get((h, c), 0)) for c in r["choices"]) + " |")
        w("")
        w("Per evaluator label, the share humans confirmed (precision):\n")
        for lbl, m in r["per_label"].items():
            w(f"- `{lbl}`: {pct_ci(m['tp'], m['predicted'])}")
        w("")
    wt = r["weighted"]
    if wt:
        w("### Production-weighted estimates\n")
        if wt.get("error"):
            w(f"Not computed: {wt['error']}.\n")
        else:
            w("Each queue stratum's gold records are weighted by that stratum's production count from the queue "
              "plan, which undoes the oversampling of rare labels and provider disagreements. Exclusions are "
              "assumed random within a stratum.\n")
            w(f"- Agreement: {100 * wt['agreement']:.0f}%")
            for lbl, rec in wt["recall"].items():
                w(f"- Recall for `{lbl}`: {'—' if rec is None else f'{100 * rec:.0f}%'}")
            w(f"- Strata with gold records cover {100 * (wt['covered_share'] or 0):.0f}% of the planned production "
              "units" + (f"; no gold in: {wt['uncovered']}" if wt["uncovered"] else "")
              + (". Some production counts are lower bounds." if wt["lower_bound"] else "."))
            w("")
    sc = r["split_counts"]
    if r["gold"]:
        w("### Held-out split\n")
        w("Gold records are split by human label, stably by record ID: **train** may supply few-shot examples, "
          "**dev** is for reading disagreements and iterating, **test** is scored once, after the last revision. "
          "`--json-out` records each record's split.\n")
        w("| Human label | Train | Dev | Test |")
        w("|---|---:|---:|---:|")
        for lbl in sorted(r["gold_classes"]):
            w(f"| `{lbl}` | {sc['train'][lbl]} | {sc['dev'][lbl]} | {sc['test'][lbl]} |")
        thin = sorted(lbl for lbl in r["gold_classes"] if sc["test"][lbl] < MIN_PER_CLASS_VALIDATED)
        if thin:
            w(f"\nTest records per label below {MIN_PER_CLASS_VALIDATED} for {thin}: a test result on them is "
              "directional only.")
        w("")
    mism = r["mismatches"]
    if mism:
        w("### Record-level discrepancies\n")
        w("| Record | Session | Trace | Human | Evaluator | Evaluator explanation |")
        w("|---|---|---|---|---|---|")
        for row in mism:
            w(f"| `{row['record_id']}` | {row['session_id']} | `{(row['trace_id'] or '')[:12]}` | `{row['consensus']}` "
              f"({row['bucket']}) | `{row['stored'].get('label')}`{' (stale)' if row['stale'] else ''} | "
              f"{clip(row['stored'].get('explanation'))} |")
        w("")
    return "\n".join(out)


def cmd_report(a):
    r = build(a)
    print(render(r))
    if a.json_out:
        slim = {
            "verdict": r["verdict"], "eval_column": r["eval_column"], "config": r["config_name"],
            "gates": [{"gate": g, "pass": ok, "value": val} for g, ok, val in r["gates"]],
            "fit": r["fit"],
            "summary": {
                "gold": len(r["gold"]), "gold_scored": len(r["gold_scored"]), "agree": r["agree"],
                "gold_classes": dict(r["gold_classes"]), "annotators": r["annotators"],
                "disagreements": len(r["mismatches"]), "stale": len(r["stale"]),
                "balanced_accuracy": r["balanced"], "weighted": r["weighted"],
                "split_counts": {k: dict(v) for k, v in r["split_counts"].items()},
            },
            "records": [{
                "record_id": row["record_id"], "session_id": row["session_id"], "trace_id": row["trace_id"],
                "votes": row["votes"], "consensus": row["consensus"], "status": row["status"],
                "bucket": row["bucket"], "eval_label": (row["stored"] or {}).get("label"),
                "eval_explanation": (row["stored"] or {}).get("explanation"),
                "stale": row["stale"], "split": row["split"],
            } for row in r["rows"]],
        }
        with open(a.json_out, "w") as f:
            json.dump(slim, f, indent=1)


def cmd_compare(a):
    """Before/after on the same gold set: agreement with intervals, flipped records, label-mix shift."""
    before, after = load(a.before), load(a.after)
    if a.split:
        keep = {x["record_id"] for x in before["records"] if x.get("split") == a.split}
    else:
        keep = None
    b = {x["record_id"]: x for x in before["records"] if x["bucket"] == "gold" and (keep is None or x["record_id"] in keep)}
    c = {x["record_id"]: x for x in after["records"] if x["record_id"] in b}
    both = [rid for rid in b if b[rid].get("eval_label") and c.get(rid, {}).get("eval_label")]
    hit = lambda x: x["eval_label"] == x["consensus"]
    fixed = [rid for rid in both if not hit(b[rid]) and hit(c[rid])]
    broke = [rid for rid in both if hit(b[rid]) and not hit(c[rid])]
    print(f"# Before/after on {len(both)} gold records" + (f" ({a.split} split)" if a.split else "") + "\n")
    print(f"- Before: {pct_ci(sum(hit(b[r]) for r in both), len(both))}")
    print(f"- After: {pct_ci(sum(hit(c[r]) for r in both), len(both))}")
    print(f"- Fixed (wrong before, right after): {len(fixed)}" + (f" — {fixed}" if fixed else ""))
    print(f"- Broken (right before, wrong after): {len(broke)}" + (f" — {broke}" if broke else ""))
    mix_b, mix_a = Counter(b[r]["eval_label"] for r in both), Counter(c[r]["eval_label"] for r in both)
    print("- Evaluator label mix: " + ", ".join(f"`{k}` {mix_b.get(k, 0)}→{mix_a.get(k, 0)}"
                                               for k in sorted(set(mix_b) | set(mix_a))))
    print("\nA change smaller than the run-to-run noise floor is not an improvement. Re-run the unchanged "
          "candidate once and compare it with itself to measure that floor.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Save queue, records, and evaluator JSON (read-only)")
    f.add_argument("--space", required=True)
    f.add_argument("--queue", required=True, help="Annotation queue name or ID")
    f.add_argument("--evaluator", required=True, help="Evaluator name or ID")
    f.add_argument("--out-dir", required=True)
    f.add_argument("--ax", default="ax", help="Path to the ax binary")
    f.add_argument("--count-turns", metavar="ROOT_FILTER",
                   help="Also count each session's turns (root spans matching this filter) so the report can flag stored "
                        f"results scored mid-session. Only for templates that report {LAST_TURN_MARKER}.")
    f.add_argument("--project", help="Project name or ID; required with --count-turns")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("report", help="Print the pre-alignment report (Markdown)")
    r.add_argument("--dir", required=True, help="Directory written by fetch")
    r.add_argument("--config", help="Annotation config name, if the queue has several")
    r.add_argument("--eval-column", help="Override the stored output column, e.g. session_eval.my_eval")
    r.add_argument("--not-applicable", nargs="*", default=DEFAULT_NOT_APPLICABLE)
    r.add_argument("--unscorable", nargs="*", default=DEFAULT_UNSCORABLE)
    r.add_argument("--adjudications", help='JSON file mapping record_id to the adjudicated label')
    r.add_argument("--json-out", help="Also write per-record results as JSON")
    r.add_argument("--plan", help="plan.json from arize-align-queue-builder; adds production-weighted estimates")
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("compare", help="Compare two report --json-out files from the same gold set")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--split", choices=["train", "dev", "test"], help="Only records in this split of the BEFORE file")
    c.set_defaults(func=cmd_compare)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
