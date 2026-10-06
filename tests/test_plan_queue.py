"""Behavioral tests for the arize-align-queue-builder planner; no live services or ax CLI.

Run: pytest --noconftest -c /dev/null -p no:cacheprovider tests/test_plan_queue.py -q
"""

import importlib.util
import json
import random
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arize-align-queue-builder" / "scripts" / "plan_queue.py"
spec = importlib.util.spec_from_file_location("plan_queue", SCRIPT)
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = START + timedelta(days=28)
ROOT_FILTER = "parent_id IS NULL"


def span(i, label, t, session=None, name="ROUTER-CHAT", compare=None, probe=None):
    evals = [{"name": "my_eval", "label": label}]
    if compare:
        evals.append({"name": "my_eval_anthropic", "label": compare})
    if probe:
        evals.append({"name": "v1_eval", "label": probe})
    return {"name": name, "start_time": t.isoformat(), "attributes": {"session.id": session or f"s-{label}-{i}"},
            "context": {"trace_id": f"t-{label}-{i}", "span_id": f"sp-{label}-{i}"}, "evaluations": evals}


class FakeAx:
    """Answers the ax calls plan_queue makes from an in-memory list of spans."""

    def __init__(self, spans, queues=None, missing_before=None):
        self.spans = spans
        self.queues = queues or {}
        self.missing_before = missing_before
        self.filters = []

    def __call__(self, ax, args, allow_empty=False, retries=5):
        if args[:2] == ["evaluators", "get"]:
            return {"id": "ev-1", "name": "My Eval", "version": {"id": "v-1", "template_config": {
                "name": "my_eval", "data_granularity": "SESSION",
                "classification_choices": {"good": 1, "bad": 0, "wrong": 0, "not_applicable": None}}}}
        if args[:2] == ["projects", "get"]:
            return {"id": "proj-1", "name": "prod"}
        if args[:2] == ["annotation-queues", "get"]:
            return {"id": args[2]}
        if args[:2] == ["annotation-queues", "list-records"]:
            return {"records": [{"data": {"attributes.session.id": s}} for s in self.queues.get(args[2], [])],
                    "pagination": {"has_more": False}}
        if args[:2] == ["spans", "export"]:
            filt = args[args.index("--filter") + 1]
            self.filters.append(filt)
            lo = datetime.fromisoformat(args[args.index("--start-time") + 1])
            hi = datetime.fromisoformat(args[args.index("--end-time") + 1])
            if self.missing_before and hi <= self.missing_before:
                raise plan.ColumnMissing("session_eval.my_eval.label")
            label = re.search(r"my_eval\.label = '([^']*)'", filt).group(1)
            limit = int(args[args.index("-l") + 1])
            hits = [s for s in self.spans if lo <= datetime.fromisoformat(s["start_time"]) < hi
                    and s["evaluations"][0]["label"] == label]
            if "v1_eval.label IS NOT NULL" in filt:
                hits = [s for s in hits if any(e["name"] == "v1_eval" for e in s["evaluations"])]
            return sorted(hits, key=lambda s: s["start_time"], reverse=True)[:limit]
        raise AssertionError(f"unexpected ax call {args}")


def run(monkeypatch, tmp_path, fake, *extra):
    monkeypatch.setattr(plan, "run_ax", fake)
    monkeypatch.setattr("sys.argv", ["plan_queue.py", "--space", "S", "--project", "prod", "--evaluator", "My Eval",
                                     "--out-dir", str(tmp_path), "--root-filter", ROOT_FILTER,
                                     "--start-time", START.isoformat(), "--end-time", END.isoformat(), *extra])
    plan.main()
    return json.loads((tmp_path / "plan.json").read_text())


def plentiful(per_label=20, labels=("good", "bad", "wrong", "not_applicable")):
    """per_label spans for each label, spread over the window at distinct times."""
    out = []
    for li, label in enumerate(labels):
        for i in range(per_label):
            t = START + timedelta(hours=i * 30 + li)
            out.append(span(i, label, t, name="ROUTER-CHAT" if i % 2 else "ROUTER-SEARCH"))
    return out


def by_label(p):
    out = {}
    for r in p["records"]:
        out.setdefault(r["sampled_as"], []).append(r)
    return out


# ---------------------------------------------------------------------------
# sizing and balance
# ---------------------------------------------------------------------------

def test_quota_follows_the_sizing_formula(monkeypatch, tmp_path):
    p = run(monkeypatch, tmp_path, FakeAx(plentiful()))
    # 3 decisive labels: ceil(max(3, 10/3) / 0.7) = 5; not_applicable gets --na-count (2)
    assert p["per_label_quota"] == 5
    assert {k: len(v) for k, v in by_label(p).items()} == {"good": 5, "bad": 5, "wrong": 5, "not_applicable": 2}
    assert all(s["shortfall"] == 0 for s in p["summary"])


def test_higher_expected_exclusion_raises_the_quota(monkeypatch, tmp_path):
    p = run(monkeypatch, tmp_path, FakeAx(plentiful()), "--expected-exclusion", "0.7")
    assert p["per_label_quota"] == 12  # ceil(3.34 / 0.3)


def test_shortfall_is_reported_not_filled_from_other_labels(monkeypatch, tmp_path):
    spans = [s for s in plentiful() if s["evaluations"][0]["label"] != "wrong"]
    spans += [span(i, "wrong", START + timedelta(days=i, minutes=7)) for i in range(2)]
    p = run(monkeypatch, tmp_path, FakeAx(spans))
    wrong = next(s for s in p["summary"] if s["label"] == "wrong")
    assert (wrong["picked"], wrong["shortfall"]) == (2, 3)
    assert len(by_label(p)["good"]) == 5
    assert "Not enough candidates for: `wrong` (short 3)" in (tmp_path / "plan.md").read_text()


def test_labels_flag_limits_sampling_for_a_top_up(monkeypatch, tmp_path):
    p = run(monkeypatch, tmp_path, FakeAx(plentiful()), "--labels", "wrong", "--per-label", "4")
    assert {k: len(v) for k, v in by_label(p).items()} == {"wrong": 4}


# ---------------------------------------------------------------------------
# dedupe, exclusions, filters
# ---------------------------------------------------------------------------

def test_one_record_per_session_and_excluded_queues_are_skipped(monkeypatch, tmp_path):
    spans = plentiful()
    # Two spans of one session: only the earlier one may be picked.
    spans.append(span(99, "good", START + timedelta(minutes=1), session="s-good-0"))
    fake = FakeAx(spans, queues={"old-q": ["s-good-1", "s-good-3"]})
    p = run(monkeypatch, tmp_path, fake, "--exclude-queue", "old-q")
    sessions = [r["session_id"] for r in p["records"]]
    assert len(sessions) == len(set(sessions))
    assert not {"s-good-1", "s-good-3"} & set(sessions)
    picked = {r["session_id"]: r for r in p["records"]}
    if "s-good-0" in picked:
        assert picked["s-good-0"]["span_id"] == "sp-good-99"


def test_root_filter_is_parenthesized_before_the_label_filter(monkeypatch, tmp_path):
    fake = FakeAx(plentiful())
    run(monkeypatch, tmp_path, fake, "--root-filter", "name = 'A' OR name = 'B'")
    assert all(f.startswith("(name = 'A' OR name = 'B') AND ") for f in fake.filters)


def test_window_is_drawn_from_every_slice(monkeypatch, tmp_path):
    fake = FakeAx(plentiful())
    run(monkeypatch, tmp_path, fake)
    assert len(fake.filters) == 4 * 4  # 4 labels x 4 slices


def test_periods_without_the_column_are_skipped_and_listed(monkeypatch, tmp_path):
    fake = FakeAx(plentiful(), missing_before=START + timedelta(days=8))
    run(monkeypatch, tmp_path, fake)
    assert "No values for an eval column in: 2026-09-01" in (tmp_path / "plan.md").read_text()


def test_column_missing_everywhere_exits(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="No part of the window has values"):
        run(monkeypatch, tmp_path, FakeAx(plentiful(), missing_before=END + timedelta(days=1)))


# ---------------------------------------------------------------------------
# disagreements and probes
# ---------------------------------------------------------------------------

def test_provider_disagreements_go_first_but_are_capped(monkeypatch, tmp_path):
    spans = []
    for label in ("good", "bad", "wrong", "not_applicable"):
        for i in range(20):
            t = START + timedelta(hours=i * 30) + timedelta(minutes=hash(label) % 50)
            spans.append(span(i, label, t, compare="bad" if label == "good" else label))
    p = run(monkeypatch, tmp_path, FakeAx(spans), "--compare-eval", "my_eval_anthropic")
    good = by_label(p)["good"]
    # All 20 good records disagree, so the cap (40% of 5 = 2) gives way only when nothing else is left.
    assert len(good) == 5 and all(r["disagree"] for r in good)
    spans = [s for s in spans if s["evaluations"][0]["label"] != "good"]
    spans += [span(i, "good", START + timedelta(hours=i * 30, minutes=3), compare="bad" if i < 10 else "good")
              for i in range(20)]
    p = run(monkeypatch, tmp_path, FakeAx(spans), "--compare-eval", "my_eval_anthropic")
    assert sum(r["disagree"] for r in by_label(p)["good"]) == 2


def test_scope_probes_pick_records_the_other_evaluator_graded(monkeypatch, tmp_path):
    spans = plentiful()
    for i, s in enumerate(x for x in spans if x["evaluations"][0]["label"] == "not_applicable"):
        s["evaluations"].append({"name": "v1_eval", "label": ["wrong", "good", "not_applicable"][i % 3]})
    p = run(monkeypatch, tmp_path, FakeAx(spans), "--na-probe-eval", "v1_eval", "--na-probe-count", "4")
    probes = [r for r in p["records"] if "probe" in r["sampled_as"]]
    assert len(probes) == 4
    assert {r["probe_label"] for r in probes} == {"wrong", "good"}
    assert not {r["session_id"] for r in probes} & {r["session_id"] for r in by_label(p)["not_applicable"]}


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------

def test_record_sources_respect_arize_limits(monkeypatch, tmp_path):
    p = run(monkeypatch, tmp_path, FakeAx(plentiful()))
    sources = json.loads((tmp_path / "record_sources.json").read_text())
    assert sum(len(s["span_ids"]) for s in sources) == len(p["records"])
    for s in sources:
        lo = datetime.fromisoformat(s["start_time"].replace("Z", "+00:00"))
        hi = datetime.fromisoformat(s["end_time"].replace("Z", "+00:00"))
        assert hi - lo <= timedelta(days=plan.SOURCE_MAX_DAYS)
    files = sorted(f.name for f in tmp_path.glob("record_sources.*.json"))
    batches = [json.loads((tmp_path / f).read_text()) for f in files]
    assert all(len(b) <= plan.SOURCES_PER_CALL for b in batches)
    assert sum(len(b) for b in batches) == len(sources)
    assert "record_sources.create.json" in files


def test_stale_split_files_from_an_earlier_run_are_removed(monkeypatch, tmp_path):
    (tmp_path / "record_sources.add_9.json").write_text("[]")
    run(monkeypatch, tmp_path, FakeAx(plentiful()))
    assert not (tmp_path / "record_sources.add_9.json").exists()


def test_picks_with_identical_start_times_do_not_crash(monkeypatch, tmp_path):
    t = START + timedelta(days=3)
    spans = [span(i, label, t) for label in ("good", "bad", "wrong", "not_applicable") for i in range(6)]
    p = run(monkeypatch, tmp_path, FakeAx(spans))
    assert len(p["records"]) == 17


def test_config_values_add_not_applicable_and_cannot_judge_once(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, FakeAx(plentiful()))
    assert json.loads((tmp_path / "config_values.json").read_text()) == [
        "good", "bad", "wrong", "not_applicable", "cannot_judge"]


def test_spread_pick_round_robins_across_span_names():
    items = [{"span_name": "A", "i": i} for i in range(6)] + [{"span_name": "B", "i": i} for i in range(2)]
    picked = plan.spread_pick(items, 4, random.Random(0))
    assert sorted(p["span_name"] for p in picked) == ["A", "A", "B", "B"]
    assert len(plan.spread_pick(items, 20, random.Random(0))) == 8


def test_run_ax_maps_missing_column_and_retries_rate_limits(monkeypatch):
    replies = [subprocess.CompletedProcess([], 1, "", "429 Too Many Requests"),
               subprocess.CompletedProcess([], 1, "", 'column "session_eval.x.label" does not exist')]
    monkeypatch.setattr(plan.subprocess, "run", lambda cmd, **_: replies.pop(0))
    monkeypatch.setattr(plan.time, "sleep", lambda _: None)
    with pytest.raises(plan.ColumnMissing):
        plan.run_ax("ax", ["spans", "export"])
