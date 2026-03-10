# Development Guide

## Adding a New Skill

### 1. Create the skill directory

```bash
mkdir skills/<skill-name>
```

The directory name must be **kebab-case** (lowercase letters, digits, hyphens, starting with a letter).

### 2. Write `SKILL.md`

Create `skills/<skill-name>/SKILL.md` with YAML frontmatter:

```markdown
---
name: <skill-name>
description: "A clear description of when this skill should be invoked (10–500 chars)"
---

# Skill Title

Your skill instructions go here. This content becomes the system prompt
when the skill is invoked by Claude Code, Cursor, or other agents.

## Prerequisites
- List what the user needs installed (e.g., `ax` CLI, API keys)

## Usage
- Document the commands and workflows the skill supports
- Include code blocks with example `ax` CLI commands
- Add troubleshooting tables for common errors
```

### 3. Validate

```bash
pip install -r scripts/requirements.txt
python scripts/validate_skills.py
```

The validator checks:

| Rule | Requirement |
|------|-------------|
| File exists | `skills/<name>/SKILL.md` must exist |
| Frontmatter | Must have opening and closing `---` delimiters |
| `name` field | Required, kebab-case, must match directory name |
| `description` field | Required, 10–500 characters |

### 4. Add tests

Create a test file at `tests/test_<skill_name_with_underscores>.py`. Follow the pattern of existing tests:

```python
import pytest
from conftest import make_runner
from harness.verifier import CompositeVerifier, NoErrorVerifier, ToolWasCalledVerifier

@pytest.fixture
def my_runner(workspace, arize_env, test_model):
    return make_runner("my-skill-name", workspace, arize_env, test_model)

class TestMySkillBasic:
    @pytest.mark.asyncio
    async def test_basic_workflow(self, my_runner, test_report):
        result = await my_runner.run("Your test prompt here")
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Bash"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed
```

### 5. Add skill selection prompts

Add test prompts to `tests/test_skill_selection.py` in the appropriate category:

```python
SPECIFIC_PROMPTS = [
    # ... existing prompts ...
    ("A clear prompt that should trigger my-skill", ["my-skill-name"], ["specific", "my-skill"]),
]

VAGUE_PROMPTS = [
    # ... existing prompts ...
    ("A vague prompt that should still route to my-skill", ["my-skill-name"], ["vague", "my-skill"]),
]
```

Also update the `SELECTION_SYSTEM_PROMPT` in `tests/harness/skill_router.py` to include the new skill's name and description.

### 6. Install and test locally

```bash
./install.sh --project .
```

## Running Tests

### Prerequisites

```bash
# Test harness dependencies
pip install -r tests/requirements.txt

# Example app dependencies (only needed for trace generation)
pip install -r tests/example_apps/requirements.txt
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | For Claude Agent SDK |
| `ARIZE_API_KEY` | Yes | For `ax` CLI and example apps |
| `ARIZE_SPACE_ID` | Yes | Arize space identifier |
| `OPENAI_API_KEY` | For example apps | Used by the faulty example applications |
| `TEST_PROJECT_NAME` | No | Arize project name (default: `skill-tests`) |
| `TEST_MODEL` | No | Claude model override (e.g., `claude-sonnet-4-6`) |
| `SKILL_TESTS_REPORT_DIR` | No | Report output directory (default: `test-results/`) |

### Generate test traces

Run the example faulty applications once to populate Arize with trace data. This is required before running `test_arize_trace.py` or the debug workflow tests.

```bash
python tests/example_apps/run_all.py
```

This runs three apps that produce traces with intentional errors:

- **openai_rag_app** — RAG app with retrieval misses (project: `skill-test-rag-app`)
- **tool_calling_agent** — Agent with tool errors (project: `skill-test-tool-agent`)
- **multi_turn_chatbot** — Chatbot with oversized inputs (project: `skill-test-chatbot`)

### Run skill tests

```bash
# All tests
pytest tests/ -v --timeout=300

# Single skill
pytest tests/test_arize_trace.py -v

# Single test class
pytest tests/test_arize_dataset.py::TestDatasetCreate -v

# With a specific model
TEST_MODEL=claude-sonnet-4-6 pytest tests/ -v
```

### Run skill selection tests

These test whether Claude picks the correct skill for various prompts:

```bash
# All selection tests
pytest tests/test_skill_selection.py -v

# Only specific prompts
pytest tests/test_skill_selection.py::TestSpecificPrompts -v

# Only vague prompts
pytest tests/test_skill_selection.py::TestVaguePrompts -v
```

### Compare models

Run skill selection across multiple models and get a comparison table:

```bash
# Default models (haiku, sonnet, opus)
python tests/compare_models.py

# Specific models
python tests/compare_models.py claude-haiku-4-5-20251001 claude-sonnet-4-6
```

Output:

```
MODEL COMPARISON
================================================================================
Model                               Accuracy       Cost    Correct
----------------------------------- ---------- ---------- ----------
claude-haiku-4-5-20251001               82.6%    $0.0312    38/46
claude-sonnet-4-6                       91.3%    $0.1845    42/46
claude-opus-4-6                         95.7%    $0.8920    44/46
```

## Reports

All test runs produce JSON reports in `test-results/`:

| Report | Generated by | Contents |
|--------|--------------|----------|
| `report_<ts>.json` | `pytest` (via `test_report` fixture) | Full skill test results with per-skill pass rate, cost, tokens, duration |
| `skill_selection_<model>_<ts>.json` | `pytest` (via `selection_results` fixture) | Skill routing accuracy by prompt category |
| `model_comparison_<ts>.json` | `compare_models.py` | Cross-model comparison with accuracy breakdown |

## Available Verifiers

Use these in test files to check skill run outcomes:

| Verifier | What it checks |
|----------|---------------|
| `NoErrorVerifier()` | Run completed without error |
| `OutputContainsVerifier(["str1", "str2"])` | Text output contains all listed substrings |
| `OutputMatchesRegexVerifier(r"pattern")` | Text output matches a regex |
| `ToolWasCalledVerifier(["Bash", "Read"])` | Specific tools were invoked |
| `FileExistsVerifier(["/path/to/file"])` | Files were created in the workspace |
| `AxResourceExistsVerifier("datasets", "name")` | An `ax` resource exists after the run |
| `URLFormatVerifier(["param1", "param2"])` | Output contains a valid Arize URL with expected query params |
| `CompositeVerifier(v1, v2, v3)` | Combine multiple verifiers (all must pass) |

## Project Structure

```
arize-skills/
├── skills/                          # Skill definitions
│   ├── arize-trace/SKILL.md
│   ├── arize-instrumentation/SKILL.md
│   ├── arize-dataset/SKILL.md
│   ├── arize-experiment/SKILL.md
│   ├── arize-prompt-optimization/SKILL.md
│   └── arize-link/SKILL.md
├── scripts/
│   └── validate_skills.py           # YAML frontmatter validator
├── tests/
│   ├── harness/                     # Test framework
│   │   ├── runner.py                # SkillTestRunner (Claude Agent SDK wrapper)
│   │   ├── result.py                # TestResult dataclass
│   │   ├── verifier.py              # Composable verification strategies
│   │   ├── ax_helpers.py            # ax CLI setup/teardown wrappers
│   │   ├── report.py                # JSON report generation
│   │   └── skill_router.py          # Skill selection testing
│   ├── example_apps/                # Faulty apps that generate traces
│   │   ├── openai_rag_app/app.py
│   │   ├── tool_calling_agent/app.py
│   │   ├── multi_turn_chatbot/app.py
│   │   └── run_all.py
│   ├── test_arize_trace.py          # 5 tests
│   ├── test_arize_dataset.py        # 4 tests
│   ├── test_arize_experiment.py     # 3 tests
│   ├── test_arize_instrumentation.py # 3 tests
│   ├── test_arize_prompt_optimization.py # 2 tests
│   ├── test_arize_link.py           # 4 tests
│   ├── test_skill_selection.py      # 46 parameterized prompts
│   └── compare_models.py            # Cross-model comparison script
├── install.sh                       # Skill installer
├── README.md                        # User-facing docs
└── DEVELOPMENT.md                   # This file
```
