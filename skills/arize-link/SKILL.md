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

- **startA**: 90 days ago as epoch milliseconds. Calculate: `(now - 90 days) * 1000`
- **endA**: Current time as epoch milliseconds. Calculate: `now * 1000`

If the user provides specific timestamps, use those instead.

## Instructions

1. Gather the required IDs from the user or from available context.
2. Calculate `startA` and `endA` epoch milliseconds (default: last 90 days).
3. Substitute values into the appropriate URL template above.
4. Present the URL as a clickable markdown link.

## Example Output

Given: org_id=`QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=`, space_id=`U3BhY2U6NzE5Mjp4V1Q1`, project_id=`TW9kZWw6MjMwMDI5NDQwNDpqdlp4`, trace_id=`fcdcfadb43b5b46d8e350af3a3a6895d`

Trace link:
```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo2ODUxOmQxNkU=/spaces/U3BhY2U6NzE5Mjp4V1Q1/projects/TW9kZWw6MjMwMDI5NDQwNDpqdlp4?selectedTraceId=fcdcfadb43b5b46d8e350af3a3a6895d&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA=1765213200000&endA=1772988919025&envA=tracing&modelType=generative_llm
```
