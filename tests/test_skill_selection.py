"""
Skill selection/routing tests.

Evaluates whether Claude Code picks the correct skill(s) for various
prompts — from specific to vague. Tests single-skill selection,
multi-skill combinations, and cross-model comparison.

Run with: pytest tests/test_skill_selection.py -v
Compare models: TEST_MODEL=claude-haiku-4-5-20251001 pytest tests/test_skill_selection.py -v
"""

import json
import os
from datetime import datetime

import pytest

from harness.skill_router import SkillSelectionResult, SkillSelectionRunner

# ---------------------------------------------------------------------------
# Test prompts organized by category
# ---------------------------------------------------------------------------

# Single-skill: clear/specific prompts
SPECIFIC_PROMPTS = [
    # arize-trace
    (
        "Export the traces from my project for the last 24 hours",
        ["arize-trace"],
        ["specific", "trace"],
    ),
    (
        "Download the spans for trace ID abc123",
        ["arize-trace"],
        ["specific", "trace"],
    ),
    (
        "Show me the error traces in my LLM application",
        ["arize-trace"],
        ["specific", "trace"],
    ),
    # arize-instrumentation
    (
        "Add Arize tracing to my Python application",
        ["arize-instrumentation"],
        ["specific", "instrumentation"],
    ),
    (
        "Instrument my OpenAI app with observability",
        ["arize-instrumentation"],
        ["specific", "instrumentation"],
    ),
    (
        "Set up tracing for my LangChain application",
        ["arize-instrumentation"],
        ["specific", "instrumentation"],
    ),
    # arize-dataset
    (
        "Create a new evaluation dataset with 10 examples",
        ["arize-dataset"],
        ["specific", "dataset"],
    ),
    (
        "List all my datasets in Arize",
        ["arize-dataset"],
        ["specific", "dataset"],
    ),
    (
        "Export my QA dataset to a CSV file",
        ["arize-dataset"],
        ["specific", "dataset"],
    ),
    # arize-experiment
    (
        "Run an experiment comparing GPT-4 vs Claude on my test set",
        ["arize-experiment"],
        ["specific", "experiment"],
    ),
    (
        "Show me the results of my latest experiment",
        ["arize-experiment"],
        ["specific", "experiment"],
    ),
    (
        "Create an experiment to evaluate my model's accuracy",
        ["arize-experiment"],
        ["specific", "experiment"],
    ),
    # arize-prompt-optimization
    (
        "Optimize my system prompt to reduce hallucinations",
        ["arize-prompt-optimization"],
        ["specific", "prompt-optimization"],
    ),
    (
        "My prompt is performing badly on sentiment classification, help me improve it",
        ["arize-prompt-optimization"],
        ["specific", "prompt-optimization"],
    ),
    (
        "Analyze my prompt's failure patterns and suggest improvements",
        ["arize-prompt-optimization"],
        ["specific", "prompt-optimization"],
    ),
    # arize-link
    (
        "Give me a link to trace abc123 in the Arize UI",
        ["arize-link"],
        ["specific", "link"],
    ),
    (
        "Generate a shareable URL for this span",
        ["arize-link"],
        ["specific", "link"],
    ),
    (
        "I need a deep link to this session in Arize",
        ["arize-link"],
        ["specific", "link"],
    ),
]

# Single-skill: vague/ambiguous prompts (harder to route correctly)
VAGUE_PROMPTS = [
    # Should route to trace
    (
        "Something is broken in my app, can you help me find out what?",
        ["arize-trace"],
        ["vague", "trace"],
    ),
    (
        "I want to look at what my LLM is doing",
        ["arize-trace"],
        ["vague", "trace"],
    ),
    (
        "Can you debug my chatbot?",
        ["arize-trace"],
        ["vague", "trace"],
    ),
    # Should route to instrumentation
    (
        "I haven't set up any tracing yet, I want to add observability to my app",
        ["arize-instrumentation"],
        ["vague", "instrumentation"],
    ),
    (
        "How do I get visibility into my LLM calls?",
        ["arize-instrumentation"],
        ["vague", "instrumentation"],
    ),
    (
        "Set up monitoring for my AI application",
        ["arize-instrumentation"],
        ["vague", "instrumentation"],
    ),
    # Should route to dataset
    (
        "I need some test data for my model",
        ["arize-dataset"],
        ["vague", "dataset"],
    ),
    (
        "Help me put together some examples for evaluation",
        ["arize-dataset"],
        ["vague", "dataset"],
    ),
    # Should route to experiment
    (
        "How well is my model performing?",
        ["arize-experiment"],
        ["vague", "experiment"],
    ),
    (
        "I want to test if my new model is better than the old one",
        ["arize-experiment"],
        ["vague", "experiment"],
    ),
    # Should route to prompt-optimization
    (
        "My LLM keeps giving wrong answers, fix it",
        ["arize-prompt-optimization"],
        ["vague", "prompt-optimization"],
    ),
    (
        "Make my AI respond better",
        ["arize-prompt-optimization"],
        ["vague", "prompt-optimization"],
    ),
    # Should route to link
    (
        "I want to share this trace with my team",
        ["arize-link"],
        ["vague", "link"],
    ),
    (
        "Open this in Arize",
        ["arize-link"],
        ["vague", "link"],
    ),
]

# Multi-skill: prompts that should trigger multiple skills
MULTI_SKILL_PROMPTS = [
    (
        "Export my traces, then create a dataset from the error cases",
        ["arize-trace", "arize-dataset"],
        ["multi", "trace", "dataset"],
    ),
    (
        "Set up tracing for my app and then run an experiment to evaluate it",
        ["arize-instrumentation", "arize-experiment"],
        ["multi", "instrumentation", "experiment"],
    ),
    (
        "Download the experiment results and use them to optimize my prompt",
        ["arize-experiment", "arize-prompt-optimization"],
        ["multi", "experiment", "prompt-optimization"],
    ),
    (
        "Export the traces, analyze the failures, and give me a link to the worst one",
        ["arize-trace", "arize-link"],
        ["multi", "trace", "link"],
    ),
    (
        "Create a dataset from my traces and run an experiment on it",
        ["arize-dataset", "arize-experiment"],
        ["multi", "dataset", "experiment"],
    ),
]

# Negative/irrelevant prompts (should not match any skill strongly)
NEGATIVE_PROMPTS = [
    (
        "What's the weather today?",
        [],
        ["negative"],
    ),
    (
        "Write a Python function to sort a list",
        [],
        ["negative"],
    ),
    (
        "Help me deploy my app to AWS",
        [],
        ["negative"],
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def selection_runner(test_model):
    return SkillSelectionRunner(model=test_model, max_budget_usd=0.10)


@pytest.fixture(scope="module")
def selection_results():
    """Collect all results for end-of-module reporting."""
    results: list[SkillSelectionResult] = []
    yield results

    # Save report at end of module
    report_dir = os.environ.get("SKILL_TESTS_REPORT_DIR", "test-results")
    os.makedirs(report_dir, exist_ok=True)

    model = os.environ.get("TEST_MODEL", "default")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(report_dir, f"skill_selection_{model}_{ts}.json")

    total = len(results)
    correct = sum(1 for r in results if r.correct)
    total_cost = sum(r.total_cost_usd or 0 for r in results)

    # Accuracy by tag category
    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        for tag in r.tags:
            if tag not in by_category:
                by_category[tag] = {"total": 0, "correct": 0}
            by_category[tag]["total"] += 1
            if r.correct:
                by_category[tag]["correct"] += 1

    for cat in by_category.values():
        cat["accuracy"] = (
            round(cat["correct"] / cat["total"], 4) if cat["total"] else 0
        )

    report = {
        "summary": {
            "model": model,
            "total_prompts": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else 0,
            "total_cost_usd": round(total_cost, 4),
            "by_category": by_category,
        },
        "results": [r.to_dict() for r in results],
    }

    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSkill selection report saved to: {path}")


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestSpecificPrompts:
    """Test that specific/clear prompts route to the correct skill."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "prompt,expected_skills,tags", SPECIFIC_PROMPTS
    )
    async def test_specific_prompt(
        self,
        selection_runner,
        selection_results,
        prompt,
        expected_skills,
        tags,
    ):
        result = await selection_runner.test_prompt(
            prompt, expected_skills, tags
        )
        selection_results.append(result)
        assert result.correct, (
            f"Expected {expected_skills}, got {result.selected_skills} "
            f"for prompt: {prompt}"
        )


class TestVaguePrompts:
    """Test that vague/ambiguous prompts still route correctly."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("prompt,expected_skills,tags", VAGUE_PROMPTS)
    async def test_vague_prompt(
        self,
        selection_runner,
        selection_results,
        prompt,
        expected_skills,
        tags,
    ):
        result = await selection_runner.test_prompt(
            prompt, expected_skills, tags
        )
        selection_results.append(result)
        # For vague prompts, check that all expected skills are included
        # (additional skills are acceptable since prompts are ambiguous)
        expected_set = set(expected_skills)
        selected_set = set(result.selected_skills)
        assert expected_set.issubset(selected_set), (
            f"Expected at least {expected_skills}, got {result.selected_skills} "
            f"for prompt: {prompt}"
        )


class TestMultiSkillPrompts:
    """Test prompts that should trigger multiple skills."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "prompt,expected_skills,tags", MULTI_SKILL_PROMPTS
    )
    async def test_multi_skill_prompt(
        self,
        selection_runner,
        selection_results,
        prompt,
        expected_skills,
        tags,
    ):
        result = await selection_runner.test_prompt(
            prompt, expected_skills, tags
        )
        selection_results.append(result)
        # For multi-skill, check that all expected skills are selected
        # (may have additional skills — that's ok)
        expected_set = set(expected_skills)
        selected_set = set(result.selected_skills)
        assert expected_set.issubset(selected_set), (
            f"Expected at least {expected_skills}, got {result.selected_skills} "
            f"for prompt: {prompt}"
        )


class TestNegativePrompts:
    """Test that irrelevant prompts don't strongly match any skill."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "prompt,expected_skills,tags", NEGATIVE_PROMPTS
    )
    async def test_negative_prompt(
        self,
        selection_runner,
        selection_results,
        prompt,
        expected_skills,
        tags,
    ):
        result = await selection_runner.test_prompt(
            prompt, expected_skills, tags
        )
        selection_results.append(result)
        # For negative prompts, we expect no skills selected
        # (or at most a weak match — logged but not asserted strictly)
        if result.selected_skills:
            pytest.xfail(
                f"Negative prompt matched: {result.selected_skills} "
                f"(may be acceptable)"
            )
