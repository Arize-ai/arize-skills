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
    args = dict(dir=str(tmp_path), adjudications=None, eval_column=None, config=None, plan=None, test_from=None,
                rubric_version=None, admission_filter=None, fail_label=None, definitions_agree=False, read_sessions=None, rescored_at=None,
                not_applicable=list(align.DEFAULT_NOT_APPLICABLE), unscorable=list(align.DEFAULT_UNSCORABLE))
    args.update(overrides)
    return align.build(argparse.Namespace(**args))


def warned(report):
    return {x["check"] for x in report["warnings"]}


def blocked(report):
    return {b["condition"] for b in report["blockers"]}


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


def test_session_records_count_only_session_level_labels(tmp_path):
    # A turn-level label left from an older span record of the same session must not override or cancel the
    # session label: the session record shows the whole conversation the evaluator graded.
    rec = record("r1", {A: "not_applicable"}, stored="good")
    rec["granularity"] = "SESSION"
    rec["session_annotations"] = [{"name": CONFIG, "label": "good", "annotator": {"email": A}}]
    r = build(tmp_path, [rec])
    assert r["rows"][0]["votes"] == {A: "good"} and r["rows"][0]["bucket"] == "gold"
    assert any("only `session_annotations` were counted" in f for f in r["fit"])
    assert not any("different labels at different levels" in f for f in r["fit"])


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
# status, blockers, warnings, agreement
# ---------------------------------------------------------------------------

NO_MARKER = "Grade the {conversation}."


def test_small_queue_is_provisional_on_size_alone(tmp_path):
    r = build(tmp_path, usable_records(), ev=evaluator(template=NO_MARKER))
    # 6 per class is far below 30 per label in each of dev and test; nothing else blocks.
    assert r["status"] == "provisional"
    assert [b["condition"].split(":")[0] for b in r["blockers"]] == ["Size"]
    # The test records are span records for a session judge: a warning, not a blocker.
    assert warned(r) == {"Session judge labeled on session records"}
    assert r["agree"] == 10 and len(r["gold_scored"]) == 12
    assert r["confusion"][("good", "bad")] == 1 and r["confusion"][("bad", "good")] == 1
    assert r["per_label"]["good"] == {"precision": 5 / 6, "recall": 5 / 6, "support": 6, "tp": 5, "predicted": 6}
    assert [p["kappa"] for p in r["iaa"]] == [1.0]


def test_measured_needs_30_per_label_in_both_dev_and_test(tmp_path):
    # 75 per label: 11 train, 32 dev, 32 test.
    recs = [record(f"r{i}", {A: "good" if i < 75 else "bad"}, stored="good" if i < 75 else "bad") for i in range(150)]
    r = build(tmp_path, recs, ev=evaluator(template=NO_MARKER))
    assert r["status"] == "measured" and r["blockers"] == []
    # 30 per label in all leaves about 13 per label in test.
    recs = [record(f"r{i}", {A: "good" if i < 30 else "bad"}, stored="good" if i < 30 else "bad") for i in range(60)]
    assert build(tmp_path, recs)["status"] == "provisional"


def test_no_verdict_tiers_anywhere(tmp_path, capsys):
    r = build(tmp_path, usable_records())
    out = align.render(r)
    for tier in ("VALIDATED", "DIRECTIONAL", "EXPLORATORY", "NOT USABLE", "Verdict"):
        assert tier not in out
    assert "verdict" not in r and "gates" not in r
    assert "## Status: provisional" in out and "Allowed next actions" in out


def test_single_class_queue_warns_and_stays_provisional(tmp_path):
    recs = [record(f"r{i}", {A: "good"}, stored="good") for i in range(12)]
    r = build(tmp_path, recs)
    assert r["status"] == "provisional"
    assert f"At least {align.MIN_PER_CLASS} gold records per label" in warned(r)


def test_warnings_carry_their_basis_and_never_change_the_status(tmp_path):
    big = [record(f"r{i}", {A: "good" if i < 75 else "bad"}, stored="good" if i < 75 else "bad") for i in range(150)]
    recs = big + [record(f"na{i}", {A: "not_applicable"}) for i in range(80)]
    r = build(tmp_path, recs, ev=evaluator(template=NO_MARKER))
    assert r["status"] == "measured"
    w = {x["check"]: x for x in r["warnings"]}
    assert w[f"Excluded share ≤ {align.MAX_EXCLUDED_RATE:.0%}"]["basis"].startswith("Arize heuristic")
    assert "Two or more annotators on some records" in w  # single annotator


def test_low_annotator_agreement_warns(tmp_path):
    recs = usable_records()
    for rec in recs[:5]:
        # B flips every vote on 5 records; adjudicate them so only κ is low.
        for ann in rec["annotations"]:
            if (ann.get("annotator") or {}).get("email") == B:
                ann["label"] = "bad" if ann["label"] == "good" else "good"
    adj = tmp_path / "adj.json"
    adj.write_text(json.dumps({rec["id"]: "good" for rec in recs[:5]}))
    r = build(tmp_path, recs, adjudications=str(adj))
    assert any(c.startswith("Annotator agreement") for c in warned(r))
    assert "No open disputes" not in warned(r)


def test_duplicate_sessions_block(tmp_path):
    recs = usable_records()
    recs[1]["data"]["attributes.session.id"] = recs[0]["data"]["attributes.session.id"]
    r = build(tmp_path, recs)
    assert "Each record is one session" in blocked(r)
    assert len(r["dup_sessions"]) == 1


def test_missing_stored_output_blocks(tmp_path):
    recs = usable_records()
    for rec in recs[:3]:
        rec["evaluations"] = []
    r = build(tmp_path, recs)
    assert "Every gold record carries a result from the current judge version" in blocked(r)


def test_stale_results_block_until_rescored(tmp_path):
    recs = usable_records()
    recs[0]["evaluations"][0]["explanation"] = "LAST_TURN_CHECK: Turn 2"
    r = build(tmp_path, recs, turns={recs[0]["data"]["attributes.session.id"]: 5})
    assert "No stale results on gold records" in blocked(r)


def test_unchecked_staleness_blocks_a_session_judge(tmp_path):
    r = build(tmp_path, usable_records())  # the template has the marker, but no turns were counted
    assert any("not checked" in b["value"] for b in r["blockers"] if b["condition"] == "No stale results on gold records")


def test_definition_diff_flags_a_criterion_question(tmp_path):
    q = queue(instructions="Labels:\n- good: the answer is right.\n- bad: the answer is wrong.\n"
                           "Evidence: a filter block or a validate_filter call.")
    ev = evaluator(template="Grade {conversation}. LAST_TURN_CHECK: Turn N\n- good: the answer is right and reached "
                            "the user; validate_filter probes alone do not count.\n- bad: the answer is wrong.")
    r = build(tmp_path, usable_records(), q=q, ev=ev)
    assert r["definitions"]["flagged"] == ["good"]
    assert "validate_filter" in r["definitions"]["shared_terms"]
    assert "Queue and template define the labels the same way" in blocked(r)
    assert "A criterion question is open" in align.render(r)
    decided = build(tmp_path, usable_records(), q=q, ev=ev, definitions_agree=True)
    assert "Queue and template define the labels the same way" not in blocked(decided)


def test_matching_definitions_are_not_flagged(tmp_path):
    defs = "\n- good: the answer is right.\n- bad: the answer is wrong."
    r = build(tmp_path, usable_records(), q=queue(instructions="Labels:" + defs),
              ev=evaluator(template="Grade {conversation}. LAST_TURN_CHECK: Turn N" + defs))
    assert r["definitions"]["flagged"] == []


def test_leniency_uses_the_named_failing_labels(tmp_path):
    r = build(tmp_path, usable_records(), fail_label=["bad"])
    # 6 human `bad`; the judge said `good` on one.
    assert r["leniency"] == (1, 6)
    out = align.render(r)
    assert "Leniency" in out and out.index("`bad` (failing)") < out.index("`good`: ")
    assert build(tmp_path, usable_records())["leniency"] is None


def test_test_split_is_reported_first(tmp_path):
    out = align.render(build(tmp_path, usable_records()))
    assert out.index("## Test split") < out.index("## All scored gold records")
    assert "directional" in out[out.index("## Test split"):out.index("## All scored gold records")]


def test_no_plan_says_nothing_is_a_production_rate(tmp_path):
    out = align.render(build(tmp_path, usable_records()))
    assert "nothing here is a production rate" in out


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
                                        json_out=str(out), plan=None, test_from=None, rubric_version=None,
                                        admission_filter=None, fail_label=None, definitions_agree=False,
                                        read_sessions=None, rescored_at=None))
    assert "## Status: provisional" in capsys.readouterr().out
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


# ---------------------------------------------------------------------------
# research-backed statistics
# ---------------------------------------------------------------------------

def test_wilson_interval_matches_published_values():
    lo, hi = align.wilson(9, 10)
    assert (round(lo, 3), round(hi, 3)) == (0.596, 0.982)
    lo, hi = align.wilson(45, 50)
    assert (round(lo, 2), round(hi, 2)) == (0.79, 0.96)
    assert align.wilson(0, 0) is None
    assert align.pct_ci(9, 10) == "9/10 (90%, 95% CI 60–98%)"


def test_skewed_pair_fails_kappa_but_passes_on_ac1():
    """20 shared records, 18 agree, 90% of votes one label: κ is low (the kappa paradox), AC1 is high."""
    pairs = [("good", "good")] * 17 + [("bad", "bad")] + [("good", "bad"), ("bad", "good")]
    assert round(align.cohen_kappa(pairs), 2) == 0.44
    assert round(align.gwet_ac1(pairs), 2) == 0.88
    assert round(align.pabak(pairs), 2) == 0.80


def test_kappa_gate_accepts_ac1_only_when_one_label_dominates(tmp_path):
    recs = [record(f"r{i}", {A: "good", B: "good"}, stored="good") for i in range(17)]
    recs += [record("rb", {A: "bad", B: "bad"}, stored="bad")]
    recs += [record("d1", {A: "good", B: "bad"}), record("d2", {A: "bad", B: "good"})]
    adj = tmp_path / "adj.json"
    adj.write_text(json.dumps({"d1": "good", "d2": "bad"}))
    r = build(tmp_path, recs, adjudications=str(adj))
    pair = r["iaa"][0]
    assert pair["skewed"] and pair["kappa"] < align.MIN_KAPPA <= pair["ac1"]
    assert not any(c.startswith("Annotator agreement") for c in warned(r))
    out = align.render(r)
    assert "kappa paradox" in out and "AC1 = 0.88" in out


def test_recall_per_human_label_and_balanced_accuracy(tmp_path):
    r = build(tmp_path, usable_records())
    assert r["balanced"] == 5 / 6
    out = align.render(r)
    assert "- `good`: 5/6 (83%, 95% CI 44–97%)" in out
    assert "Balanced accuracy (mean of the above): 83%" in out


def test_split_is_stable_per_label_and_written_to_json(tmp_path):
    recs = [record(f"r{i}", {A: "good" if i < 20 else "bad"}, stored="good") for i in range(40)]
    first = {row["record_id"]: row["split"] for row in build(tmp_path, recs)["rows"]}
    again = {row["record_id"]: row["split"] for row in build(tmp_path, list(reversed(recs)))["rows"]}
    assert first == again
    r = build(tmp_path, recs)
    # 20 per label: 3 train (15%), 8 dev (42.5%, rounded), 9 test
    assert [r["split_counts"][s]["good"] for s in ("train", "dev", "test")] == [3, 8, 9]


def test_weighted_estimates_undo_oversampling(tmp_path):
    """Production: 90 units stored good, 10 stored bad. The queue sampled 5 of each.
    Judge right on all stored-good records; wrong on 4 of 5 stored-bad (humans said good)."""
    recs, plan_records = [], []
    for i in range(5):
        recs.append(record(f"g{i}", {A: "good"}, stored="good"))
        plan_records.append({"span_id": f"sp-g{i}", "stratum": "good"})
    for i in range(5):
        recs.append(record(f"b{i}", {A: "good" if i < 4 else "bad"}, stored="bad"))
        plan_records.append({"span_id": f"sp-b{i}", "stratum": "bad"})
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"strata": [{"stratum": "good", "stream": "targeted", "population": 90},
                                           {"stratum": "bad", "stream": "targeted", "population": 10}],
                                "records": plan_records}))
    r = build(tmp_path, recs, plan=str(plan))
    wt = r["weighted"]
    assert r["agree"] == 6  # raw: 6/10 on the queue
    assert wt["agreement"] == pytest.approx(0.9 * 1 + 0.1 * 0.2)  # production-weighted: 92%
    assert wt["covered_share"] == 1.0 and wt["uncovered"] == []
    assert "secondary** estimate" in align.render(r)


def test_a_random_stream_queue_is_a_measurement_and_is_not_reweighted(tmp_path):
    recs = [record(f"r{i}", {A: "good" if i % 3 else "bad"}, stored="good") for i in range(9)]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "strata": [{"stratum": "random", "stream": "random", "population": 900, "frame": 880},
                   {"stratum": "good", "stream": "targeted", "population": 90}],
        "records": [{"span_id": f"sp-r{i}", "stratum": "random", "stream": "random"} for i in range(9)]}))
    r = build(tmp_path, recs, plan=str(plan))
    assert r["weighted"] == {"random_only": True, "streams": {"random": 9}, "frame": 880}
    assert "so the numbers above are measurement estimates" in align.render(r)


def test_random_strata_are_left_out_of_targeted_weighting(tmp_path):
    recs = [record(f"g{i}", {A: "good"}, stored="good") for i in range(4)]
    recs.append(record("r0", {A: "bad"}, stored="good"))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "strata": [{"stratum": "random", "stream": "random", "population": 900, "frame": 900},
                   {"stratum": "good", "stream": "targeted", "population": 90}],
        "records": [{"span_id": f"sp-g{i}", "stratum": "good", "stream": "targeted"} for i in range(4)]
        + [{"span_id": "sp-r0", "stratum": "random", "stream": "random"}]}))
    r = build(tmp_path, recs, plan=str(plan))
    wt = r["weighted"]
    assert wt["agreement"] == 1.0 and wt["covered_share"] == 1.0 and wt["uncovered"] == []
    assert wt["streams"] == {"targeted": 4, "random": 1}
    text = align.render(r)
    assert "These records were targeted" in text and "1 gold records here are from the random stream" in text


def test_weighted_estimates_explain_an_old_plan(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"records": []}))
    r = build(tmp_path, usable_records(), plan=str(plan))
    assert "no strata" in r["weighted"]["error"]


def test_compare_reports_flips_and_label_mix(tmp_path, capsys):
    def rec(rid, human, judge):
        return {"record_id": rid, "bucket": "gold", "consensus": human, "eval_label": judge, "split": "test"}
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(json.dumps({"records": [rec("1", "good", "bad"), rec("2", "good", "good"), rec("3", "bad", "bad")]}))
    after.write_text(json.dumps({"records": [rec("1", "good", "good"), rec("2", "good", "bad"), rec("3", "bad", "bad")]}))
    align.cmd_compare(compare_args(str(before), str(after), split="test"))
    out = capsys.readouterr().out
    assert "Fixed (wrong before, right after): 1 — ['1']" in out
    assert "Broken (right before, wrong after): 1 — ['2']" in out
    assert "`bad` 2→2" in out and "`good` 1→1" in out


# ---------------------------------------------------------------------------
# alignment SOP: π, ceiling, applicability, splits, judge version, PPI
# ---------------------------------------------------------------------------

def test_scott_pi_known_values():
    assert align.scott_pi([]) is None
    assert align.scott_pi([("x", "x"), ("y", "y")]) == 1.0
    assert align.scott_pi([("x", "x"), ("x", "y"), ("y", "x"), ("y", "y")]) == 0.0
    # Rater 1 says x on 3 of 4, rater 2 on 1 of 4: po 0.5, pooled x share 0.5, pe 0.5 -> 0, while κ is 0 too.
    assert align.scott_pi([("x", "x"), ("x", "y"), ("x", "y"), ("y", "y")]) == 0.0
    # κ credits the raters' different label mixes; π does not, so π ≤ κ.
    pairs = [("x", "x")] * 6 + [("x", "y")] * 3 + [("y", "y")]
    assert align.scott_pi(pairs) < align.cohen_kappa(pairs)


def test_bootstrap_interval_is_seeded_and_brackets_the_estimate():
    pairs = [("good", "good")] * 8 + [("good", "bad"), ("bad", "bad"), ("bad", "bad"), ("bad", "good")]
    lo, hi = align.boot_ci(pairs, align.scott_pi)
    assert lo <= align.scott_pi(pairs) <= hi
    assert align.boot_ci(pairs, align.scott_pi) == (lo, hi)


def test_judge_vs_human_pi_is_reported_next_to_agreement(tmp_path):
    r = build(tmp_path, usable_records())
    assert r["judge_pi"]["pi"] == pytest.approx(2 / 3)
    assert "Exact agreement: 10/12 (83%, 95% CI 55–95%); Scott's π 0.67" in align.render(r)


def test_stale_results_are_left_out_of_agreement(tmp_path):
    recs = [record("r1", {A: "good"}, stored="bad", explanation="LAST_TURN_CHECK: Turn 2", session="s1"),
            record("r2", {A: "good"}, stored="good", explanation="LAST_TURN_CHECK: Turn 5", session="s2")]
    r = build(tmp_path, recs, turns={"s1": 5, "s2": 5})
    assert [row["record_id"] for row in r["gold_scored"]] == ["r2"] and r["agree"] == 1
    assert "scored mid-session, so left out" in align.render(r)


def test_session_evaluator_without_the_turn_marker_is_flagged(tmp_path):
    r = build(tmp_path, usable_records(), ev=evaluator(template="Grade the {conversation}."))
    assert any("LAST_TURN_CHECK" in f for f in r["fit"])


def test_applicability_is_scored_apart_from_grade(tmp_path):
    recs = usable_records() + [record("na1", {A: "not_applicable"}, stored="not_applicable"),
                               record("na2", {A: "not_applicable"}, stored="good")]
    r = build(tmp_path, recs)
    assert sorted(r["app_pairs"]).count(("not_applicable", "applicable")) == 1
    assert len(r["app_pairs"]) == 14
    out = align.render(r)
    assert "Applicability (in scope or not): 13/14" in out
    assert "Grade (gold records only): 10/12" in out


def test_human_ceiling_holds_one_rater_out(tmp_path):
    C = "ann.c@example.com"
    recs = []
    for i in range(6):
        votes = {A: "good", B: "good", C: "good" if i else "bad"}
        recs.append(record(f"r{i}", votes, stored="good" if i > 1 else "bad"))
    r = build(tmp_path, recs)
    human, judge = r["ceiling_human"], r["ceiling_judge"]
    # r0 (C said bad): holding out C gives reference good; holding out A or B leaves a tie, skipped.
    # r1-r5: each of 3 raters held out against the other two.
    assert len(human) == len(judge) == 1 + 5 * 3
    assert sum(1 for x, y in human if x == y) == 15  # C's bad on r0 is the only human miss
    assert sum(1 for x, y in judge if x == y) == 4 * 3  # the judge said bad on r0 and r1
    assert "One rater held out at a time" in align.render(r)


def test_splits_keep_a_session_together(tmp_path):
    recs = [record(f"r{i}", {A: "good" if i % 2 else "bad"}, stored="good", session=f"s{i // 2}") for i in range(40)]
    r = build(tmp_path, recs)
    by_session = {}
    for row in r["rows"]:
        by_session.setdefault(row["session_id"], set()).add(row["split"])
    assert all(len(v) == 1 for v in by_session.values())


def test_test_from_makes_a_later_batch_the_test_split(tmp_path):
    recs = []
    for i in range(30):
        rec = record(f"r{i}", {A: "good" if i % 2 else "bad"}, stored="good")
        rec["data"]["start_time"] = str(1780000000000 + (i >= 20) * 30 * 86400 * 1000)
        recs.append(rec)
    late = align.parse_ms(str(1780000000000 + 30 * 86400 * 1000)).isoformat()
    r = build(tmp_path, recs, test_from=late)
    split = {row["record_id"]: row["split"] for row in r["rows"]}
    assert all(split[f"r{i}"] == "test" for i in range(20, 30))
    assert all(split[f"r{i}"] in ("train", "dev") for i in range(20))
    assert "a batch labeled after the prompt was frozen" in align.render(r)
    with pytest.raises(SystemExit, match="ISO 8601"):
        build(tmp_path, recs, test_from="yesterday")


def test_judge_version_tuple_is_reported(tmp_path):
    r = build(tmp_path, usable_records(), rubric_version="v3", admission_filter="parent_id IS NULL")
    j = r["judge"]
    assert j["evaluator_version"] == "v-1" and len(j["prompt_sha"]) == 12 and j["rubric_version"] == "v3"
    out = align.render(r)
    assert "rubric `v3`, admission filter `parent_id IS NULL`" in out and "Pass `--rubric-version`" not in out
    assert "Pass `--rubric-version`" in align.render(build(tmp_path, usable_records()))


def ppi_plan(tmp_path, recs, pops, random_ids):
    """A plan in the queue builder's shape: the random stratum carries the judge's label counts."""
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "strata": [{"stratum": "random", "stream": "random", "period": "", "population": sum(pops.values()),
                    "frame": 100, "label_counts": pops}],
        "records": [{"span_id": f"sp-{rid}", "stratum": "random", "stream": "random", "period": ""}
                    for rid in random_ids]}))
    return str(plan)


def test_ppi_corrects_a_judge_that_over_calls_good(tmp_path):
    # Production: the judge says good on 900 of 1,000. Random labels: humans say good on 14 of 20, and the
    # judge says good on 18 of them (it calls 4 human-bad records good).
    recs = [record(f"g{i}", {A: "good"}, stored="good") for i in range(14)]
    recs += [record(f"b{i}", {A: "bad"}, stored="good") for i in range(4)]
    recs += [record(f"c{i}", {A: "bad"}, stored="bad") for i in range(2)]
    plan = ppi_plan(tmp_path, recs, {"good": 900, "bad": 100, "not_applicable": 0}, [x["id"] for x in recs])
    r = build(tmp_path, recs, plan=plan)
    good = r["production"]["rates"]["good"]
    assert good["judge_only"] == pytest.approx(0.9)
    assert good["ppi"] == pytest.approx(0.7, abs=0.01)
    assert good["ppi_ci"][0] < 0.7 < good["ppi_ci"][1]
    assert "Corrected production rates" in align.render(r)


def test_ppi_uses_only_random_stream_labels(tmp_path):
    recs = usable_records()
    plan = ppi_plan(tmp_path, recs, {"good": 90, "bad": 10}, [])
    r = build(tmp_path, recs, plan=plan)
    assert "random sample" in r["production"]["error"]


# ---------------------------------------------------------------------------
# compare: gap, second judge, gate, ledger; lint
# ---------------------------------------------------------------------------

def report_json(path, labels, judge=None):
    """labels: list of (record_id, split, human, judge_label)."""
    path.write_text(json.dumps({"judge": judge or {"prompt_sha": "p1", "model": "m1"}, "records": [
        {"record_id": rid, "bucket": "gold", "split": sp, "consensus": h, "eval_label": j} for rid, sp, h, j in labels]}))
    return str(path)


def compare_args(before, after, **kw):
    base = dict(before=before, after=after, split=None, second_judge=None, gate=False, fail_label=None,
                ledger=None, look_budget=align.LOOK_BUDGET, candidates=1, fresh=None)
    base.update(kw)
    return argparse.Namespace(**base)


def records_for(dev_hits, test_hits, n=10):
    out = []
    for sp, hits in (("dev", dev_hits), ("test", test_hits)):
        for i in range(n):
            h = "good" if i % 2 else "bad"
            out.append((f"{sp}{i}", sp, h, h if i < hits else ("bad" if h == "good" else "good")))
    return out


def test_compare_flags_a_dev_to_test_drop(tmp_path, capsys):
    before = report_json(tmp_path / "b.json", records_for(6, 6))
    after = report_json(tmp_path / "a.json", records_for(10, 6))
    align.cmd_compare(compare_args(before, after, split="dev"))
    out = capsys.readouterr().out
    assert "Scott's π" in out and "gap +" in out and "the revision fit dev" in out


def test_ship_gate_passes_only_when_test_holds_and_recall_does_not_drop(tmp_path, capsys):
    before = report_json(tmp_path / "b.json", records_for(6, 6))
    good = report_json(tmp_path / "a.json", records_for(8, 8))
    align.cmd_compare(compare_args(before, good, gate=True, second_judge=good))
    assert "## Ship gate: PASS" in capsys.readouterr().out
    # Without a second judge model the gate fails (Kochelka et al.; SOP step 5).
    align.cmd_compare(compare_args(before, good, gate=True))
    assert "❌ Second judge model scored on test" in capsys.readouterr().out
    # The best of several candidates must be re-scored on fresh sessions (SIREN).
    align.cmd_compare(compare_args(before, good, gate=True, second_judge=good, candidates=3))
    out = capsys.readouterr().out
    assert "## Ship gate: FAIL" in out and "missing: pass `--fresh`" in out
    align.cmd_compare(compare_args(before, good, gate=True, second_judge=good, candidates=3, fresh=good))
    assert "## Ship gate: PASS" in capsys.readouterr().out
    bad = report_json(tmp_path / "a2.json", records_for(10, 5))
    align.cmd_compare(compare_args(before, bad, gate=True, fail_label=["bad"]))
    out = capsys.readouterr().out
    assert "## Ship gate: FAIL" in out and "❌ Test agreement holds" in out


def test_second_judge_is_scored_on_test(tmp_path, capsys):
    before = report_json(tmp_path / "b.json", records_for(6, 6))
    after = report_json(tmp_path / "a.json", records_for(8, 8))
    other = report_json(tmp_path / "o.json", records_for(8, 4), judge={"model": "other-model"})
    align.cmd_compare(compare_args(before, after, second_judge=other, gate=True))
    out = capsys.readouterr().out
    assert "other-model on test" in out and "property of the judge model" in out


def test_ledger_counts_looks_and_warns(tmp_path, capsys):
    before = report_json(tmp_path / "b.json", records_for(6, 6))
    after = report_json(tmp_path / "a.json", records_for(8, 8))
    ledger = str(tmp_path / "looks.json")
    for _ in range(3):
        align.cmd_compare(compare_args(before, after, split="dev", ledger=ledger, look_budget=2))
    out = capsys.readouterr().out
    assert "Dev scored 3 time(s)" in out and "Over budget" in out
    for _ in range(2):
        align.cmd_compare(compare_args(before, after, split="test", ledger=ledger))
    assert "Test has been scored 2 times for this prompt" in capsys.readouterr().out
    assert len(json.loads(Path(ledger).read_text())) == 5


def test_lint_flags_case_specific_rules(tmp_path, capsys):
    old = tmp_path / "v1.txt"
    new = tmp_path / "v2.txt"
    old.write_text("Grade the session.\nLabel bad when the answer is wrong.\n")
    new.write_text("Grade the session.\nLabel bad when the answer is wrong.\n"
                   "If session sess-abc123 asks for a refund, label good.\n"
                   "Treat the user asked twice for the same report as good.\n"
                   "When a tool call fails and is retried, judge the final result.\n")
    recs = tmp_path / "r.json"
    recs.write_text(json.dumps({"records": [{"record_id": "rec-1", "session_id": "sess-abc123", "split": "dev",
                                              "eval_explanation": "The user asked twice for the same report and got it."}]}))
    align.cmd_lint(argparse.Namespace(before_template=str(old), after_template=str(new), records=str(recs)))
    out = capsys.readouterr().out
    assert "3 added line(s), 2 flagged" in out
    assert "names a record, session or trace ID" in out and "repeats 8+ words" in out
    assert "retried" not in out.split("flagged")[1].split("Rewrite")[0]


def test_ppi_and_frames_combine_intake_periods(tmp_path):
    """Two periods: the first plan (judge good on 900/1,000) and an intake run (good on 50/100).
    The judge is right on every random record, so each period's rate is its judge rate."""
    recs = [record(f"a{i}", {A: "good" if i < 9 else "bad"}, stored="good" if i < 9 else "bad") for i in range(10)]
    recs += [record(f"b{i}", {A: "good" if i < 5 else "bad"}, stored="good" if i < 5 else "bad") for i in range(10)]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "strata": [{"stratum": "random", "stream": "random", "period": "", "frame": 1000,
                    "label_counts": {"good": 900, "bad": 100}},
                   {"stratum": "random@intake-1", "stream": "random", "period": "intake-1", "frame": 100,
                    "label_counts": {"good": 50, "bad": 50}}],
        "records": [{"span_id": f"sp-a{i}", "stratum": "random", "stream": "random", "period": ""} for i in range(10)]
        + [{"span_id": f"sp-b{i}", "stratum": "random@intake-1", "stream": "random", "period": "intake-1"}
           for i in range(10)]}))
    r = build(tmp_path, recs, plan=str(plan))
    pr = r["production"]
    assert pr["periods"] == 2 and pr["units"] == 1100
    assert pr["rates"]["good"]["ppi"] == pytest.approx((900 + 50) / 1100)
    assert r["weighted"] == {"random_only": True, "streams": {"random": 20}, "frame": 1100}


def test_skewed_gold_reports_prevalence_robust_measures(tmp_path):
    # 18 of 20 humans say good: π understates agreement here, so AC1 and PABAK are reported beside it.
    recs = [record(f"g{i}", {A: "good"}, stored="good" if i < 16 else "bad") for i in range(18)]
    recs += [record(f"b{i}", {A: "bad"}, stored="bad") for i in range(2)]
    r = build(tmp_path, recs)
    assert r["skew"]["label"] == "good" and r["skew"]["share"] == 0.9
    assert r["skew"]["ac1"] == align.gwet_ac1([(row["consensus"], row["stored"]["label"]) for row in r["gold_scored"]])
    assert "π understates agreement" in align.render(r)


def test_balanced_gold_reports_no_skew(tmp_path):
    recs = [record(f"g{i}", {A: "good"}, stored="good") for i in range(5)]
    recs += [record(f"b{i}", {A: "bad"}, stored="bad") for i in range(5)]
    r = build(tmp_path, recs)
    assert r["skew"] is None and "π understates agreement" not in align.render(r)


def test_test_split_metrics_use_only_test_records(tmp_path):
    recs = [record(f"g{i}", {A: "good"}, stored="good" if i % 2 else "bad") for i in range(20)]
    recs += [record(f"b{i}", {A: "bad"}, stored="bad") for i in range(20)]
    r = build(tmp_path, recs)
    test_rows = [row for row in r["gold_scored"] if row["split"] == "test"]
    assert len(r["test_pairs"]) == len(test_rows) > 0
    assert r["test_recall"]["bad"][1] == sum(1 for row in test_rows if row["consensus"] == "bad")
    out = align.render(r)
    assert "## Test split" in out and "**directional**" in out


def test_sessions_read_while_writing_rules_never_count_as_test(tmp_path):
    recs = [record(f"r{i}", {A: "good" if i < 20 else "bad"}, stored="good" if i < 20 else "bad") for i in range(40)]
    base = build(tmp_path, recs)
    test_sessions = sorted(str(row["session_id"]) for row in base["gold"] if row["split"] == "test")
    read = tmp_path / "read.txt"
    dev_session = next(str(row["session_id"]) for row in base["gold"] if row["split"] == "dev")
    read.write_text("\n".join(test_sessions[:3] + [dev_session]))
    r = build(tmp_path, recs, read_sessions=str(read))
    split = {str(row["session_id"]): row["split"] for row in r["gold"]}
    assert all(split[s] == "dev" for s in test_sessions[:3])
    assert len(r["test_pairs"]) == len(base["test_pairs"]) - 3
    assert r["moved_from_test"] == test_sessions[:3]
    assert "never count as test" in align.render(r)


def test_rescored_at_clears_the_older_version_blocker_after_an_in_place_edit(tmp_path):
    ev = evaluator(created_at="2030-01-01T00:00:00Z")
    r = build(tmp_path, usable_records(), ev=ev)
    assert "Every gold record carries a result from the current judge version" in blocked(r)
    r = build(tmp_path, usable_records(), ev=ev, rescored_at="2030-01-02T00:00:00Z")
    assert "Every gold record carries a result from the current judge version" not in blocked(r)
    assert "re-scored by a run at" in align.render(r)
    with pytest.raises(SystemExit):
        build(tmp_path, usable_records(), ev=ev, rescored_at="2029-12-31T00:00:00Z")
