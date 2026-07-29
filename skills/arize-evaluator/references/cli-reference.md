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

`--variables` is a JSON array of the input column names the check reads (e.g.
`'["output"]'`). Any configuration the managed check needs — a regex pattern, a keyword
list — goes through `--static-params`, not `--variables`.

```bash
# Managed: check output is valid JSON
ax evaluators create-code-evaluator \
  --name "JSON Format Check" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "json_check" \
  --managed-evaluator JSON_PARSEABLE \
  --variables '["output"]'

# Managed: check output contains required keywords
ax evaluators create-code-evaluator \
  --name "Safety Keywords" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "safety_keywords" \
  --managed-evaluator CONTAINS_ANY_KEYWORD \
  --variables '["output"]' \
  --static-params '[{"name": "keywords", "type": "STRING_ARRAY", "default_value": ["unsafe", "harmful", "illegal"]}]'
```

**Managed evaluator types** (pass the value exactly — the flag is case-sensitive):

| Value | What it checks |
|-------|---------------|
| `MATCHES_REGEX` | Output matches a regular expression |
| `JSON_PARSEABLE` | Output is valid JSON |
| `CONTAINS_ANY_KEYWORD` | Output contains at least one keyword from a list |
| `CONTAINS_ALL_KEYWORDS` | Output contains all keywords from a list |
| `EXACT_MATCH` | Output exactly equals a target string |

**Custom Python code evaluators:**

> **CRITICAL — the class contract, not a bare function.** Custom code evaluators run
> server-side as a Python **class that subclasses `CodeEvaluator`** — not a standalone
> `def evaluate(...):` function. Get any of the three things below wrong and the task
> run **cancels in ~3 seconds with `num_successes=0`, `num_errors=0`, `num_skipped=0`** —
> no error is surfaced, it just silently scores nothing.
>
> 1. **Import path.** The sandbox that executes the evaluator requires exactly this
>    import — it is the only path the platform runtime exposes:
>    ```python
>    from arize.experimental.datasets.experiments.evaluators.base import (
>        EvaluationResult,
>        CodeEvaluator,
>    )
>    ```
>    Use it verbatim. A locally-installed `arize` SDK may expose other module paths that
>    import fine on your machine but are absent on the platform, so passing a local test
>    is not proof the import will resolve at run time. Always put imports in `--imports`,
>    never inline in `--code`.
> 2. **Named parameters on `evaluate()`, not just `**kwargs`.** The platform builds the
>    list of mappable variables by introspecting the named keyword parameters of
>    `evaluate()`. `def evaluate(self, **kwargs)` exposes **zero** mappable variables, so
>    the task matches 0 rows and cancels immediately. Name every variable you need
>    explicitly, with a default:
>    ```python
>    def evaluate(self, *, prediction=None, actual=None, **kwargs) -> EvaluationResult:
>        ...
>        return EvaluationResult(label=..., score=..., explanation=...)
>    ```
>    Return `EvaluationResult`, not a bare `dict`. Each named parameter must exactly
>    match an entry in `--variables` and, at the task level, a `column_mappings` key.
> 3. **`--imports` and `--code` are separate.** `--code` must contain **only the class
>    definition** (no `import` statements inside it); all imports go in `--imports`.
>
> If a run still cancels at `0/0/0` after fixing the contract, confirm `num_skipped`
> increments on the next run — that means the platform is now reaching and invoking
> your evaluator (it may still skip rows for unrelated reasons, e.g. missing column data).

Static configuration (thresholds, keyword lists, regex patterns) that should NOT vary
per row goes through `--static-params` and is read inside `evaluate()` as `self.<name>`
— never declare these as named `evaluate()` parameters.

Write the import block and the class to their own files and pass each with `@filepath`.
Loading from files keeps the class readable and avoids shell-quoting mistakes in the
import block — prefer this for anything beyond a trivial evaluator.

`my_evaluator_imports.py`:

```python
import json

from arize.experimental.datasets.experiments.evaluators.base import (
    EvaluationResult,
    CodeEvaluator,
)
```

`my_evaluator.py` (class definition only — no imports):

```python
class JSONSchemaEval(CodeEvaluator):
    def evaluate(self, *, prediction=None, **kwargs) -> EvaluationResult:
        # required_keys is a STRING_ARRAY static param -> a Python list
        required_keys = self.required_keys or []
        try:
            parsed = json.loads(prediction or "")
        except (TypeError, ValueError) as exc:
            return EvaluationResult(
                label="fail",
                score=0.0,
                explanation=f"output is not valid JSON: {exc}",
            )
        if not isinstance(parsed, dict):
            return EvaluationResult(
                label="fail",
                score=0.0,
                explanation="output JSON is not an object",
            )
        missing = [key for key in required_keys if key not in parsed]
        passed = not missing
        return EvaluationResult(
            label="pass" if passed else "fail",
            score=float(passed),
            explanation=(
                "all required keys present"
                if passed
                else f"missing keys: {', '.join(missing)}"
            ),
        )
```

```bash
# Custom Python (recommended): load imports + class from files
ax evaluators create-code-evaluator \
  --name "JSON Schema Check" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type custom \
  --code-name "json_schema_eval" \
  --variables '["prediction"]' \
  --static-params '[{"name": "required_keys", "type": "STRING_ARRAY", "default_value": ["answer", "confidence"]}]' \
  --imports @./my_evaluator_imports.py \
  --code @./my_evaluator.py
```

You *can* inline both blocks instead, single-quoting each so the shell does not
interpolate the Python — but for anything with its own imports or multiple branches
like this, the file-based form above is easier to read and less error-prone:

```bash
# Custom Python (inline): workable, but harder to maintain than the file form
ax evaluators create-code-evaluator \
  --name "JSON Schema Check" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type custom \
  --code-name "json_schema_eval" \
  --variables '["prediction"]' \
  --static-params '[{"name": "required_keys", "type": "STRING_ARRAY", "default_value": ["answer", "confidence"]}]' \
  --imports 'import json

from arize.experimental.datasets.experiments.evaluators.base import (
    EvaluationResult,
    CodeEvaluator,
)' \
  --code 'class JSONSchemaEval(CodeEvaluator):
    def evaluate(self, *, prediction=None, **kwargs) -> EvaluationResult:
        required_keys = self.required_keys or []
        try:
            parsed = json.loads(prediction or "")
        except (TypeError, ValueError) as exc:
            return EvaluationResult(
                label="fail",
                score=0.0,
                explanation=f"output is not valid JSON: {exc}",
            )
        if not isinstance(parsed, dict):
            return EvaluationResult(
                label="fail",
                score=0.0,
                explanation="output JSON is not an object",
            )
        missing = [key for key in required_keys if key not in parsed]
        passed = not missing
        return EvaluationResult(
            label="pass" if passed else "fail",
            score=float(passed),
            explanation=(
                "all required keys present"
                if passed
                else f"missing keys: {', '.join(missing)}"
            ),
        )'
```

```bash
# Create a new version of a code evaluator
ax evaluators create-code-evaluator-version NAME_OR_ID \
  --commit-message "Updated regex pattern" \
  --code-type managed \
  --code-name "regex_check" \
  --managed-evaluator MATCHES_REGEX \
  --variables '["output"]' \
  --static-params '[{"name": "pattern", "type": "REGEX", "default_value": "^[A-Z]"}]'
```

**Key flags for `create-code-evaluator`:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Evaluator name (unique within space) |
| `--space` | yes | Space name or ID to create in |
| `--commit-message` | yes | Description of this version |
| `--code-type` | yes | `managed` (built-in pattern) or `custom` (Python class) |
| `--code-name` | yes | Eval column name — alphanumeric, spaces, hyphens, underscores. (Code evaluators have **no** `--template-name` flag; that flag belongs to `create-template-evaluator`.) |
| `--variables` | yes | JSON array of column/attribute names (strings), e.g. `'["prediction", "actual"]'`. For `custom`, each must match a named `evaluate()` parameter. For `managed`, these are the input columns the check reads — the check's own config (pattern, keyword list) goes in `--static-params`. |
| `--managed-evaluator` | managed only | Case-sensitive; one of: `MATCHES_REGEX`, `JSON_PARSEABLE`, `CONTAINS_ANY_KEYWORD`, `CONTAINS_ALL_KEYWORDS`, `EXACT_MATCH` |
| `--code` | custom only | Python source for the `CodeEvaluator` subclass only — no imports (or `@filepath` to read from file) |
| `--imports` | custom only | Python import block for `--code`, e.g. the `arize.experimental.datasets.experiments.evaluators.base` import (or `@filepath`) |
| `--static-params` | no | JSON array of static config parameters read via `self.<name>` inside `evaluate()`. Each item: `{"name": ..., "type": "STRING"\|"STRING_ARRAY"\|"REGEX", "default_value": ...}` — `default_value` is a string for `STRING`/`REGEX` and an array of strings for `STRING_ARRAY`; cast numerics explicitly (e.g. `int(self.<name>)`) |
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
ax tasks list --task-type TEMPLATE_EVALUATION   # filter by type: TEMPLATE_EVALUATION, CODE_EVALUATION, RUN_EXPERIMENT
ax tasks get TASK_ID

# Create evaluation task (project — continuous)
ax tasks create-evaluation \
  --name "Correctness Monitor" \
  --task-type TEMPLATE_EVALUATION \
  --project PROJECT_NAME \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}]' \
  --is-continuous \
  --sampling-rate 0.1

# Create evaluation task (project — one-time / backfill)
ax tasks create-evaluation \
  --name "Correctness Backfill" \
  --task-type TEMPLATE_EVALUATION \
  --project PROJECT_NAME \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}]' \
  --no-continuous

# Create evaluation task (experiment / dataset)
ax tasks create-evaluation \
  --name "Experiment Scoring" \
  --task-type TEMPLATE_EVALUATION \
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
