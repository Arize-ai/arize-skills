# Arize Skills Test Suite

## Overview

A test harness that runs Claude Code programmatically via the Claude Agent SDK to evaluate Arize agent skills. It measures:

1. **Correctness** — whether Claude solves the problem
2. **Token usage** — input, output, and cache tokens
3. **Duration** — wall-clock time per test

Additionally, a **skill selection** test suite evaluates whether Claude picks the correct skill for vague, specific, and multi-skill prompts, with cross-model comparison support.

## Harness (`tests/harness/`)

| File | Purpose |
|------|---------|
| `runner.py` | `SkillTestRunner` — runs Claude Code via `query()`, captures duration/tokens/cost |
| `result.py` | `TestResult` + `VerificationResult` dataclasses, JSON-serializable |
| `verifier.py` | 8 composable verifiers (NoError, OutputContains, Regex, ToolWasCalled, FileExists, AxResourceExists, URLFormat, Composite) |
| `ax_helpers.py` | `ax` CLI wrappers for setup/teardown (create/delete datasets, experiments, export traces) |
| `report.py` | `TestReport` — aggregates results, saves JSON with per-skill breakdown |
| `skill_router.py` | `SkillSelectionRunner` — lightweight skill routing tests (which skill does Claude pick?) |

## Skill Tests (21 test cases across 6 skills)

| Test File | What It Covers |
|-----------|-----------------|
| `test_arize_trace.py` | Prerequisite check, export by ID, filter errors, session export, debug workflow |
| `test_arize_dataset.py` | Create dataset, list datasets, export + analyze, append examples |
| `test_arize_experiment.py` | Create experiment, list experiments, compare two experiments |
| `test_arize_instrumentation.py` | Analysis only, full instrumentation, tool-calling app instrumentation |
| `test_arize_prompt_optimization.py` | Optimize from experiment data, template variable preservation |
| `test_arize_link.py` | Trace link, span link, session link, links from exported data |

## Skill Selection Tests

| File | Purpose |
|------|---------|
| `test_skill_selection.py` | Specific, vague, multi-skill, negative prompts — evaluates skill routing accuracy |
| `compare_models.py` | Runs all prompts across haiku/sonnet/opus, prints comparison table and saves JSON report |

### Prompt Categories

- **Specific** — clear, unambiguous prompts (e.g., "Export the traces from my project")
- **Vague** — ambiguous prompts requiring inference (e.g., "Something is broken in my app")
- **Multi-skill** — prompts needing multiple skills (e.g., "Export traces, then create a dataset from the errors")
- **Negative** — irrelevant prompts that should not match any skill (e.g., "What's the weather today?")

## Example Faulty Applications (`tests/example_apps/`)

These apps produce real traces with intentional errors for testing the trace/debug skills.

| App | Error Modes | Arize Project |
|-----|-------------|---------------|
| `openai_rag_app/app.py` | 30% retrieval miss rate, hallucinated answers on empty context | `skill-test-rag-app` |
| `tool_calling_agent/app.py` | `ValueError` on un-normalized rate, malformed JSON, max iteration exceeded | `skill-test-tool-agent` |
| `multi_turn_chatbot/app.py` | Oversized input triggering context overflow, session tracking | `skill-test-chatbot` |
| `run_all.py` | Runs all apps sequentially, waits 30s for trace ingestion | — |

## Prerequisites

```bash
pip install -r tests/requirements.txt
pip install -r tests/example_apps/requirements.txt
```

Environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | For Claude Agent SDK |
| `ARIZE_API_KEY` | Yes | For `ax` CLI and example apps |
| `ARIZE_SPACE_ID` | Yes | Arize space identifier |
| `OPENAI_API_KEY` | For example apps | Used by RAG app, tool agent, chatbot |
| `TEST_PROJECT_NAME` | No | Arize project name (default: `skill-tests`) |
| `TEST_MODEL` | No | Claude model override (e.g., `claude-sonnet-4-6`) |
| `SKILL_TESTS_REPORT_DIR` | No | Report output directory (default: `test-results/`) |

## Running

```bash
# 1. Generate traces (run once before first test run)
python tests/example_apps/run_all.py

# 2. Run all skill tests
pytest tests/ -v --timeout=300

# 3. Run tests for a single skill
pytest tests/test_arize_trace.py -v

# 4. Run skill selection tests only
pytest tests/test_skill_selection.py -v

# 5. Run with a specific model
TEST_MODEL=claude-sonnet-4-6 pytest tests/ -v

# 6. Compare models on skill selection
python tests/compare_models.py

# 7. Compare specific models
python tests/compare_models.py claude-haiku-4-5-20251001 claude-sonnet-4-6
```

## Reports

Test reports are saved as JSON to `test-results/`:

- `report_YYYYMMDD_HHMMSS.json` — full skill test results with per-skill breakdown
- `skill_selection_<model>_YYYYMMDD_HHMMSS.json` — skill selection accuracy per model
- `model_comparison_YYYYMMDD_HHMMSS.json` — cross-model comparison from `compare_models.py`

### Report Structure

```json
{
  "summary": {
    "total_tests": 21,
    "passed": 19,
    "failed": 2,
    "pass_rate": 0.9048,
    "total_cost_usd": 4.52,
    "total_input_tokens": 1250000,
    "total_output_tokens": 85000,
    "avg_wall_duration_ms": 45000,
    "by_skill": {
      "arize-trace": { "total": 5, "passed": 5, "failed": 0, "cost_usd": 0.80 },
      "arize-link": { "total": 4, "passed": 4, "failed": 0, "cost_usd": 0.12 }
    }
  },
  "results": [ ... ]
}
```
