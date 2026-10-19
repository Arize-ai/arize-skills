# Measuring a judge

What the report's status, warnings and numbers mean, and where each rule comes from. Source names refer to [sources.md](sources.md).

## Status: provisional or measured

There are no verdict tiers. A judge is **measured** only when every condition below holds. Otherwise it's **provisional**, and the report lists each failing condition as a blocker.

| Condition | Checked as | Source |
|---|---|---|
| Size | 30+ scored gold records per label in **each** of dev and test, for at least 2 labels | Husain & Shankar |
| No stale results | No gold record's stored result saw fewer turns than the session has (`LAST_TURN_CHECK`). If turns weren't counted, this is "not checked". | SOP rule 3 |
| Current version | Every gold record has a stored result, and none started before the current version was created | SOP rule 2 |
| One record per unit | Every record has a session ID, and none is duplicated | SOP addendum F |
| No open criterion question | The label-definition diff is empty, or the user has decided the question (`--criterion-decided`) | SOP step 1 and addendum G |

**What each status allows:**

- **Provisional:** report every number with its interval and don't claim a target. Fix criterion, scope and queue problems first, then make at most one batch of template fixes. Don't tune prompt by prompt: on small sets that overfits (Dwork; SPEAR).
- **Measured:** the revise loop and the ship gate apply. See [revision.md](revision.md).

Most judges stay provisional at discovery scale (about 30 random records). That's expected. The numbers are still worth reading, with their intervals.

## Warnings

Warnings never change the status. Each one prints its basis.

| Warning | Default | Basis |
|---|---|---|
| Fewer than 10 gold records | 10 | Arize heuristic. At 10 records, 90% agreement has a 95% interval of about 60–98%. |
| A label with fewer than 3 gold records | 3 | Arize heuristic |
| Excluded share (not applicable, unscorable, off-rubric) above 30% | 30% | Arize heuristic. Dropping hard cases inflates agreement (Zheng). A high share also suggests the admission filter is wider than the judge's scope. |
| Score or join coverage below 90% | 90% | Arize heuristic |
| Human–human κ below 0.6, or AC1 below 0.6 when one label holds ≥ 80% | 0.6 | Landis & Koch; McHugh; Gwet |
| A single annotator | — | No human ceiling was measured (SOP addendum E) |
| Open disputes | 0 | A disputed record has no gold label |
| Span records for a session judge | — | Each opens on one turn (SOP addendum F). Rebuild the queue with `SESSION` records. |

## The numbers

Every rate is shown with a count, a percentage and a 95% Wilson interval. π gets a seeded bootstrap interval.

1. **Test split first.** Agreement, Scott's π, and recall per label, with the failing labels first. These are the numbers to report for a frozen judge version. A test split from the same batch as dev is marked **directional**; the real test is a batch labeled after freezing (`--test-from`). See Kochelka and SPEAR in [sources.md](sources.md).
2. **All scored gold records:**
   - recall per human label (TPR and TNR for a binary judge) and balanced accuracy
   - precision per judge label
   - percent agreement next to π, never alone (Thakur)
   - the confusion matrix
3. **Leniency.** Of the records humans gave a failing label, the share the judge didn't fail. Name the failing labels with `--fail-label` (repeatable). Judges lean toward "correct" when unsure (Thakur §5.4).
4. **Skew.** When one human label holds ≥ 80% of the scored records, π is low even at high raw agreement, the same prevalence effect as κ. The report then adds Gwet's AC1, PABAK and balanced accuracy. Read the failing labels' recall first, and don't treat a low π on a skewed judge as a verdict on its own (SOP addendum C).
5. **Applicability and grade** as separate lines. A scope disagreement needs a scope rule, not a grading rule (SOP step 1).
6. **Human ceiling.** Hold one rater out at a time, and score that rater and the judge against the same reference made from the others (Mukherjee). Don't tune past the ceiling. With one annotator, the report says no ceiling was measured.

## Which queue measures

- **Calibration queue** (a random sample): its numbers are measurement estimates, and production rates come from it ([production-rates.md](production-rates.md)).
- **Gold queue** (targeted, a quota per stored label): it fills train and dev, and finds disagreements. Its production-weighted figures are a **secondary** estimate. They're valid only if each stratum was sampled uniformly with a known rate (Egami; Zrnic & Candès). The queue builder rotates across entry points inside a label without recording it, so treat them as approximate.

## Fit: the label-definition diff

The report puts each label's definition from the queue instructions next to the template's.

**It flags a label when:**

- the two texts are mostly different, or
- a tool or field name (for example `validate_filter`) appears in one side's definition and not the other's.

It also lists terms both documents use, so you can check they state the same rule.

**A flag is a candidate, not a finding.** Read both definitions:

- **If the human and the judge apply different rules,** it's a **criterion question**. The user decides it. Then bump the rubric version, re-review the affected labels, and pass `--criterion-decided`.
- **No template edit until it's decided.** A misread criterion can't be fixed with more grades (Shankar §7.3.3).

## Agreement between annotators

- **Aim for 20+ shared records per pair, spread across the labels.** κ from fewer is a rough check.
- **The second annotator labels blind:** no first annotator's votes and no judge output.
- **When one label holds ≥ 80% of a pair's votes,** κ understates agreement (the kappa paradox), so the check uses AC1.

## Adjudication

For each disputed record:

1. Show both votes, the IDs, and the evidence each label points to.
2. Use one policy and say which: a named adjudicator decides, the annotators agree, or the record is excluded. Majority vote needs 3 or more annotators.
3. Write `{ "RECORD_ID": "label" }` to a file and pass `--adjudications`. Never overwrite the original votes.
4. Many disputes on the same label pair mean the rubric is ambiguous. That's a criterion question (above).

For human-vs-judge disagreements, see [disagreement-review.md](disagreement-review.md).
