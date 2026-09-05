# Arize Skill Sandbox

Testing harness for Arize skills. Spins up a sandbox, has a Claude agent instrument an uninstrumented app using the `arize-instrumentation` skill, traces the agent's execution, then evaluates whether the instrumentation was correct.

## The Flow

1. Script launches a Claude agent (via `claude-agent-sdk`)
2. Agent gets a sandbox workspace with an uninstrumented app (from [Rosetta Stone](https://github.com/Arize-ai/project-rosetta-stone) `no-observability/`)
3. Agent fetches `arize-skills` and uses the `arize-instrumentation` skill
4. Agent instruments the app (adds `tracing.py`, installs packages, wires imports)
5. The agent's own execution is traced to Arize
6. Eval: compare agent's output against ground truth (`ax/` tier from Rosetta Stone)

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env
```

## Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude Agent SDK authentication |
| `ARIZE_API_KEY` | Arize tracing (agent + instrumented app) |
| `ARIZE_SPACE_ID` | Arize space identifier |

## Usage

### Quick standalone run

```bash
python run.py --app langchain-py --verbose
```

### Full pytest suite

```bash
pytest tests/test_instrumentation.py -v
```

## Supported Apps

| App | Framework | Status |
|-----|-----------|--------|
| `langchain-py` | LangChain (Python) | v1 |

## Project Structure

```
arize-skill-sandbox/
├── src/
│   ├── config.py          # Env var loading, project name generation
│   ├── sandbox.py         # Workspace setup (clone rosetta stone, install skills)
│   ├── runner.py          # Claude Agent SDK wrapper
│   └── evaluator.py       # Structural checks + ground truth comparison
├── tests/
│   ├── conftest.py        # Pytest fixtures
│   └── test_instrumentation.py
├── ground_truth/
│   └── langchain_py/      # Reference instrumentation files
├── run.py                 # Standalone runner for demos
└── requirements.txt
```
