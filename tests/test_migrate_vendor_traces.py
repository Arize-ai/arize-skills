"""Unit tests for vendor trace migration; no live services."""

import importlib.util
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrate_vendor_traces.py"
spec = importlib.util.spec_from_file_location("migrate_vendor_traces", SCRIPT)
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


def _run(rid, parent=None, minutes=0):
    start = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return SimpleNamespace(id=rid, parent_run_id=parent, start_time=start)


def test_limit_keeps_newest_roots_and_their_children():
    older_root = _run("old", minutes=0)
    older_child = _run("old-child", parent="old", minutes=1)
    newer_root = _run("new", minutes=10)
    newer_child = _run("new-child", parent="new", minutes=11)
    # A stray child from an even newer incomplete tree should not displace
    # the newest complete root when limit is 1.
    selected, missing = migrate.select_langsmith_tree(
        [older_root, older_child, newer_root, newer_child],
        limit=1,
    )
    ids = {str(r.id) for r in selected}
    assert ids == {"new", "new-child"}
    assert missing == 0


def test_child_outside_window_counts_missing_parent():
    child = _run("child", parent="missing-root", minutes=5)
    selected, missing = migrate.select_langsmith_tree([child], limit=10)
    assert {str(r.id) for r in selected} == {"child"}
    assert missing == 1


@pytest.mark.parametrize(
    ("response", "exit_code", "message"),
    [
        (b"{}", 0, "OTLP ingest OK (2 spans)"),
        (b"OK", 0, "OTLP ingest OK (2 spans)"),
        (b"[]", 0, "OTLP ingest OK (2 spans)"),
        (b'{"partialSuccess":{"errorMessage":"collector warning"}}', 0, "collector warning"),
        (
            b'{"partialSuccess":{"rejectedSpans":"1","errorMessage":"invalid span"}}',
            1,
            "OTLP ingest partial success (1 of 2 spans rejected): invalid span",
        ),
    ],
)
def test_main_reports_otlp_result(monkeypatch, capsys, response, exit_code, message):
    spans = [{"name": "example", "attributes": []}] * 2
    monkeypatch.setattr(migrate, "export_langsmith", lambda *_: spans)
    monkeypatch.setattr(migrate.sys, "argv", ["migrate", "--vendor", "langsmith", "--arize-project", "test"])
    monkeypatch.setenv("ARIZE_API_KEY", "test-key")
    monkeypatch.setenv("ARIZE_SPACE_ID", "test-space")
    monkeypatch.setattr(migrate.urllib.request, "urlopen", lambda *args, **kwargs: BytesIO(response))

    assert migrate.main() == exit_code
    output = capsys.readouterr()
    if exit_code:
        assert message in output.err
        assert "OTLP ingest OK" not in output.out
    else:
        assert message in output.out + output.err
