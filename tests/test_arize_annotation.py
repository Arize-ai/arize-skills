"""
Test cases for the arize-annotation skill.

Verifies that Claude can correctly manage annotation configs and queues
using the ax CLI, and apply annotations to spans via the Python SDK.
"""

import uuid

import pytest

from conftest import make_runner
from harness.verifier import (
    BashCommandContainsVerifier,
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
)


@pytest.fixture
def annotation_runner(workspace, arize_env, test_model):
    return make_runner("arize-annotation", workspace, arize_env, test_model)


class TestAnnotationConfigList:
    """User asks to list annotation configs in a space."""

    @pytest.mark.asyncio
    async def test_list_annotation_configs(
        self, annotation_runner, test_report, arize_space_id
    ):
        result = await annotation_runner.run(
            f"List all annotation configs in space {arize_space_id}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax annotation-configs list"]),
            OutputContainsVerifier(["annotation"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestAnnotationConfigCreate:
    """User asks to create a categorical annotation config."""

    @pytest.mark.asyncio
    async def test_create_categorical_config(
        self, annotation_runner, test_report, arize_space_id
    ):
        config_name = f"test-correctness-{uuid.uuid4().hex[:8]}"

        result = await annotation_runner.run(
            f"Create a categorical annotation config called '{config_name}' "
            f"in space {arize_space_id} with labels 'correct' and 'incorrect'. "
            f"Use maximize as the optimization direction."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax annotation-configs create"]),
            OutputContainsVerifier(["annotation", "config"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed

    @pytest.mark.asyncio
    async def test_create_continuous_config(
        self, annotation_runner, test_report, arize_space_id
    ):
        config_name = f"test-quality-{uuid.uuid4().hex[:8]}"

        result = await annotation_runner.run(
            f"Create a continuous annotation config called '{config_name}' "
            f"in space {arize_space_id} with a score range from 0 to 10. "
            f"Use maximize as the optimization direction."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax annotation-configs create"]),
            OutputContainsVerifier(["annotation", "config"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestAnnotationQueueList:
    """User asks to list annotation queues."""

    @pytest.mark.asyncio
    async def test_list_annotation_queues(
        self, annotation_runner, test_report, arize_space_id
    ):
        result = await annotation_runner.run(
            f"List all annotation queues in space {arize_space_id}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax annotation-queues list"]),
            OutputContainsVerifier(["queue", "annotation"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestAnnotationQueueCreateWorkflow:
    """End-to-end: create config then create a queue linked to it."""

    @pytest.mark.asyncio
    async def test_create_config_and_queue(
        self, annotation_runner, test_report, arize_space_id
    ):
        config_name = f"test-helpfulness-{uuid.uuid4().hex[:8]}"
        queue_name = f"test-review-queue-{uuid.uuid4().hex[:8]}"

        result = await annotation_runner.run(
            f"In space {arize_space_id}: "
            f"1. Create a categorical annotation config called '{config_name}' "
            f"with labels 'helpful' and 'unhelpful'. "
            f"2. Then create an annotation queue called '{queue_name}' "
            f"linked to that config with instructions 'Label each response'. "
            f"Tell me the IDs of both resources."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(
                ["ax annotation-configs create", "ax annotation-queues create"]
            ),
            OutputContainsVerifier(["config", "queue"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "annotation-workflow"]
        test_report.add(result)
        assert result.passed
