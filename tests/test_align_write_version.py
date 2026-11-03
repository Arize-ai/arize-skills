"""Behavioral tests for arize-align-evaluator's write_version.py; ax and the Arize SDK are faked.

Run: pytest --noconftest -c /dev/null -p no:cacheprovider tests/test_align_write_version.py -q
"""

import copy
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arize-align-evaluator" / "scripts" / "write_version.py"
spec = importlib.util.spec_from_file_location("write_version", SCRIPT)
wv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wv)

MSG = "Rubric v3, 2026-10-19 (criterion change): empty validated filters count as produced"
CURRENT = {
    "id": "ev-1", "name": "aql", "type": "TEMPLATE", "space_id": "sp-1",
    "version": {"id": "ver-2", "created_at": "2026-10-06T16:08:14Z", "commit_message": "v2",
                "template_config": {"name": "aql_v2", "template": "Grade it.\nOld rule.\n", "include_explanations": True,
                                    "use_function_calling": True, "use_structured_output": True,
                                    "classification_choices": {"good": 1, "bad": 0}, "direction": "MAXIMIZE",
                                    "data_granularity": "SESSION",
                                    "llm_config": {"ai_integration_id": "int-1", "model_name": "gpt-5.5",
                                                   "invocation_parameters": None}}},
}


class FakeAx:
    """`ax evaluators get` returns the current version until the SDK writes a new one."""

    def __init__(self):
        self.ev = copy.deepcopy(CURRENT)
        self.calls = []

    def run(self, cmd, **_):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(self.ev), "")


def fake_sdk(monkeypatch, ax, drop=None):
    created = {}

    class TemplateConfigInput:
        @classmethod
        def model_validate(cls, d):
            return d

    def create_template_version(evaluator, space, commit_message, template_config):
        created.update(evaluator=evaluator, space=space, commit_message=commit_message, config=template_config)
        stored = dict(template_config)
        if drop:
            stored.pop(drop)
        ax.ev["version"] = {"id": "ver-3", "created_at": "2026-10-20T00:25:21Z", "commit_message": commit_message,
                            "template_config": stored}
        return {"id": "ver-3", "created_at": "2026-10-20T00:25:21Z"}

    client = types.SimpleNamespace(evaluators=types.SimpleNamespace(create_template_version=create_template_version))
    factory = types.ModuleType("ax.core.client_factory")
    factory.make_client = lambda: (client, None)
    evtypes = types.ModuleType("arize.evaluators.types")
    evtypes.TemplateConfigInput = TemplateConfigInput
    for name, mod in (("ax", types.ModuleType("ax")), ("ax.core", types.ModuleType("ax.core")),
                      ("ax.core.client_factory", factory), ("arize", types.ModuleType("arize")),
                      ("arize.evaluators", types.ModuleType("arize.evaluators")), ("arize.evaluators.types", evtypes)):
        monkeypatch.setitem(sys.modules, name, mod)
    return created


def args(tmp_path, *extra, msg=MSG, template="Grade it.\nNew rule.\n"):
    f = tmp_path / "t.txt"
    f.write_text(template)
    return ["--space", "sp-1", "--evaluator", "ev-1", "--template-file", str(f), "--commit-message", msg,
            "--out-dir", str(tmp_path / "out"), *extra]


def test_dry_run_prints_the_diff_and_writes_nothing(tmp_path, monkeypatch, capsys):
    ax = FakeAx()
    monkeypatch.setattr(wv.subprocess, "run", ax.run)
    assert wv.main(args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "-Old rule." in out and "+New rule." in out and "Dry run: nothing written" in out
    assert "`use_structured_output`" in out and "`llm_config`" in out
    assert not (tmp_path / "out").exists()
    assert all(c[1:3] == ["evaluators", "get"] for c in ax.calls)


def test_commit_message_must_follow_the_changelog_format(tmp_path, monkeypatch):
    monkeypatch.setattr(wv.subprocess, "run", FakeAx().run)
    for bad in ("tweak the template", "Rubric v3 (criterion change): x", "Rubric v3, 2026-10-19 (fix): x"):
        with pytest.raises(SystemExit, match="changelog"):
            wv.main(args(tmp_path, msg=bad))


def test_identical_template_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(wv.subprocess, "run", FakeAx().run)
    with pytest.raises(SystemExit, match="identical"):
        wv.main(args(tmp_path, template=CURRENT["version"]["template_config"]["template"]))


def test_execute_saves_rollback_copies_every_field_and_reads_back(tmp_path, monkeypatch, capsys):
    ax = FakeAx()
    monkeypatch.setattr(wv.subprocess, "run", ax.run)
    created = fake_sdk(monkeypatch, ax)
    assert wv.main(args(tmp_path, "--execute")) == 0
    rollback = json.loads((tmp_path / "out" / "rollback_ver-2.json").read_text())
    assert rollback["version"]["template_config"]["template"] == "Grade it.\nOld rule.\n"
    cfg = created["config"]
    assert cfg["template"] == "Grade it.\nNew rule.\n" and cfg["use_structured_output"] is True
    assert cfg["llm_config"] == {"ai_integration_id": "int-1", "model_name": "gpt-5.5"}  # null settings left out
    assert created["commit_message"] == MSG and created["space"] == "sp-1"
    out = capsys.readouterr().out
    assert "every template_config field matches" in out and "Switch time (created_at): 2026-10-20T00:25:21Z" in out


def test_execute_reports_a_field_the_api_dropped(tmp_path, monkeypatch, capsys):
    ax = FakeAx()
    monkeypatch.setattr(wv.subprocess, "run", ax.run)
    fake_sdk(monkeypatch, ax, drop="use_structured_output")
    assert wv.main(args(tmp_path, "--execute")) == 1
    assert "Read-back differs from the intended config in: `use_structured_output`" in capsys.readouterr().out


def test_execute_without_the_sdk_explains_which_python_to_use(tmp_path, monkeypatch):
    monkeypatch.setattr(wv.subprocess, "run", FakeAx().run)
    monkeypatch.setitem(sys.modules, "ax.core.client_factory", None)
    with pytest.raises(SystemExit, match="Python that runs ax"):
        wv.main(args(tmp_path, "--execute"))


def test_warns_when_the_current_version_sets_a_model_setting_the_api_drops(tmp_path, monkeypatch, capsys):
    ax = FakeAx()
    ax.ev["version"]["template_config"]["llm_config"]["invocation_parameters"] = {
        "temperature": 0, "top_p": None, "additional_properties": {"seed": 7}}
    monkeypatch.setattr(wv.subprocess, "run", ax.run)
    assert wv.main(args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "won't keep the current model settings" in out
    assert "`invocation_parameters.temperature` = 0" in out and "`invocation_parameters.seed` = 7" in out
    assert "top_p" not in out


def test_no_warning_without_model_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wv.subprocess, "run", FakeAx().run)
    wv.main(args(tmp_path))
    assert "model settings" not in capsys.readouterr().out
