# Evaluation tasks

Tasks run evaluators over data and produce scored runs. All tool names and parameters below are the verified MCP surface — do not invent others.

## Task types

| `type` | Data source | Required | Notes |
|--------|-------------|----------|-------|
| `TEMPLATE_EVALUATION` | `project_id` or `dataset_id` | `evaluators` | Dataset-based tasks require `experiment_ids` with at least one entry. `sampling_rate` and `is_continuous` are project-based only. |
| `CODE_EVALUATION` | `project_id` or `dataset_id` | `evaluators` | Same rules as `TEMPLATE_EVALUATION`. |
| `RUN_EXPERIMENT` | `dataset_id` only | `run_configuration` | Generates experiment runs from dataset examples. Never continuous. |

Duplicate `evaluator_id`s in one task are rejected. System-managed fields (`id`, `created_at`, `updated_at`) are rejected on input.

## Attaching evaluators

Span-granularity evaluators use `column_mappings`; trace/session evaluators use `query_mappings`. Mixing the two shapes in one task is rejected — every evaluator must resolve to the same data scope.

### Span evaluators

```json
{
  "evaluator_id": "<evaluator_id>",
  "evaluator_version_id": null,
  "query_filter": "status_code = 'ERROR'",
  "column_mappings": {
    "input": "attributes.input.value",
    "output": "attributes.output.value"
  }
}
```

- `column_mappings` maps the evaluator's template variable names to span attribute paths.
- Per-evaluator `query_filter` (span shape) ANDs with the task-level `query_filter`.
- `evaluator_version_id` pins one version; omit it or send `null` to always run the evaluator's latest version. The pinned version must belong to `evaluator_id`, otherwise the request fails with 422.

### Trace and session evaluators

Task-level `query_filters` declares one to five named filters (single-letter ids `A`–`E`, unique) plus an optional boolean `expression` combining them (required when two or more filters are declared):

```json
{
  "query_filters": {
    "filters": [
      { "id": "A", "filter": "span_kind = 'LLM'" },
      { "id": "B", "filter": "span_kind = 'TOOL'" }
    ],
    "expression": "A AND B"
  },
  "evaluators": [
    {
      "evaluator_id": "<evaluator_id>",
      "query_mappings": [
        {
          "variable_name": "conversation",
          "query_ids": ["A", "B"],
          "attribute_path": "attributes.input.value"
        }
      ]
    }
  ]
}
```

`query_filters` (trace/session shape) and `query_filter` (span shape) are mutually exclusive. An empty `query_ids` list means "any declared query" — valid for session-level variables that match all spans in the conversation.

## RUN_EXPERIMENT run_configuration

Exactly one variant, selected by `experiment_type`:

- `LLM_GENERATION` — runs a prompt over each dataset example. Requires `ai_integration_id` and `messages`; optional `model_name` (defaults to the integration's default), `prompt_version_id` for traceability, `input_variable_format`, `invocation_parameters`, `provider_parameters`.
- `TEMPLATE_EVALUATION` — an inline LLM judge. Requires `ai_integration_id` and `template` (with `{{variable}}` placeholders mapped by `column_mapping` to dataset column paths); optional `classification_choices`, `provide_explanation`, `evaluator_version_id`.
- `AGENT_CALL` — calls an `AGENT` integration per example. Requires `integration_id` and `input_template` (a JSON body with `{{column}}` placeholders substituted from each dataset row).

## Triggering and polling

`trigger_task_run` with `task_id` starts an asynchronous run. Field applicability follows the task type — sending inapplicable fields returns 400.

- `TEMPLATE_EVALUATION` / `CODE_EVALUATION`: optional `data_start_time`, `data_end_time` (model-based tasks need `data_start_time` on the first run), `max_spans` (default 10000), `override_evaluations` (default `false`), `experiment_ids` (dataset-based).
- `RUN_EXPERIMENT`: required `experiment_name` (unique within the dataset, no double quotes or backslashes); optional `dataset_version_id`, `example_ids` (mutually exclusive with `max_examples`), `max_examples`, `query_filter`, `tracing_metadata`, `evaluation_task_ids` (chained evaluation tasks triggered after the run completes).

Poll `get_task_run` with the returned `run_id` until a terminal status. Statuses: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`. `cancel_task_run` works only while a run is `PENDING` or `RUNNING`. `list_task_runs` filters by `status` for a task's history.

## Updating and deleting

- `update_task` — mutable fields: `name`, `sampling_rate`, `is_continuous`, `query_filter` / `query_filters`, and `evaluators` (providing `evaluators` replaces the entire list, including each entry's version pin; omit the field to leave attachments untouched).
- `delete_task` — irreversible; deletes the task's runs and evaluator configs.
- `delete_evaluator` — irreversible; returns 409 listing the tasks that still use it. Remove the evaluator from those tasks (or delete them) first.

## LLM integrations

Template evaluators and `LLM_GENERATION` runs need an `ai_integration_id`. Resolve one with `list_integrations` filtered to `type: "LLM"` — pass `space_id` or `space_name` to narrow to integrations visible in a space. Integration IDs are opaque base64 strings.
