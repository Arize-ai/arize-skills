---
name: arize-eval
description: "INVOKE THIS SKILL when creating LLM-as-judge evaluators, setting up AI integrations for evaluation, running evals on project spans, or scoring experiment runs on Arize. Use when the user says: create an evaluator, set up an LLM judge, run evals, score my spans, evaluate my experiment, create a task, trigger an eval run, add an AI integration, or configure an OpenAI/Anthropic/Bedrock integration for Arize."
---

# Arize Eval Skill

## Concepts

- **AI Integration** = stored LLM provider credentials (OpenAI, Anthropic, Bedrock, etc.) used by evaluators to call the judge model
- **Evaluator** = an LLM-as-judge definition; consists of a prompt template and a linked AI integration
- **Evaluator Version** = an immutable snapshot of an evaluator's prompt + model config; new versions supersede the previous one automatically
- **Task** = an evaluation job that applies one or more evaluators to either project spans (ongoing monitoring) or experiment runs (one-time scoring)
- **Task Run** = a single execution of a task; returns scores/labels per span or experiment run

**Three workflows this skill handles:**

1. **Create an Evaluator** — set up an AI integration (if needed), create an evaluator, then create an evaluator version with a prompt template
2. **Evaluate Project Spans** — create a task linked to a project and trigger it to score live or historical spans
3. **Evaluate an Experiment** — create a task linked to a dataset + experiment(s) and trigger it to score experiment runs

## Prerequisites

Three things are needed: `ax` CLI, an API key (env var or profile), and a space ID.

### Install ax

If `ax` is not installed, not on PATH, or below version `0.3.0`, see ax-setup.md.

### Verify environment

Run a quick check for credentials:

**macOS/Linux (bash):**
```bash
ax --version && echo "--- env ---" && if [ -n "$ARIZE_API_KEY" ]; then echo "ARIZE_API_KEY: (set)"; else echo "ARIZE_API_KEY: (not set)"; fi && echo "ARIZE_SPACE_ID: ${ARIZE_SPACE_ID:-(not set)}" && echo "--- profiles ---" && ax profiles show 2>&1
```

**Windows (PowerShell):**
```powershell
ax --version; Write-Host "--- env ---"; Write-Host "ARIZE_API_KEY: $(if ($env:ARIZE_API_KEY) { '(set)' } else { '(not set)' })"; Write-Host "ARIZE_SPACE_ID: $env:ARIZE_SPACE_ID"; Write-Host "--- profiles ---"; ax profiles show 2>&1
```

**Read the output and proceed immediately** if either the env var or the profile has an API key. Only ask the user if **both** are missing. Resolve failures:

- No API key in env **and** no profile → **AskQuestion**: "Arize API key (https://app.arize.com/admin > API Keys)"
- Space ID unknown → run `ax spaces list -o json` to list all accessible spaces and pick the right one, or **AskQuestion** if the user prefers to provide it directly

---

## Workflow 1: Create an Evaluator

### Step 1: Set up an AI Integration

An AI integration stores the LLM provider credentials that the evaluator will use. Check for existing integrations first — the user may already have one.

```bash
ax ai-integrations list --space-id SPACE_ID
```

If a suitable integration exists, note its ID and skip to Step 2. If not, create one:

```bash
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider openAI \
  --api-key "sk-..."
```

**Supported providers:** `openAI`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `anthropic`, `custom`, `nvidiaNim`, `gemini`

**Provider-specific requirements:**

| Provider | Required extra flags |
|----------|---------------------|
| `azureOpenAI` | `--base-url <azure-endpoint>` |
| `awsBedrock` | `--role-arn <arn>` |
| `vertexAI` | `--project-id <gcp-project>`, `--location <region>` |
| `anthropic` | `--api-key <key>` |
| `custom` | `--base-url <endpoint>` |

**Get the integration ID:** After creation, capture the returned ID (e.g., `int_abc123`). Or retrieve it:
```bash
ax ai-integrations get INT_ID
```

### Step 2: Create an Evaluator (with initial version)

`ax evaluators create` creates the evaluator **and** its first version in one command. All version config (template, model, integration) is required up front.

```bash
ax evaluators create \
  --name "Relevance Evaluator" \
  --space-id SPACE_ID \
  --description "Scores whether the response is relevant to the user query" \
  --template-name "relevance" \
  --commit-message "Initial version" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --use-function-calling \
  --template 'You are an evaluator. Rate whether the response is relevant to the query.

User Query: {input}

Response: {output}

Respond with one of: "relevant", "partial", "irrelevant"'
```

Capture the returned evaluator ID (e.g., `RXZhbH...`). Or list to find it:
```bash
ax evaluators list --space-id SPACE_ID
```

**Key flags for `create`:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Evaluator name (unique within space) |
| `--space-id` | yes | Space to create the evaluator in |
| `--template-name` | yes | Eval column name — alphanumeric, spaces, hyphens, underscores |
| `--commit-message` | yes | Description of this initial version |
| `--ai-integration-id` | yes | AI integration global ID (base64) from Step 1 |
| `--model-name` | yes | Model name (e.g., `gpt-4o`, `us.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| `--template` | yes | Prompt with `{variable}` single-brace placeholders |
| `--description` | no | Human-readable description of the evaluator |
| `--include-explanations` | no | Flag: include reasoning alongside the score |
| `--use-function-calling` | no | Flag: prefer structured function-call output when supported |
| `--invocation-params` | no | JSON object of model params (e.g., `'{"temperature": 0.7}'`) |

**Prompt template tips:**
- Use single braces `{input}` and `{output}` — NOT double braces. Double braces will cause a validation error.
- `{input}` and `{output}` map to span `attributes.input.value` and `attributes.output.value` by default (override with `column_mappings` in the task)
- Keep labels simple and consistent (e.g., `"good"`, `"partial"`, `"poor"`)
- Add `--include-explanations` to get reasoning alongside the label

### Step 3: Create Additional Evaluator Versions (optional)

Versions are immutable — to update the prompt or model, create a new version. New versions supersede the previous one automatically.

```bash
ax evaluators create-version EVALUATOR_ID \
  --commit-message "Improve label descriptions" \
  --template-name "relevance" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --template 'Updated prompt here with {input} and {output}'
```

**Verify the evaluator:**
```bash
ax evaluators get EVALUATOR_ID
ax evaluators list-versions EVALUATOR_ID
```

---

## Workflow 2: Evaluate Project Spans

This creates a task that runs evaluators against spans in a live project. Can run continuously on incoming data or on-demand over a time window.

### Step 1: Resolve the Evaluator

List evaluators to find the one to use:
```bash
ax evaluators list --space-id SPACE_ID
```

Or retrieve a specific one if the ID is known:
```bash
ax evaluators get EVALUATOR_ID
```

### Step 2: Resolve the Project ID

Project IDs are base64-encoded. Resolve the project name to its ID:
```bash
ax projects list --space-id SPACE_ID -l 100 -o json
```

Find the project by `name`, copy its `id` field (e.g., `UHJvamVjdDo...`).

### Step 3: Create the Task

```bash
ax tasks create \
  --name "Relevance Monitor" \
  --task-type template_evaluation \
  --project-id PROJ_ID \
  --evaluators '[{"evaluator_id": "ev_abc123"}]' \
  --is-continuous \
  --sampling-rate 0.1
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--project-id` | Base64 project ID (mutually exclusive with `--dataset-id`) |
| `--evaluators` | JSON array of evaluator objects (see format below) |
| `--is-continuous` | Run continuously on new incoming spans |
| `--no-continuous` | One-time run only |
| `--sampling-rate` | Fraction of spans to evaluate (0–1); project-based only |
| `--query-filter` | SQL-style filter applied to all evaluators in this task |

**Evaluators JSON format:**
```json
[
  {
    "evaluator_id": "ev_abc123",
    "query_filter": null,
    "column_mappings": {
      "input": "attributes.input.value",
      "output": "attributes.output.value"
    }
  }
]
```

`column_mappings` maps template variable names (e.g., `{input}`, `{output}`) to span attribute paths. Always specify these explicitly — the defaults may not match your span structure.

**Common column paths by span kind:**

| Template var | LLM span | CHAIN span |
|---|---|---|
| `output` | `attributes.llm.output_messages.0.message.content` | `attributes.output.value` |
| `input` / `user_question` | `attributes.input.value` | `attributes.input.value` |
| `tool_output` | `attributes.input.value` (fallback) | `attributes.output.value` (tool result) |

**Important:** Evaluators designed for LLM spans (e.g., ones that read `llm.output_messages`) will run for several minutes then cancel if pointed at CHAIN spans — even with a valid integration. Always match the query filter to the span kind the evaluator expects.

Multiple evaluators can be chained in a single task:
```json
[
  {"evaluator_id": "ev_relevance", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}},
  {"evaluator_id": "ev_hallucination", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}
]
```

**Verify task was created:**
```bash
ax tasks list --space-id SPACE_ID --project-id PROJ_ID
ax tasks get TASK_ID
```

### Step 4: Trigger a Run

**On-demand (specific time window):**
```bash
ax tasks trigger-run TASK_ID \
  --data-start-time "2024-01-01T00:00:00" \
  --data-end-time "2024-02-01T00:00:00" \
  --wait
```

**Important:** Time format must be `%Y-%m-%dT%H:%M:%S` (no trailing `Z`). ISO 8601 with `Z` suffix will be rejected.

**On-demand (recent data, wait for completion):**
```bash
ax tasks trigger-run TASK_ID --wait
```

**Fire and forget (return immediately):**
```bash
ax tasks trigger-run TASK_ID
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--data-start-time` | ISO 8601 start of data window |
| `--data-end-time` | ISO 8601 end of data window (defaults to now) |
| `--max-spans` | Max spans to process (default 10,000) |
| `--override-evaluations` | Re-evaluate spans that already have labels |
| `--wait` / `-w` | Block until run completes |
| `--timeout` | Max seconds to wait when using `--wait` (default 600) |
| `--poll-interval` | Seconds between polls when using `--wait` (default 5) |

### Step 5: Monitor the Run

```bash
# List runs for a task
ax tasks list-runs TASK_ID

# Get run details
ax tasks get-run RUN_ID

# Wait for an already-triggered run
ax tasks wait-for-run RUN_ID --timeout 300
```

---

## Workflow 3: Evaluate an Experiment

This creates a task that runs evaluators against experiment runs in a dataset. Used for offline evaluation of LLM outputs.

### Step 1: Resolve the Evaluator

```bash
ax evaluators list --space-id SPACE_ID
```

### Step 2: Resolve the Dataset and Experiment IDs

```bash
# List datasets
ax datasets list --space-id SPACE_ID -o json

# List experiments for a dataset
ax experiments list --dataset-id DATASET_ID -o json
```

Capture the dataset `id` and the experiment `id`(s) you want to evaluate.

### Step 3: Create the Task

```bash
ax tasks create \
  --name "Experiment Evaluation" \
  --task-type template_evaluation \
  --dataset-id DATASET_ID \
  --experiment-ids "exp_abc123,exp_def456" \
  --evaluators '[{"evaluator_id": "ev_abc123"}]' \
  --no-continuous
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--dataset-id` | Dataset global ID (mutually exclusive with `--project-id`) |
| `--experiment-ids` | Comma-separated experiment IDs to evaluate |
| `--no-continuous` | Required for dataset-based tasks (experiments are bounded) |

### Step 4: Trigger and Wait

```bash
ax tasks trigger-run TASK_ID \
  --experiment-ids "exp_abc123,exp_def456" \
  --wait
```

**Note:** Pass `--experiment-ids` again on `trigger-run` to specify which experiments this run should score.

---

## Managing Evaluators

### List and inspect

```bash
# List all evaluators in a space
ax evaluators list --space-id SPACE_ID

# Get a specific evaluator with version details
ax evaluators get EVALUATOR_ID

# List all versions
ax evaluators list-versions EVALUATOR_ID

# Get a specific version
ax evaluators get-version VERSION_ID
```

### Update metadata

```bash
ax evaluators update EVALUATOR_ID \
  --name "New Name" \
  --description "Updated description"
```

Note: versions are immutable. To change the prompt or model, create a new version with `ax evaluators create-version`.

### Delete

```bash
ax evaluators delete EVALUATOR_ID
```

**Warning:** This is permanent and removes all versions.

## Managing AI Integrations

```bash
# List integrations
ax ai-integrations list --space-id SPACE_ID

# Get specific integration
ax ai-integrations get INT_ID

# Update (partial update — only provided fields change)
ax ai-integrations update INT_ID --name "New Name"

# Delete (irreversible)
ax ai-integrations delete INT_ID --force
```

## Managing Tasks

```bash
# List tasks (filter by project, dataset, or type)
ax tasks list --space-id SPACE_ID
ax tasks list --project-id PROJ_ID
ax tasks list --dataset-id DATASET_ID
ax tasks list --task-type template_evaluation

# Get task details
ax tasks get TASK_ID

# Cancel a running or pending run
ax tasks cancel-run RUN_ID --force

# Wait for a specific run
ax tasks wait-for-run RUN_ID --timeout 300 --poll-interval 10
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See ax-setup.md |
| `401 Unauthorized` | API key may not have access to this space. Verify key and space ID at https://app.arize.com/admin > API Keys |
| `No profile found` | Run `ax profiles show --expand`; set `ARIZE_API_KEY` env var or write `~/.arize/config.toml` |
| `Evaluator not found` | Verify ID with `ax evaluators list --space-id SPACE_ID` |
| `Integration not found` | Verify with `ax ai-integrations list --space-id SPACE_ID` |
| `Task not found` | Verify with `ax tasks list --space-id SPACE_ID` |
| `project-id and dataset-id are mutually exclusive` | Use only one of `--project-id` or `--dataset-id` when creating a task |
| `experiment-ids required for dataset tasks` | Add `--experiment-ids "exp_abc123"` to both create and trigger-run |
| `sampling-rate only valid for project tasks` | Remove `--sampling-rate` from dataset-based task creation |
| Run stuck in `pending` | Check `ax tasks get-run RUN_ID`; cancel with `ax tasks cancel-run RUN_ID` |
| Run `failed` with `num_skipped > 0` | Spans were found but LLM calls failed — check integration credentials and model name |
| Run `cancelled` instantly (0 successes/errors/skipped) | Backend cancelled the run before processing — check that `data-start-time` window contains actual spans; verify the integration's API key is valid; `trigger-run` is an alpha API and may have edge cases |
| Run `completed` with 0 spans | No spans matched the query_filter in the given time window — broaden the time range or remove the filter |
| No scores appear in the UI | Verify `column_mappings` correctly map template variables to span attribute paths (e.g., `"input": "attributes.input.value"`) |
| Time format error on `trigger-run` | Use `%Y-%m-%dT%H:%M:%S` format (e.g., `2026-03-21T09:00:00`), not ISO 8601 with `Z` suffix |

---

## Related Skills

- **arize-experiment**: Create experiments to evaluate against → use `arize-experiment` to set up the experiment first
- **arize-dataset**: Manage the datasets that experiment-based tasks target → use `arize-dataset`
- **arize-trace**: Export spans to inspect which are being evaluated → use `arize-trace`
- **arize-link**: Generate clickable Arize UI links to tasks and evaluators → use `arize-link`

---

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any of the following during this conversation (via AskQuestion response, pasted text, or inline values) **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them for future use.

| Credential | Where it gets saved |
|------------|---------------------|
| API key | `ax` profile at `~/.arize/config.toml` |
| Space ID | **macOS/Linux:** shell config (`~/.zshrc` or `~/.bashrc`) as `export ARIZE_SPACE_ID="..."`. **Windows:** user environment variable via `[System.Environment]::SetEnvironmentVariable('ARIZE_SPACE_ID', '...', 'User')` |

**Skip this entirely if:**
- The API key was already loaded from an existing profile or `ARIZE_API_KEY` env var
- The space ID was already set via `ARIZE_SPACE_ID` env var

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — Check if `~/.arize/config.toml` exists. If it does, read it and update the `[auth]` section. If not, create it:

   ```toml
   [profile]
   name = "default"

   [auth]
   api_key = "THE_API_KEY"

   [output]
   format = "table"
   ```

   Verify with: `ax profiles show`

2. **Space ID** — Persist as an environment variable:

   **macOS/Linux** — Detect the user's shell config file (`~/.zshrc` for zsh, `~/.bashrc` for bash). Append:

   ```bash
   export ARIZE_SPACE_ID="THE_SPACE_ID"
   ```

   Tell the user to run `source ~/.zshrc` (or restart their terminal) for it to take effect.

   **Windows (PowerShell):**

   ```powershell
   [System.Environment]::SetEnvironmentVariable('ARIZE_SPACE_ID', 'THE_SPACE_ID', 'User')
   ```
