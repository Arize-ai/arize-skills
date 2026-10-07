# Ground truth outside annotation queues

Both sources here keep **one label per record**, with no per-annotator votes, so annotator agreement cannot be measured from them. That is allowed, but the report must say every label rests on one annotator. The rest of the workflow is the same: phases 3–6 in the main skill, including the stop for approval before any evaluator change. `align_report.py` reads queue exports only, so for these sources, build the join yourself and produce the same report sections and gates by hand.

## Span annotations

Human labels applied to spans through the SDK or UI appear as `annotation.<name>.label` columns on exported spans. The evaluator's stored output is `<prefix>.<template_config.name>.label` on the same spans, or on the session or trace for higher-granularity evaluators.

```bash
ax spans export PROJECT --space SPACE --days 30 --stdout > spans.json
```

Use a filter if the project is large; see **arize-trace** for the export filters. Then join with structured JSON handling:

1. Keep spans where `annotation.<name>.label` is present.
2. For a session evaluator, group by `attributes.session.id`. If the spans in one session carry conflicting human labels, the session is **disputed**. Do not pick one.
3. Read the evaluator column for each unit. A session evaluator's results are keyed to the session, so check where they appear in the export before assuming a column name.
4. Bucket each unit (gold, not applicable, unscorable, off rubric, disputed, unlabeled) using the rules in [gates-and-agreement.md](gates-and-agreement.md#record-buckets), then apply the gates.

`annotation.<name>.updated_by` identifies only the **last** annotator, not every annotator.

## Dataset label column

Use this when a dataset holds a human label column (for example `expected_label`), and an experiment's runs have been scored by the evaluator.

```bash
ax datasets export DATASET --space SPACE --stdout > examples.json
ax experiments export EXPERIMENT --dataset DATASET --space SPACE --stdout > runs.json
```

If a REST export returns exactly 500 runs, re-run with `--all`. See **arize-experiment**.

Join rules:
- Join `run.example_id` to the example's **top-level `id`**.
- The human label is the dataset column the user names. Ask if it is not obvious, and never guess between two candidate columns.
- Evaluator task results are in `run.additional_properties["eval.<template_config.name>.label"]`, with `.explanation` alongside. `run.annotations` holds values written by `annotate-runs`, which may be the human labels if they were attached that way.
- Experiment tasks evaluate runs directly; data granularity does not apply.

To get a fresh baseline in Phase 6, create the candidate evaluator, then a dataset task targeting the experiment, and trigger it with `--experiment-ids`. See Workflow B in **arize-evaluator**. Column mappings use top-level run fields such as `output`, not span attribute paths.

## No ground truth yet

Do not label records yourself and present the result as human ground truth. Use **arize-align-queue-builder** to design a queue for this evaluator: a label config matching its choices, balanced records across its labels, and instructions. When labeling is complete, run the main workflow from Phase 1.
