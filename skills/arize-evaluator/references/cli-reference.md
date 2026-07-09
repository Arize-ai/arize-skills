# Arize Evaluator — CLI Command Reference

Full CRUD reference for AI integrations, evaluators (template and code), and tasks. Referenced from `SKILL.md`.


### AI Integrations

AI integrations store the LLM provider credentials the evaluator uses. For full CRUD — listing, creating for all providers (OpenAI, Anthropic, Azure, Bedrock, Vertex, Gemini, NVIDIA NIM, custom), updating, and deleting — use the **arize-ai-provider-integration** skill.

Quick reference for the common case (OpenAI):

```bash
# Check for an existing integration first
ax ai-integrations list --space SPACE

# Create if none exists
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider openAI \
  --api-key $OPENAI_API_KEY
```

Copy the returned integration ID — it is required for `ax evaluators create-template-evaluator --ai-integration-id`.

### Evaluators

```bash
# List / Get
ax evaluators list --space SPACE
ax evaluators list --space SPACE --name "Hallucination"   # substring filter
ax evaluators get ID                    # accepts name or ID
ax evaluators get NAME --space SPACE   # required when using name instead of ID
ax evaluators list-versions NAME_OR_ID
ax evaluators get-version VERSION_ID

# Update metadata only (name, description — not prompt/code)
ax evaluators update NAME_OR_ID \
  --name "New Name" \
  --description "Updated description"

# Delete (permanent — removes all versions)
ax evaluators delete NAME_OR_ID
```

#### Template evaluators (LLM-as-judge)

```bash
# Create a template evaluator (LLM-as-judge)
ax evaluators create-template-evaluator \
  --name "Answer Correctness" \
  --space SPACE \
  --description "Judges if the model answer is correct" \
  --template-name "correctness" \
  --commit-message "Initial version" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanation \
  --use-function-calling \
  --classification-choices '{"correct": 1, "incorrect": 0}' \
  --template 'You are an evaluator. Given the user question and the model response, decide if the response correctly answers the question.

User question: {input}

Model response: {output}

Respond with exactly one of these labels: correct, incorrect'

# Create a new template version (for prompt or model changes — versions are immutable)
ax evaluators create-template-evaluator-version NAME_OR_ID \
  --commit-message "Added context grounding" \
  --template-name "correctness" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanation \
  --classification-choices '{"correct": 1, "incorrect": 0}' \
  --template 'Updated prompt...

{input} / {output} / {context}'
```

**Key flags for `create-template-evaluator`:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Evaluator name (unique within space) |
| `--space` | yes | Space name or ID to create in |
| `--template-name` | yes | Eval column name — alphanumeric, spaces, hyphens, underscores |
| `--commit-message` | yes | Description of this version |
| `--ai-integration-id` | yes | AI integration ID (from above) |
| `--model-name` | yes | Judge model (e.g. `gpt-4o`) |
| `--template` | yes | Prompt with `{variable}` placeholders (single-quoted in bash) |
| `--classification-choices` | yes | JSON object mapping choice labels to numeric scores e.g. `'{"correct": 1, "incorrect": 0}'` |
| `--description` | no | Human-readable description |
| `--include-explanation` | no | Include reasoning alongside the label |
| `--use-function-calling` | no | Prefer structured function-call output |
| `--invocation-params` | no | JSON of model params e.g. `'{"temperature": 0}'` |
| `--provider-params` | no | JSON object of provider-specific parameters |
| `--data-granularity` | no | `span` (default), `trace`, or `session`. Only relevant for project tasks, not dataset/experiment tasks. See Data Granularity section. |
| `--direction` | no | Optimization direction: `maximize`, `minimize`, or `none`. Sets how the UI renders trends. |

#### Code evaluators (deterministic, no LLM)

Code evaluators run without an AI integration — they use deterministic logic (regex, JSON checks, keyword matching, or custom Python). Use them for fast, low-cost checks that don't need language understanding.

**Managed code evaluators** use built-in patterns:

```bash
# Managed: check output matches a regex
ax evaluators create-code-evaluator \
  --name "JSON Format Check" \
  --space SPACE \
  --template-name "json_format" \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "json_check" \
  --managed-evaluator JSONParseable \
  --variables '[]'

# Managed: check output contains required keywords
ax evaluators create-code-evaluator \
  --name "Safety Keywords" \
  --space SPACE \
  --template-name "safety_check" \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "safety_keywords" \
  --managed-evaluator ContainsAnyKeyword \
  --variables '[{"name": "keywords", "value": ["unsafe", "harmful", "illegal"]}]'
```

**Managed evaluator types:**

| Value | What it checks |
|-------|---------------|
| `MatchesRegex` | Output matches a regular expression |
| `JSONParseable` | Output is valid JSON |
| `ContainsAnyKeyword` | Output contains at least one keyword from a list |
| `ContainsAllKeywords` | Output contains all keywords from a list |
| `ExactMatch` | Output exactly equals a target string |

**Custom Python code evaluators:**

```bash
# Custom Python: inline code
ax evaluators create-code-evaluator \
  --name "Word Count Check" \
  --space SPACE \
  --template-name "word_count" \
  --commit-message "Initial version" \
  --code-type custom \
  --code-name "word_count_eval" \
  --variables '[{"name": "max_words", "value": 100}]' \
  --code 'def evaluate(output, max_words):
    count = len(output.split())
    return {"label": "pass" if count <= max_words else "fail", "score": count}'

# Custom Python: from file
ax evaluators create-code-evaluator \
  --name "Custom Evaluator" \
  --space SPACE \
  --template-name "custom_eval" \
  --commit-message "Initial version" \
  --code-type custom \
  --code-name "my_eval" \
  --variables '[]' \
  --code @./my_evaluator.py

# Create a new version of a code evaluator
ax evaluators create-code-evaluator-version NAME_OR_ID \
  --commit-message "Updated regex pattern" \
  --code-type managed \
  --code-name "regex_check" \
  --managed-evaluator MatchesRegex \
  --variables '[{"name": "pattern", "value": "^[A-Z]"}]'
```

**Key flags for `create-code-evaluator`:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Evaluator name (unique within space) |
| `--space` | yes | Space name or ID to create in |
| `--template-name` | yes | Eval column name — alphanumeric, spaces, hyphens, underscores |
| `--commit-message` | yes | Description of this version |
| `--code-type` | yes | `managed` (built-in pattern) or `custom` (Python function) |
| `--code-name` | yes | Internal identifier for the code evaluator |
| `--variables` | yes | JSON array of variable definitions `[{"name": "...", "value": ...}]` |
| `--managed-evaluator` | managed only | One of: `MatchesRegex`, `JSONParseable`, `ContainsAnyKeyword`, `ContainsAllKeywords`, `ExactMatch` |
| `--code` | custom only | Python code string (or `@filepath` to read from file) |
| `--imports` | custom only | Python import block for the code |
| `--static-params` | no | JSON of static parameters passed to the evaluator function |
| `--query-filter` | no | SQL-style filter to restrict which spans are evaluated |
| `--description` | no | Human-readable description |
| `--data-granularity` | no | `span` (default), `trace`, or `session` |
| `--direction` | no | Optimization direction: `maximize`, `minimize`, or `none` |

### Tasks

> `PROJECT_NAME`, `DATASET_NAME`, and `evaluator_id` all accept a name or base64 ID.

```bash
# List / Get
ax tasks list --space SPACE
ax tasks list --project PROJECT_NAME
ax tasks list --dataset DATASET_NAME --space SPACE
ax tasks list --task-type template_evaluation   # filter by type: template_evaluation, code_evaluation, run_experiment
ax tasks get TASK_ID

# Create evaluation task (project — continuous)
ax tasks create-evaluation \
  --name "Correctness Monitor" \
  --task-type template_evaluation \
  --project PROJECT_NAME \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}]' \
  --is-continuous \
  --sampling-rate 0.1

# Create evaluation task (project — one-time / backfill)
ax tasks create-evaluation \
  --name "Correctness Backfill" \
  --task-type template_evaluation \
  --project PROJECT_NAME \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}]' \
  --no-continuous

# Create evaluation task (experiment / dataset)
ax tasks create-evaluation \
  --name "Experiment Scoring" \
  --task-type template_evaluation \
  --dataset DATASET_NAME --space SPACE \
  --experiment-ids "EXP_ID_1,EXP_ID_2" \   # base64 IDs from `ax experiments list --space SPACE -o json`
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"output": "output"}}]' \
  --no-continuous

# Create run-experiment task (runs an experiment via a task)
ax tasks create-run-experiment \
  --name "GPT-4o Baseline Run" \
  --dataset DATASET_NAME \
  --run-configuration '{"model": "gpt-4o", "temperature": 0}' \
  --space SPACE

# Update a task (mutable fields only)
ax tasks update TASK \
  --name "New Task Name" \
  --sampling-rate 0.2 \
  --is-continuous \
  --query-filter "span_kind = 'LLM'" \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"output": "output"}}]'

# Delete a task (irreversible)
ax tasks delete TASK --force

# Trigger a run (project task — use data window)
ax tasks trigger-run TASK_ID \
  --data-start-time "2026-03-20T00:00:00" \
  --data-end-time "2026-03-21T23:59:59" \
  --wait

# Trigger a run (experiment task — use experiment IDs)
ax tasks trigger-run TASK_ID \
  --experiment-ids "EXP_ID_1" \   # base64 ID from `ax experiments list --space SPACE -o json`
  --wait

# Monitor
ax tasks list-runs TASK_ID
ax tasks get-run RUN_ID
ax tasks wait-for-run RUN_ID --timeout 300
ax tasks cancel-run RUN_ID --force
```

> **Note:** `ax tasks create` (generic) also works and dispatches by `--task-type`. `create-evaluation` and `create-run-experiment` are dedicated shortcuts with clearer flag validation.

**Time format for trigger-run:** `2026-03-21T09:00:00` — no trailing `Z`.

**Additional trigger-run flags:**

| Flag | Description |
|------|-------------|
| `--max-spans` | Cap processed spans (default 10,000) |
| `--override-evaluations` | Re-score spans that already have labels |
| `--wait` / `-w` | Block until the run finishes |
| `--timeout` | Seconds to wait with `--wait` (default 600) |
| `--poll-interval` | Poll interval in seconds when waiting (default 5) |

**Run status guide:**

| Status | Meaning |
|--------|---------|
| `completed`, 0 spans | The eval index lags 1–2 hours — spans ingested recently may not be indexed yet. Shift the window to data at least 2 hours old, or widen the time range to cover more historical data. |
| `cancelled` ~1s | Integration credentials invalid |
| `cancelled` ~3min | Found spans but LLM call failed — check model name or key |
| `completed`, N > 0 | Success — check scores in UI |
