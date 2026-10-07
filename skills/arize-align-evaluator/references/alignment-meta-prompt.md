# Alignment meta-prompt

Use this prompt only in Phase 6, after the user has approved changing the evaluator, to draft a revision of the **candidate** evaluator's template. The input must be gold records only, from a fresh run of the current version, with adjudicated labels. Never feed it not-applicable, unscorable, off-rubric or disputed records as if they were grading errors.

Keep a held-out slice of the gold records out of the disagreement list, so the revision can be checked against records it never saw.

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

BASELINE ON GOLD SET: {AGREE}/{TOTAL}; per-class precision/recall: {PER_CLASS}

DISAGREEMENTS (gold records only)
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
- Change only what the identified patterns require. Leave the rest verbatim.

OUTPUT
1. The full revised template as raw text.
2. A diff-style list: each changed passage, before -> after, and which pattern it fixes.
3. Which records each change should flip, and any records it could break.
````

## Using it

1. Fill the placeholders from `ax evaluators get` (template and choices), the queue (rubric and instructions), and the Phase 6 report (baseline and disagreements). For each disagreement, include the session excerpt that decides it, not the whole transcript.
2. Review the output. Every placeholder and label must be preserved, and no record may be named.
3. Show the user the diff. Apply it as a new version of the candidate evaluator only, re-run on the gold set, and report the before/after numbers for both the revised set and the held-out set.
