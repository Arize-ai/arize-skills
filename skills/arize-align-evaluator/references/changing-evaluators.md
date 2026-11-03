# Changing an evaluator safely

Phase 5 writes approved changes as new versions of the evaluator itself. A new version is append-only: the previous one stays in the history, so the template can be rolled back. But the API does not carry every setting over, so read this before writing any version.

## Writing a version

Write template changes with [scripts/write_version.py](../scripts/write_version.py). It builds the version from the current version's full `template_config` and changes only the template:

```bash
python3 SKILL_ROOT/scripts/write_version.py --space SPACE --evaluator EVALUATOR \
  --template-file WORK_DIR/template_new.txt --out-dir WORK_DIR \
  --commit-message "Rubric v3, 2026-10-19 (criterion change): what changed"
```

- **Without `--execute`** it's a dry run: it checks the commit message and prints a unified diff of the template and the fields it will copy unchanged. Show the user that diff for approval.
- **With `--execute`** it saves the current evaluator JSON to `--out-dir` as `rollback_<version id>.json`, then creates the version with the arize SDK (`client.evaluators.create_template_version` with `TemplateConfigInput`), which keeps `use_structured_output`. It reads the evaluator back, compares every `template_config` field with the old version (and the template with the new text), and prints the **switch time**. A field the API dropped is reported and the script exits non-zero; tell the user and set it in the UI.
- **Credentials** come from the same client factory `ax` uses, so `--execute` must run with the Python that runs `ax`: `"$(head -1 "$(command -v ax)" | sed 's/^#!//')" write_version.py …`. Nothing reads credential files.
- **Changes beyond the template** (model, choices, granularity) aren't covered; make them in the Arize UI, then read the version back with `ax evaluators get` and compare every field yourself.

Model parameters such as `temperature` sit at the top level of `invocation_parameters`, outside `additional_properties`. The API may drop some (below); the read-back shows which.

## What the CLI and API cannot set

| Setting | Limitation | What to do |
|---|---|---|
| `use_structured_output` | `ax evaluators create-evaluator-version template` has no flag for it. | Use `write_version.py`, which creates the version through the SDK and keeps it. |
| `temperature` | Dropped when a version is created through the API; the new version stores empty model parameters. | If it matters, set it in the Arize UI after creating the version, and tell the user it changed. `write_version.py` warns when the current version sets one. |
| `{turn_data}` templates | The API rejects a new version with `Turn data mode requires a Turn Definition`. The turn definition is set in the UI and the API has no field for it. | Edit the template in the UI, or migrate the evaluator to `{conversation}` (below). |

## Turn-data templates

An evaluator that reads `{turn_data}` gets per-turn data from its task's `query_mappings`, not the whole session. To move it to the full session:

1. Create a new version whose template replaces `{turn_data}` with `{conversation}`, with the approved changes and every other setting copied.
2. Update each task that runs it to drop the `query_mappings`: `ax tasks update TASK --evaluators '[{"evaluator_id": "ID"}]'`. Leave its filters, sampling rate and continuous setting unchanged, and read the task back to confirm.
3. Save the old evaluator and task JSON first, so the change can be rolled back.

This changes what the evaluator sees, so it needs its own approval, separate from any rubric change.

## Changelog

The version's **commit message is the changelog**. Arize stores it with the version and its `created_at`, which is the switch time, so no separate file is kept. Write it as:

```
Rubric vN, YYYY-MM-DD (criterion change|judge change): what changed
```

`write_version.py` refuses any other format, and the report reads the rubric version and the kind of change from it (`ax evaluators list-versions EVALUATOR --space SPACE` lists the history). Each entry is one of two kinds:
- **Criterion change:** what "pass" means changed. Bump the rubric version, and measure the new version in a later, separate run with new labels; older gold labels stay as they are. A re-grade of those sessions under the new rule is a good optional next step, for dev only. Scores before and after aren't comparable.
- **Judge change:** the prompt, model or filter changed, but the criterion didn't. This is tuning, and the held-out and ship-gate rules apply.

Either kind changes the judge, so re-measure, and re-collect random-stream labels before reporting corrected production rates.

## Provider copies

Projects often run a second copy of an evaluator on another model provider (for example `*_anthropic`), with the same template, to compare providers. Search for copies with `ax evaluators list --name KEYWORD` and compare templates. If the copies share a template, change them together. Otherwise the comparison measures the wording difference, not the provider.

## Editing in place: what to record

In-place editing is the default (SKILL.md Phase 5). Before writing the version, tell the user:

- **Live traffic switches immediately.** The production task scores new data with the new version from the switch time (the version's `created_at`).
- **The output column mixes versions.** Stored results carry no version ID; the switch time, which `write_version.py` prints and Arize stores with the version, is the only way to tell the versions' results apart.
- **Rollback restores the template, not the scores** written while the new version ran.
- **Re-score the gold sessions** with a one-off task after the switch, and pass its start time to `report --rescored-at`. Otherwise the report treats every earlier session's result as possibly an older version's.
