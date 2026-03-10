"""
Test cases for the arize-trace skill.

Verifies that Claude can correctly use the ax CLI to export traces,
spans, and sessions, and interpret the results.
"""

import pytest

from conftest import make_runner
from harness.verifier import (
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
    ToolWasCalledVerifier,
)


@pytest.fixture
def trace_runner(workspace, arize_env, test_model):
    return make_runner("arize-trace", workspace, arize_env, test_model)


class TestTracePrerequisiteCheck:
    """Verify the skill checks for ax CLI and credentials."""

    @pytest.mark.asyncio
    async def test_checks_prerequisites(self, trace_runner, test_report):
        result = await trace_runner.run(
            "Check if I have the Arize tools configured correctly."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestTraceExportByTraceId:
    """User provides a trace ID and asks to export it."""

    @pytest.mark.asyncio
    async def test_export_single_trace(
        self, trace_runner, test_report, arize_space_id, test_project_name
    ):
        result = await trace_runner.run(
            f"Export the most recent trace from project "
            f"'{test_project_name}' using space ID {arize_space_id}. "
            f"Save the output to a file."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestTraceExportWithFilter:
    """User asks to find error traces in a project."""

    @pytest.mark.asyncio
    async def test_export_error_traces(
        self, trace_runner, test_report, test_project_name
    ):
        result = await trace_runner.run(
            f"Find and export recent error traces from the project "
            f"'{test_project_name}'. Show me what went wrong."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestTraceExportBySessionId:
    """User wants to download a conversation session."""

    @pytest.mark.asyncio
    async def test_export_session(
        self, trace_runner, test_report, test_project_name
    ):
        result = await trace_runner.run(
            f"List the recent traces from project '{test_project_name}' "
            f"and export the spans from the first one."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestTraceDebugWorkflow:
    """End-to-end debug workflow: find errors, export, summarize root cause."""

    @pytest.mark.asyncio
    async def test_debug_failing_traces(
        self, trace_runner, test_report, test_project_name
    ):
        result = await trace_runner.run(
            f"Debug the failing traces in '{test_project_name}'. "
            f"Find the error traces, export them, read the error details, "
            f"and tell me the root cause."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash", "Read"]),
            OutputContainsVerifier(["error"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "debug-workflow"]
        test_report.add(result)
        assert result.passed
