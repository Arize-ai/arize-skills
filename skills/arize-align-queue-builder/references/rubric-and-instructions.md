# Label config and annotator instructions

## Label values

| Include | Why |
|---|---|
| Every evaluator classification choice, spelled exactly the same | Human and evaluator labels are compared by exact string. `metric_correct` ≠ `Metric correct`. |
| `not_applicable` (if the evaluator does not already have it) | Lets humans flag records outside the evaluator's scope instead of forcing a grade |
| `cannot_judge` | Lets humans flag records where the evidence is missing or truncated. Excluded from agreement, never mapped onto an evaluator label. |

An abstain option such as `cannot_judge` improves the accuracy of the labels people do give, and annotators who see a model's answer tend to agree with it, so the instructions keep labelers blind. Sources are in [Where the defaults come from](research.md).

Leave out:
- **Labels the evaluator cannot output.** Every human use of one becomes an off-rubric record that can't be compared.
- **Near-duplicates of `cannot_judge`** such as `unclear`. Two "I can't tell" labels split the same records and add nothing.

Use a categorical config with optimization direction `NONE`, so the UI doesn't imply one label is better. If an earlier round's config has exactly these values, reuse it so labels stay comparable across rounds.

## Instructions template

Annotators see these instructions on every record, and the limit is 5000 characters. Fill in each `<…>` from the evaluator template, using its definitions rather than new wording, so humans and the judge apply the same rule.

```text
Goal: judge whether <one-sentence statement of what the evaluator decides>.

Unit: judge the WHOLE <session|trace|span>, from the first user message to the final state.
Put your label on the <session|trace|span>, not on an individual span. If the user changed
their request part way, judge against the final request.

Do not look at any automated evaluation results, scores, or explanations shown on the record.

Labels:
- <label_1>: <definition from the evaluator template, including what evidence counts>
- <label_2>: <definition>
- ...
- not_applicable: the <session> is not about <evaluator's topic>, for example <common
  out-of-scope case>.
- cannot_judge: the evidence needed to decide is missing or truncated. Use sparingly; say
  what is missing in a note if the tool allows it.

Evidence: <what counts as evidence, e.g. tool calls and their results over the assistant's
claims; artifacts the user accepted>.

If two labels seem to fit, <tie-break rule from the template>.
```

## Checks before proposing

- Every evaluator label has a definition in the instructions, and the definitions agree with the template.
- The instructions name the unit, and for session evaluators, say to label the session.
- The blindness line is present.
- The length is under 5000 characters: `wc -c instructions.txt`.
- The instructions carry a version line (for example `Instructions v2, 2026-10-06`). Change it whenever a definition changes, so labels made under older definitions can be found.
- Spot-check 2–3 planned records with **arize-trace**: open the session and confirm an annotator could reach a label from what is visible. If not, the unit or the instructions need adjusting before creation.
