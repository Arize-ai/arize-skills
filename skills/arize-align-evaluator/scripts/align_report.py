#!/usr/bin/env python3
"""Pre-alignment report for an Arize evaluator against human ground truth.

Two subcommands, standard library only (Python 3.9+):

  fetch   Read-only. Calls `ax` to save a queue, all of its records (every
          page), and an evaluator to a directory.
  report  Joins the saved files and prints a Markdown pre-alignment report:
          queue/evaluator fit, label coverage, annotator agreement, quality
          gates, and human-vs-evaluator agreement on the gold subset.
          Writes nothing to Arize.

Examples:
  align_report.py fetch --space SPACE --queue QUEUE --evaluator EVALUATOR --out-dir align/
  align_report.py report --dir align/ --json-out align/report.json > align/report.md
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations

GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}
DEFAULT_NOT_APPLICABLE = ["not_applicable"]
DEFAULT_UNSCORABLE = ["cannot_judge", "unclear"]

# Gate defaults. A queue must clear every "usable" gate before its agreement
# numbers are treated as evidence; otherwise results are exploratory at best.
# A single annotator is allowed; agreement is gated only when records overlap.
MIN_GOLD_USABLE = 10
MIN_GOLD_EXPLORATORY = 5
MIN_PER_CLASS = 3
MAX_EXCLUDED_RATE = 0.30
MIN_JOIN_RATE = 0.90
MIN_KAPPA = 0.60


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def run_ax(ax, args):
    proc = subprocess.run([ax] + args + ["-o", "json"], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ax {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
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


def pct(x, n):
    return f"{x}/{n} ({100 * x / n:.0f}%)" if n else f"{x}/0"


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
        rows.append({
            "record_id": r.get("id"),
            "granularity": r.get("granularity"),
            "session_id": data.get("attributes.session.id"),
            "trace_id": data.get("context.trace_id"),
            "span_id": data.get("context.span_id"),
            "start_time": parse_ms(data.get("start_time")),
            "votes": votes,
            "stored": stored,
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
            iaa.append({"a": x, "b": y, "n": len(pairs),
                        "agree": sum(1 for p, q in pairs if p == q), "kappa": cohen_kappa(pairs)})
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
                          "recall": tp / (tp + fn) if tp + fn else None, "support": tp + fn}
    agree = sum(c for (h, e), c in confusion.items() if h == e)
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
        (f"Annotator agreement κ ≥ {MIN_KAPPA} (when records have 2+ votes)",
         all(p["kappa"] is not None and p["kappa"] >= MIN_KAPPA for p in iaa),
         "; ".join(f"{short_email(p['a'])}/{short_email(p['b'])} κ={p['kappa']:.2f} on {p['n']}" for p in iaa)
         or "single annotator; not measured"),
        ("No unresolved disputes", not disputed, f"{len(disputed)} disputed"),
    ]
    if all(ok for _, ok, _ in gates):
        verdict = "USABLE"
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
    }


def render(r):
    q, ev, v, tc = r["queue"], r["evaluator"], r["version"], r["tc"]
    rows, out = r["rows"], []
    w = out.append
    w(f"# Pre-alignment report: `{ev.get('name')}` vs queue \"{q.get('name')}\"\n")
    w(f"**Verdict: {r['verdict']}.** No evaluator, task, or queue was changed to produce this report.\n")

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
            w(f"- {short_email(p['a'])} vs {short_email(p['b'])}: {pct(p['agree'], p['n'])} agree, Cohen's κ = {p['kappa']:.2f}")
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
        w(f"Exact agreement: {pct(r['agree'], len(gs))}. Descriptive only unless the verdict is USABLE.\n")
        w("| Human \\ Evaluator | " + " | ".join(f"`{c}`" for c in r["choices"]) + " |")
        w("|---|" + "---:|" * len(r["choices"]))
        for h in sorted({row["consensus"] for row in gs}):
            w(f"| `{h}` | " + " | ".join(str(r["confusion"].get((h, c), 0)) for c in r["choices"]) + " |")
        w("")
        for lbl, m in r["per_label"].items():
            fmt = lambda x: "—" if x is None else f"{x:.2f}"
            w(f"- `{lbl}`: precision {fmt(m['precision'])}, recall {fmt(m['recall'])}, support {m['support']}")
        w("")
    mism = [row for row in rows if row["stored"] and row["consensus"] and row["stored"].get("label") != row["consensus"]]
    if mism:
        w("### Record-level discrepancies\n")
        w("| Record | Session | Trace | Human | Evaluator | Evaluator explanation |")
        w("|---|---|---|---|---|---|")
        for row in mism:
            w(f"| `{row['record_id']}` | {row['session_id']} | `{(row['trace_id'] or '')[:12]}` | `{row['consensus']}` "
              f"({row['bucket']}) | `{row['stored'].get('label')}` | {clip(row['stored'].get('explanation'))} |")
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
            "records": [{
                "record_id": row["record_id"], "session_id": row["session_id"], "trace_id": row["trace_id"],
                "votes": row["votes"], "consensus": row["consensus"], "status": row["status"],
                "bucket": row["bucket"], "eval_label": (row["stored"] or {}).get("label"),
                "eval_explanation": (row["stored"] or {}).get("explanation"),
            } for row in r["rows"]],
        }
        with open(a.json_out, "w") as f:
            json.dump(slim, f, indent=1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Save queue, records, and evaluator JSON (read-only)")
    f.add_argument("--space", required=True)
    f.add_argument("--queue", required=True, help="Annotation queue name or ID")
    f.add_argument("--evaluator", required=True, help="Evaluator name or ID")
    f.add_argument("--out-dir", required=True)
    f.add_argument("--ax", default="ax", help="Path to the ax binary")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("report", help="Print the pre-alignment report (Markdown)")
    r.add_argument("--dir", required=True, help="Directory written by fetch")
    r.add_argument("--config", help="Annotation config name, if the queue has several")
    r.add_argument("--eval-column", help="Override the stored output column, e.g. session_eval.my_eval")
    r.add_argument("--not-applicable", nargs="*", default=DEFAULT_NOT_APPLICABLE)
    r.add_argument("--unscorable", nargs="*", default=DEFAULT_UNSCORABLE)
    r.add_argument("--adjudications", help='JSON file mapping record_id to the adjudicated label')
    r.add_argument("--json-out", help="Also write per-record results as JSON")
    r.set_defaults(func=cmd_report)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
