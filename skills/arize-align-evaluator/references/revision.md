# Revising a judge without overfitting

Every step here comes after the user has approved a named change. Source names refer to [sources.md](sources.md).

## Two kinds of change (SOP step 1)

- **Criterion change.** What "good" means changes. Bump the rubric version and start a new judge version. Measuring it needs labels collected under the new rule, in a later, separate run the user starts; the old labels follow the old rubric (Kochelka; Divekar). Suggest re-grading the old sessions under the new rule as a good next step (Shankar §8.1), but don't require it; re-graded labels are dev only. Scores before and after aren't comparable.
- **Judge change.** The prompt, model or admission filter changes, and the criterion doesn't. This is tuning, and the loop below applies.

Never tune your way around an open criterion question. A misread criterion can't be fixed with more grades (Shankar §7.3.3).

## The loop: edit in place

Arize keeps every evaluator version, so an approved change is written as a new version of the evaluator itself. No copy is made, and the template can be rolled back.

1. **Save the baseline.** Save the current version's JSON (`ax evaluators get … -o json`) for rollback, and run `report … --json-out baseline.json` on the stored results. Leave out stale results, as the report does.
2. **Write the new version** from the current version's full config, changing only what was approved. Read it back and compare every field ([changing-evaluators.md](changing-evaluators.md)). Its `created_at` is the **switch time**; record it in the changelog.
3. **Re-score the gold sessions.** Run a one-off, non-continuous task for the evaluator on those sessions only. Use `--query-filter` with the session IDs and a data window covering them, and try a small `--max-spans` first. Then run `report --rescored-at RUN_START --json-out after.json`. Run the same task once more and compare the two runs to get the **noise floor**. A gain smaller than that isn't a gain.
4. **Treat what you read as dev.** Every session you read while writing the rule goes in a `--read-sessions` file, so it never counts as test, whatever its hash split. Those sessions can show that the edit does what it says. They can't show the judge is aligned, because the rule was written to fit them (SOP rule 1; Dwork).
5. **Revise from dev only.** Train and dev come from the gold queue (SOP addendum A). Train records can be few-shot examples; prefer 2–3 human-rated examples over rescaling scores (Mukherjee). Test records stay out of the template and this prompt.
6. **Make general edits.** Each edit states a rule. Before writing the version, check it:

   ```bash
   python3 SKILL_ROOT/scripts/align_report.py lint OLD.txt NEW.txt --records baseline.json
   ```

   `lint` flags added lines that name a record, session or trace, or copy wording from dev records. Rewrite those as general rules (SPEAR; Elganayni).
7. **Batch, and look at dev once per batch.** Combine several edits into one version, then score dev once. `compare --ledger looks.json` counts the looks and warns past `--look-budget` (default 5, an Arize heuristic; Dwork).
8. **Reproduce check.** Summarize the change in 2–3 sentences. Give a fresh agent only the baseline template and that summary, never the dev records, and have it write its own version. Score it on dev. If it doesn't reproduce most of the gain, the gain came from fitting the records (Bertran, Roth, Wu).
9. **Compare on the same records:**

   ```bash
   python3 SKILL_ROOT/scripts/align_report.py compare baseline.json after.json --split dev --ledger looks.json
   ```

   It prints both rates and π with intervals, recall per label, the records that flipped each way, and the shift in the judge's label mix. After a criterion change this shows the rule took effect, not an improvement: scores before and after aren't comparable.
10. **Optimizers.** If one drafts revisions instead, give it train and dev only. Have it maximize π or macro-F1, never accuracy, which collapses to the majority label (SPEAR). Keep a rollback to the best dev version.

### What an in-place edit costs

Tell the user before writing the version:

- From the switch time, the production task scores live traffic with the new version.
- Stored results carry no version ID, so the output column mixes versions. The switch time is the only way to tell them apart.
- Rolling back restores the template, not the scores written since.

### When to use a temporary copy instead

Make a copy with its own `template_config.name` only when the user wants old and new scored side by side on the same records before live traffic changes. Delete it after the ship gate, so it doesn't clutter the space.

## Freeze and test (SOP steps 3 and 9)

1. **Freeze** the template: no more edits to this version.
2. **Label a later batch** after the switch. Queue intake into the calibration queue does this. Then run `report --test-from FREEZE_TIME`, and score it **once** per frozen version, not on a calendar. A tuning judge can hold on its own batch and collapse on a later one (Kochelka). Use the same-batch test split only when no later batch can be labeled, call the result directional, and still leave out every session in `--read-sessions`.
3. **Score one other judge model** on the same test records, with the frozen template. Use a temporary evaluator copy with the other model, and delete it after scoring. A judge can agree well overall and still carry a model-specific bias (Kochelka).
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

## If the gate fails

Roll back to the saved version, or write a fixed one, and say so in the changelog with the time. The scores written while the failed version ran stay in the column; note their time range so reports can leave them out.

Record every version in the changelog as a **criterion change** or a **judge change**, with its switch time ([changing-evaluators.md](changing-evaluators.md#changelog)).

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

Use this to draft a revision of the template from dev-split disagreements only. Feed it gold records from a fresh run of the current version, with adjudicated labels. Never feed it not-applicable, unscorable, off-rubric or disputed records as if they were grading errors.

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
