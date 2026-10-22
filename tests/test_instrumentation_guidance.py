"""Regression tests for TypeScript filtering and span I/O review guidance."""

import os
from pathlib import Path


ROOT = Path(os.environ.get("ARIZE_SKILL_ROOT", Path(__file__).resolve().parents[1]))


def read_skill_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8").lower()


def test_typescript_filter_is_default_when_integration_supports_it() -> None:
    skill = read_skill_file("skills/arize-instrumentation/SKILL.md")
    verification = read_skill_file(
        "skills/arize-instrumentation/references/verification.md"
    )

    assert "filter non-genai spans" in skill
    assert "spanfilter: isopeninferencespan" in skill
    assert "reparentorphanedspans: true" in skill
    assert "span.type !== spantype.generic" in skill
    assert "@mastra/observability" in skill
    assert "do not assume a universal opentelemetry option" in skill
    assert "typescript span filtering" in verification


def test_verification_reviews_missing_io_and_rest_boundaries() -> None:
    verification = read_skill_file(
        "skills/arize-instrumentation/references/verification.md"
    )
    skill = read_skill_file("skills/arize-instrumentation/SKILL.md")

    assert "missing i/o on every span" in verification
    assert "unclassified `get`/`post`/rest/http spans" in verification
    assert "user-facing request/response boundary" in verification
    assert "work with the user" in verification
    assert "do not fabricate payloads" in verification
    assert "review all spans in the new trace for missing input/output" in skill


def test_health_audit_checks_semantic_span_io() -> None:
    skill = read_skill_file("skills/arize-instrumentation-health/SKILL.md")
    checks = read_skill_file(
        "skills/arize-instrumentation-health/references/checks.md"
    )

    assert "missing semantic-span i/o" in skill
    assert "missing input/output on semantic spans" in checks
    assert "raw http/rest" in checks
