---
name: arize-prompt-optimization
description: "INVOKE THIS SKILL when optimizing, improving, or debugging LLM prompts using production trace data, evaluations, and annotations. Covers extracting prompts from spans, gathering performance signal, and running a data-driven optimization loop using the ax CLI."
---

# Arize Prompt Optimization Skill

## Concepts

### Where Prompts Live in Trace Data

LLM applications emit spans following OpenInference semantic conventions. Prompts are stored in different span attributes depending on the span kind and instrumentation:

| Column | What it contains | When to use |
|--------|-----------------|-------------|
| `attributes.llm.input_messages` | Structured chat messages (system, user, assistant, tool) in role-based format | **Primary source** for chat-based LLM prompts |
| `attributes.llm.input_messages.roles` | Array of roles: `system`, `user`, `assistant`, `tool` | Extract individual message roles |
| `attributes.llm.input_messages.contents` | Array of message content strings | Extract message text |
| `attributes.input.value` | Serialized prompt or user question (generic, all span kinds) | Fallback when structured messages are not available |
| `attributes.llm.prompt_template.template` | Template with `{variable}` placeholders (e.g., `"Answer {question} using {context}"`) | When the app uses prompt templates |
| `attributes.llm.prompt_template.variables` | Template variable values (JSON object) | See what values were substituted into the template |
| `attributes.output.value` | Model response text | See what the LLM produced |
| `attributes.llm.output_messages` | Structured model output (including tool calls) | Inspect tool-calling responses |

### Finding Prompts by Span Kind

- **LLM span** (`attributes.openinference.span.kind = 'LLM'`): Check `attributes.llm.input_messages` for structured chat messages, OR `attributes.input.value` for a serialized prompt. Check `attributes.llm.prompt_template.template` for the template.
- **Chain/Agent span**: `attributes.input.value` contains the user's question. The actual LLM prompt lives on **child LLM spans** -- navigate down the trace tree.
- **Tool span**: `attributes.input.value` has tool input, `attributes.output.value` has tool result. Not typically where prompts live.

### Performance Signal Columns

These columns carry the feedback data used for optimization:

| Column pattern | Source | What it tells you |
|---------------|--------|-------------------|
| `annotation.<name>.label` | Human reviewers | Categorical grade (e.g., `correct`, `incorrect`, `partial`) |
| `annotation.<name>.score` | Human reviewers | Numeric quality score (e.g., 0.0 - 1.0) |
| `annotation.<name>.text` | Human reviewers | Freeform explanation of the grade |
| `eval.<name>.label` | LLM-as-judge evals | Automated categorical assessment |
| `eval.<name>.score` | LLM-as-judge evals | Automated numeric score |
| `eval.<name>.explanation` | LLM-as-judge evals | Why the eval gave that score -- **most valuable for optimization** |
| `attributes.input.value` | Trace data | What went into the LLM |
| `attributes.output.value` | Trace data | What the LLM produced |
| `{experiment_name}.output` | Experiment runs | Output from a specific experiment |

## Prerequisites

Three things are needed: `ax` CLI, an API key (env var or profile), and a space ID. A project name or ID is also needed but usually comes from the user's message.

### Install ax

Verify `ax` is installed and working before proceeding:

1. Check if `ax` is on PATH: `command -v ax` (Unix) or `where ax` (Windows)
2. If not found, check common install locations:
   - macOS/Linux: `test -x ~/.local/bin/ax && export PATH="$HOME/.local/bin:$PATH"`
   - Windows: check `%APPDATA%\Python\Scripts\ax.exe` or `%LOCALAPPDATA%\Programs\Python\Scripts\ax.exe`
3. If still not found, install it (requires shell access to install packages):
   - Preferred: `uv tool install arize-ax-cli`
   - Alternative: `pipx install arize-ax-cli`
   - Fallback: `pip install arize-ax-cli`
4. After install, if `ax` is not on PATH:
   - macOS/Linux: `export PATH="$HOME/.local/bin:$PATH"`
   - Windows (PowerShell): `$env:PATH = "$env:APPDATA\Python\Scripts;$env:PATH"`
5. If `ax --version` fails with an SSL/certificate error:
   - macOS: `export SSL_CERT_FILE=/etc/ssl/cert.pem`
   - Linux: `export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`
   - Windows (PowerShell): `$env:SSL_CERT_FILE = "C:\Program Files\Common Files\SSL\cert.pem"` (or use `python -c "import certifi; print(certifi.where())"` to find the cert bundle)
6. `ax --version` must succeed before proceeding. If it doesn't, stop and ask the user for help.

### Verify environment

Run a quick check for credentials:

**macOS/Linux (bash):**
```bash
ax --version && echo "--- env ---" && if [ -n "$ARIZE_API_KEY" ]; then echo "ARIZE_API_KEY: (set)"; else echo "ARIZE_API_KEY: (not set)"; fi && echo "ARIZE_SPACE_ID: ${ARIZE_SPACE_ID:-(not set)}" && echo "ARIZE_DEFAULT_PROJECT: ${ARIZE_DEFAULT_PROJECT:-(not set)}" && echo "--- profiles ---" && ax profiles show 2>&1
```

**Windows (PowerShell):**
```powershell
ax --version; Write-Host "--- env ---"; Write-Host "ARIZE_API_KEY: $(if ($env:ARIZE_API_KEY) { '(set)' } else { '(not set)' })"; Write-Host "ARIZE_SPACE_ID: $env:ARIZE_SPACE_ID"; Write-Host "ARIZE_DEFAULT_PROJECT: $env:ARIZE_DEFAULT_PROJECT"; Write-Host "--- profiles ---"; ax profiles show 2>&1
```

**Read the output and proceed immediately** if either the env var or the profile has an API key. Only ask the user if **both** are missing. Resolve failures:

- No API key in env **and** no profile → **AskQuestion**: "Arize API key (https://app.arize.com/admin > API Keys)"
- Space ID unknown → **AskQuestion**, or run `ax projects list -o json --limit 100 --space-id $ARIZE_SPACE_ID` and search for a match
- Project unclear → ask, or run `ax projects list -o json --limit 100` and present as selectable options

**IMPORTANT:** `--space-id` is required when using a human-readable project name as the `PROJECT` positional argument on `ax spans export` and `ax traces export`. It is not needed when using a base64-encoded project ID. If you hit `401 Unauthorized` or limit errors when using a project name, resolve it to a base64 ID first: run `ax projects list --space-id SPACE_ID -l 100 -o json`, find the project by `name`, and use its `id` as `PROJECT`.

### Default Project

If `ARIZE_DEFAULT_PROJECT` is set (visible in the output above), use its value as the project for **all** commands in this session. Do NOT ask the user for a project ID -- just use it. Continue using this default until the user explicitly provides a different project.

If `ARIZE_DEFAULT_PROJECT` is not set and no project is provided, ask the user for one.

## Phase 1: Extract the Current Prompt

### Find LLM spans containing prompts

```bash
# Sample LLM spans (where prompts live) -- use ax spans export with --filter
ax spans export PROJECT_ID --filter "attributes.openinference.span.kind = 'LLM'" -l 10 --output-dir .arize-tmp-traces

# Filter by model
ax spans export PROJECT_ID --filter "attributes.llm.model_name = 'gpt-4o'" -l 10 --output-dir .arize-tmp-traces

# Filter by span name (e.g., a specific LLM call)
ax spans export PROJECT_ID --filter "name = 'ChatCompletion'" -l 10 --stdout | jq '.[0]'
```

### Export a trace to inspect prompt structure

```bash
# Export all spans in a trace (PROJECT_ID is the first positional argument)
ax spans export PROJECT_ID --trace-id TRACE_ID --output-dir .arize-tmp-traces

# Export a single span
ax spans export PROJECT_ID --span-id SPAN_ID --output-dir .arize-tmp-traces
```

### Extract prompts from exported JSON

```bash
# Extract structured chat messages (system + user + assistant)
jq '.[0] | {
  messages: .attributes.llm.input_messages,
  model: .attributes.llm.model_name
}' trace_*/spans.json

# Extract the system prompt specifically
jq '[.[] | select(.attributes.llm.input_messages.roles[]? == "system")] | .[0].attributes.llm.input_messages' trace_*/spans.json

# Extract prompt template and variables
jq '.[0].attributes.llm.prompt_template' trace_*/spans.json

# Extract from input.value (fallback for non-structured prompts)
jq '.[0].attributes.input.value' trace_*/spans.json
```

### Reconstruct the prompt as messages

Once you have the span data, reconstruct the prompt as a messages array:

```json
[
  {"role": "system", "content": "You are a helpful assistant that..."},
  {"role": "user", "content": "Given {input}, answer the question: {question}"}
]
```

If the span has `attributes.llm.prompt_template.template`, the prompt uses variables. Preserve these placeholders (`{variable}` or `{{variable}}`) -- they are substituted at runtime.

## Phase 2: Gather Performance Data

### From traces (production feedback)

```bash
# Find error spans -- these indicate prompt failures
ax spans export PROJECT_ID \
  --filter "status_code = 'ERROR' AND attributes.openinference.span.kind = 'LLM'" \
  -l 20 --output-dir .arize-tmp-traces

# Find spans with low eval scores
ax spans export PROJECT_ID \
  --filter "annotation.correctness.label = 'incorrect'" \
  -l 20 --output-dir .arize-tmp-traces

# Find spans with high latency (may indicate overly complex prompts)
ax spans export PROJECT_ID \
  --filter "attributes.openinference.span.kind = 'LLM' AND latency_ms > 10000" \
  -l 20 --output-dir .arize-tmp-traces

# Export error traces for detailed inspection (PROJECT_ID is positional)
ax spans export PROJECT_ID --trace-id TRACE_ID --output-dir .arize-tmp-traces
```

### From datasets and experiments

```bash
# Export a dataset (ground truth examples)
ax datasets export DATASET_ID
# -> dataset_*/examples.json

# Export experiment results (what the LLM produced)
ax experiments export EXPERIMENT_ID
# -> experiment_*/runs.json
```

### Merge dataset + experiment for analysis

Join the two files by `example_id` to see inputs alongside outputs and evaluations:

```bash
# Count examples and runs
jq 'length' dataset_*/examples.json
jq 'length' experiment_*/runs.json

# View a single joined record
jq -s '
  .[0] as $dataset |
  .[1][0] as $run |
  ($dataset[] | select(.id == $run.example_id)) as $example |
  {
    input: $example,
    output: $run.output,
    evaluations: $run.evaluations
  }
' dataset_*/examples.json experiment_*/runs.json

# Find failed examples (where eval score < threshold)
jq '[.[] | select(.evaluations.correctness.score < 0.5)]' experiment_*/runs.json
```

### Identify what to optimize

Look for patterns across failures:

1. **Compare outputs to ground truth**: Where does the LLM output differ from expected?
2. **Read eval explanations**: `eval.*.explanation` tells you WHY something failed
3. **Check annotation text**: Human feedback describes specific issues
4. **Look for verbosity mismatches**: If outputs are too long/short vs ground truth
5. **Check format compliance**: Are outputs in the expected format?

### Choose a primary metric to optimize

Before proceeding, discover what metrics are actually in the data and present them to the user:

```bash
# List all available evaluation metrics and their failure counts
jq -r '
  [.[] | .evaluations // {} | to_entries[]] |
  group_by(.key) |
  map({
    metric: .[0].key,
    failures: map(select(.value.label == "incorrect")) | length,
    total: length
  }) |
  sort_by(-.failures)[] |
  "\(.metric): \(.failures)/\(.total) failures"
' runs.json
```

Present the results and ask: **"Which metric do you want to optimize for? Pick one from the list, or describe something else (e.g. 'responses are too verbose', 'tone is too formal')."** Recommend the one with the highest failure rate as a starting point, but let the user decide.

If the user provides a free-form goal instead of a named metric, treat it as the optimization target and use it to guide failure analysis and the meta-prompt.

Focus on **one metric at a time** — optimizing for multiple at once often makes things worse. Check secondary metrics for regressions after each iteration.

## Phase 3: Optimize the Prompt

### The Optimization Meta-Prompt

See `meta-prompt.md` in this skill directory for the full template. Fill in the three placeholders (`{PASTE_ANY_HARD_CONSTRAINTS_HERE}`, `{PASTE_ORIGINAL_PROMPT_HERE}`, `{PASTE_RECORDS_HERE}`) and send it to your LLM (GPT-4o, Claude, etc.).

### Preparing the performance data

Format the records as a JSON array before pasting into the template:

```bash
# From dataset + experiment: join and select relevant columns
jq -s '
  .[0] as $ds |
  [.[1][] | . as $run |
    ($ds[] | select(.id == $run.example_id)) as $ex |
    {
      input: $ex.input,
      expected: $ex.expected_output,
      actual_output: $run.output,
      eval_score: $run.evaluations.correctness.score,
      eval_label: $run.evaluations.correctness.label,
      eval_explanation: $run.evaluations.correctness.explanation
    }
  ]
' dataset_*/examples.json experiment_*/runs.json

# From exported spans: extract input/output pairs with annotations
jq '[.[] | select(.attributes.openinference.span.kind == "LLM") | {
  input: .attributes.input.value,
  output: .attributes.output.value,
  status: .status_code,
  model: .attributes.llm.model_name
}]' trace_*/spans.json
```

### Applying the revised prompt

After the LLM returns the revised messages array:

1. Compare the original and revised prompts side by side
2. Verify all template variables are preserved
3. Check that format instructions are intact
4. Test on a few examples before full deployment

## Phase 4: Iterate

### The optimization loop

```
1. Extract prompt    -> Phase 1 (once)
2. Record current prompt version (see below)
3. Run experiment    -> ax experiments create ...
4. Export results    -> ax experiments export EXPERIMENT_ID
5. Analyze failures  -> jq to find low scores
6. Run meta-prompt   -> Phase 3 with new failure data
7. Apply revised prompt
8. Check convergence -> STOP if criteria met, else repeat from step 2
```

**Stop conditions (convergence criteria):** Stop iterating when ANY of these is true:
- Primary metric score improves by < 2% between iterations
- Primary metric score exceeds your target threshold (e.g., > 90%)
- 3 iterations completed with no meaningful improvement
- A new iteration introduces regressions that offset the gains

**Prompt version tracking:** Before each experiment, record the prompt version so results are reproducible:
```bash
# Save prompt version alongside the experiment name
echo '{"experiment": "gpt4o-prompt-v2", "prompt": PASTE_PROMPT_JSON_HERE}' > prompt_versions.jsonl
# Or store as experiment metadata field in the runs file
```
Always name experiments to reflect the prompt version: `gpt4o-baseline`, `gpt4o-prompt-v2`, etc.

### Measure improvement

```bash
# Compare scores across experiments
# Experiment A (baseline)
jq '[.[] | .evaluations.correctness.score] | add / length' experiment_a/runs.json

# Experiment B (optimized)
jq '[.[] | .evaluations.correctness.score] | add / length' experiment_b/runs.json

# Find examples that flipped from fail to pass
jq -s '
  [.[0][] | select(.evaluations.correctness.label == "incorrect")] as $fails |
  [.[1][] | select(.evaluations.correctness.label == "correct") |
    select(.example_id as $id | $fails | any(.example_id == $id))
  ] | length
' experiment_a/runs.json experiment_b/runs.json
```

### A/B compare two prompts

1. Create two experiments against the same dataset, each using a different prompt version
2. Export both: `ax experiments export EXP_A` and `ax experiments export EXP_B`
3. Compare average scores, failure rates, and specific example flips
4. Check for regressions -- examples that passed with prompt A but fail with prompt B:
   ```bash
   # Regression detection: passed A but failed B
   jq -s '
     [.[0][] | select(.evaluations.correctness.label == "correct")] as $passed_a |
     [.[1][] | select(.evaluations.correctness.label != "correct") |
       select(.example_id as $id | $passed_a | any(.example_id == $id))
     ]
   ' experiment_a/runs.json experiment_b/runs.json | jq 'length'
   ```

## Prompt Engineering Best Practices

Apply these when writing or revising prompts:

| Technique | When to apply | Example |
|-----------|--------------|---------|
| Clear, detailed instructions | Output is vague or off-topic | "Classify the sentiment as exactly one of: positive, negative, neutral" |
| Instructions at the beginning | Model ignores later instructions | Put the task description before examples |
| Step-by-step breakdowns | Complex multi-step processes | "First extract entities, then classify each, then summarize" |
| Specific personas | Need consistent style/tone | "You are a senior financial analyst writing for institutional investors" |
| Delimiter tokens | Sections blend together | Use `---`, `###`, or XML tags to separate input from instructions |
| Few-shot examples | Output format needs clarification | Show 2-3 synthetic input/output pairs |
| Output length specifications | Responses are too long or short | "Respond in exactly 2-3 sentences" |
| Reasoning instructions | Accuracy is critical | "Think step by step before answering" |
| "I don't know" guidelines | Hallucination is a risk | "If the answer is not in the provided context, say 'I don't have enough information'" |

### Variable preservation

When optimizing prompts that use template variables:

- **Single braces** (`{variable}`): Python f-string / Jinja style. Most common in Arize.
- **Double braces** (`{{variable}}`): Mustache style. Used when the framework requires it.
- Never add or remove variable placeholders during optimization
- Never rename variables -- the runtime substitution depends on exact names
- If adding few-shot examples, use literal values, not variable placeholders

## Workflow Examples

See `workflows.md` in this skill directory for end-to-end examples covering common scenarios:
- Optimize a prompt from a failing trace
- Optimize using a dataset and experiment
- Debug a prompt that produces wrong format
- Reduce hallucination in a RAG prompt

## Related Skills

For workflow steps that involve other skills, invoke that skill's full instructions rather than duplicating them here:

- **arize-trace** — find and export failing/annotated spans, extract prompts from LLM spans, inspect trace trees
- **arize-dataset** — create or export labeled datasets from failed traces for systematic evaluation
- **arize-experiment** — create experiments, run them against a dataset, export results, compare versions

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | **macOS/Linux:** check `~/.local/bin/ax`. **Windows:** check if `ax` is on PATH. If missing: `uv tool install arize-ax-cli` (requires shell access to install packages) |
| `No profile found` | Follow "Verify environment" in Prerequisites to auto-discover or prompt for the API key |
| `401 Unauthorized` with valid API key | You are likely using a project name without `--space-id`. Add `--space-id SPACE_ID`, or resolve to a base64 project ID first: `ax projects list --space-id SPACE_ID -l 100 -o json` and use the project's `id` |
| No `input_messages` on span | Check span kind -- Chain/Agent spans store prompts on child LLM spans, not on themselves |
| Prompt template is `null` | Not all instrumentations emit `prompt_template`. Use `input_messages` or `input.value` instead |
| Variables lost after optimization | Verify the revised prompt preserves all `{var}` placeholders from the original |
| Optimization makes things worse | Check for overfitting -- the meta-prompt may have memorized test data. Ensure few-shot examples are synthetic |
| No eval/annotation columns | Run evaluations first (via Arize UI or SDK), then re-export |
| Experiment output column not found | The column name is `{experiment_name}.output` -- check exact experiment name via `ax experiments get` |
| `jq` errors on span JSON | Ensure you're targeting the correct file path (e.g., `trace_*/spans.json`) |
