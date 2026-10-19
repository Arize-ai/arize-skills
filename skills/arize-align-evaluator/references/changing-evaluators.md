# Changing an evaluator safely

Phase 5 writes approved changes as new versions of the evaluator itself. A new version is append-only: the previous one stays in the history, so the template can be rolled back. But the API does not carry every setting over, so read this before writing any version.

## Build each version from the current one, then read it back

Start from the current version's full `template_config` and change only what was approved. Pass every field explicitly: template name, template, classification choices, direction, granularity, include explanations, function calling, structured output, model and integration, and the model parameters. Then read the new version back with `ax evaluators get` and compare every field with the old one. Report any difference to the user.

Model parameters such as `temperature` sit at the top level of `invocation_parameters`, outside `additional_properties`, so copy both. Even then the API may drop some (below); the read-back shows which.

## What the CLI and API cannot set

| Setting | Limitation | What to do |
|---|---|---|
| `use_structured_output` | `ax evaluators create-evaluator-version template` has no flag for it. | Create the version with the Python SDK (`client.evaluators.create_template_version` with a `TemplateConfigInput`), which accepts it and defaults it to true. |
| `temperature` | Dropped when a version is created through the API; the new version stores empty model parameters. | If it matters, set it in the Arize UI after creating the version, and tell the user it changed. |
| `{turn_data}` templates | The API rejects a new version with `Turn data mode requires a Turn Definition`. The turn definition is set in the UI and the API has no field for it. | Edit the template in the UI, or migrate the evaluator to `{conversation}` (below). |

## Turn-data templates

An evaluator that reads `{turn_data}` gets per-turn data from its task's `query_mappings`, not the whole session. To move it to the full session:

1. Create a new version whose template replaces `{turn_data}` with `{conversation}`, with the approved changes and every other setting copied.
2. Update each task that runs it to drop the `query_mappings`: `ax tasks update TASK --evaluators '[{"evaluator_id": "ID"}]'`. Leave its filters, sampling rate and continuous setting unchanged, and read the task back to confirm.
3. Save the old evaluator and task JSON first, so the change can be rolled back.

This changes what the evaluator sees, so it needs its own approval, separate from any rubric change.

## Changelog

Keep a changelog per evaluator, one line per version, with its switch time (the version's `created_at`) and the judge version the report prints (rubric version, prompt hash, model, admission filter). Mark each entry as one of two kinds:
- **Criterion change:** what "pass" means changed. Bump the rubric version, and measure the new version on a new queue pair; older gold labels stay as they are. A re-grade of those sessions under the new rule is a good optional next step, for dev only. Scores before and after aren't comparable.
- **Judge change:** the prompt, model or filter changed, but the criterion didn't. This is tuning, and the held-out and ship-gate rules apply.

Either kind changes the judge, so re-measure, and re-collect random-stream labels before reporting corrected production rates.

## Provider copies

Projects often run a second copy of an evaluator on another model provider (for example `*_anthropic`), with the same template, to compare providers. Search for copies with `ax evaluators list --name KEYWORD` and compare templates. If the copies share a template, change them together. Otherwise the comparison measures the wording difference, not the provider.

## Editing in place: what to record

In-place editing is the default (SKILL.md Phase 5). Before writing the version, tell the user:

- **Live traffic switches immediately.** The production task scores new data with the new version from the switch time (the version's `created_at`).
- **The output column mixes versions.** Stored results carry no version ID, so record the switch time in the changelog; it's the only way to tell the versions' results apart.
- **Rollback restores the template, not the scores** written while the new version ran.
- **Re-score the gold sessions** with a one-off task after the switch, and pass its start time to `report --rescored-at`. Otherwise the report treats every earlier session's result as possibly an older version's.
