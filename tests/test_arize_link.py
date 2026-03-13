"""
Test cases for the arize-link skill.
"""

import pytest

from conftest import make_runner
from harness.verifier import (
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
    URLFormatVerifier,
)


@pytest.fixture
def link_runner(workspace, arize_env, test_model):
    return make_runner(
        "arize-link",
        workspace,
        arize_env,
        test_model,
        max_turns=10,
        max_budget_usd=0.20,
    )


class TestTraceLinkGeneration:
    """User asks for a link to a specific trace."""

    @pytest.mark.asyncio
    async def test_generate_trace_link(self, link_runner, test_report):
        result = await link_runner.run(
            "Generate a link to trace ID abc123def456 in project "
            "TW9kZWw6MTpkZUZn, org QWNjb3VudDox, space U3BhY2U6MQ==. "
            "The trace was created on 2026-03-01."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            URLFormatVerifier(
                expected_params=["selectedTraceId", "startA", "endA"]
            ),
            # The specific trace ID must appear in the generated URL
            OutputContainsVerifier(["app.arize.com", "abc123def456"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestSpanLinkGeneration:
    """User wants a link to a specific span within a trace."""

    @pytest.mark.asyncio
    async def test_generate_span_link(self, link_runner, test_report):
        result = await link_runner.run(
            "Generate a link to span ID span789 in trace abc123def456, "
            "project TW9kZWw6MTpkZUZn, org QWNjb3VudDox, space U3BhY2U6MQ==."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            URLFormatVerifier(
                expected_params=[
                    "selectedTraceId",
                    "selectedSpanId",
                ]
            ),
            # Both the trace ID and span ID must be present in the output
            OutputContainsVerifier(["abc123def456", "span789"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestSessionLinkGeneration:
    """User wants a link to a session."""

    @pytest.mark.asyncio
    async def test_generate_session_link(self, link_runner, test_report):
        result = await link_runner.run(
            "Generate a link to session sess_12345 in project "
            "TW9kZWw6MTpkZUZn, org QWNjb3VudDox, space U3BhY2U6MQ==."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            URLFormatVerifier(expected_params=["selectedSessionId"]),
            OutputContainsVerifier(["app.arize.com", "sess_12345"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestLinkFromExportedData:
    """User provides a trace export and wants links to items in it."""

    @pytest.mark.asyncio
    async def test_link_from_trace_context(self, link_runner, test_report):
        result = await link_runner.run(
            "I exported a trace and it has these details: "
            "trace_id=0123456789abcdef, span_id=fedcba9876543210, "
            "start_time=2026-03-07T05:39:15.822147Z. "
            "My org is QWNjb3VudDox, space is U3BhY2U6MQ==, "
            "project is TW9kZWw6MTpkZUZn. "
            "Generate links to both the trace and the specific span."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            URLFormatVerifier(
                expected_params=["selectedTraceId", "selectedSpanId"]
            ),
            # Both IDs must appear in the output links
            OutputContainsVerifier(
                ["app.arize.com", "0123456789abcdef", "fedcba9876543210"]
            ),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed
