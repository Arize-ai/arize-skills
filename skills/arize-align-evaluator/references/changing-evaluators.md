# Changing an evaluator safely

Phase 6 creates candidate copies and, after approval, new versions of production evaluators. A new version is append-only: the previous one stays in the history. But the API does not carry every setting over, so read this before writing any version.

## Build each version from the current one, then read it back

Start from the current version's full `template_config` and change only what was approved. Pass every field explicitly: template name, template, classification choices, direction, granularity, include explanations, function calling, structured output, model and integration, and the model parameters. Then read the new version back with `ax evaluators get` and compare every field with the old one. Report any difference to the user.

Model parameters such as `temperature` can sit at the top level of `invocation_parameters`, outside `additional_properties`. Copying only `additional_properties` drops them.

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

## Provider copies

Projects often run a second copy of an evaluator on another model provider (for example `*_anthropic`), with the same template, to compare providers. Search for copies with `ax evaluators list --name KEYWORD` and compare templates. If the copies share a template, change them together. Otherwise the comparison measures the wording difference, not the provider.

## Changing production directly

When the user approves changing production without a candidate, state the costs first:
- There is no before-and-after measurement on the gold set.
- Continuous tasks score new data with the new version, while existing scores stay, so the column mixes versions. Stored results carry no version ID.
