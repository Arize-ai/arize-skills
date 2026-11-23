---
name: arize-experiment
description: Creates, runs, and analyzes Arize experiments for evaluating and comparing model performance. Covers experiment CRUD, exporting runs, comparing results, and evaluation workflows using the ax CLI. Use when the user mentions create experiment, run experiment, compare models, model performance, evaluate AI, experiment results, benchmark, A/B test models, or measure accuracy.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.39.0) and a configured Arize profile.
---

# Arize Experiment Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Resolve a known name or ID directly with `ax spaces get NAME_OR_ID`; `ax spaces list` is for human browsing when no space is known (see [Space](references/ax-profiles.md#space)).

## Concepts

- **Experiment** = a named evaluation run against a specific dataset version, containing one run per example
- **Experiment Run** = the result of processing one dataset example -- includes the model output, optional evaluations, and optional metadata
- **Dataset** = a versioned collection of examples; every experiment is tied to a dataset and a specific dataset version
- **Evaluation** = a named metric attached to a run (e.g., `correctness`, `relevance`), with optional label, score, and explanation

The typical flow: export a dataset → process each example → create an experiment with the outputs → attach evaluations with `annotate-runs`.

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `401 Unauthorized` / missing API key → run `ax profiles show` to inspect the current profile. If the profile is missing or the API key is wrong, follow [references/ax-profiles.md](references/ax-profiles.md) to create/update it. If the user doesn't have their key, direct them to https://app.arize.com/admin > API Keys
- Space unknown → see [Space](references/ax-profiles.md#space)
- Project unclear → ask the user, or run `ax projects list --space SPACE -o json --limit 100` and present as selectable options
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Use `ax profiles` for Arize credentials and `ax ai-integrations` for LLM provider keys. Never ask the user to paste secrets into chat. For missing credentials, see [references/ax-profiles.md](references/ax-profiles.md).
- **CRITICAL — Never fabricate outputs:** When running an experiment, you MUST call the real model API specified by the user for every dataset example. Never fabricate, simulate, or hardcode model outputs, latencies, or evaluation scores. If you cannot call the API (missing SDK, missing credentials, network error), stop and tell the user what is needed before proceeding.

## List Experiments: `ax experiments list`

Browse experiments, optionally filtered by dataset. When the experiment name or ID is known, use `ax experiments get` directly; `list` is for human browsing.

```bash
ax experiments list --space SPACE   # every experiment in the space, including standalone
ax experiments list --dataset DATASET_NAME --space SPACE --limit 20   # DATASET_NAME: name or ID (name preferred)
ax experiments list --cursor CURSOR_TOKEN
ax experiments list -o json
```

Flags: `ax experiments list --help`.

## Get Experiment: `ax experiments get`

Quick metadata lookup -- returns experiment name, linked dataset/version, and timestamps.

```bash
ax experiments get NAME_OR_ID
ax experiments get NAME_OR_ID -o json
ax experiments get NAME_OR_ID --dataset DATASET_NAME --space SPACE   # required when using experiment name instead of ID
```

Flags: `ax experiments get --help`.

### Response fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Experiment ID |
| `name` | string | Experiment name |
| `dataset_id` | string | Linked dataset ID |
| `dataset_version_id` | string | Specific dataset version used |
| `experiment_traces_project_id` | string | Project where experiment traces are stored |
| `created_at` | datetime | When the experiment was created |
| `updated_at` | datetime | Last modification time |

## Export Experiment: `ax experiments export`

Download all runs to a file. By default uses the REST API; pass `--all` to use Arrow Flight for bulk transfer.

```bash
# EXPERIMENT_NAME, DATASET_NAME: name or ID (name preferred)
ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE
# -> experiment_abc123_20260305_141500/runs.json

ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --all
ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --output-dir ./results
ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --stdout
ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --stdout | jq '[.[] | select(.additional_properties["eval.correctness.score"] < 0.5)]'
```

Flags: `ax experiments export --help`.

### REST vs Flight (`--all`)

- **REST** (default): Lower friction -- no Arrow/Flight dependency, standard HTTPS ports, works through any corporate proxy or firewall. Limited to 500 runs per page.
- **Flight** (`--all`): Required for experiments with more than 500 runs. Uses gRPC+TLS on a separate host/port which some corporate networks may block. The active `ax` profile supplies the regional endpoint; see [profile setup](references/ax-profiles.md).

**Agent auto-escalation rule:** If a REST export returns exactly 500 runs, the result is likely truncated. Re-run with `--all` to get the full dataset.

Output is a JSON array of run objects:

```json
[
  {
    "id": "run_001",
    "example_id": "ex_001",
    "output": "The answer is 4.",
    "annotations": [
      { "name": "correctness", "label": "correct", "updated_at": "2026-03-01T00:00:00Z" }
    ],
    "additional_properties": {
      "eval.relevance.label": "relevant",
      "eval.relevance.score": 1,
      "eval.relevance.explanation": "Directly answers the question"
    }
  }
]
```

Failed runs (the task raised an exception) are still exported, with `output: null` and an `error` field holding the exception message. Filter them out (`select(.output != null)`) before scoring or averaging.

Where results appear in each run:

- `annotations`: values written by `annotate-runs` (`null` when there are none)
- `additional_properties["eval.<name>.label|score|explanation"]`: results from an evaluator task
- With `--all`, annotations are flat keys too: `additional_properties["annotation.<name>.label|score|text"]`

## Create Experiment: `ax experiments create`

Create a new experiment with runs from a data file.

```bash
ax experiments create --name "gpt-4o-baseline" --dataset DATASET_NAME --space SPACE --file runs.json
ax experiments create --name "claude-test" --dataset DATASET_NAME --space SPACE --file runs.csv
```

Flags, including standalone experiments without `--dataset`: `ax experiments create --help`.

### Passing data via stdin

Use `--file -` to pipe data directly — no temp file needed:

```bash
echo '[{"example_id": "ex_001", "output": "Paris"}]' | ax experiments create --name "my-experiment" --dataset DATASET_NAME --space SPACE --file -

# Or with a heredoc
ax experiments create --name "my-experiment" --dataset DATASET_NAME --space SPACE --file - << 'EOF'
[{"example_id": "ex_001", "output": "Paris"}]
EOF
```

### Required columns in the runs file

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `example_id` | string | yes | The dataset example's **top-level `id`** from `ax datasets export` |
| `output` | string | yes | The model/system output for this example |

> **`example_id` must be the Arize row id** — the top-level `id` field on each exported dataset example (`ex["id"]`). Do **not** use a value nested inside the example's input fields or `additional_properties`; a wrong value fails silently or attaches the run to the wrong example. Export the dataset and inspect the top-level `id` field before creating runs.

> **⚠️ Inline evaluations in the create file do NOT attach as scores.** `create` only reads `example_id` and `output`; every other column — including an `evaluations` object — is stored as a passthrough additional field, **not** as an experiment evaluation, and will **not** appear as a score in the UI. This fails silently (no error). To attach scores/labels, create the experiment first, then run `ax experiments annotate-runs`.

## Run a Task Locally: `ax experiments run`

Unlike `create` (needs a pre-computed outputs file), `run` loads a Python task function, executes it against every dataset row, and uploads the results as an experiment.

```bash
ax experiments run -n "my-experiment" --dataset DATASET_NAME --space SPACE --task task.py
ax experiments run -n "my-experiment" --dataset DATASET_NAME --space SPACE --task task.py --concurrency 5 --dry-run
```

`task.py` must define a top-level `task(dataset_row)` function returning a JSON-serializable value:

```python
from anthropic import Anthropic

def task(dataset_row):
    resp = Anthropic().messages.create(
        model="claude-sonnet-4-6", max_tokens=256,
        messages=[{"role": "user", "content": dataset_row["question"]}]
    )
    return resp.content[0].text
```

`--dry-run` tests against the first 10 examples without uploading, to validate the task before a full run. Flags: `ax experiments run --help`.

> **Choose the run path based on where the logic lives.** Use `ax experiments run` when there's a local Python task to execute — it runs `task.py` on this machine and uploads the results; no AI integration is required. Use `ax tasks create-run-experiment` when the run should be hosted and recurring — it registers a platform-side `run_experiment` task that Arize executes on a schedule or on demand, driven by a JSON `--run-configuration` (model + messages + AI integration) instead of local code. Default to `ax experiments run` for local/ad-hoc runs and custom logic; use the task path for recurring, hosted runs — see the **arize-evaluator** skill for that route.

## List Runs: `ax experiments list-runs`

Paginated terminal view of an experiment's runs (vs. `export`, which downloads them to a file).

```bash
ax experiments list-runs EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --limit 30
ax experiments list-runs EXPERIMENT_ID
```

`--filter` narrows runs server-side (e.g. by `eval.<name>.label`); syntax: `ax experiments list-runs --help`. To process every run, use `export` instead; `list-runs` is for human browsing.

## Delete Experiment: `ax experiments delete`

```bash
ax experiments delete NAME_OR_ID
ax experiments delete NAME_OR_ID --dataset DATASET_NAME --space SPACE   # required when using experiment name instead of ID
ax experiments delete NAME_OR_ID --force   # skip confirmation prompt
```

Flags: `ax experiments delete --help`.

## Annotate Runs: `ax experiments annotate-runs`

**The only way to attach scores/labels you compute yourself so they show in the UI** (evaluator tasks attach their own) (see the warning under [Create Experiment](#create-experiment-ax-experiments-create)). Upsert semantics — resubmitting the same annotation `name` for the same run overwrites the previous value. Up to 1000 runs per request.

Each `name` must be an existing annotation config in the space (create it first; see the **arize-annotation** skill), and the value must fit its type: categorical → `label` (one of the config's values, no `score`), continuous → `score`, freeform → `text`.

```bash
ax experiments annotate-runs NAME_OR_ID --file annotations.json --dataset DATASET_NAME --space SPACE
ax experiments annotate-runs NAME_OR_ID --file annotations.csv --dataset DATASET_NAME --space SPACE
```

### Annotation file schema

A JSON array; each item annotates one run:

```json
[
  {
    "record_id": "run_001",
    "values": [
      { "name": "correctness", "label": "correct" },
      { "name": "relevance", "score": 0.95 }
    ]
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_id` | string | yes | The **experiment run ID** (the run's `id` from `ax experiments export`) — **not** the `example_id`. Unmatched IDs are silently ignored. |
| `values` | array | yes | One or more annotation dicts, each with a `name` plus at least one of `score`, `label`, or `text` |
| `values[].name` | string | yes | Name of an existing annotation config (e.g., `correctness`) — becomes the column in the UI |
| `values[].score` | number | no | Continuous configs |
| `values[].label` | string | no | Categorical configs; must be one of the config's values |
| `values[].text` | string | no | Freeform configs |

> Run ids exist only after `create`, so the order is always: `create` → `export` (to read each run's `id`) → build annotations → `annotate-runs`.

Flags: `ax experiments annotate-runs --help`.

## Experiment Run Schema

Each run corresponds to one dataset example; extra fields such as `metadata` are passthrough (see [Create Experiment](#create-experiment-ax-experiments-create)). For what `export` returns, see [Export Experiment](#export-experiment-ax-experiments-export).

```json
{
  "example_id": "required -- the dataset example's top-level id",
  "output": "required -- the model/system output for this example",
  "metadata": { "model": "gpt-4o", "latency_ms": 1234 }
}
```

## Workflows

### Run an experiment against a dataset

1. Find or create a dataset:
   ```bash
   ax datasets list --space SPACE
   ax datasets export DATASET_NAME --space SPACE --stdout | jq 'length'
   ```
2. Export the dataset examples:
   ```bash
   ax datasets export DATASET_NAME --space SPACE
   ```
   `ax datasets export` returns one page of examples by default. Add `--all` only when the dataset is larger than one page and the experiment must cover every example.
3. Call the real model API for each example and collect outputs. Use `ax datasets export --stdout` to pipe examples directly into an inference script:

   ```bash
   ax datasets export DATASET_NAME --space SPACE --stdout | python3 infer.py > runs.json
   ```

   Write `infer.py` to read examples from stdin, call the target model, and write runs JSON to stdout. Start from the template at `references/inference-template.py` — copy it, inspect the exported dataset JSON to confirm the input field name, then uncomment the provider block the user wants.

   **Before running:** install the SDK, set the API key env var. If the API isn't reachable, stop and tell the user.

4. Verify the runs file:
   ```bash
   python3 -c "import json; runs=json.load(open('runs.json')); print(f'{len(runs)} runs'); print(json.dumps(runs[0], indent=2))"
   ```
   Each run must have `example_id` (the dataset row's top-level `id`) and `output`. `metadata` is optional. Scores are attached in steps 7–9.
5. Create the experiment:
   ```bash
   ax experiments create --name "gpt-4o-baseline" --dataset DATASET_NAME --space SPACE --file runs.json
   ```
6. Verify: `ax experiments get "gpt-4o-baseline" --dataset DATASET_NAME --space SPACE`

7. Export the experiment to structured data so you can read each run's `id` alongside its `example_id`. Confirm that the exported run records include both fields.
8. Build the annotation file with structured JSON handling, keyed by `record_id` (the run `id`). Score/label each run via an LLM-as-judge, a code check, or human review; never fabricate scores. Create the annotation config first (here, categorical `correctness` with values `correct`/`incorrect`). Emit the shape in [Annotation file schema](#annotation-file-schema).
9. Attach the scores with `ax experiments annotate-runs ... --file annotations.json`, then export or inspect the experiment to confirm the evaluations are attached.

### Compare two experiments

1. Export both experiments with `--stdout > a.json` and `--stdout > b.json` (see [Export Experiment](#export-experiment-ax-experiments-export)).
   These examples read an evaluator task's `correctness` results (`.additional_properties["eval.correctness.score"]`). For `annotate-runs` values, use `(.annotations // [] | map(select(.name == "correctness"))[0].score)` instead.
2. Average correctness score (swap `a.json` for `b.json` to check the other experiment):
   ```bash
   jq '[.[] | .additional_properties["eval.correctness.score"]] | add / length' a.json
   ```
3. Find examples where results differ:
   ```bash
   jq -s '.[0] as $a | .[1][] | . as $run | {example_id: $run.example_id, b_score: $run.additional_properties["eval.correctness.score"], a_score: ($a[] | select(.example_id == $run.example_id) | .additional_properties["eval.correctness.score"])}' a.json b.json
   ```
4. Score distribution per evaluator (pass/fail/partial counts; swap files for the other experiment):
   ```bash
   jq '[.[] | .additional_properties["eval.correctness.label"]] | group_by(.) | map({label: .[0], count: length})' a.json
   ```
5. Find regressions (examples that passed in A but fail in B):
   ```bash
   jq -s '[.[0][] | select(.additional_properties["eval.correctness.label"] == "correct")] as $passed_a | [.[1][] | select(.additional_properties["eval.correctness.label"] != "correct") | select(.example_id as $id | $passed_a | any(.example_id == $id))]' a.json b.json
   ```

**Statistical significance note:** reliable with ≥ 30 examples per evaluator; with fewer, treat the delta as directional only — a 5% difference on n=10 may be noise. Report sample size alongside scores: `jq 'length' a.json`.

## Related Skills

- **arize-dataset**: Create or export the dataset this experiment runs against → use `arize-dataset` first
- **arize-prompts**: Store and version the prompt template in Prompt Hub (`ax prompts`) before or after experiments
- **arize-prompt-optimization**: Use experiment results to improve prompts → next step is `arize-prompt-optimization`
- **arize-trace**: Inspect individual span traces for failing experiment runs → use `arize-trace`
- **arize-link**: Generate clickable UI links to traces from experiment runs → use `arize-link`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See [references/ax-setup.md](references/ax-setup.md) |
| `401 Unauthorized` | API key is wrong, expired, or doesn't have access to this space. Fix the profile using [references/ax-profiles.md](references/ax-profiles.md). |
| `No profile found` | No profile is configured. See [references/ax-profiles.md](references/ax-profiles.md) to create one. |
| `Experiment not found` | Check with `ax experiments get NAME --dataset DATASET --space SPACE` (omit `--dataset` if standalone) |
| `Invalid runs file` | Each run must have `example_id` and `output` fields |
| `example_id mismatch` | `example_id` must be the dataset row's **top-level `id`** from `ax datasets export` — not a value nested in the example's fields or `additional_properties`. Export the dataset and inspect the top-level `id` field. |
| Runs created but no scores / evals in the UI | See the warning under [Create Experiment](#create-experiment-ax-experiments-create); attach scores with `annotate-runs`. |
| `annotate-runs` reports success but nothing changes | `record_id` must be the run `id`; see [Annotation file schema](#annotation-file-schema). |
| `annotate-runs`: `no annotation config with name '...'` | Create the config first (see the **arize-annotation** skill); `name` must match it exactly. |
| `annotate-runs`: `score must not be set` or `label '...' is not one of` | The value doesn't fit the config type: categorical takes a `label` from its values, continuous a `score`, freeform `text`. |
| `No runs found` | Export returned empty -- verify experiment has runs via `ax experiments get` |
| `Dataset not found` | The linked dataset may have been deleted; check with `ax datasets get NAME --space SPACE` |

## Save Credentials for Future Use

See [references/ax-profiles.md](references/ax-profiles.md) § Save Credentials for Future Use.
