# ax prompts — CLI gotchas

Run `ax prompts <subcommand> --help` for the full, current flag list and required/optional status — it now also prints the messages JSON shape and examples. This file holds only what `--help` doesn't cover.

## Provider enum has no GEMINI

`--provider` on `create` and `create-version` accepts `OPEN_AI`, `AZURE_OPEN_AI`, `AWS_BEDROCK`, `VERTEX_AI`, `ANTHROPIC`, `CUSTOM` — unlike `ax ai-integrations`, there is no `GEMINI` option here.

## No `--tags` flag

Prompt Hub's new-prompt save form has comma-separated **Tags (optional)**, but `ax prompts create` has no `--tags` (or similar) flag. Add tags in the UI after create, or tell the user to add them there.

## `--model` is always required in practice

`ax prompts create` and `create-version` accept omitting `--model`, but always pass an explicit `--model` when proposing these commands — see the main **SKILL.md** for this skill.

## Version-label semantics

`ax prompts set-version-labels` **replaces all** existing labels on that version with the ones passed — it is not additive. `ax prompts remove-version-label` removes one label without touching the version itself.
