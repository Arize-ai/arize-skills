# Arize Evaluator — CLI Command Reference

Commands not shown in the `SKILL.md` workflows: evaluator versions and CRUD, code evaluators, and task management. Run `ax <command> --help` for flags.


### AI Integrations

Find or create the judge's AI integration as in Workflow A, Step 3 of `SKILL.md`; its ID is the `--ai-integration-id` for template evaluators.

### Evaluators

```bash
# Get directly by name or ID (--space is required with a name)
ax evaluators get NAME_OR_ID --space SPACE -o json
# Browse (for humans; --name is a substring filter)
ax evaluators list --space SPACE --name "Hallucination"
ax evaluators list-versions NAME_OR_ID --space SPACE
ax evaluators get-version VERSION_ID

# Update metadata only (name, description — not prompt/code)
ax evaluators update NAME_OR_ID \
  --name "New Name" \
  --description "Updated description"

# Delete (permanent — removes all versions)
ax evaluators delete NAME_OR_ID --space SPACE --force
```

#### Template evaluators (LLM-as-judge)

Create a template evaluator as in Workflow A, Step 4 of `SKILL.md`.

```bash
# Create a new template version (for prompt or model changes — versions are immutable)
ax evaluators create-evaluator-version template NAME_OR_ID \
  --space SPACE \
  --commit-message "Added context grounding" \
  --template-name "correctness" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --classification-choices '{"correct": 1, "incorrect": 0}' \
  --template 'Updated prompt with {input}, {output}, {context}'
```

Run `ax evaluators create-evaluator template --help` for the full flag list. `--classification-choices` is optional: omit it only for freeform (non-classification) output.

#### Code evaluators (deterministic, no LLM)

Code evaluators run without an AI integration — they use deterministic logic (regex, JSON checks, keyword matching, or custom Python). Use them for fast, low-cost checks that don't need language understanding.

**Managed code evaluators** use built-in patterns:

`--variables` is a JSON array of the input column names the check reads (e.g.
`'["output"]'`). Any configuration the managed check needs — a regex pattern, a keyword
list — goes through `--static-params`, not `--variables`.

```bash
# Managed: check output is valid JSON
ax evaluators create-evaluator code \
  --name "JSON Format Check" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "json_check" \
  --managed-evaluator JSON_PARSEABLE \
  --variables '["output"]'

# Managed: check output contains required keywords
ax evaluators create-evaluator code \
  --name "Safety Keywords" \
  --space SPACE \
  --commit-message "Initial version" \
  --code-type managed \
  --code-name "safety_keywords" \
  --managed-evaluator CONTAINS_ANY_KEYWORD \
  --variables '["output"]' \
  --static-params '[{"name": "keywords", "type": "STRING_ARRAY", "default_value": ["unsafe", "harmful", "illegal"]}]'
```

Run `ax evaluators create-evaluator code --help` for the accepted `--managed-evaluator` values; pass the value exactly as listed (uppercase).

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
ax evaluators create-evaluator code \
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
ax evaluators create-evaluator code \
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
ax evaluators create-evaluator-version code NAME_OR_ID \
  --space SPACE \
  --commit-message "Updated regex pattern" \
  --code-type managed \
  --code-name "regex_check" \
  --managed-evaluator MATCHES_REGEX \
  --variables '["output"]' \
  --static-params '[{"name": "pattern", "type": "REGEX", "default_value": "^[A-Z]"}]'
```

Run `ax evaluators create-evaluator code --help` for the full flag list.

### Tasks

> `PROJECT_NAME`, `DATASET_NAME`, and `evaluator_id` all accept a name or base64 ID.

Creating evaluation tasks and triggering runs are covered in `SKILL.md` (Workflow A Steps 7–8, Workflow B Steps 6–7).

```bash
ax tasks get TASK_ID
ax tasks list --space SPACE   # human browsing; run `ax tasks list --help` for filters

# Create run-experiment task (runs an experiment via a task)
ax tasks create-run-experiment \
  --name "GPT-4o Baseline Run" \
  --dataset DATASET_NAME \
  --run-configuration '{"experiment_type": "LLM_GENERATION", "ai_integration_id": "AI_INTEGRATION_ID", "model_name": "gpt-4o", "messages": [{"role": "USER", "content": "{{input}}"}]}' \
  --space SPACE

# Update a task (mutable fields only)
ax tasks update TASK \
  --name "New Task Name" \
  --sampling-rate 0.2 \
  --is-continuous \
  --query-filter "attributes.openinference.span.kind = 'LLM'" \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"output": "output"}}]'

# Delete a task (irreversible)
ax tasks delete TASK --force

# Monitor
ax tasks wait-for-run RUN_ID --timeout 300
ax tasks cancel-run RUN_ID --force
```

> **Note:** `ax tasks create` (generic) also works and dispatches by `--task-type`. `create-evaluation` and `create-run-experiment` are dedicated shortcuts with clearer flag validation.

Run `ax tasks trigger-run --help` for the remaining flags (`--max-spans`, `--override-evaluations`, `--timeout`). For `run_experiment` tasks it also lists the experiment-only flags; `--experiment-name` is required for that task type.

For run statuses (`completed` with 0 spans, `cancelled` ~1s / ~3min), see the Troubleshooting table in `SKILL.md` and [troubleshooting.md](troubleshooting.md).
