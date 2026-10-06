#!/usr/bin/env python3
"""Score historical sessions with a candidate copy of an evaluator, safely.

Subcommands (standard library only, Python 3.9+):

  estimate         Read-only. Reads an admission rule (the production task's filters, or an
                   --admission file for an evaluator with no production task) and estimates
                   how many units in a window it admits.
  copy-evaluator   Prints the candidate evaluator that would be created. With --execute,
                   creates it and diffs its config against the source.
  calibrate        Read-only. Copy mode only. After a calibration run on a window production
                   already scored, compares which units the candidate and the evaluator it was
                   copied from each scored, and how their labels agree. Refuses to compare
                   evaluators that are not copies of each other.
  check-admission  Read-only. New-evaluator mode. After a test run, compares the units the
                   candidate scored with the units its admission rule should admit. No other
                   evaluator is involved.
  verify           Read-only. After the historical run, counts candidate labels in the window.

Nothing is written to Arize except by `copy-evaluator --execute`.
"""

import argparse
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

UNIT_FIELD = {"SESSION": ("attributes", "session.id"), "TRACE": ("context", "trace_id"), "SPAN": ("context", "span_id")}
GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}
PAGE = 500  # REST export page cap
ID_BATCH = 100  # unit IDs per `IN (...)` filter
# Fields that must match for one evaluator to count as a copy of another. The CLI cannot set
# use_structured_output, so a difference there is reported but does not refuse calibration.
COPY_FIELDS = ("template", "classification_choices", "data_granularity", "direction",
               "include_explanations", "use_function_calling")


class ColumnMissing(Exception):
    """An eval column the filter references has no values in the requested period (or is not indexed yet)."""


def run_ax(ax, args, allow_empty=False, retries=5):
    for attempt in range(retries + 1):
        proc = subprocess.run([ax] + args, capture_output=True, text=True)
        out, msg = proc.stdout.strip(), proc.stderr + proc.stdout
        if proc.returncode == 0 and out:
            break
        if "429" in msg or "Too Many Requests" in msg:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
        if allow_empty and "No spans found" in msg:
            return []
        missing = re.search(r'column\s+"([^"]*eval\.[^"]+)"\s+does not exist', msg)
        if missing:
            raise ColumnMissing(missing.group(1))
        sys.exit(f"ax {' '.join(args[:3])} ... failed:\n{msg.strip()[:800]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        sys.exit(f"ax {' '.join(args[:3])} ... did not return JSON. Run `ax --version` and upgrade if it is old.")


def parse_time(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def quote(v):
    return "'" + str(v).replace("'", "''") + "'"


def export_page(a, filt, lo, hi, limit):
    """One export call. A period where a referenced eval column has no values counts as empty."""
    try:
        return run_ax(a.ax, ["spans", "export", a.project, "--space", a.space, "--filter", filt,
                             "--start-time", lo.isoformat(), "--end-time", hi.isoformat(),
                             "-l", str(min(limit, PAGE)), "--stdout"], allow_empty=True), False
    except ColumnMissing:
        return [], True


def slices(a, start, end):
    t0, t1 = parse_time(start), parse_time(end)
    step = (t1 - t0) / a.slices
    return [(t0 + step * i, t0 + step * (i + 1)) for i in range(a.slices)]


def require_some(missing, n, filt):
    if missing == n:
        sys.exit(f"No part of the window has values for the eval column in `{filt}`. If the evaluator ran there, "
                 "new results can take 20+ minutes to become queryable; re-run shortly. Otherwise check the "
                 "evaluator and the window.")


def export(a, filt, start, end):
    """Export up to --pool spans matching filt, drawn evenly across --slices sub-windows. Returns (spans, truncated)."""
    per = min(PAGE, math.ceil(a.pool / a.slices))
    spans, truncated, missing = [], False, 0
    for lo, hi in slices(a, start, end):
        page, gone = export_page(a, filt, lo, hi, per)
        truncated |= len(page) >= per
        missing += gone
        spans += page
    require_some(missing, a.slices, filt)
    return spans, truncated


def export_all(a, filt, start, end, min_span=timedelta(minutes=30), require=True):
    """Export every span matching filt by bisecting any time slice that hits the page cap.
    Returns (spans, truncated); truncated only if a slice at min_span still hits the cap.
    With require=False, a column with no values anywhere in the window returns nothing instead of exiting."""
    missing = 0

    def fetch(lo, hi):
        nonlocal missing
        page, gone = export_page(a, filt, lo, hi, PAGE)
        missing += gone
        if len(page) < PAGE:
            return page, False
        if hi - lo <= min_span:
            return page, True
        mid = lo + (hi - lo) / 2
        left, t1 = fetch(lo, mid)
        right, t2 = fetch(mid, hi)
        return left + right, t1 or t2

    spans, trunc = [], False
    for lo, hi in slices(a, start, end):
        got, t = fetch(lo, hi)
        spans += got
        trunc |= t
    if require:
        require_some(missing, a.slices, filt)
    return spans, trunc


def unit_of(span, gran):
    group, key = UNIT_FIELD.get(gran, UNIT_FIELD["SPAN"])
    return (span.get(group) or {}).get(key)


def units(spans, gran):
    return {u for u in (unit_of(s, gran) for s in spans) if u}


def parse_filters(qf):
    """Return ({clause_id: filter}, expression) from a {"filters": [...], "expression": ...} dict."""
    clauses = {f["id"]: f["filter"] for f in (qf or {}).get("filters") or [] if f.get("filter")}
    return clauses, ((qf or {}).get("expression") or " AND ".join(clauses)) if clauses else ""


def task_filters(task):
    """Return ({clause_id: filter}, expression) from a task, whichever form it stores."""
    clauses, expr = parse_filters(task.get("query_filters"))
    if clauses:
        return clauses, expr
    if task.get("query_filter"):
        return {"A": task["query_filter"]}, "A"
    return {}, ""


def eval_expression(expr, sets):
    """Evaluate an expression like 'A AND (B OR NOT C)' over sets of unit IDs."""
    tokens = re.findall(r"\(|\)|AND|OR|NOT|[A-Za-z0-9_]+", expr)
    universe = set().union(*sets.values()) if sets else set()
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def atom():
        t = take()
        if t == "(":
            v = disj()
            take()
            return v
        if t == "NOT":
            return universe - atom()
        return sets.get(t, set())

    def conj():
        v = atom()
        while peek() == "AND":
            take()
            v = v & atom()
        return v

    def disj():
        v = conj()
        while peek() == "OR":
            take()
            v = v | conj()
        return v

    return disj()


def single_string(clauses, expr):
    """The task expression rewritten as one --query-filter string."""
    return re.sub(r"\b([A-Za-z0-9_]+)\b", lambda m: f"({clauses[m.group(1)]})" if m.group(1) in clauses else m.group(1), expr)


# ---------------------------------------------------------------------------


def load_admission(a):
    """Return (clauses, expression, source, task) from --task or --admission, whichever was given."""
    if a.admission:
        clauses, expr = parse_filters(json.load(open(a.admission)))
        if not clauses:
            sys.exit(f"{a.admission} has no filters. Expected {{\"filters\": [{{\"id\": \"A\", \"filter\": \"...\"}}], "
                     "\"expression\": \"A AND B\"}.")
        return clauses, expr, f"admission file `{a.admission}`", None
    task = run_ax(a.ax, ["tasks", "get", a.task, "-o", "json"])
    clauses, expr = task_filters(task)
    return clauses, expr, f"task `{task.get('name')}`", task


def admitted_units(a, clauses, expr, gran, quiet=False):
    """Units in the window whose spans satisfy the expression, reading each clause across the unit's spans.
    Returns (units, lower_bound)."""
    say = (lambda *_: None) if quiet else print
    sets, truncated = {}, set()
    for cid, filt in clauses.items():
        # A clause matching nearly every unit (e.g. "is a root span") is sampled, then re-checked below;
        # narrower clauses are exported exhaustively.
        spans, t = (export if cid in a.broad else export_all)(a, filt, a.start_time, a.end_time)
        if t:
            truncated.add(cid)
        sets[cid] = units(spans, gran)
        say(f"- Clause {cid} `{filt}`: {len(sets[cid])} {gran.lower()}(s){' (truncated: at least)' if t else ''}")
    # Re-check each truncated (sampled) clause only for units the complete clauses found but the sample missed.
    complete = set().union(*(sets[c] for c in clauses if c not in truncated))
    id_attr = ".".join(UNIT_FIELD.get(gran, UNIT_FIELD["SPAN"]))
    recheck = bool(truncated and complete)
    if complete:
        t0, t1 = parse_time(a.start_time), parse_time(a.end_time)
        for cid in sorted(truncated):
            ids, found = sorted(complete - sets[cid]), set()
            for i in range(0, len(ids), ID_BATCH):
                batch = ", ".join(quote(x) for x in ids[i:i + ID_BATCH])
                page, _ = export_page(a, f"({clauses[cid]}) AND {id_attr} IN ({batch})", t0, t1, PAGE)
                found |= units(page, gran)
            sets[cid] |= found
            truncated.discard(cid)
            say(f"  - Clause {cid} re-checked against {len(ids)} more {gran.lower()}(s): {len(found)} match")
    # The re-check is exact only when clauses are ANDed; OR/NOT can admit units outside the complete clauses.
    trunc = bool(truncated) or (bool(re.search(r"\b(OR|NOT)\b", expr)) and len(clauses) > 1 and recheck)
    return (eval_expression(expr, sets) if clauses else set()), trunc


def evaluator_config(a, ref):
    ev = run_ax(a.ax, ["evaluators", "get", ref, "--space", a.space, "-o", "json"])
    return ev, (ev.get("version") or {}).get("template_config") or {}


def model_params(params):
    """Model parameters as one flat dict. Top-level keys (e.g. temperature) and additional_properties both count."""
    flat = dict(params or {})
    flat.update(flat.pop("additional_properties", None) or {})
    return flat


def model_of(tc):
    return (tc.get("llm_config") or {}).get("model_name")


def copy_diffs(src_tc, tc):
    """Fields where tc is not a copy of src_tc."""
    diffs = [k for k in COPY_FIELDS if src_tc.get(k) != tc.get(k)]
    return diffs + (["model_name"] if model_of(src_tc) != model_of(tc) else [])


def granularity(tc):
    return (tc.get("data_granularity") or "SPAN").upper()


def write_units(path, admitted, gran, root_filter):
    """Write the admitted unit IDs, plus ready-to-use task filters in batches of ID_BATCH."""
    ids = sorted(map(str, admitted))
    id_attr = ".".join(UNIT_FIELD.get(gran, UNIT_FIELD["SPAN"]))
    filters = [f"({root_filter}) AND {id_attr} IN ({', '.join(quote(x) for x in ids[i:i + ID_BATCH])})"
               for i in range(0, len(ids), ID_BATCH)]
    with open(path, "w") as f:
        json.dump({"units": ids, "query_filters": filters}, f, indent=1)
    print(f"\nWrote the {len(ids)} admitted units to {path}, with {len(filters)} `--query-filter` string(s) that "
          "admit exactly them. Each string is for one task run over this window.")


def cmd_estimate(a):
    if a.admission and not a.evaluator:
        sys.exit("--admission needs --evaluator, the evaluator that will be scored.")
    if a.write_units and not a.root_filter:
        sys.exit("--write-units needs --root-filter, which every written task filter starts with.")
    clauses, expr, source, task = load_admission(a)
    ev, tc = evaluator_config(a, (task.get("evaluators") or [{}])[0].get("evaluator_id") if task else a.evaluator)
    gran = granularity(tc)
    print(f"# Backfill estimate for {source}\n")
    print(f"- Evaluator `{ev.get('name')}` (`{tc.get('name')}`), granularity `{gran}`, model `{model_of(tc)}`")
    if task:
        print(f"- Task created {task.get('created_at')}, continuous={task.get('is_continuous')}, sampling_rate={task.get('sampling_rate')}")
    print(f"- Window {a.start_time} → {a.end_time}\n")
    if not clauses:
        print("No filter: every unit in the window is admitted.")
    admitted, trunc = admitted_units(a, clauses, expr, gran)
    print(f"\nExpression `{expr}` evaluated per {gran.lower()}: **{len(admitted)}{'+' if trunc else ''} admitted**.")
    if a.root_filter:
        scored, _ = labels_by_unit(a, tc.get("name"), list(tc.get("classification_choices") or {}), gran, require=False)
        print(f"Already scored by `{tc.get('name')}` in this window: {len(set(scored) & admitted)} of the admitted.")
    check = "calibrate" if task else "check-admission"
    print(f"\nSingle-string filter for the candidate task (verify with `{check}`):\n\n    {single_string(clauses, expr)}\n")
    if len(clauses) > 1:
        print("The single string is read one span at a time, but the expression above is read across a unit's spans. "
              "If a clause other than the root filter matches child spans, the single string admits fewer units. "
              f"`{check}` measures the gap.")
    print("Each admitted unit is one judge call at the evaluator's model."
          + (" The count is a lower bound because a clause was truncated; raise --pool or --slices." if trunc else ""))
    if task:
        print("This count uses a per-unit reading of the filter. The platform may admit differently; calibration "
              "measures the real ratio. Run `estimate` on the calibration window too, and scale the backfill cost by "
              "(units production scored there) / (units estimated there).")
    if a.write_units:
        write_units(a.write_units, admitted, gran, a.root_filter)


def cmd_copy(a):
    src, tc = evaluator_config(a, a.source)
    v = src.get("version") or {}
    llm = tc.get("llm_config") or {}
    inv, prov = model_params(llm.get("invocation_parameters")), model_params(llm.get("provider_parameters"))
    args = ["evaluators", "create-evaluator", "template", "--name", a.name, "--space", a.space,
            "--commit-message", f"Backfill candidate copied from {src.get('name')} version {v.get('id')}",
            "--template-name", a.template_name, "--template", tc.get("template", ""),
            "--ai-integration-id", llm.get("ai_integration_id", ""), "--model-name", llm.get("model_name", ""),
            "--description", f"Backfill candidate of {src.get('name')}. Writes {a.template_name}; never production.",
            "--classification-choices", json.dumps(tc.get("classification_choices") or {}),
            "--direction", tc.get("direction") or "NONE",
            "--data-granularity", (tc.get("data_granularity") or "span").lower(),
            "--invocation-params", json.dumps(inv), "--provider-params", json.dumps(prov)]
    if tc.get("include_explanations"):
        args.append("--include-explanations")
    if tc.get("use_function_calling"):
        args.append("--use-function-calling")
    print(f"Source: `{src.get('name')}` version `{v.get('id')}` ({v.get('created_at')})")
    print(f"Candidate: name `{a.name}`, template name `{a.template_name}`, model `{model_of(tc)}`, "
          f"granularity `{tc.get('data_granularity')}`, template {len(tc.get('template', ''))} chars copied verbatim")
    if tc.get("use_structured_output"):
        print("Note: the source uses structured output; the CLI cannot set it. Calibration will show whether labels differ.")
    if not a.execute:
        print("\nDry run. Re-run with --execute after the user approves.")
        return
    made = run_ax(a.ax, args + ["-o", "json"])
    _, got = evaluator_config(a, made["id"])
    diffs = copy_diffs(tc, got)
    if model_params((got.get("llm_config") or {}).get("invocation_parameters")) != inv:
        diffs.append(f"invocation parameters (source {inv}; the API may drop some, such as temperature; set them in the UI)")
    print(f"\nCreated `{made.get('name')}` ({made.get('id')}).")
    print("Config matches the source." if not diffs else f"Differs from the source in: {diffs}")


def labels_by_unit(a, column, labels, gran, require=True):
    """Every unit with a stored label for `column` (a template name) in the window, exported in full."""
    filt = f"{GRANULARITY_PREFIX.get(gran, 'eval')}.{column}.label IN ({', '.join(quote(l) for l in labels)})"
    if a.root_filter:
        filt = f"{a.root_filter} AND {filt}"
    spans, trunc = export_all(a, filt, a.start_time, a.end_time, require=require)
    out = {}
    for s in spans:
        for e in s.get("evaluations") or []:
            if e.get("name") == column and e.get("label") is not None:
                out[unit_of(s, gran)] = e.get("label")
    return out, trunc


def cmd_calibrate(a):
    prod_ev, prod_tc = evaluator_config(a, a.prod_evaluator)
    cand_ev, cand_tc = evaluator_config(a, a.cand_evaluator)
    diffs = copy_diffs(prod_tc, cand_tc)
    if diffs:
        sys.exit(f"`{cand_ev.get('name')}` is not a copy of `{prod_ev.get('name')}`: they differ in {diffs}.\n"
                 "Calibration only compares a candidate with the evaluator it was copied from. A different evaluator, "
                 "including an earlier version or a predecessor, was built to behave differently, so neither its labels "
                 "nor its admission are a reference. For an evaluator with no production task, use `check-admission` "
                 "against the admission rule agreed with the user. If production changed after the copy was made, "
                 "make a fresh copy with `copy-evaluator`.")
    gran, labels = granularity(cand_tc), list(cand_tc.get("classification_choices") or {})
    prod_name, cand_name = prod_tc.get("name"), cand_tc.get("name")
    prod, t1 = labels_by_unit(a, prod_name, labels, gran)
    cand, t2 = labels_by_unit(a, cand_name, labels, gran)
    both, union = set(prod) & set(cand), set(prod) | set(cand)
    agree = sum(1 for u in both if prod[u] == cand[u])
    p_only, c_only = len(set(prod) - set(cand)), len(set(cand) - set(prod))
    ok = union and p_only / len(union) <= a.tolerance and c_only / len(union) <= a.tolerance
    print(f"# Calibration on {a.start_time} → {a.end_time}\n")
    print(f"- Candidate `{cand_ev.get('name')}` is a copy of `{prod_ev.get('name')}` (same {', '.join(COPY_FIELDS)}, model)")
    if prod_tc.get("use_structured_output") != cand_tc.get("use_structured_output"):
        print("- Structured output differs (the CLI cannot set it); label disagreements may partly reflect that.")
    print(f"- Scored by production `{prod_name}`: {len(prod)}; by candidate `{cand_name}`: {len(cand)}"
          + (" (export truncated; raise --slices)" if t1 or t2 else ""))
    print(f"- Both: {len(both)}; production only: {p_only}; candidate only: {c_only}")
    print(f"- Label agreement where both scored: {agree}/{len(both)}")
    if both:
        print("- Confusion (production → candidate): " + ", ".join(
            f"{p}→{c}: {n}" for (p, c), n in Counter((prod[u], cand[u]) for u in both).most_common()))
    print(f"\n**Admission {'MATCHES' if ok else 'DOES NOT MATCH'}** (tolerance {a.tolerance:.0%} each way).")
    if not ok:
        print("Do not run the historical window. See the skill's 'If the admission check fails' section.")


def cmd_check_admission(a):
    cand_ev, cand_tc = evaluator_config(a, a.cand_evaluator)
    gran = granularity(cand_tc)
    clauses, expr, source, _ = load_admission(a)
    print(f"# Admission check on {a.start_time} → {a.end_time}\n")
    print(f"- Candidate `{cand_ev.get('name')}` (`{cand_tc.get('name')}`) against the rule in {source}: `{expr}`")
    intended, trunc = admitted_units(a, clauses, expr, gran, quiet=True)
    scored, t2 = labels_by_unit(a, cand_tc.get("name"), list(cand_tc.get("classification_choices") or {}), gran)
    scored = set(scored)
    missed, extra = intended - scored, scored - intended
    union = intended | scored
    ok = union and len(missed) / len(union) <= a.tolerance and len(extra) / len(union) <= a.tolerance
    print(f"- The rule admits {len(intended)}{'+' if trunc else ''} {gran.lower()}(s), reading each clause across the "
          f"unit's spans; the candidate scored {len(scored)}{'+' if t2 else ''}")
    print(f"- Both: {len(intended & scored)}; rule only (missed): {len(missed)}; candidate only (extra): {len(extra)}")
    for title, us in (("Missed", missed), ("Extra", extra)):
        if us:
            print(f"  - {title}, first 5: " + ", ".join(sorted(map(str, us))[:5]))
    print(f"\n**Admission {'MATCHES' if ok else 'DOES NOT MATCH'} the rule** (tolerance {a.tolerance:.0%} each way).")
    if not ok:
        print("Do not run the historical window. See the skill's 'If the admission check fails' section.")
    if a.write_units:
        write_units(a.write_units, intended, gran, a.root_filter)


def cmd_verify(a):
    ev, tc = evaluator_config(a, a.cand_evaluator)
    cand, trunc = labels_by_unit(a, tc.get("name"), list(tc.get("classification_choices") or {}), granularity(tc))
    print(f"# Backfill results for `{tc.get('name')}`, {a.start_time} → {a.end_time}\n")
    print(f"- Units scored: {len(cand)}{'+' if trunc else ''}")
    for lbl, n in Counter(cand.values()).most_common():
        print(f"  - `{lbl}`: {n}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ax", default="ax")
    sub = p.add_subparsers(dest="cmd", required=True)

    def window(sp, root_required=True):
        sp.add_argument("--space", required=True)
        sp.add_argument("--project", required=True)
        sp.add_argument("--start-time", required=True)
        sp.add_argument("--end-time", required=True)
        sp.add_argument("--slices", type=int, default=8)
        sp.add_argument("--root-filter", required=root_required, help="One span per unit")

    def admission(sp, task_help):
        rule = sp.add_mutually_exclusive_group(required=True)
        rule.add_argument("--admission", help="JSON file with the agreed admission rule: "
                          '{"filters": [{"id": "A", "filter": "..."}], "expression": "A AND B"}')
        rule.add_argument("--task", help=task_help)
        sp.add_argument("--pool", type=int, default=2000, help="Max spans sampled per --broad clause across all slices")
        sp.add_argument("--broad", nargs="*", default=[], help="Clause IDs that match nearly every unit (e.g. A for "
                        "'is a root span'); sampled and re-checked against the other clauses instead of exported in full")
        sp.add_argument("--write-units", help="Write the admitted unit IDs, and task filters that admit exactly them, "
                        "to this JSON file")

    e = sub.add_parser("estimate")
    window(e, root_required=False)
    admission(e, "Copy mode: the production task whose admission to reproduce")
    e.add_argument("--evaluator", help="New-evaluator mode (with --admission): the evaluator that will be scored")
    e.set_defaults(func=cmd_estimate)

    c = sub.add_parser("copy-evaluator")
    c.add_argument("--space", required=True)
    c.add_argument("--source", required=True, help="Production evaluator name or ID")
    c.add_argument("--name", required=True, help="New evaluator name, e.g. <source>-backfill")
    c.add_argument("--template-name", required=True, help="New output column name, e.g. <template_name>_backfill")
    c.add_argument("--execute", action="store_true")
    c.set_defaults(func=cmd_copy)

    cal = sub.add_parser("calibrate")
    window(cal)
    cal.add_argument("--prod-evaluator", required=True, help="The production evaluator the candidate was copied from")
    cal.add_argument("--cand-evaluator", required=True, help="The candidate copy (name or ID)")
    cal.add_argument("--tolerance", type=float, default=0.05)
    cal.set_defaults(func=cmd_calibrate)

    ck = sub.add_parser("check-admission")
    window(ck)
    admission(ck, "A task whose filters the user agreed to use as the rule; only its filters are read")
    ck.add_argument("--cand-evaluator", required=True, help="The evaluator being backfilled (name or ID)")
    ck.add_argument("--tolerance", type=float, default=0.05)
    ck.set_defaults(func=cmd_check_admission)

    v = sub.add_parser("verify")
    window(v)
    v.add_argument("--cand-evaluator", required=True, help="The evaluator that was backfilled (name or ID)")
    v.set_defaults(func=cmd_verify)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
