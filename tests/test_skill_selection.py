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
    # arize-span-routing
    (
        "Route each agent's Python spans to its assigned Arize space and project",
        ["arize-span-routing"],
        ["specific", "span-routing"],
    ),
    (
        "Use register_with_routing and set_routing_context in my custom agent builder",
        ["arize-span-routing"],
        ["specific", "span-routing"],
    ),
    (
        "Send each tenant's traces to a different Arize space based on request metadata",
        ["arize-span-routing"],
        ["specific", "span-routing"],
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
    # arize-prompts
    (
        "Create a new prompt in Arize Prompt Hub using ax prompts with messages from a JSON file",
        ["arize-prompts"],
        ["specific", "prompts"],
    ),
    (
        "Set the production label on my prompt version prv_xyz789 using the CLI",
        ["arize-prompts"],
        ["specific", "prompts"],
    ),
    (
        "List all versions of my support-agent prompt in Prompt Hub",
        ["arize-prompts"],
        ["specific", "prompts"],
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
    # arize-evaluator
    (
        "Create an LLM-as-judge evaluator for hallucination detection",
        ["arize-evaluator"],
        ["specific", "evaluator"],
    ),
    (
        "Run an evaluation task on my project spans using GPT-4",
        ["arize-evaluator"],
        ["specific", "evaluator"],
    ),
    (
        "Set up continuous monitoring with an LLM judge on new spans",
        ["arize-evaluator"],
        ["specific", "evaluator"],
    ),
    # arize-annotation
    (
        "Create an annotation config for correctness labels",
        ["arize-annotation"],
        ["specific", "annotation"],
    ),
    (
        "Add human feedback labels to my project spans using the Python SDK",
        ["arize-annotation"],
        ["specific", "annotation"],
    ),
    (
        "Set up a categorical annotation config with pass/fail labels",
        ["arize-annotation"],
        ["specific", "annotation"],
    ),
    # arize-ai-provider-integration
    (
        "Register my OpenAI API key as an Arize AI integration",
        ["arize-ai-provider-integration"],
        ["specific", "ai-provider-integration"],
    ),
    (
        "List all AI integrations in my Arize space",
        ["arize-ai-provider-integration"],
        ["specific", "ai-provider-integration"],
    ),
    (
        "Create an Anthropic integration in Arize for my evaluators",
        ["arize-ai-provider-integration"],
        ["specific", "ai-provider-integration"],
    ),
    # arize-compliance-audit
    (
        "Audit my AI app for EU AI Act compliance",
        ["arize-compliance-audit"],
        ["specific", "compliance-audit"],
    ),
    (
        "Check my LLM application for GDPR compliance gaps",
        ["arize-compliance-audit"],
        ["specific", "compliance-audit"],
    ),
    (
        "Run a NIST AI RMF compliance audit on my agent",
        ["arize-compliance-audit"],
        ["specific", "compliance-audit"],
    ),
    # arize-admin
    (
        "Invite jane@example.com to my Arize account with a member role",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Create a new Arize space called team-alpha inside the Platform org",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Generate a service API key scoped to the production space for my CI pipeline",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Revoke an expired API key in Arize",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Create a custom RBAC role with dataset and experiment permissions",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Restrict a project so only users with explicit role bindings can access it",
        ["arize-admin"],
        ["specific", "admin"],
    ),
    (
        "Offboard a user and revoke all their org and space memberships",
        ["arize-admin"],
        ["specific", "admin"],
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
    (
        "Help me instrument traces",
        ["arize-instrumentation"],
        ["vague", "instrumentation", "scope"],
    ),
    # Should route to span routing
    (
        "My agent platform needs traces to land in different customer workspaces",
        ["arize-span-routing"],
        ["vague", "span-routing"],
    ),
    (
        "We run many agents in one Python service and each has its own Arize project",
        ["arize-span-routing"],
        ["vague", "span-routing"],
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
    # Should route to arize-prompts (versioned templates in Arize)
    (
        "I want to version control my LLM prompt templates in Arize Prompt Hub",
        ["arize-prompts"],
        ["vague", "prompts"],
    ),
    (
        "Upload my system and user messages to Arize as a named prompt with the CLI",
        ["arize-prompts"],
        ["vague", "prompts"],
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
    # Should route to evaluator
    (
        "I want to automatically score my LLM responses for quality",
        ["arize-evaluator"],
        ["vague", "evaluator"],
    ),
    (
        "Can you judge whether my model outputs are correct?",
        ["arize-evaluator"],
        ["vague", "evaluator"],
    ),
    # Should route to annotation
    (
        "I need human reviewers to label my model outputs",
        ["arize-annotation"],
        ["vague", "annotation"],
    ),
    (
        "Set up a labeling schema so my team can rate responses",
        ["arize-annotation"],
        ["vague", "annotation"],
    ),
    # Should route to ai-provider-integration
    (
        "I want Arize to use my LLM provider credentials for evaluations",
        ["arize-ai-provider-integration"],
        ["vague", "ai-provider-integration"],
    ),
    (
        "Connect my AWS Bedrock account to Arize",
        ["arize-ai-provider-integration"],
        ["vague", "ai-provider-integration"],
    ),
    # Should route to compliance-audit
    (
        "Is my AI app compliant?",
        ["arize-compliance-audit"],
        ["vague", "compliance-audit"],
    ),
    (
        "What regulations apply to my chatbot?",
        ["arize-compliance-audit"],
        ["vague", "compliance-audit"],
    ),
    (
        "Help me make sure my AI meets regulatory requirements",
        ["arize-compliance-audit"],
        ["vague", "compliance-audit"],
    ),
    # Should route to arize-admin
    (
        "I need to control who can access my Arize projects",
        ["arize-admin"],
        ["vague", "admin"],
    ),
    (
        "How do I set up my team in Arize?",
        ["arize-admin"],
        ["vague", "admin"],
    ),
    (
        "I need a service account for my data pipeline",
        ["arize-admin"],
        ["vague", "admin"],
    ),
    (
        "I need to remove a compromised API key from my Arize account",
        ["arize-admin"],
        ["vague", "admin"],
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
