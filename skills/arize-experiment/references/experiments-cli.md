# `ax experiments` — Notes

Run `ax experiments <subcommand> --help` for the full, current flag list on `list`, `get`, `export`, `create`, `run`, `list-runs`, `delete`, and `annotate-runs`. See [SKILL.md](../SKILL.md) for usage examples, workflows, and data schemas. This file covers only what `--help` doesn't.

**Standalone experiments:** every subcommand accepts an experiment with no linked dataset. Omit `--dataset` for a standalone experiment; `--space` then becomes required instead (to resolve the experiment directly). When `--dataset` is given, `--space` is only needed to resolve the dataset by name.

**`export`:** failed runs (where the task raised an exception) are included in the export with `output: null` and an `error` field containing the exception message.
