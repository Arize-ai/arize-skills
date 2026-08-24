# `ax experiments` — Flag Reference

Full flag tables for every `ax experiments` subcommand. See [SKILL.md](../SKILL.md) for usage examples, workflows, and data schemas.

## list

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dataset` | string | none | Filter by dataset |
| `--name, -n` | string | none | Substring filter on experiment name |
| `--limit, -l` | int | 15 | Max results (1-100) |
| `--cursor` | string | none | Pagination cursor from previous response |
| `-o, --output` | string | table | Output format: table, json, csv, parquet, or file path |

## get

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID (required if using experiment name instead of ID) |
| `--space` | string | none | Space name or ID (required if using dataset name instead of ID) |
| `-o, --output` | string | table | Output format |

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Experiment ID |
| `name` | string | Experiment name |
| `dataset_id` | string | Linked dataset ID |
| `dataset_version_id` | string | Specific dataset version used |
| `experiment_traces_project_id` | string | Project where experiment traces are stored |
| `created_at` | datetime | When the experiment was created |
| `updated_at` | datetime | Last modification time |

## export

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID (required if using experiment name instead of ID) |
| `--space` | string | none | Space name or ID (required if using dataset name instead of ID) |
| `--all` | bool | false | Use Arrow Flight for bulk export (required for >500 runs) |
| `--output-dir` | string | `.` | Output directory |
| `--stdout` | bool | false | Print JSON to stdout instead of file |

## create

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--name, -n` | string | yes | Experiment name |
| `--dataset` | string | yes | Dataset to run the experiment against |
| `--space, -s` | string | no | Space name or ID (required if using dataset name instead of ID) |
| `--file, -f` | path | yes | Data file with runs: CSV, JSON, JSONL, or Parquet (use `-` for stdin) |
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
| `--dataset` | no | Required if using experiment name instead of ID |
| `--space, -s` | no | Required when dataset is a name |
| `--limit, -l` | no | Max runs to return (default: 15) |
| `-o, --output` | no | Output format |

## delete

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME_OR_ID` | string | required | Experiment name or ID (positional) |
| `--dataset` | string | none | Dataset name or ID (required if using experiment name instead of ID) |
| `--space` | string | none | Space name or ID (required if using dataset name instead of ID) |
| `--force, -f` | bool | false | Skip confirmation prompt |

## annotate-runs

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `NAME_OR_ID` | string | yes | Experiment name or ID (positional) |
| `--file, -f` | path | yes | Annotation file: JSON, JSONL, CSV, or Parquet (use `-` for stdin) |
| `--dataset` | string | yes | Dataset name or ID (required when using experiment name instead of ID) |
| `--space` | string | no | Space name or ID |
