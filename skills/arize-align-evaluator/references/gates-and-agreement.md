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
| Gold records | ≥ 10 | Below 10, one record moves accuracy by more than 10 points. Even at 10, one record is 10 points, so treat small differences between versions as noise. |
| Class coverage | ≥ 2 classes with ≥ 3 gold records each | With one class, accuracy cannot show whether the evaluator discriminates. A queue of 10 `usable` labels says nothing about how it handles `flawed`. |
| Excluded rate | ≤ 30% of labeled records | A high not-applicable or unscorable share means the queue's admission filter is mismatched to the evaluator. The remaining sample may not be representative. |
| Join | ≥ 90% joined, no duplicate units | Missing or duplicated sessions make the numbers describe a different population |
| Stored output coverage | ≥ 90% of gold | Descriptive agreement on 2 of 10 records is not a 10-record result |
| Annotator agreement | Cohen's κ ≥ 0.6 for every annotator pair, when records have 2+ votes. A single annotator passes. | If humans don't agree with each other, the gold label is a coin flip and the evaluator cannot be held to it. With one annotator, this can't be checked; the report says so. |
| Disputes | 0 unresolved | Disputed records have no gold label |

The thresholds are defaults. If the user wants different ones, state the new threshold in the report and explain what it allows them to claim. Do not loosen a gate silently.

**Verdicts:** USABLE means every gate passes. EXPLORATORY means at least 5 gold records in 2 or more classes. NOT USABLE is anything else. A single-annotator queue can be USABLE, but the report must state that every gold label rests on one person.

## Agreement metrics

| Metric | Meaning |
|---|---|
| Exact agreement | Share of gold records where the evaluator label equals the human label. Quote it with its denominator, such as "8/10". |
| Confusion matrix | Counts of (human, evaluator) pairs. Shows which classes get confused. |
| Per-class precision | Of the records the evaluator gave label X, the share humans also labeled X. Low precision means the evaluator over-applies X. |
| Per-class recall | Of the records humans labeled X, the share the evaluator labeled X. Low recall means the evaluator misses X. |
| Cohen's κ (human vs human) | Agreement corrected for chance: `(p_o − p_e) / (1 − p_e)`. Here `p_o` is observed agreement, and `p_e` is the sum over labels of the product of each annotator's share of that label. Read roughly: below 0.4 poor, 0.4–0.6 moderate, 0.6–0.8 substantial, above 0.8 near-perfect. |

With n ≤ 30, give counts next to every percentage. Do not quote a single number as "the" alignment score.

## Getting second labels

A second annotator is optional. To measure agreement when the queue has one annotator, or a second annotator is still `PENDING`:
- Ask the second annotator to finish, or assign one with `ax annotation-queues assign-record` (through **arize-annotation**; passing the emails replaces the existing assignees).
- Labeling a representative subset of at least 10 records, spread across the classes, is enough to measure κ.
- The second annotator must label blind, without seeing the first annotator's votes or the evaluator's output.

## Adjudication

For each disputed record:
1. Show both votes, the record and session IDs, and the evidence each label points to.
2. Decide using one of these policies, and state which one applies: a named **adjudicator** decides, the **annotators discuss** and agree, or the record is **excluded** from gold. Majority vote is acceptable only with 3 or more annotators.
3. Write the result to an adjudications file `{ "RECORD_ID": "label", ... }` and pass it with `--adjudications`. Do not overwrite the original votes in the queue. The report keeps them.
4. If many disputes involve the same pair of labels, the rubric is ambiguous. Fix the label definitions and relabel before aligning.

## Target thresholds

Apply these only to a USABLE gold set re-run on the current version.

| Evaluator type | Reasonable exact-agreement target |
|---|---|
| Binary, crisp (correct/incorrect) | 85–90% |
| Binary, fuzzy (hallucinated/factual) | 80–85% |
| Multi-class (3+ labels) | 70–80%; also check recall on each minority class |
| Subjective (tone, helpfulness) | 70–75%; humans often agree only 75–80% |

An evaluator cannot be held to more agreement with the humans than the humans have with each other. If human-human agreement is 78%, that is roughly the ceiling for evaluator-human agreement.

## Sample size and overfitting

- Prefer 30–50 gold records with edge cases over 100 easy ones. Diversity matters more than volume.
- Keep a held-out slice (about 20–30% of the gold records) that you don't look at while revising. Report agreement on it separately.
- A revised template that names specific records or quotes their content is overfitting. Revisions must state general rules.
