# Presenting the report

Use this structure when presenting to the user at the stop point. Keep it short; the full report is the script's output.

## 1. Judge and status

- **Judge version:** the evaluator version, prompt hash, model, rubric version (from the commit message) and admission filter.
- **Status: provisional or measured.** For each blocker, give one plain sentence: what it is, its value and its source. For example, "10 of 29 calibration sessions were scored before they ended (SOP rule 3); re-score them with the current version."
- **What the status allows,** in one line. For a discovery round, say it normally ends in a criterion decision and template edits, not a measured number.

## 2. Human labels

- The label distribution and exclusions, kept apart from what the judge says.
- How many annotators. With one annotator, say "single annotator; no human ceiling measured."

## 3. Numbers

- **Test batch first:** agreement, π and recall per label, failing labels first, each with its interval, on the batch labeled after freezing. Without one, say there's no test batch and that the numbers are dev.
- **All scored gold:** recall per label, balanced accuracy, leniency, precision, π next to percent agreement.
- **If skewed:** AC1 and PABAK next to π.
- **Calibration queue:** corrected production rates and which interval to use, or that they weren't computed (fewer than about 100 random labels).
- **Gold queue:** the weighted secondary estimate, labeled as secondary.
- **Warnings** that fired, each with its basis, in one list.

## 4. Fit and disagreements

- **The label-definition diff:** each flagged label, with the queue's and the template's wording quoted. If it's a criterion question, say so and frame the decision for the user.
- **Applicability vs grade,** and the unit (session records).
- **Each disagreement:** record ID, session ID, both labels, and your reading of the evidence (human right, judge right, or ambiguous). Group them into patterns.

## 5. Proposal

Give exactly one of these:

- **A criterion decision for the user.** State the question and the options, with your recommendation. Draft both the template wording and the matching queue instructions. No template edit until it's decided; this alignment then ends, and the decided rule is measured in a later, separate run the user starts. Note that re-grading the old sessions under it would be a good next step.
- **A queue or label fix.** For example: re-score stale sessions, top up a label, or adjudicate. Queue changes such as top-ups go to **arize-align-queue-builder**.
- **One batch of template edits.** Quote the exact current wording, the exact replacement, and the records that justify each edit. Only when no criterion question is open.

## 6. Uncertain

What the intervals don't settle, and what's still unverified.

End by asking the user to approve, edit or reject the proposal.
