# Reviewing human-vs-evaluator disagreements

The report's discrepancy table lists records where the human label and the stored evaluator label differ. Each one needs a reading of the actual session before it counts as evidence about the evaluator. Most disagreements fall into one of four groups, and only the first is a reason to change the template.

| Finding | What it means | Next step |
|---|---|---|
| The evaluator misapplied or lacks a rule, in 2 or more records | A template problem | Propose the change (SKILL.md Phase 4) |
| The session supports the evaluator | A labeling problem | Adjudicate the human label (below) |
| The stored result graded part of the session, or an older version | A stale result | Re-run the current version before judging |
| The rubric genuinely doesn't settle it | An ambiguous rule | Ask the user to decide the rule, then relabel |

## Reading the sessions

Export the whole session, not just the record's span: `ax spans export PROJECT --space SPACE --filter "attributes.session.id = 'SID'" --start-time … --end-time … -l 500 --stdout`. Use a window from shortly before the record's `start_time` to a few days after. Run exports one at a time, because parallel exports hit rate limits.

For each record, decide **human right**, **evaluator right** or **ambiguous**, and quote the decisive evidence in a sentence or two: the turn, the tool call or the block. If the evaluator is wrong, name the template rule it misapplied, quoting its wording. If the explanation reports the last turn it saw (for example `LAST_TURN_CHECK: Turn 4`) and the session has more, say the result is stale. A "Turn N" elsewhere in the explanation is usually only the decisive turn.

With many queues (dozens of discrepancies), group the records by evaluator and give each group to a read-only subagent. Pass it the template, the queue instructions, the record and session IDs, and the stored explanations. Ask for a table of record, session, human label, evaluator label, verdict and evidence, plus any pattern seen in 2 or more records. Tell it not to change anything in Arize.

## Patterns that point at the labels, not the evaluator

- **Labels without definitions.** If the queue instructions only say "apply the labels", the labeler never saw the evaluator's definitions. Expect labels that contradict the template, for example `no_answer` for a session where a tool ran successfully. The report's fit section flags instructions that never mention the labels.
- **Span records for a session evaluator** ([background](queue-records.md#unit-mismatch-span-records-session-evaluators)). If the human label matches the record's turn and the evaluator's matches the session's final state, the labeler graded the span.
- **A single annotator.** Nothing catches slips, such as a queue labeled `no_queue_produced` when the session shows it was created.

## Adjudicating

Adjudication follows [gates-and-agreement.md](gates-and-agreement.md#adjudication). For human-vs-evaluator disagreements:

1. Prepare a worksheet with one row per disagreement: record ID, session ID, human label, evaluator label, your verdict, a suggested resolution, the evidence, and a blank decision column. Group the rows by evaluator, and list the rubric questions that the ambiguous rows depend on.
2. Prepare a proposed adjudications file (`{"RECORD_ID": "label"}`) covering only the evaluator-favored records, marked as proposed.
3. The named adjudicator, usually the person who labeled, decides each row. Never write the final labels yourself, and never present the evaluator's label as the human's.
4. Note the bias: the adjudicator has now seen the evaluator's verdict. The worksheet's evidence column is what the decision should rest on.
5. Re-run `report --adjudications FILE`. The report keeps the original votes. If the verdict stays NOT USABLE or EXPLORATORY because a label has too few examples, adjudication cannot fix it; build a new queue with **arize-align-queue-builder**.
