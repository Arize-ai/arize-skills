"""Focused regression tests for instrumentation health-check guidance."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "instrumentation_health"
CHECKS_MD = (
    Path(__file__).parent.parent
    / "skills"
    / "arize-instrumentation-health"
    / "references"
    / "checks.md"
)
TIME_PROXIMITY_SECONDS = 0.25


def _span_id(span: dict[str, Any]) -> str:
    return span.get("context", {}).get("span_id", "")


def _trace_id(span: dict[str, Any]) -> str:
    return span.get("context", {}).get("trace_id", "")


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    return span.get("attributes", {})


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value).strip()


def _payload(span: dict[str, Any]) -> tuple[str, str]:
    attrs = _attrs(span)
    request = (
        attrs.get("input.value")
        or attrs.get("llm.input_messages")
        or attrs.get("prompt")
        or attrs.get("messages")
    )
    response = (
        attrs.get("output.value")
        or attrs.get("llm.output_messages")
        or attrs.get("completion")
        or attrs.get("response")
    )
    return _normalized(request), _normalized(response)


def _is_llm_candidate(span: dict[str, Any]) -> bool:
    attrs = _attrs(span)
    return any(
        [
            attrs.get("openinference.span.kind") == "LLM",
            attrs.get("llm.model_name"),
            attrs.get("llm.input_messages"),
            attrs.get("llm.output_messages"),
            any(key.startswith("llm.token_count.") for key in attrs),
            span.get("name") in {"openai.chat.completions", "chat.completions"},
        ]
    )


def _start_delta_seconds(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_start = datetime.fromisoformat(left["start_time"].replace("Z", "+00:00"))
    right_start = datetime.fromisoformat(right["start_time"].replace("Z", "+00:00"))
    return abs((left_start - right_start).total_seconds())


def _retry_or_progression_explains_pair(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    left_attrs = _attrs(left)
    right_attrs = _attrs(right)
    retry_keys = {
        "retry",
        "retries",
        "attempt",
        "llm.retry.attempt",
        "gen_ai.request.retry_count",
    }
    if any(key in left_attrs or key in right_attrs for key in retry_keys):
        return True
    return {left.get("status_code"), right.get("status_code")} == {"ERROR", "OK"}


def _duplicate_llm_trace_ids(spans: list[dict[str, Any]]) -> set[str]:
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        by_trace[_trace_id(span)].append(span)

    duplicate_trace_ids: set[str] = set()
    for trace_id, trace_spans in by_trace.items():
        llm_spans = [span for span in trace_spans if _is_llm_candidate(span)]
        for index, left in enumerate(llm_spans):
            for right in llm_spans[index + 1 :]:
                if _span_id(left) == _span_id(right):
                    continue
                if left.get("parent_id") != right.get("parent_id"):
                    continue
                if left.get("name") != right.get("name"):
                    continue
                if _attrs(left).get("llm.model_name") != _attrs(right).get(
                    "llm.model_name"
                ):
                    continue
                if _payload(left) != _payload(right):
                    continue
                if _start_delta_seconds(left, right) > TIME_PROXIMITY_SECONDS:
                    continue
                if _retry_or_progression_explains_pair(left, right):
                    continue
                duplicate_trace_ids.add(trace_id)

    return duplicate_trace_ids


def test_duplicate_llm_fixture_flags_ad_hoc_provider_spans() -> None:
    spans = json.loads((FIXTURE_DIR / "duplicate_llm_spans.json").read_text())

    assert _duplicate_llm_trace_ids(spans) == {"trace-duplicate"}


def test_duplicate_span_guidance_keeps_provider_and_guardrail_language() -> None:
    checks = CHECKS_MD.read_text()

    assert "openai.chat.completions" in checks
    assert "`prompt`" in checks
    assert "`completion`" in checks
    assert "legitimate retries" in checks
    assert "Do not skip duplicate detection just because check 3" in checks
