# Revising a judge without overfitting

Every step here comes after the user has approved a named change. Source names refer to [sources.md](sources.md).

## Two kinds of change (SOP step 1)

- **Criterion change.** What "good" means changes. Bump the rubric version, flag the gold labels on that criterion for re-review, and start a new judge version. Scores before and after aren't comparable.
- **Judge change.** The prompt, model or admission filter changes, and the criterion doesn't. This is tuning, and the loop below applies.

Never tune your way around an open criterion question. A misread criterion can't be fixed with more grades (Shankar §7.3.3).

## The loop

1. **Make a candidate copy.** Copy the evaluator with a distinct `template_config.name` (for example `<name>_candidate`), so its results go to their own column. Start from the current production template, unchanged. See [changing-evaluators.md](changing-evaluators.md) for the API's limits.
2. **Baseline.** Run a non-continuous task for the candidate on the gold sessions only. Use `--query-filter` with the session IDs and a data window covering them. Try a small `--max-spans` first. Then run `report --eval-column <candidate column> --json-out baseline.json`. Run the unchanged candidate once more and compare the two runs to get the **noise floor**. A gain smaller than that isn't a gain.
3. **Revise from dev only.** Train and dev come from the gold queue (SOP addendum A). Train records can be few-shot examples. Prefer 2–3 human-rated examples over rescaling scores (Mukherjee). Dev records are the disagreements you read. Test records stay out of the template and this prompt.
4. **Make general edits.** Each edit states a rule. Before re-running, check it:

   ```bash
   python3 SKILL_ROOT/scripts/align_report.py lint OLD.txt NEW.txt --records baseline.json
   ```

   `lint` flags added lines that name a record, session or trace, or copy wording from dev records. Rewrite those as general rules (SPEAR; Elganayni).
5. **Batch, and look at dev once per batch.** Combine several edits, then score dev once. `compare --ledger looks.json` counts the looks and warns past `--look-budget` (default 5, an Arize heuristic; Dwork).
6. **Reproduce check.** Summarize the change in 2–3 sentences. Give a fresh agent only the baseline template and that summary, never the dev records, and have it write its own version. Score it on dev. If it doesn't reproduce most of the gain, the gain came from fitting the records (Bertran, Roth, Wu).
7. **Compare on the same records:**

   ```bash
   python3 SKILL_ROOT/scripts/align_report.py compare baseline.json after.json --split dev --ledger looks.json
   ```

   It prints both rates and π with intervals, recall per label, the records that flipped each way, and the shift in the judge's label mix.
8. **Optimizers.** If one drafts revisions instead, give it train and dev only. Have it maximize π or macro-F1, never accuracy, which collapses to the majority label (SPEAR). Keep a rollback to the best dev version.

## Freeze and test (SOP steps 3 and 9)

1. **Freeze** the candidate's template.
2. **Label a later batch** after freezing. Queue intake into the calibration queue does this. Then run `report --test-from FREEZE_TIME`, and score it **once** per frozen version, not on a calendar. A tuning judge can hold on its own batch and collapse on a later one (Kochelka). Use the same-batch test split only when no later batch can be labeled, and call the result directional.
3. **Score one other judge model** on the same test records, with the frozen template, as a second candidate. A judge can agree well overall and still carry a model-specific bias (Kochelka).
4. **Revise only as many judges at a time as the labeling budget can test,** usually one or two a week (SOP addendum B, an Arize heuristic).

## Ship gate (SOP step 9.4)

```bash
python3 SKILL_ROOT/scripts/align_report.py compare baseline.json final.json --gate \
  --fail-label FAILING_LABEL --second-judge second.json --ledger looks.json \
  [--candidates N --fresh fresh.json]
```

It passes only when all of these hold:

| Check | Basis |
|---|---|
| Test π after ≥ before | SOP step 9.4 |
| Dev → test π gap ≤ 0.10 | Arize heuristic; observed gaps were 0.25–0.44 κ (SPEAR) and 0.205 κ_w (Kochelka) |
| Test recall on each failing label didn't drop | SOP step 9.4 |
| A second judge model was scored on test | Kochelka; SOP step 5 |
| With `--candidates` > 1, the winner was re-scored on fresh sessions (`--fresh`) | SIREN: the best of several on the same data looks better than it is |

## Promotion

Promoting the candidate to production is a separate decision. Present its results, the gate and the exact diff, and create a new production version only on the user's explicit approval. Record it in the changelog as a **criterion change** or a **judge change** ([changing-evaluators.md](changing-evaluators.md#changelog)).

## When to stop

Stop when any of these is true:

- the test result clears the target on a measured judge
- agreement plateaus between batches
- the judge reaches the human ceiling
- the remaining disagreements are ones annotators also dispute
- dev looks pass the budget
- you've done 3–4 batches

Template edits rarely give more after that.

## Revision meta-prompt

Use this to draft a revision of the **candidate** template from dev-split disagreements only. Feed it gold records from a fresh run of the current version, with adjudicated labels. Never feed it not-applicable, unscorable, off-rubric or disputed records as if they were grading errors.

````
You are calibrating an LLM-as-judge evaluator to match human judgment. Given the
current template and gold records where it disagrees with adjudicated human labels,
produce a revised template that matches the human labeling pattern.

CURRENT EVALUATOR TEMPLATE
==========================
{CURRENT_TEMPLATE}
==========================

CLASSIFICATION CHOICES: {CHOICES}
DATA GRANULARITY: {SPAN|TRACE|SESSION}
HUMAN RUBRIC (label definitions given to annotators):
{RUBRIC_AND_QUEUE_INSTRUCTIONS}

BASELINE ON THE DEV SPLIT: {AGREE}/{TOTAL}; recall per human label: {PER_CLASS}

DISAGREEMENTS (dev-split gold records only)
=================================
For each: record/session ID, the evidence excerpt that decides it, the human label,
the evaluator label, and the evaluator's explanation.
{DISAGREEMENT_RECORDS}
=================================

ANALYSIS
1. Group the disagreements and name the PATTERN. Common patterns:
   - Applicability: the evaluator grades sessions the rubric treats as out of scope, or the reverse
   - Final-state vs intermediate: the evaluator credits or penalizes a step the user later revised
   - Absence vs wrongness: the evaluator conflates "no artifact produced" with "wrong artifact"
   - Too strict / too lenient on partial or paraphrased results
   - Evidence source: the evaluator trusts the assistant's claims over the tool calls or results
2. For each pattern, quote the template instruction that causes it (or note its absence).
3. Check that fixing one pattern would not flip the records the evaluator currently gets right.

RULES FOR THE REVISION
- Keep every {variable} placeholder exactly as in the original.
- Keep the classification choice labels exactly (spelling, casing), and the final
  response instruction.
- State general rules. Do not copy, paraphrase, or name specific records.
- Do not raise or lower how often the evaluator gives a label overall unless the
  patterns call for it; general rules can shift the pass rate on records you did not see.
- Change only what the identified patterns require. Leave the rest verbatim.

OUTPUT
1. The full revised template as raw text.
2. A diff-style list: each changed passage, before -> after, and which pattern it fixes.
3. Which records each change should flip, and any records it could break.
````

Fill the placeholders from `ax evaluators get` (template and choices), the queue (rubric and instructions), and the baseline report. For each disagreement, include the session excerpt that decides it, not the whole transcript.

Then review the output:

- Every placeholder and label must be preserved.
- No record may be named. Run `lint` on the output.
