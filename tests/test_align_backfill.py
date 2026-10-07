"""Behavioral tests for the arize-align-history-backfill script; no live services or ax CLI.

Run: pytest --noconftest -c /dev/null -p no:cacheprovider tests/test_align_backfill.py -q
"""

import argparse
import importlib.util
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arize-align-history-backfill" / "scripts" / "backfill.py"
spec = importlib.util.spec_from_file_location("backfill", SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

START, END = "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"


def args(**kw):
    base = dict(ax="ax", space="S", project="P", start_time=START, end_time=END, slices=2, pool=100,
                broad=[], root_filter=None, tolerance=0.05, repeat_evaluator=None, noise_margin=0.05)
    base.update(kw)
    return argparse.Namespace(**base)


def sess_span(sid, evals=None):
    return {"attributes": {"session.id": sid}, "context": {"trace_id": f"t-{sid}", "span_id": f"sp-{sid}"},
            "evaluations": evals or []}


def tc(template="Grade {conversation}", choices=None, model="gpt-4o", name="my_eval", **llm):
    return {"name": name, "template": template, "data_granularity": "SESSION", "direction": "NONE",
            "classification_choices": choices or {"good": 1, "bad": 0},
            "include_explanations": True, "use_function_calling": False,
            "llm_config": {"model_name": model, **llm}}


# ---------------------------------------------------------------------------
# admission expressions
# ---------------------------------------------------------------------------

SETS = {"A": {1, 2, 3, 4}, "B": {2, 3}, "C": {3}, "ORDERS": {4}}


@pytest.mark.parametrize("expr, want", [
    ("A", {1, 2, 3, 4}),
    ("A AND B", {2, 3}),
    ("B OR ORDERS", {2, 3, 4}),
    ("A AND NOT B", {1, 4}),
    ("A AND (B OR ORDERS) AND NOT C", {2, 4}),
    ("a and (b or orders)", set()),  # clause IDs are case-sensitive; only operators are not
    ("A and not C", {1, 2, 4}),
    ("B OR C AND ORDERS", {2, 3}),  # AND binds tighter than OR
    ("MISSING", set()),
])
def test_eval_expression(expr, want):
    assert backfill.eval_expression(expr, SETS) == want


def test_single_string_inlines_each_clause_in_parentheses():
    clauses = {"A": "parent_id IS NULL", "B": "name = 'search' OR name = 'lookup'"}
    assert backfill.single_string(clauses, "A AND B") == \
        "(parent_id IS NULL) AND (name = 'search' OR name = 'lookup')"


def test_parse_filters_defaults_to_and_of_all_clauses():
    clauses, expr = backfill.parse_filters({"filters": [{"id": "A", "filter": "x"}, {"id": "B", "filter": "y"},
                                                        {"id": "C", "filter": ""}]})
    assert clauses == {"A": "x", "B": "y"} and expr == "A AND B"
    assert backfill.parse_filters(None) == ({}, "")


def test_task_filters_reads_either_stored_form():
    assert backfill.task_filters({"query_filters": {"filters": [{"id": "A", "filter": "x"}], "expression": "A"}}) == \
        ({"A": "x"}, "A")
    assert backfill.task_filters({"query_filter": "y"}) == ({"A": "y"}, "A")
    assert backfill.task_filters({}) == ({}, "")


# ---------------------------------------------------------------------------
# copy checks
# ---------------------------------------------------------------------------

def test_model_params_flattens_additional_properties():
    assert backfill.model_params({"temperature": 0, "additional_properties": {"top_p": 1}}) == \
        {"temperature": 0, "top_p": 1}
    assert backfill.model_params(None) == {}


def test_dropped_temperature_is_reported_not_treated_as_a_different_evaluator():
    src = tc(invocation_parameters={"temperature": 0})
    cand = tc(invocation_parameters={})
    assert backfill.copy_diffs(src, cand) == []
    assert "temperature" in backfill.param_note(src, cand)
    assert backfill.param_note(src, src) is None


def test_template_choices_or_model_differences_are_not_copies():
    assert backfill.copy_diffs(tc(), tc(template="Other")) == ["template"]
    assert backfill.copy_diffs(tc(), tc(choices={"good": 1})) == ["classification_choices"]
    assert backfill.copy_diffs(tc(), tc(model="claude")) == ["model_name"]


def test_calibrate_refuses_an_evaluator_that_is_not_a_copy(monkeypatch):
    configs = {"prod": tc(), "cand": tc(template="Rewritten", name="my_eval_backfill")}
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: ({"name": ref}, configs[ref]))
    with pytest.raises(SystemExit, match="is not a copy of"):
        backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", root_filter="parent_id IS NULL"))


def test_calibrate_compares_admission_and_labels(monkeypatch, capsys):
    configs = {"prod": tc(), "cand": tc(name="my_eval_backfill")}
    labels = {"my_eval": {f"s{i}": "good" for i in range(20)},
              "my_eval_backfill": {**{f"s{i}": "good" for i in range(19)}, "s0": "bad", "s99": "good"}}
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: ({"name": ref}, configs[ref]))
    monkeypatch.setattr(backfill, "labels_by_unit", lambda a, col, lbls, gran, require=True, explanations=None: (labels[col], False))
    backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", root_filter="parent_id IS NULL"))
    out = capsys.readouterr().out
    assert "Both: 19; production only: 1; candidate only: 1" in out
    assert "Label agreement where both scored: 18/19, κ = " in out
    assert "Noise floor not measured" in out
    assert "**Admission MATCHES**" in out
    labels["my_eval_backfill"] = {f"s{i}": "good" for i in range(10)}
    backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", root_filter="parent_id IS NULL"))
    assert "DOES NOT MATCH" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# exports
# ---------------------------------------------------------------------------

def test_export_all_bisects_slices_that_hit_the_page_cap(monkeypatch):
    """Any window longer than 3 hours returns a full page; shorter windows return 10 spans."""
    windows = []

    def fake_page(a, filt, lo, hi, limit):
        windows.append(hi - lo)
        n = backfill.PAGE if hi - lo > timedelta(hours=3) else 10
        return [sess_span(f"{lo.isoformat()}-{i}") for i in range(n)], False

    monkeypatch.setattr(backfill, "export_page", fake_page)
    spans, trunc = backfill.export_all(args(), "x", START, END)
    assert not trunc
    assert all(len(s) for s in spans) and len(spans) == 10 * 8  # 24h in 2 slices, each halved to 3h pieces
    assert max(w for w in windows) == timedelta(hours=12)


def test_export_all_marks_truncation_at_the_minimum_slice(monkeypatch):
    monkeypatch.setattr(backfill, "export_page", lambda a, f, lo, hi, limit: ([sess_span("x")] * backfill.PAGE, False))
    _, trunc = backfill.export_all(args(), "x", START, END, min_span=timedelta(hours=6))
    assert trunc


def test_export_all_exits_only_when_every_slice_lacks_the_column(monkeypatch):
    monkeypatch.setattr(backfill, "export_page", lambda a, f, lo, hi, limit: ([], True))
    with pytest.raises(SystemExit, match="No part of the window"):
        backfill.export_all(args(), "x", START, END)
    assert backfill.export_all(args(), "x", START, END, require=False) == ([], False)


def test_admission_recheck_splits_id_batches_that_hit_the_cap(monkeypatch):
    """Clause A (broad) is sampled and misses s1, s2; each has 300 matching spans, so a 2-ID re-check hits the cap."""
    calls = []

    def fake_run_ax(ax, argv, allow_empty=False, retries=5):
        filt = argv[argv.index("--filter") + 1]
        if "IN (" in filt:
            ids = re.findall(r"'([^']+)'", filt.split("IN (")[1])
            calls.append(ids)
            return [sess_span(s) for s in ids for _ in range(300)]
        if filt == "root":
            return [sess_span("s0")] * 50  # a full sample page: truncated
        return [sess_span(s) for s in ("s0", "s1", "s2")]

    monkeypatch.setattr(backfill, "run_ax", fake_run_ax)
    a = args(broad=["A"])
    admitted, trunc = backfill.admitted_units(a, {"A": "root", "B": "tool"}, "A AND B", "SESSION", quiet=True)
    assert admitted == {"s0", "s1", "s2"}
    assert not trunc
    assert calls == [["s1", "s2"], ["s1"], ["s2"]]


def test_labels_by_unit_parenthesizes_the_root_filter(monkeypatch):
    seen = []

    def fake_export_all(a, filt, start, end, require=True):
        seen.append(filt)
        return [sess_span("s1", [{"name": "my_eval", "label": "good"}, {"name": "other", "label": "bad"}]),
                sess_span("s2", [{"name": "my_eval", "label": None}])], False

    monkeypatch.setattr(backfill, "export_all", fake_export_all)
    out, _ = backfill.labels_by_unit(args(root_filter="a = 1 OR b = 2"), "my_eval", ["good", "bad"], "SESSION")
    assert out == {"s1": "good"}
    assert seen == ["(a = 1 OR b = 2) AND session_eval.my_eval.label IN ('good', 'bad')"]


def test_write_units_batches_ids_into_task_filters(tmp_path, capsys):
    path = tmp_path / "units.json"
    backfill.write_units(str(path), {f"s{i:03d}" for i in range(250)}, "SESSION", "parent_id IS NULL")
    data = json.loads(path.read_text())
    assert len(data["units"]) == 250 and len(data["query_filters"]) == 3
    assert data["query_filters"][0].startswith("(parent_id IS NULL) AND attributes.session.id IN ('s000', ")
    assert data["query_filters"][2].count("'") == 2 * 50


def test_slices_split_the_window_evenly():
    got = backfill.slices(args(slices=4), START, END)
    assert len(got) == 4 and got[0][0] == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert all(hi - lo == timedelta(hours=6) for lo, hi in got)


def test_run_ax_retries_429_then_maps_missing_column(monkeypatch):
    replies = [subprocess.CompletedProcess([], 1, "", "429 Too Many Requests"),
               subprocess.CompletedProcess([], 1, "", 'column "session_eval.x.label" does not exist')]
    monkeypatch.setattr(backfill.subprocess, "run", lambda cmd, **_: replies.pop(0))
    monkeypatch.setattr(backfill.time, "sleep", lambda _: None)
    with pytest.raises(backfill.ColumnMissing):
        backfill.run_ax("ax", ["spans", "export"])


def test_run_ax_treats_no_spans_as_empty_only_when_allowed(monkeypatch):
    monkeypatch.setattr(backfill.subprocess, "run",
                        lambda cmd, **_: subprocess.CompletedProcess([], 1, "", "No spans found"))
    assert backfill.run_ax("ax", ["spans", "export"], allow_empty=True) == []
    with pytest.raises(SystemExit):
        backfill.run_ax("ax", ["spans", "export"])


# ---------------------------------------------------------------------------
# noise floor, turn counts, model pinning
# ---------------------------------------------------------------------------

def fake_labels(monkeypatch, labels, expl=None):
    def fake(a, col, lbls, gran, require=True, explanations=None):
        if explanations is not None:
            explanations.update((expl or {}).get(col, {}))
        return labels[col], False
    monkeypatch.setattr(backfill, "labels_by_unit", fake)


def test_calibrate_flags_a_gap_beyond_the_noise_floor(monkeypatch, capsys):
    configs = {"prod": tc(), "cand": tc(name="c"), "rep": tc(name="r")}
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: ({"name": ref}, configs[ref]))
    units = [f"s{i}" for i in range(20)]
    labels = {"my_eval": {u: "good" for u in units},
              "c": {u: ("bad" if i < 6 else "good") for i, u in enumerate(units)},
              "r": {u: ("bad" if i < 6 else "good") for i, u in enumerate(units)}}
    fake_labels(monkeypatch, labels)
    backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", repeat_evaluator="rep"))
    out = capsys.readouterr().out
    assert "Noise floor (candidate vs repeat copy `r`): 20/20" in out
    assert "30% below the noise floor" in out
    labels["r"] = {u: ("bad" if i < 5 else "good") for i, u in enumerate(units)}
    labels["c"] = {u: ("bad" if i < 1 else "good") for i, u in enumerate(units)}
    backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", repeat_evaluator="rep"))
    assert "within run-to-run noise" in capsys.readouterr().out


def test_calibrate_refuses_a_repeat_that_is_not_a_copy(monkeypatch):
    configs = {"prod": tc(), "cand": tc(name="c"), "rep": tc(template="Other", name="r")}
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: ({"name": ref}, configs[ref]))
    fake_labels(monkeypatch, {"my_eval": {}, "c": {}, "r": {}})
    with pytest.raises(SystemExit, match="noise floor needs two identical copies"):
        backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand", repeat_evaluator="rep"))


def test_disagreements_with_different_turn_counts_are_set_aside(monkeypatch, capsys):
    configs = {"prod": tc(), "cand": tc(name="c")}
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: ({"name": ref}, configs[ref]))
    labels = {"my_eval": {"s1": "bad", "s2": "bad", "s3": "good"}, "c": {"s1": "good", "s2": "good", "s3": "good"}}
    expl = {"my_eval": {"s1": "LAST_TURN_CHECK: Turn 2", "s2": "LAST_TURN_CHECK: Turn 5"},
            "c": {"s1": "LAST_TURN_CHECK: Turn 5", "s2": "LAST_TURN_CHECK: Turn 5"}}
    fake_labels(monkeypatch, labels, expl)
    backfill.cmd_calibrate(args(prod_evaluator="prod", cand_evaluator="cand"))
    out = capsys.readouterr().out
    assert "Label agreement where both scored: 1/3" in out
    assert "1 disagreement(s) saw different turn counts" in out and "Excluding them: 1/2" in out


@pytest.mark.parametrize("model, alias", [
    ("gpt-4o", True), ("claude-sonnet-4-5", True), ("gpt-4o-2024-08-06", False),
    ("claude-3-5-sonnet-20241022", False), ("gemini-1.5-pro-002", False), (None, False),
])
def test_alias_detection(model, alias):
    assert backfill.looks_like_alias(model) is alias


def test_copy_evaluator_writes_a_manifest(monkeypatch, tmp_path, capsys):
    src = tc(invocation_parameters={"temperature": 0}, ai_integration_id="int-1")
    src["use_structured_output"] = True
    got = tc(name="my_eval_backfill", invocation_parameters={})
    monkeypatch.setattr(backfill, "evaluator_config", lambda a, ref: (
        ({"name": "prod", "id": "ev-1", "version": {"id": "v-1"}}, src) if ref == "prod" else ({"id": ref}, got)))
    monkeypatch.setattr(backfill, "run_ax", lambda ax, argv, **kw: {"id": "ev-2", "name": "prod-backfill"})
    path = tmp_path / "m.json"
    backfill.cmd_copy(argparse.Namespace(ax="ax", space="S", source="prod", name="prod-backfill",
                                         template_name="my_eval_backfill", execute=True, manifest=str(path)))
    m = json.loads(path.read_text())
    assert m["model_name"] == "gpt-4o" and m["model_is_alias"]
    assert m["use_structured_output"] == {"source": True, "candidate": None}
    assert m["candidate"]["evaluator_id"] == "ev-2" and len(m["template_sha256"]) == 64
    assert "temperature" in m["parameter_note"]
    assert "looks like an alias" in capsys.readouterr().out
