---
name: arize-align-evaluator
description: "INVOKE THIS SKILL when aligning an LLM-as-judge evaluator against human ground truth. Covers measuring agreement, diagnosing bias, revising evaluator templates, and iterating until alignment meets a threshold. Triggers: align evaluator, evaluator agreement, compare eval to human labels, ground truth alignment, calibrate evaluator, evaluator bias, confusion matrix, inter-rater agreement."
---

# Arize Align Evaluator Skill

Align an LLM-as-judge evaluator to human ground truth. This skill measures how well an evaluator's automated labels match human judgments, diagnoses disagreement patterns, and iterates on the evaluator template until agreement reaches a target threshold.

---

## Prerequisites

Three things are needed: `ax` CLI, an API key (env var or profile), and a space ID.

If `ax` is not installed, not on PATH, or below version `0.8.0`, see ax-setup.md.

**macOS/Linux:**
```bash
ax --version && echo "--- env ---" && if [ -n "$ARIZE_API_KEY" ]; then echo "ARIZE_API_KEY: (set)"; else echo "ARIZE_API_KEY: (not set)"; fi && echo "ARIZE_SPACE_ID: ${ARIZE_SPACE_ID:-(not set)}" && echo "--- profiles ---" && ax profiles show 2>&1
```

**Windows (PowerShell):**
```powershell
ax --version; Write-Host "--- env ---"; Write-Host "ARIZE_API_KEY: $(if ($env:ARIZE_API_KEY) { '(set)' } else { '(not set)' })"; Write-Host "ARIZE_SPACE_ID: $env:ARIZE_SPACE_ID"; Write-Host "--- profiles ---"; ax profiles show 2>&1
```

Proceed immediately if env var or profile has an API key. Only ask the user if both are missing.

- No API key in env **and** no profile → **AskQuestion**: "Arize API key (https://app.arize.com/admin > API Keys)"
- Space ID unknown → run `ax spaces list -o json` to list all accessible spaces, or **AskQuestion**

---

## Concepts

### What is Evaluator Alignment?

**Alignment** measures how well an LLM-as-judge evaluator reproduces human judgments. A perfectly aligned evaluator would label every example exactly the way a human reviewer would.

The alignment loop:

```
1. Gather ground truth (human labels)
2. Run the evaluator on the same data
3. Compare: eval label vs human label for each example
4. Compute agreement metrics (accuracy, confusion matrix)
5. Analyze disagreements — find systematic patterns
6. Revise the evaluator template to fix the patterns
7. Re-run and re-measure — repeat until agreement meets threshold
```

### Agreement Metrics

| Metric | What it tells you |
|--------|-------------------|
| **Accuracy** | % of examples where eval label == ground truth label. Start here. |
| **Confusion matrix** | Counts per (ground_truth, eval_label) pair. Shows where the evaluator gets confused. |
| **Per-label precision** | Of all examples the evaluator labeled X, what fraction actually are X? Low precision = too many false positives for that label. |
| **Per-label recall** | Of all examples that are truly X, what fraction did the evaluator label X? Low recall = too many false negatives for that label. |

### Where Ground Truth Can Come From

| Source | How it looks | Which flow to use |
|--------|-------------|-------------------|
| Human annotations on project spans | `annotation.<name>.label` on exported spans | Flow A |
| A dataset column with human labels | e.g. `ground_truth_label` field on dataset examples | Flow B |
| User provides labels interactively or in bulk | No ground truth exists yet | Flow C (builds a dataset, then uses Flow B) |

---

## Flow Decision

Ask the user (or infer from context) which situation they are in:

1. **"I have annotated spans in a project"** → Flow A
2. **"I have a dataset with ground truth labels"** → Flow B
3. **"I don't have ground truth yet"** → Flow C

If the user mentions a dataset with a label column, or provides a file with labels, use Flow B. If they mention annotations on spans, use Flow A. If they want to build ground truth from scratch, use Flow C.

---

## Flow A: Align Against Span Annotations

Use when the user has a project with human annotations on spans and wants an evaluator that matches those annotations.

### Step 1: Export annotated spans

```bash
ax spans export PROJECT_ID --space-id SPACE_ID --days 30 --stdout
```

Filter to spans that have the relevant annotation. Inspect the annotation name:

```bash
ax spans export PROJECT_ID --space-id SPACE_ID -l 5 --days 30 --stdout | \
  python3 -c "
import sys, json
spans = json.load(sys.stdin)
for s in spans:
    for k in s:
        if k.startswith('annotation.') and k.endswith('.label'):
            print(k, '=', s[k])
"
```

Note the annotation name (e.g. `annotation.Correctness.label`) and its possible values.

### Step 2: Check for an existing evaluator

```bash
ax evaluators list --space-id SPACE_ID -o json
```

If one exists for this task, note its ID and get the current template:

```bash
ax evaluators get EVALUATOR_ID -o json
```

### Step 3: Create or confirm an evaluator

If no evaluator exists, create one. Match the classification choices to the annotation's label values:

```bash
ax ai-integrations list --space-id SPACE_ID -o json
```

```bash
ax evaluators create \
  --name "Correctness (aligned)" \
  --space-id SPACE_ID \
  --template-name "correctness" \
  --commit-message "Initial alignment version" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --use-function-calling \
  --invocation-params '{"temperature": 0}' \
  --classification-choices '{"correct": 1, "incorrect": 0}' \
  --template 'You are a correctness evaluator. Given the user question and the model response, decide if the response correctly answers the question.

Question: {input}

Model response: {output}

Respond with exactly one of these labels: correct, incorrect'
```

### Step 4: Run the evaluator on spans

Determine column mappings from actual span data:

```bash
ax spans export PROJECT_ID --space-id SPACE_ID -l 5 --days 7 --stdout
```

Create and trigger a task:

```bash
ax tasks create \
  --name "Alignment Run" \
  --task-type template_evaluation \
  --project-id PROJECT_ID \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "attributes.input.value", "output": "attributes.output.value"}}]' \
  --no-continuous

ax tasks trigger-run TASK_ID \
  --data-start-time "START_TIME" \
  --data-end-time "END_TIME" \
  --override-evaluations \
  --wait
```

Use `--override-evaluations` so re-runs during iteration replace previous scores.

### Step 5: Export scored spans and compute agreement

```bash
ax spans export PROJECT_ID --space-id SPACE_ID --days 30 --stdout > scored_spans.json
```

Extract label pairs and compute metrics:

```bash
python3 -c "
import json, sys

spans = json.load(open('scored_spans.json'))
pairs = []
for s in spans:
    human = s.get('annotation.ANNOTATION_NAME.label')
    evl = s.get('eval.EVAL_NAME.label')
    if human and evl:
        pairs.append({'human': human, 'eval': evl, 'input': s.get('attributes.input.value', '')[:100], 'output': s.get('attributes.output.value', '')[:100]})

total = len(pairs)
agree = sum(1 for p in pairs if p['human'] == p['eval'])
print(f'Agreement: {agree}/{total} ({100*agree/total:.1f}%)')

# Confusion matrix
from collections import Counter
matrix = Counter((p['human'], p['eval']) for p in pairs)
print('\nConfusion matrix (human_label, eval_label): count')
for (h, e), c in sorted(matrix.items()):
    print(f'  ({h}, {e}): {c}')

# Disagreements
print(f'\nDisagreements ({total - agree}):')
for p in pairs:
    if p['human'] != p['eval']:
        print(f'  human={p[\"human\"]} eval={p[\"eval\"]} input={p[\"input\"]}...')
"
```

### Step 6: Analyze and revise

If agreement is below the target threshold (suggest 80-90%), analyze the disagreements and revise the evaluator template. See the Alignment Meta-Prompt section below.

Create a new evaluator version:

```bash
ax evaluators create-version EVALUATOR_ID \
  --commit-message "Alignment iteration 2 — fixed bias toward X" \
  --template-name "correctness" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --use-function-calling \
  --classification-choices '{"correct": 1, "incorrect": 0}' \
  --template 'REVISED_TEMPLATE_HERE'
```

### Step 7: Re-run and re-measure

Go back to Step 4 with `--override-evaluations`. Compare the new agreement to the previous round. Continue until the target threshold is met or improvement plateaus.

---

## Flow B: Align Against Dataset Ground Truth

Use when the user has a dataset with a ground truth label column and an experiment with model outputs.

### Step 1: Inspect the dataset and experiment

```bash
ax datasets export DATASET_ID --stdout | python3 -c "import sys,json; ex=json.load(sys.stdin); print(json.dumps(ex[0], indent=2))"
```

Identify the ground truth column name (e.g. `ground_truth_label`, `expected_label`, `human_label`).

```bash
ax experiments export EXPERIMENT_ID --stdout | python3 -c "import sys,json; runs=json.load(sys.stdin); print(json.dumps(runs[0], indent=2))"
```

Note the `output` field and any existing `evaluations`.

**If the user has a dataset but no experiment:** Create an experiment first using the **arize-experiment** skill, or build one from a runs file:

```bash
ax experiments create --name "alignment-baseline" --dataset-id DATASET_ID --file runs.json
```

### Step 2: Create or confirm an evaluator

Same as Flow A Steps 2-3. Match classification choices to the ground truth label values in the dataset.

### Step 3: Run the evaluator on the experiment

```bash
ax tasks create \
  --name "Alignment Scoring" \
  --task-type template_evaluation \
  --dataset-id DATASET_ID \
  --experiment-ids "EXP_ID" \
  --evaluators '[{"evaluator_id": "EVAL_ID", "column_mappings": {"input": "input", "output": "output"}}]' \
  --no-continuous

ax tasks trigger-run TASK_ID \
  --experiment-ids "EXP_ID" \
  --wait
```

Column mappings for experiment runs use top-level field names (e.g. `"output"` not `"attributes.output.value"`). If `input` is not on the run, check the dataset examples — the platform may resolve it from the linked example.

### Step 4: Export and compute agreement

```bash
ax experiments export EXPERIMENT_ID --stdout > runs.json
ax datasets export DATASET_ID --stdout > examples.json
```

Join by `example_id` and compare:

```bash
python3 -c "
import json

examples = {e['id']: e for e in json.load(open('examples.json'))}
runs = json.load(open('runs.json'))

GT_COL = 'ground_truth_label'  # adjust to actual column name
EVAL_NAME = 'correctness'      # adjust to actual eval template-name

pairs = []
for r in runs:
    ex = examples.get(r['example_id'], {})
    human = ex.get(GT_COL)
    evl = (r.get('evaluations', {}).get(EVAL_NAME, {}) or {}).get('label')
    if human and evl:
        pairs.append({
            'example_id': r['example_id'],
            'human': human,
            'eval': evl,
            'output': str(r.get('output', ''))[:100],
            'explanation': (r.get('evaluations', {}).get(EVAL_NAME, {}) or {}).get('explanation', '')
        })

total = len(pairs)
agree = sum(1 for p in pairs if p['human'] == p['eval'])
print(f'Agreement: {agree}/{total} ({100*agree/total:.1f}%)')

from collections import Counter
matrix = Counter((p['human'], p['eval']) for p in pairs)
print('\\nConfusion matrix (human, eval): count')
for (h, e), c in sorted(matrix.items()):
    print(f'  ({h}, {e}): {c}')

labels = sorted(set(p['human'] for p in pairs))
for lbl in labels:
    tp = sum(1 for p in pairs if p['human'] == lbl and p['eval'] == lbl)
    fp = sum(1 for p in pairs if p['human'] != lbl and p['eval'] == lbl)
    fn = sum(1 for p in pairs if p['human'] == lbl and p['eval'] != lbl)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    print(f'\\n{lbl}: precision={prec:.2f} recall={rec:.2f}')

print(f'\\nDisagreements ({total - agree}):')
for p in pairs:
    if p['human'] != p['eval']:
        print(f'  id={p[\"example_id\"]} human={p[\"human\"]} eval={p[\"eval\"]} output={p[\"output\"]}...')
        if p['explanation']:
            print(f'    eval_explanation: {p[\"explanation\"][:200]}')
"
```

### Step 5: Analyze and revise

Use the Alignment Meta-Prompt below with the disagreement data. Create a new evaluator version:

```bash
ax evaluators create-version EVALUATOR_ID \
  --commit-message "Alignment iteration N" \
  --template-name "TEMPLATE_NAME" \
  --ai-integration-id INT_ID \
  --model-name "gpt-4o" \
  --include-explanations \
  --use-function-calling \
  --classification-choices 'SAME_CHOICES' \
  --template 'REVISED_TEMPLATE'
```

### Step 6: Re-run and re-measure

Trigger a new run on the same experiment and compare. Continue until the target is met.

```bash
ax tasks trigger-run TASK_ID \
  --experiment-ids "EXP_ID" \
  --wait
```

---

## Flow C: Build an Alignment Dataset

Use when the user wants to align an evaluator but has no ground truth yet. This flow creates a labeled alignment dataset, then hands off to Flow B.

### Step 1: Sample representative data

From a project:

```bash
ax spans export PROJECT_ID --space-id SPACE_ID -l 30 --days 30 --stdout
```

Or from an existing dataset:

```bash
ax datasets export DATASET_ID --stdout
```

### Step 2: Present examples for labeling

Show the user each example's input and output and ask them to label it. Use **AskQuestion** to collect labels in batches:

> "Here are 10 examples. For each, what label would you assign? (correct / incorrect)"

Alternatively, the user can provide labels in bulk as a JSON or CSV file.

### Step 3: Create the alignment dataset

Build a JSON array with `input`, `output`, and `ground_truth_label`:

```bash
python3 -c "
import json
data = [
    {'input': '...', 'output': '...', 'ground_truth_label': 'correct'},
    {'input': '...', 'output': '...', 'ground_truth_label': 'incorrect'},
]
print(json.dumps(data))
" | ax datasets create --name "alignment-set-EVAL_NAME" --space-id SPACE_ID --file -
```

### Step 4: Create an experiment

Build a runs file from the same data:

```bash
ax datasets export DATASET_ID --stdout | python3 -c "
import json, sys
examples = json.load(sys.stdin)
runs = [{'example_id': ex['id'], 'output': ex['output']} for ex in examples]
print(json.dumps(runs))
" | ax experiments create --name "alignment-baseline" --dataset-id DATASET_ID --file -
```

### Step 5: Continue with Flow B

Proceed from Flow B Step 2 (create or confirm evaluator) onward.

---

## Alignment Meta-Prompt

Use this template when the evaluator's agreement is below threshold. Fill in the placeholders and use the LLM to generate a revised evaluator template.

````
You are an expert at calibrating LLM-as-judge evaluators to match human judgment.
Given the current evaluator template and examples where it disagrees with human
reviewers, produce a revised template that better matches the human labeling pattern.

CURRENT EVALUATOR TEMPLATE
===========================

{PASTE_CURRENT_TEMPLATE}

===========================

CLASSIFICATION CHOICES: {PASTE_CHOICES}

AGREEMENT SO FAR: {ACCURACY}% ({AGREE}/{TOTAL})

DISAGREEMENT EXAMPLES
=====================

Each record shows: the input, the model output, what the human labeled, what the
evaluator labeled, and the evaluator's explanation (if available).

{PASTE_DISAGREEMENT_RECORDS}

=====================

ANALYSIS INSTRUCTIONS

1. Look at the disagreements as a group. Identify the PATTERN — what kind of
   examples does the evaluator get wrong?

   Common patterns:
   - Too strict: rejects partial/paraphrased but acceptable answers
   - Too lenient: accepts plausible-sounding but factually wrong answers
   - Format-sensitive: penalizes correct answers that are verbose or differently formatted
   - Literal matching: requires exact wording instead of semantic equivalence

2. For each pattern, determine what instruction in the template causes it and
   how to fix it.

RULES FOR THE REVISED TEMPLATE

- Keep the same template variables: {input}, {output}, and any others in the original
- Keep the same classification choice labels (same spelling, same casing)
- Keep the final instruction line ("Respond with exactly one of these labels: ...")
- DO NOT add few-shot examples copied from the disagreement data
- DO add general guidelines that address the identified patterns
- Keep temperature-0 scoring in mind: be precise and unambiguous

OUTPUT FORMAT

Return the revised template as a single text block (not JSON, not messages — just
the raw template text with {variable} placeholders preserved).

Then provide a brief summary of:
- What pattern(s) you identified
- What you changed and why
- Expected impact on agreement
````

### How to use the meta-prompt

1. Paste the current evaluator template (from `ax evaluators get`)
2. Paste the classification choices
3. Paste the accuracy from the agreement computation
4. Paste the disagreement records (input, output, human label, eval label, explanation)
5. Send to the LLM (the agent itself can process this)
6. Review the revised template — verify variables and labels are preserved
7. Create a new evaluator version with the revised template

---

## Iteration Best Practices

### How many examples are enough?

- **Minimum**: 20 labeled examples for a binary evaluator. Fewer than that and agreement percentages are noisy.
- **Recommended**: 30-50 examples for reliable metrics. Include edge cases and borderline examples, not just easy ones.
- **Diminishing returns**: Beyond 100 examples, improvement per iteration slows. Invest in example diversity over volume.

### When to stop iterating

- Agreement is above the target threshold (80-90% is a reasonable default for binary evaluators)
- Agreement stopped improving between iterations (plateau)
- Remaining disagreements are genuinely ambiguous — reasonable humans would disagree too
- After 3-4 iterations, further gains are unlikely from template changes alone

### Avoiding overfitting

- The revised template should express **general principles**, not memorize specific examples
- If the template starts referencing very specific patterns from the test data ("if the answer mentions X, label it Y"), it is overfitting
- After revising, consider testing on a held-out set of labeled examples that were NOT used in the disagreement analysis

### Target thresholds by evaluator type

| Evaluator type | Reasonable target | Why |
|---------------|-------------------|-----|
| Binary (correct/incorrect) | 85-90% | Clear-cut labels; high agreement is achievable |
| Binary (hallucinated/factual) | 80-85% | Hallucination boundaries are fuzzier |
| Multi-class (3+ labels) | 70-80% | Middle classes are inherently ambiguous |
| Subjective (tone, helpfulness) | 70-75% | Even humans disagree at ~75-80% on these |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See ax-setup.md |
| `401 Unauthorized` | API key may not have access to this space. Verify at https://app.arize.com/admin > API Keys |
| No annotations on spans | Human annotations must be applied first — use the **arize-annotation** skill or the Arize UI |
| No `ground_truth_label` column | The dataset needs a column with human labels. Ask the user which column contains ground truth, or use Flow C to create one. |
| Evaluator task requires an experiment | Tasks run against experiments, not bare datasets. Create an experiment first. |
| Agreement is 0% | Check that classification choice labels match ground truth labels exactly (same spelling, same casing). E.g. `correct` vs `Correct` will never match. |
| Agreement doesn't improve after revision | The disagreements may be genuinely ambiguous. Review the examples — if reasonable humans would disagree, the evaluator is at its ceiling. |
| `--override-evaluations` not working | Ensure the flag is passed to `trigger-run`, not `tasks create`. |
| Eval scores present but labels are null | The evaluator template may not be producing valid labels. Check that the template's response instruction matches `--classification-choices` exactly. |
| Run `completed` with 0 spans | Widen the time window on `trigger-run`. The eval index may not cover the requested range. |
| Column mapping errors | For project tasks, use span attribute paths (e.g. `attributes.input.value`). For experiment tasks, use top-level run field names (e.g. `output`). |

---

## Related Skills

- **arize-evaluator**: Full evaluator and task CRUD — creating evaluators, running tasks, column mappings, continuous monitoring
- **arize-annotation**: Create annotation configs and bulk-annotate spans with the Python SDK
- **arize-experiment**: Create experiments and export runs for alignment measurement
- **arize-dataset**: Create and manage datasets that hold ground truth labels
- **arize-prompt-optimization**: Optimize application prompts (distinct from evaluator template alignment)
- **arize-link**: Deep links to evaluators and tasks in the Arize UI

---

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any credentials during this conversation **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them.

**Skip this entirely if:**
- The API key was already loaded from an existing profile or `ARIZE_API_KEY` env var
- The space ID was already set via `ARIZE_SPACE_ID` env var

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — See ax-profiles.md. Run `ax profiles show` to check the current state, then use `ax profiles create` or `ax profiles update` with the appropriate flags to save the key (and region if relevant).

2. **Space ID** — See ax-profiles.md (Space ID section) to persist it as an environment variable.
