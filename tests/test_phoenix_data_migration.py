"""Behavioral tests for Phoenix dataset and evaluation migration."""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "arize-phoenix-migration" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("migrate_data", SCRIPTS / "migrate_data.py")
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


def test_serializable_handles_datetimes_and_dataclasses():
    assert data.serializable({"time": datetime(2026, 1, 1, tzinfo=timezone.utc)}) == {
        "time": "2026-01-01T00:00:00+00:00"
    }


def test_manifest_is_owner_only_and_detects_changes(tmp_path):
    value = {"schema": 1, "datasets": [], "state": {}}
    value["checksum"] = data.checksum(value)
    path = tmp_path / "data.json"
    data.save(path, value)
    assert path.stat().st_mode & 0o777 == 0o600
    loaded = json.loads(path.read_text())
    loaded["datasets"].append({"name": "changed"})
    path.write_text(json.dumps(loaded))
    with pytest.raises(data.DataMigrationError, match="checksum"):
        data.load(path)


def test_ax_row_preserves_nested_values_as_canonical_json():
    row = data.ax_row(
        {
            "source_id": "custom",
            "source_global_id": "global",
            "input": {"nested": {"same": "input"}},
            "output": {"nested": {"same": "output"}},
            "metadata": {"nested": {"same": "metadata"}},
        }
    )
    assert json.loads(row["input_json"])["nested"]["same"] == "input"
    assert json.loads(row["output_json"])["nested"]["same"] == "output"
    assert json.loads(row["metadata_json"])["nested"]["same"] == "metadata"


def test_destination_examples_follows_cursor_pages():
    first = SimpleNamespace(
        examples=[SimpleNamespace(id="a", additional_properties={"phoenix_example_id": "one"})],
        pagination=SimpleNamespace(has_more=True, next_cursor="next"),
    )
    second = SimpleNamespace(
        examples=[SimpleNamespace(id="b", additional_properties={"phoenix_example_id": "two"})],
        pagination=SimpleNamespace(has_more=False, next_cursor=None),
    )
    datasets = SimpleNamespace(list_examples=lambda **kwargs: first if kwargs["cursor"] is None else second)
    result = data.destination_examples(SimpleNamespace(datasets=datasets), "dataset")
    assert set(result) == {"one", "two"}


def test_destination_examples_rejects_missing_cursor():
    response = SimpleNamespace(examples=[], pagination=SimpleNamespace(has_more=True, next_cursor=None))
    client = SimpleNamespace(datasets=SimpleNamespace(list_examples=lambda **kwargs: response))
    with pytest.raises(data.DataMigrationError, match="next cursor"):
        data.destination_examples(client, "dataset")


def test_get_dataset_after_create_retries():
    calls = []
    def get(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("not indexed")
        return "ready"
    client = SimpleNamespace(datasets=SimpleNamespace(get=get))
    assert data.get_dataset_after_create(client, "name", "space", sleep=lambda _: None) == "ready"
    assert len(calls) == 2


def test_missing_configuration_names_only_missing_values():
    with pytest.raises(data.DataMigrationError, match="ARIZE_SPACE_ID") as error:
        data.require({"ARIZE_API_KEY": "secret"}, ["ARIZE_API_KEY", "ARIZE_SPACE_ID"])
    assert "secret" not in str(error.value)


def test_cli_does_not_include_dependency_error_details(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(data, "configuration", lambda _: {})
    monkeypatch.setattr(data, "export_data", lambda *args: (_ for _ in ()).throw(RuntimeError("secret response body")))
    monkeypatch.setattr(sys, "argv", ["migrate_data.py", "export", "--manifest", str(tmp_path / "x")])
    assert data.main() == 1
    assert "secret response body" not in capsys.readouterr().out
