# Quality gates, agreement metrics, and adjudication

## Record buckets

| Bucket | Rule | Used in human-vs-evaluator agreement? |
|---|---|---|
| `gold` | Resolved label (unanimous, single vote, or adjudicated) that is one of the evaluator's classification choices and is not a not-applicable label | Yes |
| `not_applicable` | Resolved label is in `--not-applicable` (default `not_applicable`) | No. Reported separately as applicability agreement. |
| `unscorable` | Resolved label is in `--unscorable` (default `cannot_judge`, `unclear`) | No |
| `off_rubric` | Resolved label is not one of the evaluator's choices | No. This is a rubric mismatch to discuss. |
| `disputed` | Annotators disagree and there is no adjudication | No, until adjudicated |
| `unlabeled` | No vote for the ground-truth config | No |

If the evaluator has its own `not_applicable` class, also check **applicability agreement**: among the records humans marked not applicable, how many did the evaluator also mark `not_applicable`? A substantive evaluator label on a human-not-applicable record usually points to the admission filter or the evaluator's applicability instruction, not its grading criteria.

## Gates

| Gate | Default | Why |
|---|---|---|
| Gold records | ≥ 10 | Below 10, one record moves accuracy by more than 10 points. Even at 10, the 95% interval on 9/10 is about 60–98%, so this is a floor for starting, not for a claim. |
| Class coverage | ≥ 2 classes with ≥ 3 gold records each | With one class, accuracy cannot show whether the evaluator discriminates. A queue of 10 `usable` labels says nothing about how it handles `flawed`. |
| Excluded rate | ≤ 30% of labeled records | A high not-applicable or unscorable share means the queue's admission filter is mismatched to the evaluator. The remaining sample may not be representative, and if the excluded records are the hard ones, agreement on the rest is inflated. |
| Join | ≥ 90% joined, no duplicate units | Missing or duplicated sessions make the numbers describe a different population |
| Stored output coverage | ≥ 90% of gold | Descriptive agreement on 2 of 10 records is not a 10-record result |
| Annotator agreement | Cohen's κ ≥ 0.6 for every annotator pair, when records have 2+ votes. When one label holds ≥ 80% of a pair's votes, Gwet's AC1 ≥ 0.6 also passes. A single annotator passes. | If humans don't agree with each other, the gold label is a coin flip and the evaluator cannot be held to it. With one dominant label, κ is low even at high raw agreement (the kappa paradox), so AC1 is used there. With one annotator, agreement can't be checked; the report says so. |
| Disputes | 0 unresolved | Disputed records have no gold label |

The thresholds are defaults. If the user wants different ones, state the new threshold in the report and explain what it allows them to claim. Do not loosen a gate silently.

## Verdicts

| Verdict | Rule | What you may claim |
|---|---|---|
| **VALIDATED** | Every gate passes, ≥ 50 gold records, and ≥ 2 classes with ≥ 30 gold records each | Agreement on those classes is evidence of alignment, once re-run on the current version. Classes with fewer than 30 gold records are listed as not validated. |
| **DIRECTIONAL** | Every gate passes, below the VALIDATED sizes | Enough to start aligning and to propose changes. Quote every rate with its interval and do not claim a target is met. |
| **EXPLORATORY** | At least 5 gold records in 2 or more classes, but some gate fails | Patterns worth investigating. No rate is evidence of alignment. |
| **NOT USABLE** | Anything else | Fix the queue first. |

A single-annotator queue can reach any verdict, but the report must say that every gold label rests on one person.

## Agreement metrics

The report quotes every rate as a count, a percentage and a 95% Wilson interval, such as "9/10 (90%, 95% CI 60–98%)".

| Metric | Meaning |
|---|---|
| Recall per human label | Of the records humans labeled X, the share the evaluator labeled X. For a binary evaluator these are the TPR and TNR. Low recall means the evaluator misses X. Lead with these: on imbalanced data a judge that always gives the common label scores high exact agreement and catches nothing. |
| Balanced accuracy | The mean of the per-label recalls |
| Precision per evaluator label | Of the records the evaluator gave label X, the share humans also labeled X. Low precision means the evaluator over-applies X. |
| Exact agreement | Share of gold records where the evaluator label equals the human label. The queue may oversample rare labels, so this is not a production rate; see the weighted estimate. |
| Confusion matrix | Counts of (human, evaluator) pairs. Shows which classes get confused. |
| Production-weighted estimate | With `--plan plan.json` from **arize-align-queue-builder**, agreement and per-label recall weighted by each queue stratum's production count. This undoes the oversampling of rare labels and provider disagreements. |
| Cohen's κ (human vs human) | Agreement corrected for chance: `(p_o − p_e) / (1 − p_e)`. Here `p_o` is observed agreement, and `p_e` is the sum over labels of the product of each annotator's share of that label. Landis & Koch bands: below 0 poor, 0.00–0.20 slight, 0.21–0.40 fair, 0.41–0.60 moderate, 0.61–0.80 substantial, 0.81–1.00 almost perfect. |
| AC1 and PABAK (human vs human) | Agreement statistics that stay stable when one label dominates. The report prints both next to κ, with the most common label's share. |

Do not quote a single number as "the" alignment score.

## Getting second labels

A second annotator is optional; one domain expert as the source of truth is common practice. To measure agreement when the queue has one annotator, or a second annotator is still `PENDING`:
- Ask the second annotator to finish, or assign one with `ax annotation-queues assign-record` (through **arize-annotation**; passing the emails replaces the existing assignees).
- Aim for at least 20 shared records, spread across the classes. κ from fewer is a rough check, and the report says so.
- The second annotator must label blind, without seeing the first annotator's votes or the evaluator's output.

## Adjudication

For each disputed record:
1. Show both votes, the record and session IDs, and the evidence each label points to.
2. Decide using one of these policies, and state which one applies: a named **adjudicator** decides, the **annotators discuss** and agree, or the record is **excluded** from gold. Majority vote is acceptable only with 3 or more annotators.
3. Write the result to an adjudications file `{ "RECORD_ID": "label", ... }` and pass it with `--adjudications`. Do not overwrite the original votes in the queue. The report keeps them.
4. If many disputes involve the same pair of labels, the rubric is ambiguous. Fix the label definitions and relabel before aligning. Note the instructions version on the queue, so labels made under older definitions can be found later.

## Target thresholds

These are Arize heuristics, not published standards. Apply them only to a VALIDATED gold set re-run on the current version, and only when the interval, not just the point estimate, clears the target.

| Evaluator type | Reasonable exact-agreement target |
|---|---|
| Binary, crisp (correct/incorrect) | 85–90%, and possibly higher: humans can agree 98% or more on crisp grading |
| Binary, fuzzy (hallucinated/factual) | 80–85% |
| Multi-class (3+ labels) | 70–80%; also check recall on each minority class |
| Subjective (tone, helpfulness) | 70–75%; humans often agree only 75–80% |

Hold the evaluator to the human-human agreement measured on this queue, not to a fixed ceiling. A judge can match or slightly exceed agreement between humans, so measured human agreement, within its interval, is the reference.

## Held-out split and overfitting

- The report splits gold records by human label, stably by record ID: about 15% **train**, 42.5% **dev** and 42.5% **test**. `--json-out` records each record's split.
- **Train** records may appear in the template as few-shot examples. **Dev** records are the ones you read and iterate on. **Test** records stay out of the template and the meta-prompt, and are scored once, after the last revision.
- Size the test set by class, not by percentage: below 30 test records per class, a test result is directional.
- A revised template that names specific dev or test records, or quotes their content, is overfitting. Revisions must state general rules.
- Edge cases beat easy cases for building the prompt. They don't replace the sample size needed to validate it.
