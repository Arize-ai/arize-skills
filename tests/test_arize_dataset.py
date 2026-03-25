"""
Test cases for the arize-dataset skill.
"""

import uuid

import pytest

from conftest import make_runner
from harness.ax_helpers import create_dataset, delete_dataset, export_dataset
from harness.verifier import (
    AxResourceExistsVerifier,
    BashCommandContainsVerifier,
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
    ToolWasCalledVerifier,
)


@pytest.fixture
def dataset_runner(workspace, arize_env, test_model):
    return make_runner("arize-dataset", workspace, arize_env, test_model)


class TestDatasetCreate:
    """User asks to create a dataset from inline data."""

    @pytest.mark.asyncio
    async def test_create_dataset_from_description(
        self, dataset_runner, test_report, arize_space_id
    ):
        unique_name = f"test-dataset-{uuid.uuid4().hex[:8]}"

        result = await dataset_runner.run(
            f"Create a dataset called '{unique_name}' in space {arize_space_id} "
            f"with 5 question/answer pairs about world capitals."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax datasets create"]),
            OutputContainsVerifier(["dataset", "created"]),
            AxResourceExistsVerifier("datasets", unique_name),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestDatasetList:
    """User asks to list available datasets."""

    @pytest.mark.asyncio
    async def test_list_datasets(self, dataset_runner, test_report):
        result = await dataset_runner.run("List all my Arize datasets.")
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax datasets list"]),
            OutputContainsVerifier(["dataset"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestDatasetExport:
    """User asks to export and examine a dataset."""

    @pytest.mark.asyncio
    async def test_export_and_analyze_dataset(
        self, dataset_runner, test_report, arize_space_id
    ):
        ds_id = create_dataset(
            name=f"test-export-{uuid.uuid4().hex[:8]}",
            space_id=arize_space_id,
            examples=[
                {"question": "What is 2+2?", "answer": "4"},
                {"question": "Capital of France?", "answer": "Paris"},
                {"question": "Largest planet?", "answer": "Jupiter"},
            ],
        )

        try:
            result = await dataset_runner.run(
                f"Export dataset {ds_id} and tell me how many examples it has "
                f"and what the columns are."
            )
            verifier = CompositeVerifier(
                NoErrorVerifier(),
                BashCommandContainsVerifier(["ax datasets export"]),
                OutputContainsVerifier(["3", "question", "answer"]),
            )
            result.verification = verifier.verify(result)
            test_report.add(result)
            assert result.passed
        finally:
            delete_dataset(ds_id)


class TestDatasetAppend:
    """User asks to add examples to an existing dataset."""

    @pytest.mark.asyncio
    async def test_append_inline_examples(
        self, dataset_runner, test_report, arize_space_id
    ):
        ds_id = create_dataset(
            name=f"test-append-{uuid.uuid4().hex[:8]}",
            space_id=arize_space_id,
            examples=[{"question": "Seed?", "answer": "Yes"}],
        )

        try:
            result = await dataset_runner.run(
                f"Add these examples to dataset {ds_id}: "
                f'"What color is the sky?" -> "Blue", '
                f'"How many days in a week?" -> "7"'
            )
            verifier = CompositeVerifier(
                NoErrorVerifier(),
                BashCommandContainsVerifier(["ax datasets append"]),
            )
            result.verification = verifier.verify(result)
            test_report.add(result)
            assert result.passed

            # Post-run: verify examples were actually appended via ax CLI
            examples_after = export_dataset(ds_id)
            assert len(examples_after) == 3, (
                f"Expected 3 examples after append, got {len(examples_after)}"
            )
        finally:
            delete_dataset(ds_id)
