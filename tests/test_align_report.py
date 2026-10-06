"""Behavioral tests for the arize-align-evaluator report script; no live services or ax CLI.

Run: pytest --noconftest -c /dev/null -p no:cacheprovider tests/test_align_report.py -q
"""

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arize-align-evaluator" / "scripts" / "align_report.py"
spec = importlib.util.spec_from_file_location("align_report", SCRIPT)
align = importlib.util.module_from_spec(spec)
spec.loader.exec_module(align)

CONFIG = "quality-gold"
COLUMN = "session_eval.my_eval"
A, B = "ann.a@example.com", "ann.b@example.com"


def evaluator(template="Grade the {conversation}. LAST_TURN_CHECK: Turn N", created_at="2026-01-01T00:00:00Z"):
    return {
        "id": "ev-1", "name": "My Eval",
        "version": {"id": "v-1", "created_at": created_at, "commit_message": "init",
                    "template_config": {"name": "my_eval", "data_granularity": "SESSION", "template": template,
                                        "classification_choices": {"good": 1, "bad": 0, "not_applicable": None}}},
    }


def queue(instructions="Label good when the answer is right, bad otherwise.", configs=None):
    configs = configs or [{"actual_instance": {"name": CONFIG, "values": [
        {"label": "good"}, {"label": "bad"}, {"label": "not_applicable"}, {"label": "cannot_judge"}]}}]
    return {"id": "q-1", "name": "Gold", "instructions": instructions, "annotation_configs": configs,
            "annotators": [{"email": A}, {"email": B}]}


def record(rid, votes, stored=None, explanation="", session=None, config=CONFIG, level="annotations"):
    """A queue record. Each attributed vote also appears once without an annotator, as the API returns it."""
    anns = []
    for who, label in votes.items():
        anns.append({"name": config, "label": label, "annotator": {"email": who}})
        anns.append({"name": config, "label": label})
    return {
        "id": rid, "granularity": "SPAN",
        "data": {"attributes.session.id": session or f"s-{rid}", "context.trace_id": f"t-{rid}",
                 "context.span_id": f"sp-{rid}", "start_time": "1780000000000"},
        level: anns,
        "evaluations": [{"name": COLUMN, "label": stored, "explanation": explanation}] if stored else [],
        "assigned_users": [{"user": {"email": who}, "completion_status": "COMPLETED"} for who in votes],
    }


def build(tmp_path, records, q=None, ev=None, turns=None, **overrides):
    for name, obj in (("queue", q or queue()), ("records", records), ("evaluator", ev or evaluator())):
        (tmp_path / f"{name}.json").write_text(json.dumps(obj))
    if turns is not None:
        (tmp_path / "turns.json").write_text(json.dumps(turns))
    args = dict(dir=str(tmp_path), adjudications=None, eval_column=None, config=None,
                not_applicable=list(align.DEFAULT_NOT_APPLICABLE), unscorable=list(align.DEFAULT_UNSCORABLE))
    args.update(overrides)
    return align.build(argparse.Namespace(**args))


def gates(report):
    return {name: ok for name, ok, _ in report["gates"]}


def usable_records():
    """12 gold records, 6 per class, both annotators agree, evaluator wrong on one per class."""
    recs = []
    for i in range(12):
        human = "good" if i < 6 else "bad"
        stored = ("bad" if human == "good" else "good") if i in (0, 6) else human
        recs.append(record(f"r{i}", {A: human, B: human}, stored=stored))
    return recs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_cohen_kappa_known_values():
    assert align.cohen_kappa([]) is None
    assert align.cohen_kappa([("x", "x"), ("y", "y")]) == 1.0
    # po = 0.5, pe = 0.5 -> chance-level agreement
    assert align.cohen_kappa([("x", "x"), ("x", "y"), ("y", "x"), ("y", "y")]) == 0.0
    # Both annotators always give one label: pe == 1, perfect agreement
    assert align.cohen_kappa([("x", "x")] * 3) == 1.0


def test_last_turn_seen_reads_the_marker_only():
    assert align.last_turn_seen("... LAST_TURN_CHECK: Turn 7") == 7
    assert align.last_turn_seen("last_turn_check -> turn 3") == 3
    assert align.last_turn_seen("Turn 4 was decisive") is None
    assert align.last_turn_seen(None) is None


# ---------------------------------------------------------------------------
# buckets and votes
# ---------------------------------------------------------------------------

def test_records_sort_into_buckets(tmp_path):
    recs = [
        record("gold", {A: "good"}, stored="good"),
        record("na", {A: "not_applicable"}, stored="good"),
        record("unscorable", {A: "cannot_judge"}),
        record("off", {A: "meh"}),
        record("disputed", {A: "good", B: "bad"}),
        record("unlabeled", {}),
    ]
    r = build(tmp_path, recs)
    assert {row["record_id"]: row["bucket"] for row in r["rows"]} == {
        "gold": "gold", "na": "not_applicable", "unscorable": "unscorable",
        "off": "off_rubric", "disputed": "disputed", "unlabeled": "unlabeled"}
    assert r["applicability"] == {"good": 1}


def test_duplicate_unattributed_copy_is_not_a_second_vote(tmp_path):
    r = build(tmp_path, [record("r1", {A: "good"}, stored="good")])
    row = r["rows"][0]
    assert row["votes"] == {A: "good"}
    assert row["status"] == "single"
    assert r["multi"] == []


def test_unattributed_only_labels_count_as_one_vote(tmp_path):
    rec = record("r1", {}, stored="good")
    rec["annotations"] = [{"name": CONFIG, "label": "good"}]
    r = build(tmp_path, [rec])
    assert r["rows"][0]["votes"] == {"(unattributed)": "good"}
    assert r["rows"][0]["bucket"] == "gold"


def test_labels_from_other_configs_are_ignored(tmp_path):
    rec = record("r1", {A: "good"}, stored="good")
    rec["annotations"].append({"name": "other-queue", "label": "bad", "annotator": {"email": B}})
    r = build(tmp_path, [rec])
    assert r["rows"][0]["votes"] == {A: "good"}
    assert any("other-queue" in f for f in r["fit"])


def test_session_level_votes_are_read(tmp_path):
    r = build(tmp_path, [record("r1", {A: "bad"}, stored="bad", level="session_annotations")])
    assert r["rows"][0]["bucket"] == "gold"
    assert any("session_annotations" in f for f in r["fit"])


def test_same_annotator_conflicting_across_levels_is_unlabeled(tmp_path):
    rec = record("r1", {A: "good"}, stored="good")
    rec["session_annotations"] = [{"name": CONFIG, "label": "bad", "annotator": {"email": A}}]
    r = build(tmp_path, [rec])
    assert r["rows"][0]["bucket"] == "unlabeled"
    assert any("different labels at different levels" in f for f in r["fit"])


def test_adjudication_resolves_a_dispute_and_keeps_original_votes(tmp_path):
    adj = tmp_path / "adj.json"
    adj.write_text(json.dumps({"r1": "bad"}))
    r = build(tmp_path, [record("r1", {A: "good", B: "bad"}, stored="bad")], adjudications=str(adj))
    row = r["rows"][0]
    assert (row["consensus"], row["status"], row["bucket"]) == ("bad", "adjudicated", "gold")
    assert row["votes"] == {A: "good", B: "bad"}
    assert r["disputed"] == []


def test_multiple_configs_need_config_flag(tmp_path):
    configs = [{"name": CONFIG, "values": []}, {"name": "other", "values": []}]
    with pytest.raises(SystemExit):
        build(tmp_path, [], q=queue(configs=configs))
    r = build(tmp_path, [], q=queue(configs=configs), config=CONFIG)
    assert r["config_name"] == CONFIG


# ---------------------------------------------------------------------------
# gates, verdict, agreement
# ---------------------------------------------------------------------------

def test_usable_queue_passes_every_gate(tmp_path):
    r = build(tmp_path, usable_records())
    assert all(gates(r).values()), r["gates"]
    assert r["verdict"] == "USABLE"
    assert r["agree"] == 10 and len(r["gold_scored"]) == 12
    assert r["confusion"][("good", "bad")] == 1 and r["confusion"][("bad", "good")] == 1
    assert r["per_label"]["good"] == {"precision": 5 / 6, "recall": 5 / 6, "support": 6}
    assert [p["kappa"] for p in r["iaa"]] == [1.0]


def test_single_class_queue_is_not_usable(tmp_path):
    recs = [record(f"r{i}", {A: "good"}, stored="good") for i in range(12)]
    r = build(tmp_path, recs)
    assert not gates(r)[f"≥2 gold classes with ≥{align.MIN_PER_CLASS} each"]
    assert r["verdict"] == "NOT USABLE"


def test_small_two_class_queue_is_exploratory(tmp_path):
    recs = [record(f"r{i}", {A: "good" if i < 3 else "bad"}, stored="good") for i in range(6)]
    r = build(tmp_path, recs)
    assert r["verdict"] == "EXPLORATORY"


def test_too_many_exclusions_fails_the_excluded_rate_gate(tmp_path):
    recs = usable_records() + [record(f"na{i}", {A: "not_applicable"}) for i in range(6)]
    r = build(tmp_path, recs)
    assert not gates(r)["Excluded rate (not applicable + unscorable + off-rubric)"]
    assert r["verdict"] == "EXPLORATORY"


def test_low_annotator_agreement_fails_the_kappa_gate(tmp_path):
    recs = usable_records()
    for rec in recs[:5]:
        # B flips every vote on 5 records; adjudicate them so only κ fails.
        for ann in rec["annotations"]:
            if (ann.get("annotator") or {}).get("email") == B:
                ann["label"] = "bad" if ann["label"] == "good" else "good"
    adj = tmp_path / "adj.json"
    adj.write_text(json.dumps({rec["id"]: "good" for rec in recs[:5]}))
    r = build(tmp_path, recs, adjudications=str(adj))
    g = gates(r)
    assert not g[f"Annotator agreement κ ≥ {align.MIN_KAPPA} (when records have 2+ votes)"]
    assert g["No unresolved disputes"]


def test_duplicate_sessions_fail_the_join_gate(tmp_path):
    recs = usable_records()
    recs[1]["data"]["attributes.session.id"] = recs[0]["data"]["attributes.session.id"]
    r = build(tmp_path, recs)
    assert not gates(r)["Join to evaluator unit"]
    assert len(r["dup_sessions"]) == 1


def test_missing_stored_output_fails_the_coverage_gate(tmp_path):
    recs = usable_records()
    for rec in recs[:3]:
        rec["evaluations"] = []
    r = build(tmp_path, recs)
    assert not gates(r)["Stored evaluator output on gold records"]


# ---------------------------------------------------------------------------
# fit warnings and staleness
# ---------------------------------------------------------------------------

def test_instructions_that_never_mention_labels_are_flagged(tmp_path):
    r = build(tmp_path, usable_records(), q=queue(instructions="Please review each session."))
    assert any("never mention 2 of 2" in f for f in r["fit"])


def test_label_mentions_match_spaces_underscores_and_case(tmp_path):
    ev = evaluator()
    ev["version"]["template_config"]["classification_choices"] = {"target_retrieved": 1, "wrong_target": 0}
    r = build(tmp_path, [], ev=ev, q=queue(instructions="Use Target Retrieved or wrong_target."))
    assert not any("never mention" in f for f in r["fit"])
    r = build(tmp_path, [], ev=ev, q=queue(instructions="Use target-retrieved-ish or wrong_targets."))
    assert any("never mention 2 of 2" in f for f in r["fit"])


def test_turn_data_template_is_flagged(tmp_path):
    r = build(tmp_path, [], ev=evaluator(template="Grade {turn_data}"))
    assert any("{turn_data}" in f for f in r["fit"])


def test_result_seeing_fewer_turns_than_the_session_is_stale(tmp_path):
    recs = [record("r1", {A: "good"}, stored="bad", explanation="LAST_TURN_CHECK: Turn 2", session="s1"),
            record("r2", {A: "good"}, stored="good", explanation="LAST_TURN_CHECK: Turn 5", session="s2"),
            record("r3", {A: "good"}, stored="good", explanation="no marker here", session="s3")]
    r = build(tmp_path, recs, turns={"s1": 5, "s2": 5, "s3": 5})
    assert [row["record_id"] for row in r["stale"]] == ["r1"]
    assert "(stale)" in align.render(r)


def test_records_older_than_the_version_are_reported(tmp_path):
    r = build(tmp_path, usable_records(), ev=evaluator(created_at="2030-01-01T00:00:00Z"))
    assert len(r["older"]) == 12
    assert "started before the current version" in align.render(r)


def test_report_writes_json_summary(tmp_path, capsys):
    build(tmp_path, usable_records())
    out = tmp_path / "report.json"
    align.cmd_report(argparse.Namespace(dir=str(tmp_path), adjudications=None, eval_column=None, config=None,
                                        not_applicable=["not_applicable"], unscorable=["cannot_judge", "unclear"],
                                        json_out=str(out)))
    assert "**Verdict: USABLE.**" in capsys.readouterr().out
    slim = json.loads(out.read_text())
    assert slim["summary"]["gold"] == 12 and slim["summary"]["disagreements"] == 2
    assert len(slim["records"]) == 12


# ---------------------------------------------------------------------------
# ax calls
# ---------------------------------------------------------------------------

def fake_proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_run_ax_retries_rate_limits(monkeypatch):
    replies = [fake_proc(1, stderr="429 Too Many Requests"), fake_proc(0, stdout='{"id": "q"}')]
    calls = []
    monkeypatch.setattr(align.subprocess, "run", lambda cmd, **_: calls.append(cmd) or replies.pop(0))
    monkeypatch.setattr(align.time, "sleep", lambda _: None)
    assert align.run_ax("ax", ["annotation-queues", "get", "q"]) == {"id": "q"}
    assert len(calls) == 2 and calls[0][-2:] == ["-o", "json"]


def test_run_ax_empty_stdout_is_only_valid_for_spans_export(monkeypatch):
    monkeypatch.setattr(align.subprocess, "run", lambda cmd, **_: fake_proc(0, stdout=""))
    assert align.run_ax("ax", ["spans", "export"], json_flag=False) == []
    with pytest.raises(SystemExit):
        align.run_ax("ax", ["evaluators", "get", "e"])


def test_count_turns_splits_batches_that_hit_the_page_cap(monkeypatch):
    """Each session has 300 matching root spans, so any batch of 2+ sessions hits the 500 cap."""
    calls = []

    def fake_run_ax(ax, args, json_flag=True):
        filt = args[args.index("--filter") + 1]
        ids = [s.strip(" '") for s in filt.split("IN (")[1].rstrip(")").split(",")]
        calls.append(ids)
        return [{"attributes": {"session.id": sid}} for sid in ids for _ in range(300)]

    monkeypatch.setattr(align, "run_ax", fake_run_ax)
    records = [{"data": {"attributes.session.id": f"s{i}", "start_time": str(1780000000000 + i)}} for i in range(3)]
    a = argparse.Namespace(project="P", space="S", ax="ax", count_turns="parent_id IS NULL")
    assert align.count_turns(a, records) == {"s0": 300, "s1": 300, "s2": 300}
    assert calls == [["s0", "s1", "s2"], ["s0"], ["s1", "s2"], ["s1"], ["s2"]]
