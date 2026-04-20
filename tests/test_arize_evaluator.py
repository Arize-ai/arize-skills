"""
Test cases for the arize-evaluator skill.

Verifies that Claude can create LLM-as-judge evaluators, manage tasks,
and trigger evaluation runs using the ax CLI.
"""

import pytest

from conftest import make_runner
from harness.verifier import (
    BashCommandContainsVerifier,
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
)


@pytest.fixture
def evaluator_runner(workspace, arize_env, test_model):
    return make_runner("arize-evaluator", workspace, arize_env, test_model)


class TestEvaluatorList:
    """User asks to list existing evaluators."""

    @pytest.mark.asyncio
    async def test_list_evaluators(
        self, evaluator_runner, test_report, arize_space_id
    ):
        result = await evaluator_runner.run(
            f"List all evaluators in space {arize_space_id}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax evaluators list"]),
            OutputContainsVerifier(["evaluator"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestEvaluatorCreate:
    """User asks to create a new LLM-as-judge evaluator."""

    @pytest.mark.asyncio
    async def test_create_evaluator_requires_integration(
        self, evaluator_runner, test_report, arize_space_id
    ):
        result = await evaluator_runner.run(
            f"I want to create a correctness evaluator for space {arize_space_id}. "
            f"First check if I have any AI integrations set up. "
            f"Tell me what integrations exist and what I need to do next."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax ai-integrations list"]),
            OutputContainsVerifier(["integration"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestEvaluatorWorkflowA:
    """Workflow A: inspect spans and propose evaluator ideas for a project."""

    @pytest.mark.asyncio
    async def test_propose_evaluators_from_spans(
        self, evaluator_runner, test_report, arize_space_id, test_project_name
    ):
        result = await evaluator_runner.run(
            f"I want to add LLM-as-judge evaluation to my project "
            f"'{test_project_name}' in space {arize_space_id}. "
            f"Sample some recent spans and propose 2-3 evaluator ideas based "
            f"on what you see in the data."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax spans export"]),
            OutputContainsVerifier(["evaluator"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "evaluator-workflow-a"]
        test_report.add(result)
        assert result.passed


class TestTaskList:
    """User asks to list evaluation tasks."""

    @pytest.mark.asyncio
    async def test_list_tasks(
        self, evaluator_runner, test_report, arize_space_id
    ):
        result = await evaluator_runner.run(
            f"List all evaluation tasks in space {arize_space_id}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax tasks list"]),
            OutputContainsVerifier(["task"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestEvaluatorColumnMappingWorkflow:
    """User wants to understand column mapping for an evaluator task."""

    @pytest.mark.asyncio
    async def test_inspect_spans_for_column_mapping(
        self, evaluator_runner, test_report, arize_space_id, test_project_name
    ):
        result = await evaluator_runner.run(
            f"I have an evaluator with template variables {{input}} and {{output}}. "
            f"Export a few recent spans from project '{test_project_name}' in space "
            f"{arize_space_id} and tell me what column mappings I should use."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax spans export"]),
            OutputContainsVerifier(["input", "output", "column"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "column-mapping"]
        test_report.add(result)
        assert result.passed
