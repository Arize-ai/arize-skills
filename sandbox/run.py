#!/usr/bin/env python3
"""Standalone runner for quick iteration and demos.

Usage:
    python run.py --app langchain-py --verbose
"""

import argparse
import sys
import tempfile
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.config import SUPPORTED_APPS
from src.evaluator import evaluate_instrumentation
from src.runner import run_agent
from src.sandbox import audit_workspace, create_sandbox


def main():
    parser = argparse.ArgumentParser(description="Arize Skill Sandbox Runner")
    parser.add_argument(
        "--app",
        choices=list(SUPPORTED_APPS.keys()),
        default="langchain-py",
        help="Which Rosetta Stone app to instrument (default: langchain-py)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print agent output in real-time",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Custom prompt for the agent (overrides default)",
    )
    args = parser.parse_args()

    print(f"Setting up sandbox for {args.app}...")
    with tempfile.TemporaryDirectory(prefix="skill-sandbox-") as tmp_dir:
        workspace = create_sandbox(Path(tmp_dir), app_name=args.app)
        print(f"Workspace: {workspace}")

        print(f"\nRunning agent...")
        kwargs = {"workspace": workspace, "verbose": args.verbose}
        if args.prompt:
            kwargs["prompt"] = args.prompt

        result = run_agent(**kwargs)

        if result.is_error:
            print(f"\nAgent errored!")
            print(result.text_output[-1000:])
            sys.exit(1)

        # Security audit
        warnings = audit_workspace(workspace, result.tool_calls)
        if warnings:
            print(f"\nSECURITY WARNINGS:")
            for w in warnings:
                print(f"  - {w}")

        print(f"\nAgent finished. Evaluating...")
        eval_result = evaluate_instrumentation(
            workspace=workspace,
            framework=args.app,
            run_result=result,
        )

        print(f"\n{'='*60}")
        print(f"  EVALUATION RESULTS: {args.app}")
        print(f"{'='*60}")
        print(f"  tracing.py exists:          {'PASS' if eval_result.tracing_file_exists else 'FAIL'}")
        print(f"  tracing.py has register():  {'PASS' if eval_result.tracing_file_has_register else 'FAIL'}")
        print(f"  tracing.py has instrumentor:{'PASS' if eval_result.tracing_file_has_instrumentor else 'FAIL'}")
        print(f"  main.py imports tracing:    {'PASS' if eval_result.main_imports_tracing else 'FAIL'}")
        print(f"  requirements has packages:  {'PASS' if eval_result.requirements_has_packages else 'FAIL'}")
        print(f"  business logic unchanged:   {'PASS' if eval_result.business_logic_unchanged else 'FAIL'}")
        print(f"  ground truth similarity:    {eval_result.ground_truth_similarity:.2f}")
        print(f"{'='*60}")
        print(f"  Cost:     ${eval_result.agent_cost_usd:.4f}")
        print(f"  Tokens:   {eval_result.agent_tokens:,}")
        print(f"  Duration: {eval_result.agent_duration_ms:,}ms")
        print(f"  Turns:    {eval_result.agent_num_turns}")
        print(f"{'='*60}")

        overall = "PASS" if eval_result.structural_pass else "FAIL"
        print(f"\n  Overall: {overall}\n")

        sys.exit(0 if eval_result.structural_pass else 1)


if __name__ == "__main__":
    main()
