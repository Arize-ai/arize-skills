"""
Test cases for the arize-experiment skill.
"""

import uuid

import pytest

from conftest import make_runner
from harness.ax_helpers import (
    create_dataset,
    create_experiment,
    delete_dataset,
    delete_experiment,
    export_dataset,
)
from harness.verifier import (
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
    ToolWasCalledVerifier,
)


@pytest.fixture
def experiment_runner(workspace, arize_env, test_model):
    return make_runner("arize-experiment", workspace, arize_env, test_model)


@pytest.fixture
def eval_dataset(arize_space_id):
    """Create a small evaluation dataset for experiment tests."""
    ds_id = create_dataset(
        name=f"test-eval-{uuid.uuid4().hex[:8]}",
        space_id=arize_space_id,
        examples=[
            {"question": "What is 2+2?", "expected_answer": "4"},
            {"question": "Capital of France?", "expected_answer": "Paris"},
            {"question": "Largest ocean?", "expected_answer": "Pacific"},
        ],
    )
    yield ds_id
    delete_dataset(ds_id)


class TestExperimentCreate:
    """User wants to run an experiment against a dataset."""

    @pytest.mark.asyncio
    async def test_run_experiment_against_dataset(
        self, experiment_runner, test_report, eval_dataset
    ):
        exp_name = f"test-exp-{uuid.uuid4().hex[:8]}"

        result = await experiment_runner.run(
            f"Run an experiment called '{exp_name}' against dataset "
            f"{eval_dataset}. For each example, answer the question and "
            f"evaluate whether your answer matches the expected_answer. "
            f"Use 'correctness' as the evaluation metric."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
            OutputContainsVerifier(["experiment"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "experiment-create"]
        test_report.add(result)
        assert result.passed


class TestExperimentList:
    """User asks to list experiments for a dataset."""

    @pytest.mark.asyncio
    async def test_list_experiments(
        self, experiment_runner, test_report, eval_dataset
    ):
        result = await experiment_runner.run(
            f"List all experiments for dataset {eval_dataset}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestExperimentCompare:
    """User wants to compare two experiments."""

    @pytest.mark.asyncio
    async def test_compare_experiments(
        self, experiment_runner, test_report, eval_dataset
    ):
        examples = export_dataset(eval_dataset)

        runs_a = [
            {
                "example_id": ex["id"],
                "output": ex.get("expected_answer", ""),
                "evaluations": {
                    "correctness": {"label": "correct", "score": 1.0}
                },
            }
            for ex in examples
        ]
        runs_b = [
            {
                "example_id": ex["id"],
                "output": "wrong answer",
                "evaluations": {
                    "correctness": {"label": "incorrect", "score": 0.0}
                },
            }
            for ex in examples
        ]

        exp_a = create_experiment(
            f"compare-a-{uuid.uuid4().hex[:8]}", eval_dataset, runs_a
        )
        exp_b = create_experiment(
            f"compare-b-{uuid.uuid4().hex[:8]}", eval_dataset, runs_b
        )

        try:
            result = await experiment_runner.run(
                f"Compare experiments {exp_a} and {exp_b}. "
                f"Which one performed better on correctness?"
            )
            verifier = CompositeVerifier(
                NoErrorVerifier(),
                ToolWasCalledVerifier(["Bash"]),
                OutputContainsVerifier(["better", "correctness"]),
            )
            result.verification = verifier.verify(result)
            result.tags = ["e2e", "experiment-compare"]
            test_report.add(result)
            assert result.passed
        finally:
            delete_experiment(exp_a)
            delete_experiment(exp_b)
