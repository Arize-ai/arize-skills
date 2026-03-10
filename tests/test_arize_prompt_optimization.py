"""
Test cases for the arize-prompt-optimization skill.
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
def prompt_opt_runner(workspace, arize_env, test_model):
    return make_runner(
        "arize-prompt-optimization",
        workspace,
        arize_env,
        test_model,
        max_turns=60,
        max_budget_usd=2.0,
    )


@pytest.fixture
def optimization_dataset_and_experiment(arize_space_id):
    """Create a dataset and a baseline experiment with poor results."""
    ds_id = create_dataset(
        name=f"opt-test-{uuid.uuid4().hex[:8]}",
        space_id=arize_space_id,
        examples=[
            {"input": "Classify: I love this!", "expected_output": "positive"},
            {
                "input": "Classify: Terrible experience",
                "expected_output": "negative",
            },
            {
                "input": "Classify: It was okay I guess",
                "expected_output": "neutral",
            },
            {
                "input": "Classify: Absolutely wonderful!",
                "expected_output": "positive",
            },
            {"input": "Classify: Worst ever", "expected_output": "negative"},
        ],
    )
    examples = export_dataset(ds_id)
    runs = [
        {
            "example_id": ex["id"],
            "output": "The sentiment is positive.",
            "evaluations": {
                "correctness": {
                    "label": (
                        "incorrect"
                        if ex["expected_output"] != "positive"
                        else "correct"
                    ),
                    "score": (
                        1.0 if ex["expected_output"] == "positive" else 0.0
                    ),
                    "explanation": (
                        "Model always says positive regardless of input."
                        if ex["expected_output"] != "positive"
                        else "Correct by chance."
                    ),
                }
            },
        }
        for ex in examples
    ]
    exp_id = create_experiment(
        f"baseline-{uuid.uuid4().hex[:8]}", ds_id, runs
    )

    yield ds_id, exp_id

    delete_experiment(exp_id)
    delete_dataset(ds_id)


class TestPromptOptimizationFromExperiment:
    """Optimize a prompt based on experiment results."""

    @pytest.mark.asyncio
    async def test_optimize_from_experiment_data(
        self,
        prompt_opt_runner,
        test_report,
        optimization_dataset_and_experiment,
    ):
        ds_id, exp_id = optimization_dataset_and_experiment

        result = await prompt_opt_runner.run(
            f"Optimize the prompt for the experiment {exp_id} against "
            f"dataset {ds_id}. The current prompt always outputs 'positive' "
            f"regardless of input. Produce a revised prompt that correctly "
            f"classifies sentiment."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
            OutputContainsVerifier(
                ["sentiment", "positive", "negative"]
            ),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "prompt-optimization"]
        test_report.add(result)
        assert result.passed


class TestPromptOptimizationVariablePreservation:
    """Verify that optimization preserves template variables."""

    @pytest.mark.asyncio
    async def test_preserves_template_variables(
        self,
        prompt_opt_runner,
        test_report,
        optimization_dataset_and_experiment,
    ):
        ds_id, exp_id = optimization_dataset_and_experiment

        result = await prompt_opt_runner.run(
            f"The current system prompt is: "
            f"'Classify the sentiment of {{text}} as positive, negative, or neutral.' "
            f"Optimize this prompt using experiment {exp_id} and dataset {ds_id}. "
            f"Make sure to preserve the {{text}} template variable."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            OutputContainsVerifier(["{text}"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed
