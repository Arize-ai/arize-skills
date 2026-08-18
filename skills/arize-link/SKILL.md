---
name: arize-link
description: Generates deep links to the Arize UI for projects, traces, spans, sessions, datasets, labeling queues, evaluators, and annotation configs. Discovers organization and project IDs with the ax CLI and produces clickable URLs for sharing Arize resources with team members. Use when the user wants to link to or open a project, trace, span, session, dataset, evaluator, or annotation config in the Arize UI.
metadata:
  author: arize
  version: "1.0"
---

# Arize Link

Generate deep links to the Arize UI for projects, traces, spans, sessions, datasets, labeling queues, evaluators, and annotation configs.

## When to Use

- User wants a link to a project, trace, span, session, dataset, labeling queue, evaluator, or annotation config
- You have IDs from exported data or logs and need to link back to the UI
- User asks to "open" or "view" any of the above in Arize

## Required Inputs

Collect from the user, context (exported trace data or parsed URLs), or the `ax` CLI:

| Always required | Resource-specific |
|---|---|
| `org_id` (base64) | `project_id` + `trace_id` [+ `span_id`] — trace/span |
| `space_id` (base64) | `project_id` + `session_id` — session |
| | `dataset_id` — dataset |
| | `queue_id` — specific queue (omit for list) |
| | `evaluator_id` [+ `version`] — evaluator |

### Discover organization and project IDs

Prefer the CLI over asking the user for IDs that it can provide:

```bash
ax organizations list --output json
```

Use `.organizations[].id` for the organization ID. If more than one organization is returned, match the user-provided organization name or ask them to choose.

To discover a project ID, list projects in the relevant space:

```bash
ax projects list --space "{space_name_or_id}" --limit 100 --output json
```

Use the matching project's `id`; its `space_id` supplies the space ID required in the URL. The command accepts a space name or ID; if no space is known, run `ax projects list --limit 100 --output json` and select the matching project.

**All path IDs must be base64-encoded** (characters: `A-Za-z0-9+/=`). A raw numeric ID produces a valid-looking URL that 404s. If the user provides a number, ask them to copy the ID directly from their Arize browser URL (`https://app.arize.com/organizations/{org_id}/spaces/{space_id}/…`). If you have a raw internal ID (e.g. `Organization:1:abC1`), base64-encode it before inserting into the URL.

## URL Templates

Base URL: `https://app.arize.com` (override for on-prem)

**Project:**
```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}
```

**Trace** (add `&selectedSpanId={span_id}` to highlight a specific span):
```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}?selectedTraceId={trace_id}&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA={start_ms}&endA={end_ms}&envA=tracing&modelType=generative_llm
```

**Session:**
```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}?selectedSessionId={session_id}&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA={start_ms}&endA={end_ms}&envA=tracing&modelType=generative_llm
```

**Dataset** (`selectedTab`: `examples` or `experiments`):
```
{base_url}/organizations/{org_id}/spaces/{space_id}/datasets/{dataset_id}?selectedTab=examples
```

**Queue list / specific queue:**
```
{base_url}/organizations/{org_id}/spaces/{space_id}/queues
{base_url}/organizations/{org_id}/spaces/{space_id}/queues/{queue_id}
```

**Evaluator** (omit `?version=…` for latest):
```
{base_url}/organizations/{org_id}/spaces/{space_id}/evaluators/{evaluator_id}
{base_url}/organizations/{org_id}/spaces/{space_id}/evaluators/{evaluator_id}?version={version_url_encoded}
```
The `version` value must be URL-encoded (e.g., trailing `=` → `%3D`).

**Annotation configs:**
```
{base_url}/organizations/{org_id}/spaces/{space_id}/annotation-configs
```

## Time Range

CRITICAL: `startA` and `endA` (epoch milliseconds) are **required** for trace/span/session links — omitting them defaults to the last 7 days and will show "no recent data" if the trace falls outside that window.

**Priority order:**
1. **User-provided URL** — extract and reuse `startA`/`endA` directly.
2. **Span `start_time`** — pad ±1 day (or ±1 hour for a tighter window).
3. **Fallback** — last 90 days (`now - 90d` to `now`).

Prefer tight windows; 90-day windows load slowly.

## Instructions

1. Gather IDs from user, exported data, URL context, or the CLI. Use `ax organizations list --output json` to obtain `org_id`; use `ax projects list` to obtain `project_id` when needed.
2. Verify all path IDs are base64-encoded.
3. Determine `startA`/`endA` using the priority order above for trace, span, and session links.
4. Substitute into the appropriate template and present as a clickable markdown link.

## Troubleshooting

| Problem | Solution |
|---|---|
| "No data" / empty view | Trace outside time window — widen `startA`/`endA` (±1h → ±1d → 90d). |
| 404 | ID wrong or not base64. Re-check `org_id` with `ax organizations list --output json`, `project_id` with `ax projects list`, and `space_id` from the browser URL. |
| Span not highlighted | `span_id` may belong to a different trace. Verify against exported span data. |
| `org_id` unknown | Run `ax organizations list --output json` and use `.organizations[].id`. If the CLI cannot access the organization, ask the user to copy it from their Arize browser URL. |

## Related Skills

- **arize-trace**: Export spans to get `trace_id`, `span_id`, and `start_time`.

## Examples

See [references/EXAMPLES.md](references/EXAMPLES.md) for a complete set of concrete URLs for every link type.
