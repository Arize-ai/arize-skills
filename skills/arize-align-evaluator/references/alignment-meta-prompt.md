# Alignment meta-prompt

Use this prompt only in Phase 6, after the user has approved changing the evaluator, to draft a revision of the **candidate** evaluator's template. The input must be gold records only, from a fresh run of the current version, with adjudicated labels. Never feed it not-applicable, unscorable, off-rubric or disputed records as if they were grading errors.

Use only **dev** records from the report's held-out split (`split` in `--json-out`) as disagreements. **Train** records may appear in the template as few-shot examples. **Test** records stay out of this prompt and the template, and are scored once, after the last revision.

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

## Using it

1. Fill the placeholders from `ax evaluators get` (template and choices), the queue (rubric and instructions), and the Phase 6 report (baseline and disagreements). For each disagreement, include the session excerpt that decides it, not the whole transcript.
2. Review the output. Every placeholder and label must be preserved, and no record may be named. Run `align_report.py lint OLD.txt NEW.txt --records BEFORE.json` and rewrite any flagged line as a general rule.
3. **Batch the edits.** Collect the changes for several patterns into one revision, then score dev once. Don't re-score after every tweak.
4. **Reproduce check.** Summarize the revision in 2–3 sentences. Give a fresh agent only the baseline template and that summary, never the dev records, and have it write its own revision. Score both on dev. If the fresh agent's version doesn't reproduce most of the gain, the gain came from fitting the records.
5. Show the user the diff. Apply it as a new version of the candidate evaluator only, re-run on the gold set, and compare with `align_report.py compare BEFORE.json AFTER.json --split dev --ledger LOOKS.json`. It prints both rates and Scott's π with intervals, recall per label, the records that flipped each way, the shift in the label mix and the number of dev looks.
6. Treat a gain smaller than run-to-run noise as no gain: re-run the unchanged candidate once and compare it with itself to see the noise floor.
7. After the last revision, freeze the template and score test once, ideally on a batch labeled after freezing (`report --test-from`). Use `compare --gate` with a second judge model's report before proposing promotion.

If an optimizer drafts revisions instead of this prompt, give it train and dev only. Have it maximize π or macro-F1, not accuracy, which can collapse to the majority label. Keep a rollback to the best dev version.
