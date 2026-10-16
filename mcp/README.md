# Arize MCP Skills

MCP-native Agent Skills for the [Arize MCP server](https://api.arize.com/mcp). These skills teach an MCP-connected assistant (for example, a ChatGPT plugin using the OAuth client ID `codex`) to accomplish Arize workflows by calling the Arize MCP tools directly — no `ax` CLI, no terminal, no locally stored API keys.

The skills in [`skills/`](../skills/) remain the CLI-based originals and are untouched. The skills below cover the same domains through the MCP tool surface.

| Skill | Purpose |
|-------|---------|
| [arize-trace](arize-trace/SKILL.md) | Investigate traces, spans, sessions, errors, and latency |
| [arize-dataset](arize-dataset/SKILL.md) | Create and curate datasets and dataset examples |
| [arize-experiment](arize-experiment/SKILL.md) | Record experiment runs, search runs, compare experiments |
| [arize-evaluator](arize-evaluator/SKILL.md) | Create evaluators, run evaluation tasks, read results |
| [arize-project](arize-project/SKILL.md) | Discover and manage projects (and the org/space hierarchy) |
| [arize-prompt](arize-prompt/SKILL.md) | Create prompt versions, inspect history, manage labels |

## ax CLI → MCP tool mapping

| CLI workflow (`skills/`) | MCP tools |
|--------------------------|-----------|
| `ax projects list` / `ax spaces list` / `ax orgs list` | `list_projects`, `list_spaces`, `list_organizations` |
| `ax spans export PROJECT [--trace-id/--span-id/--session-id/--filter]` | `list_spans` (`project_id`, `filter`, `start_time`/`end_time`, `limit`, `cursor`, `included_columns`, `truncate_string_length`) |
| `ax traces export PROJECT [--filter]` | `list_traces` (`project_id`, `filter`, time window, `limit`, `cursor`) |
| `ax spans annotate PROJECT --file` | `annotate_spans` (`project_id`, `annotations`, `granularity`, lookup window) |
| `ax spans delete PROJECT --span-id` | `delete_spans` (`project_id`, `span_ids`, optional time window) |
| `ax datasets list` / `get` / `create` | `list_datasets`, `get_dataset`, `create_dataset` |
| `ax datasets append` / `search` / `update` / `delete examples` | `insert_dataset_examples`, `search_dataset_examples`, `update_dataset_examples`, `delete_dataset_examples` |
| `ax datasets rename` / `delete` / annotate | `update_dataset`, `delete_dataset`, `annotate_dataset_examples` |
| `ax experiments list` / `get` / `create` / `append` / `search` | `list_experiments`, `get_experiment`, `create_experiment`, `insert_experiment_runs`, `search_experiment_runs` |
| `ax experiments annotate` / `delete` | `annotate_experiment_runs`, `delete_experiment` |
| `ax evaluators list` / `create` / `versions` / `delete` | `list_evaluators`, `create_evaluator`, `create_evaluator_version`, `list_evaluator_versions`, `delete_evaluator`, `delete_evaluator_versions`, plus `list_evaluator_templates` for the built-in judge catalog |
| `ax evaluations run` (evaluations over projects/datasets) | `create_task` (`TEMPLATE_EVALUATION` / `CODE_EVALUATION`), `trigger_task_run`, `get_task_run`, `list_task_runs`, `cancel_task_run`, `update_task`, `list_tasks` |
| `ax ai-integrations list` | `list_integrations` (`type: LLM`) |
| `ax prompts list` / `get` / `create` / version / label | `list_prompts`, `get_prompt`, `create_prompt`, `create_prompt_version`, `list_prompt_versions`, `get_prompt_version`, `get_prompt_label`, `set_prompt_version_label`, `delete_prompt_version_label` |
| `ax projects create` / `rename` / `delete` | `create_project`, `update_project`, `delete_project` |

## Workflows with no MCP equivalent

These CLI-skill workflows cannot be completed through the MCP tool surface and are intentionally not advertised by the MCP skills:

- **Unbounded bulk export** (`--all` via Arrow Flight): MCP listing tools are cursor-paginated with per-page caps (spans 100, traces 50, searches 500). Large exports must page through cursors.
- **Arize UI deep links** (`arize-link`): no MCP tool returns UI URLs. The MCP skills report opaque IDs and do not construct links.
- **Prompt execution / playground**: no MCP tool invokes a model with a stored prompt. Prompt skills cover authoring, versioning, and labeling only. (Running a prompt over a dataset is possible via a `RUN_EXPERIMENT` task — see [arize-evaluator](arize-evaluator/SKILL.md).)
- **Prompt optimization** (`arize-prompt-optimization`): no MCP optimization tooling; only manual version iteration.
- **Server-side experiment comparison/aggregation**: comparisons are client-side over `search_experiment_runs` results; MCP has no comparison endpoint.
- **Monitors**: read-only (`list_monitors`, `get_monitor`, `list_monitor_tags`); creating or editing monitors and alerting is not exposed.
- **File-based annotation payloads** (CSV/Parquet via `--file`): MCP annotation tools accept JSON arrays only.
- **Dataset export to files**: examples are read through `search_dataset_examples` pagination; no file export tool exists.
