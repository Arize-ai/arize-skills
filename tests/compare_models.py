"""
Run skill selection tests across multiple models and compare results.

Usage:
    python tests/compare_models.py

Generates a comparison report in test-results/model_comparison_<ts>.json

Requires:
    ANTHROPIC_API_KEY environment variable set.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness.skill_router import SkillSelectionRunner
from test_skill_selection import (
    MULTI_SKILL_PROMPTS,
    NEGATIVE_PROMPTS,
    SPECIFIC_PROMPTS,
    VAGUE_PROMPTS,
)

MODELS_TO_COMPARE = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]

ALL_PROMPTS = (
    [(p, e, t) for p, e, t in SPECIFIC_PROMPTS]
    + [(p, e, t) for p, e, t in VAGUE_PROMPTS]
    + [(p, e, t) for p, e, t in MULTI_SKILL_PROMPTS]
    + [(p, e, t) for p, e, t in NEGATIVE_PROMPTS]
)


async def run_model(model: str) -> dict:
    """Run all prompts through a single model and return results."""
    print(f"\n{'=' * 60}")
    print(f"Testing model: {model}")
    print(f"{'=' * 60}")

    runner = SkillSelectionRunner(model=model, max_budget_usd=0.10)
    results = []
    correct = 0
    total = 0

    for i, (prompt, expected_skills, tags) in enumerate(ALL_PROMPTS):
        total += 1
        try:
            result = await runner.test_prompt(prompt, expected_skills, tags)
            results.append(result.to_dict())
            if result.correct:
                correct += 1
            status = "PASS" if result.correct else "FAIL"
            print(
                f"  [{i + 1}/{len(ALL_PROMPTS)}] {status} | "
                f"Expected: {expected_skills} | "
                f"Got: {result.selected_skills} | "
                f"${result.total_cost_usd or 0:.4f}"
            )
        except Exception as e:
            print(f"  [{i + 1}/{len(ALL_PROMPTS)}] ERROR: {e}")
            results.append(
                {
                    "prompt": prompt,
                    "expected_skills": expected_skills,
                    "selected_skills": [],
                    "correct": False,
                    "error": str(e),
                    "model": model,
                    "tags": tags,
                }
            )

    # Accuracy by category
    by_category: dict[str, dict[str, int | float]] = {}
    for r in results:
        for tag in r.get("tags", []):
            if tag not in by_category:
                by_category[tag] = {"total": 0, "correct": 0}
            by_category[tag]["total"] += 1
            if r.get("correct"):
                by_category[tag]["correct"] += 1

    for cat in by_category.values():
        cat["accuracy"] = (
            round(cat["correct"] / cat["total"], 4) if cat["total"] else 0
        )

    total_cost = sum(r.get("total_cost_usd") or 0 for r in results)

    return {
        "model": model,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0,
        "total_cost_usd": round(total_cost, 4),
        "by_category": by_category,
        "results": results,
    }


async def main():
    models_to_test = MODELS_TO_COMPARE
    if len(sys.argv) > 1:
        models_to_test = sys.argv[1:]

    all_model_results = []
    for model in models_to_test:
        model_result = await run_model(model)
        all_model_results.append(model_result)

    # Print comparison table
    print(f"\n{'=' * 80}")
    print("MODEL COMPARISON")
    print(f"{'=' * 80}")
    print(f"{'Model':<35} {'Accuracy':>10} {'Cost':>10} {'Correct':>10}")
    print(f"{'-' * 35} {'-' * 10} {'-' * 10} {'-' * 10}")
    for r in all_model_results:
        print(
            f"{r['model']:<35} {r['accuracy']:>9.1%} "
            f"${r['total_cost_usd']:>8.4f} "
            f"{r['correct']}/{r['total']:>7}"
        )

    # Category breakdown
    categories = ["specific", "vague", "multi", "negative"]
    print(f"\n{'Category Breakdown':}")
    print(f"{'Model':<35}", end="")
    for cat in categories:
        print(f" {cat:>10}", end="")
    print()
    print("-" * (35 + 11 * len(categories)))
    for r in all_model_results:
        print(f"{r['model']:<35}", end="")
        for cat in categories:
            acc = r["by_category"].get(cat, {}).get("accuracy", 0)
            print(f" {acc:>9.1%}", end="")
        print()

    # Save report
    report_dir = os.environ.get("SKILL_TESTS_REPORT_DIR", "test-results")
    os.makedirs(report_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(report_dir, f"model_comparison_{ts}.json")

    report = {
        "timestamp": datetime.now().isoformat(),
        "models_compared": [r["model"] for r in all_model_results],
        "summary": [
            {
                "model": r["model"],
                "accuracy": r["accuracy"],
                "total_cost_usd": r["total_cost_usd"],
                "correct": r["correct"],
                "total": r["total"],
                "by_category": r["by_category"],
            }
            for r in all_model_results
        ],
        "detailed_results": all_model_results,
    }

    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nDetailed report saved to: {path}")


if __name__ == "__main__":
    asyncio.run(main())
