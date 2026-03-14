---
name: arize-link
description: Generate deep links to traces, spans, and sessions in the Arize UI. Use when the user wants a clickable URL to open a specific trace, span, or session.
---

# Arize Link

Generate deep links to the Arize UI for traces, spans, and sessions.

## When to Use

- User wants a link to a specific trace, span, or session
- You have trace/span/session IDs from exported data or logs and need to link back to the UI
- User asks to "open" or "view" a trace/span/session in Arize

## Required Inputs

Collect these from the user or from context (e.g., exported trace data, parsed URLs):

- **org_id** -- Base64-encoded organization ID (from URL path or user)
- **space_id** -- Base64-encoded space ID (from URL path or user)
- **project_id** -- Base64-encoded project/model ID (from URL path or user)
- One of:
  - **trace_id** (and optionally **span_id**) for trace/span links
  - **session_id** for session links

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
2. Verify that `org_id`, `space_id`, and `project_id` are base64-encoded (see above).
3. Determine `startA` and `endA` epoch milliseconds using the priority order above.
4. Substitute values into the appropriate URL template above.
5. Present the URL as a clickable markdown link.
6. **Validate the link** by checking it returns HTTP 200:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" "THE_GENERATED_URL"
   # 200 = valid, 404 = wrong IDs or path, 403 = auth required
   ```
   If it returns 404, the IDs are likely wrong or not base64-encoded. Ask the user to copy IDs from their browser URL bar.

## Unsupported link types

The URL templates above cover **traces, spans, and sessions only**. Deep links to the following are **not currently supported** via this skill:
- Dataset detail pages
- Experiment result pages
- Evaluation annotation views
- User/team management pages

Do not attempt to construct URLs for these using the trace/session templates — the URL schema is different and the links will not work.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Link opens but shows "no data" | The trace falls outside the time window. Widen `startA`/`endA` — pad by ±7 days when unsure. |
| Link returns 404 | An ID is wrong or not base64-encoded. Re-check `org_id`, `space_id`, `project_id` from the browser URL bar. |
| Trace loads but span is not highlighted | The `span_id` may be from a different trace. Verify `span_id` belongs to `trace_id` in the exported span data. |
| Wrong timezone / time appears shifted | The URL hardcodes `timeZoneA=America%2FLos_Angeles`. This affects display only, not which data is shown. No fix needed unless the user reports confusion — then note that all timestamps in the UI are shown in Pacific time. |
| `org_id` is unknown | The `ax` CLI does not expose `org_id`. Ask the user to open `https://app.arize.com` in their browser, navigate to any project, and copy `org_id` from the URL: `https://app.arize.com/organizations/{org_id}/spaces/{space_id}/...` |

## Related Skills

- **arize-trace**: Export spans to get `trace_id`, `span_id`, and `start_time` needed for link construction → use `arize-trace`

## Example Output

Given: org_id=`QWNjb3VudE9yZ2FuaXphdGlvbjoxOmFiQzE=`, space_id=`U3BhY2U6MTp4eVo5`, project_id=`TW9kZWw6MTpkZUZn`, trace_id=`0123456789abcdef0123456789abcdef`

Trace link:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjoxOmFiQzE=/spaces/U3BhY2U6MTp4eVo5/projects/TW9kZWw6MTpkZUZn?selectedTraceId=0123456789abcdef0123456789abcdef&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA=1700000000000&endA=1700086400000&envA=tracing&modelType=generative_llm
```
