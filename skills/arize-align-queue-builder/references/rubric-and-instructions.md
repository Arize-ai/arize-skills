# Label config and annotator instructions

## Label values

| Include | Why |
|---|---|
| Every evaluator classification choice, spelled exactly the same | Human and evaluator labels are compared by exact string. `metric_correct` ≠ `Metric correct`. |
| `not_applicable` (if the evaluator does not already have it) | Lets humans flag records outside the evaluator's scope instead of forcing a grade |
| `cannot_judge` | Lets humans flag records where the evidence is missing or truncated. Excluded from agreement, never mapped onto an evaluator label. |

An abstain option such as `cannot_judge` improves the accuracy of the labels people do give, and annotators who see a model's answer tend to agree with it, so the instructions keep labelers blind.

Leave out:
- **Labels the evaluator cannot output.** Every human use of one becomes an off-rubric record that can't be compared.
- **Near-duplicates of `cannot_judge`** such as `unclear`. Two "I can't tell" labels split the same records and add nothing.

Use a categorical config with optimization direction `NONE`, so the UI doesn't imply one label is better. If an earlier round's config has exactly these values, reuse it so labels stay comparable across rounds.

## Critique config

Attach a second, free-text config (`critique_config_name` in `plan.json`, for example `my_eval-critique`) to both queues. The critique is **optional**, because labeling time is the main cost of alignment. The instructions ask for one line in two cases, where it pays off most:
- **Close calls**, where two labels seemed to fit. These are the records most likely to end up in adjudication.
- **`cannot_judge`**, to say what evidence was missing.

A useful line names the decisive turn and what decided it, like the judge's own explanation (for example "T4 saved a widget grouped by model; the user asked for grouping by project"). That makes adjudication faster.

Critiques detailed enough to reuse as few-shot examples (Husain's "critique shadowing") are written later, during adjudication. The reviewer is already rereading those records, and only the ones picked as dev or few-shot examples need them. Don't require a critique on every label unless labeling time isn't a constraint.

```bash
ax annotation-configs create freeform --name "CRITIQUE_CONFIG_NAME" --space SPACE -o json
```

## Keeping labelers blind

Annotators who see a model's label or score drift toward it. In one controlled study, pre-filled suggestions roughly doubled a judge's measured F1 against the resulting "gold" labels. Agreement between annotators also rises when everyone sees the same suggestion, which makes it meaningless.

The instructions line is not enough, because the Arize record view can show eval results. Each queue has an **Annotator Columns** allowlist that sets which columns annotators see. ax can't set it, so after creating each queue:
1. Open the queue in the Arize UI, edit it, and under Annotator Columns leave out every `eval.*`, `trace_eval.*` and `session_eval.*` column.
2. Open one record as an annotator and confirm no evaluator label, score or explanation is visible.
3. If the record view still shows them, say so in the report, so its results aren't presented as blind.

In a test on 2026-10-16, a `SESSION` record's session view showed no evaluation results. Still check one record as in step 2.

Never pre-fill or highlight a label. Showing the evaluator's reasoning after a human submits is untested as a way to improve labels; if it's used, keep the first label.

## Instructions template

Annotators see these instructions on every record of both queues, and the limit is 5000 characters. Fill in each `<…>` from the evaluator template, using its definitions rather than new wording, so humans and the judge apply the same rule.

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
  what is missing in the critique.

Critique (optional): if two labels seemed to fit, or you chose cannot_judge, add one line
in the critique field naming the decisive turn and why, e.g. "T4 saved the widget grouped
by model; the user asked for grouping by project". Otherwise the label alone is enough.
You may go back and change an earlier label if your reading of a definition changes.

Work in sittings of about 100 records at most. Take a break before continuing.

Evidence: <what counts as evidence, e.g. tool calls and their results over the assistant's
claims; artifacts the user accepted>.

If two labels seem to fit, <tie-break rule from the template>.
```

## Checks before proposing

- Every evaluator label has a definition in the instructions, and the definitions agree with the template.
- The instructions name the unit, and for session evaluators, say to label the session.
- The blindness line is present.
- The length is under 5000 characters: `wc -c instructions.txt`.
- The instructions carry a version line (for example `Instructions v2, 2026-10-06`). Pass the same text to the planner as `--instructions-version`, so each record in `plan.json` carries it. Change it whenever a definition changes. Labels made under the older version, on the labels whose definitions changed, then need re-review.
- The optional-critique line and the sitting limit are present.
- Spot-check 2–3 planned records with **arize-trace**: open the session and confirm an annotator could reach a label from what is visible. If not, the unit or the instructions need adjusting before creation.
