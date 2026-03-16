---
name: arize-link
description: Generate deep links to the Arize UI. Use when the user wants a clickable URL to open a specific trace, span, session, dataset, labeling queue, evaluator, or annotation config.
---

# Arize Link

Generate deep links to the Arize UI for traces, spans, sessions, datasets, labeling queues, evaluators, and annotation configs.

## When to Use

- User wants a link to a specific trace, span, session, dataset, labeling queue, evaluator, or annotation config
- You have IDs from exported data or logs and need to link back to the UI
- User asks to "open" or "view" any of the above in Arize

## Required Inputs

Collect these from the user or from context (e.g., exported trace data, parsed URLs):

- **org_id** -- Base64-encoded organization ID (from URL path or user)
- **space_id** -- Base64-encoded space ID (from URL path or user)
- Plus one of the following depending on link type:
  - **project_id** (base64) + **trace_id** (and optionally **span_id**) for trace/span links
  - **project_id** (base64) + **session_id** for session links
  - **dataset_id** (base64) for dataset links
  - **queue_id** (base64) for a specific labeling queue (or no ID for the queue list)
  - **evaluator_id** (base64) for a specific evaluator (optionally **version** base64)
  - No additional ID for the annotation configs list

**Verify IDs are base64-encoded:** All three path IDs (`org_id`, `space_id`, `project_id`) must be base64-encoded strings, not raw numeric or UUID values. A misencoded ID produces a well-formed URL that returns a 404 when opened.

```python
# Quick check: a valid base64 ID contains only A-Z, a-z, 0-9, +, /, = characters
import base64, re

def is_base64(s):
    return bool(re.match(r'^[A-Za-z0-9+/]+=*$', s))

# If you have a raw numeric ID, encode it:
# base64.b64encode(b"Organization:1:abC1=").decode()
```

If a user provides `123456` instead of `QWNjb3VudE9yZ2FuaXphdGlvbjoxOmFiQzE=`, ask them to copy the ID directly from their Arize URL (e.g., `https://app.arize.com/organizations/{org_id}/spaces/{space_id}/...`).

## URL Construction

Base URL: `https://app.arize.com` (override for on-prem if the user specifies a custom base URL)

### Trace Link

Opens the trace slideover showing all spans in the trace.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}?selectedTraceId={trace_id}&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA={start_epoch_ms}&endA={end_epoch_ms}&envA=tracing&modelType=generative_llm
```

If a **span_id** is also available, add `&selectedSpanId={span_id}` to highlight that span within the trace.

### Span Link

Opens a specific span within a trace. Both trace_id and span_id are required.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}?selectedTraceId={trace_id}&selectedSpanId={span_id}&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA={start_epoch_ms}&endA={end_epoch_ms}&envA=tracing&modelType=generative_llm
```

### Session Link

Opens the session view for a conversation/interaction flow.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/projects/{project_id}?selectedSessionId={session_id}&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA={start_epoch_ms}&endA={end_epoch_ms}&envA=tracing&modelType=generative_llm
```

### Dataset Link

Opens a dataset. The optional `selectedTab` query parameter controls which tab is shown:
- `examples` — the dataset examples table (default view)
- `experiments` — the experiments run against this dataset

```
{base_url}/organizations/{org_id}/spaces/{space_id}/datasets/{dataset_id}
{base_url}/organizations/{org_id}/spaces/{space_id}/datasets/{dataset_id}?selectedTab=examples
{base_url}/organizations/{org_id}/spaces/{space_id}/datasets/{dataset_id}?selectedTab=experiments
```

If the user asks for experiment results on a dataset, use the `?selectedTab=experiments` variant.

### Annotation Configs List

Opens the space-level list of annotation configs.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/annotation-configs
```

### Labeling Queue List

Opens the space-level list of labeling queues.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/queues
```

### Specific Labeling Queue

Opens a specific labeling queue.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/queues/{queue_id}
```

### Evaluator Link

Opens a specific evaluator. The `version` query parameter (base64-encoded, URL-encoded) is optional — omit it to open the evaluator's default/latest version.

```
{base_url}/organizations/{org_id}/spaces/{space_id}/evaluators/{evaluator_id}
{base_url}/organizations/{org_id}/spaces/{space_id}/evaluators/{evaluator_id}?version={version_id_url_encoded}
```

**Note:** The `version` value must be URL-encoded (e.g., a trailing `=` becomes `%3D`).

## Time Range

**CRITICAL**: `startA` and `endA` are **required** query parameters. Without them, the Arize UI defaults to the last 7 days and will show a "Your model doesn't have any recent data" error if the trace/span falls outside that window.

- **startA**: Start of the time window as epoch milliseconds
- **endA**: End of the time window as epoch milliseconds

### How to Determine the Time Range

Use these sources in priority order:

1. **User-provided URL**: If the user shared an Arize URL, extract `startA` and `endA` from it and reuse them. This is the most reliable approach since it preserves the user's original time window.

2. **Exported span data**: If you have span data (e.g., from `ax spans export`), use the span's `start_time` field to calculate a range that covers the data:
   ```bash
   # Convert span start_time to epoch ms, then pad ±1 day
   python -c "
   from datetime import datetime, timedelta
   t = datetime.fromisoformat('2026-03-07T05:39:15.822147Z'.replace('Z','+00:00'))
   start = int((t - timedelta(days=1)).timestamp() * 1000)
   end = int((t + timedelta(days=1)).timestamp() * 1000)
   print(f'startA={start}&endA={end}')
   "
   ```

3. **Default fallback**: If no time information is available, use the last 90 days. Calculate:
   - `startA`: `(now - 90 days)` as epoch milliseconds
   - `endA`: current time as epoch milliseconds

   **Prefer a tight window when possible.** A 90-day window loads slowly and the trace may be hard to find. If you have `start_time` from span data, use ± 1 hour instead of ± 1 day for a faster-loading view. An overly narrow window that excludes the trace shows an empty view — pad generously if in doubt.

## Instructions

1. Gather the required IDs from the user or from available context (URLs, exported trace data, conversation history).
2. Verify that all path IDs (`org_id`, `space_id`, and any resource ID) are base64-encoded (see above). `project_id` is only required for trace/span/session links.
3. Determine `startA` and `endA` epoch milliseconds using the priority order above.
4. Substitute values into the appropriate URL template above.
5. Present the URL as a clickable markdown link.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Link opens but shows "no data" | The trace falls outside the time window. Widen `startA`/`endA` — if you used ±1 hour initially, retry with ±1 day; if still empty, fall back to a 90-day window. |
| Link returns 404 | An ID is wrong or not base64-encoded. Re-check `org_id`, `space_id`, `project_id` from the browser URL bar. |
| Trace loads but span is not highlighted | The `span_id` may be from a different trace. Verify `span_id` belongs to `trace_id` in the exported span data. |
| Wrong timezone / time appears shifted | The URL hardcodes `timeZoneA=America%2FLos_Angeles`. This affects display only, not which data is shown. No fix needed unless the user reports confusion — then note that all timestamps in the UI are shown in Pacific time. |
| `org_id` is unknown | The `ax` CLI does not expose `org_id`. Ask the user to open `https://app.arize.com` in their browser, navigate to any project, and copy `org_id` from the URL: `https://app.arize.com/organizations/{org_id}/spaces/{space_id}/...` |

## Related Skills

- **arize-trace**: Export spans to get `trace_id`, `span_id`, and `start_time` needed for link construction → use `arize-trace`

## Example Output

### Trace / Span / Session

Given: org_id=`QWNjb3VudE9yZ2FuaXphdGlvbjoxOmFiQzE=`, space_id=`U3BhY2U6MTp4eVo5`, project_id=`TW9kZWw6MTpkZUZn`, trace_id=`0123456789abcdef0123456789abcdef`

Trace link:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjoxOmFiQzE=/spaces/U3BhY2U6MTp4eVo5/projects/TW9kZWw6MTpkZUZn?selectedTraceId=0123456789abcdef0123456789abcdef&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA=1700000000000&endA=1700086400000&envA=tracing&modelType=generative_llm
```

### Dataset

Given: org_id=`QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=`, space_id=`U3BhY2U6NzE5Mjp4V1Q1`, dataset_id=`RGF0YXNldDozMzM2Nzk6MVVjTQ==`

Dataset examples tab:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/datasets/RGF0YXNldDozMzM2Nzk6MVVjTQ==?selectedTab=examples
```

Dataset experiments tab:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/datasets/RGF0YXNldDozMzM2Nzk6MVVjTQ==?selectedTab=experiments
```

### Labeling Queue

Queue list:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/queues
```

Specific queue (queue_id=`QW5ub3RhdGlvblF1ZXVlOjE0MTA6ZllnRg==`):
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/queues/QW5ub3RhdGlvblF1ZXVlOjE0MTA6ZllnRg==
```

### Evaluator

Given: evaluator_id=`RXZhbHVhdG9yOjIyOTg6SzFRTQ==`, version=`RXZhbHVhdG9yVmVyc2lvbjozOTMzOlo0b2I=` (URL-encoded: `RXZhbHVhdG9yVmVyc2lvbjozOTMzOlo0b2I%3D`)

Evaluator (latest version):
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/evaluators/RXZhbHVhdG9yOjIyOTg6SzFRTQ==
```

Evaluator (specific version):
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/evaluators/RXZhbHVhdG9yOjIyOTg6SzFRTQ==?version=RXZhbHVhdG9yVmVyc2lvbjozOTMzOlo0b2I%3D
```

### Annotation Configs

```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/annotation-configs
```
