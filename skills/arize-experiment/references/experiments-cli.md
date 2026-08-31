# `ax experiments` — Flag Reference

Full flag tables for every `ax experiments` subcommand, verified against `ax experiments <subcommand> --help` on arize-ax-cli 0.32.0. See [SKILL.md](../SKILL.md) for usage examples, workflows, and data schemas.

**Standalone experiments:** every subcommand below accepts an experiment with no linked dataset. Omit `--dataset` for a standalone experiment; `--space` then becomes required instead (to resolve the experiment directly). When `--dataset` is given, `--space` is only needed to resolve the dataset by name.

## list

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dataset` | string | none | Filter by dataset name or ID |
| `--space, -s` | string | none | Space name or ID. Lists every experiment in the space when `--dataset` is omitted, including standalone ones; otherwise resolves `--dataset` by name |
| `--limit, -l` | int | 15 | Max results |
| `--cursor, -c` | string | none | Pagination cursor from previous response |
| `-o, --output` | string | table | Output format: table, json, csv, parquet, or file path |

## get

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID, to resolve `NAME_OR_ID` by name; omit for a standalone experiment |
| `--space, -s` | string | none | Space name or ID — resolves `--dataset` by name, or resolves the experiment itself when `--dataset` is omitted (required for standalone experiments) |
| `-o, --output` | string | table | Output format |

## export

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID, to resolve `NAME_OR_ID` by name; omit for a standalone experiment |
| `--space, -s` | string | none | Space name or ID — resolves `--dataset` by name, or resolves the experiment itself when `--dataset` is omitted (required for standalone experiments) |
| `--all` | bool | false | Use Arrow Flight for bulk export (streams all runs) |
| `--output-dir` | string | `.` | Output directory |
| `--stdout` | bool | false | Print JSON to stdout instead of file |

Failed runs (where the task raised an exception) are included in the export with `output: null` and an `error` field containing the exception message.

## create

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--name, -n` | string | yes | Experiment name |
| `--file, -f` | path | yes | Data file with runs: CSV, JSON, JSONL, or Parquet (use `-` for stdin) |
| `--dataset` | string | no | Dataset name or ID to attach the experiment to; omit to create a standalone experiment |
| `--space, -s` | string | no | Space name or ID — required when `--dataset` is omitted (standalone); with `--dataset` it only resolves the dataset by name |
| `-o, --output` | string | no | Output format |

## run

| Flag | Required | Description |
|------|----------|-------------|
| `--name, -n` | yes | Experiment name |
| `--dataset` | yes | Dataset name or ID |
| `--task` | yes | Path to Python file with a top-level `task(dataset_row)` function |
| `--space, -s` | no | Required if using dataset name instead of ID |
| `--concurrency, -c` | no | Concurrent task executions (default: 3) |
| `--dry-run` | no | Run against first 10 examples only, no upload |
| `-o, --output` | no | Output format |

## list-runs

| Flag | Required | Description |
|------|----------|-------------|
| `NAME_OR_ID` | yes | Experiment name or ID (positional) |
| `--dataset` | no | Dataset name or ID, to resolve `NAME_OR_ID` by name; omit for a standalone experiment |
| `--space, -s` | no | Resolves `--dataset` by name, or resolves the experiment itself when `--dataset` is omitted (required for standalone experiments) |
| `--limit, -l` | no | Max runs to return (default: 15) |
| `-o, --output` | no | Output format |

## delete

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID, to resolve `NAME_OR_ID` by name; omit for a standalone experiment |
| `--space, -s` | string | none | Resolves `--dataset` by name, or resolves the experiment itself when `--dataset` is omitted (required for standalone experiments) |
| `--force, -f` | bool | false | Skip confirmation prompt |

## annotate-runs

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `NAME_OR_ID` | string | yes | Experiment name or ID (positional) |
| `--file, -f` | path | yes | Annotation file: JSON, JSONL, CSV, or Parquet (use `-` for stdin) |
| `--dataset` | string | no | Dataset name or ID, to resolve `NAME_OR_ID` by name; omit for a standalone experiment |
| `--space, -s` | string | no | Resolves `--dataset` by name, or resolves the experiment itself when `--dataset` is omitted (required for standalone experiments) |
