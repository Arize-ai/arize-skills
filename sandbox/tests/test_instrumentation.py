"""End-to-end test: agent instruments a LangChain app using the arize-instrumentation skill."""

import pytest

from src.evaluator import evaluate_instrumentation
from src.runner import run_agent
from src.sandbox import audit_workspace


class TestInstrumentationSkill:

    @pytest.mark.timeout(300)
    def test_langchain_py_instrumentation(self, sandbox_workspace):
        """Agent should correctly instrument the langchain-py app."""
        # Run the agent
        result = run_agent(
            workspace=sandbox_workspace,
            prompt=(
                "Instrument this Python app with Arize AX tracing. "
                "Analyze the codebase first, then implement. "
                "Use the arize-instrumentation skill in .claude/skills/arize-instrumentation/."
            ),
            verbose=True,
        )

        # Agent should complete without error
        assert not result.is_error, f"Agent errored: {result.text_output[-500:]}"

        # Security audit: check for suspicious file access
        warnings = audit_workspace(sandbox_workspace, result.tool_calls)
        for w in warnings:
            print(f"SECURITY WARNING: {w}")

        # Evaluate correctness
        eval_result = evaluate_instrumentation(
            workspace=sandbox_workspace,
            framework="langchain-py",
            run_result=result,
        )

        # Structural checks
        assert eval_result.tracing_file_exists, "tracing.py not created"
        assert eval_result.tracing_file_has_register, "tracing.py missing register() call"
        assert eval_result.tracing_file_has_instrumentor, "tracing.py missing LangChainInstrumentor"
        assert eval_result.main_imports_tracing, "main.py does not import tracing"
        assert eval_result.requirements_has_packages, "requirements.txt missing required packages"
        assert eval_result.business_logic_unchanged, "Business logic files were modified"

        # Report metrics
        print(f"\n{'='*50}")
        print(f"Cost: ${eval_result.agent_cost_usd:.4f}")
        print(f"Tokens: {eval_result.agent_tokens}")
        print(f"Duration: {eval_result.agent_duration_ms}ms")
        print(f"Turns: {eval_result.agent_num_turns}")
        print(f"Ground truth similarity: {eval_result.ground_truth_similarity:.2f}")
        print(f"{'='*50}")
