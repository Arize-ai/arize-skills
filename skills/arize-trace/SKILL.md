---
name: arize-trace
description: "INVOKE THIS SKILL when downloading, browsing, or filtering Arize traces and spans. Covers downloading traces by ID, sessions by ID, browsing spans with filters, and debugging LLM application issues using the ax CLI."
---

# Arize Trace Skill

## Concepts

- **Trace** = a tree of spans sharing a `context.trace_id`, rooted at a span with `parent_id = null`
- **Span** = a single operation (LLM call, tool call, retriever, chain, agent)
- **Session** = a group of traces sharing `attributes.session.id` (e.g., a multi-turn conversation)

`ax traces list` returns root spans only (auto-injects `parent_id = null`).
`ax spans list` returns all spans.

## Prerequisites

### Install ax

Check for `ax` on PATH, then fall back to the common `uv tool` install location:

```bash
command -v ax || test -x ~/.local/bin/ax && export PATH="$HOME/.local/bin:$PATH"
```

If neither exists, install it (**requires `required_permissions: ["all"]`** in Cursor sandbox):

```bash
uv tool install arize-ax-cli   # preferred
pipx install arize-ax-cli      # alternative
```

### Configure profile

If no profile exists (check: `ax profiles list`) **and** `ARIZE_API_KEY` is set, create one non-interactively (`ax profiles create` is interactive and cannot be driven by an agent):

```bash
mkdir -p ~/.arize && cat > ~/.arize/config.toml << 'EOF'
[profile]
name = "default"

[auth]
api_key = "${ARIZE_API_KEY}"
EOF
```

If `ARIZE_API_KEY` is not set, ask the user for it.

### Default Project

Before running any command, check for a default project:

```bash
echo $ARIZE_DEFAULT_PROJECT
```

If `ARIZE_DEFAULT_PROJECT` is set, use its value as the project for **all** commands in this session. Do NOT ask the user for a project ID -- just use it. Continue using this default until the user explicitly provides a different project.

If `ARIZE_DEFAULT_PROJECT` is not set and no project is provided, ask the user for one.

## Export Spans: `ax spans export`

The primary command for downloading trace data to a file.

### By trace ID

```bash
ax spans export --trace-id TRACE_ID --project PROJECT_ID
```

### By span ID

```bash
ax spans export --span-id SPAN_ID --project PROJECT_ID
```

### By session ID

```bash
ax spans export --session-id SESSION_ID --project PROJECT_ID
```

### Flags

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--trace-id` | string | mutex | Filter: `context.trace_id = 'X'` |
| `--span-id` | string | mutex | Filter: `context.span_id = 'X'` |
| `--session-id` | string | mutex | Filter: `attributes.session.id = 'X'` |
| `--project` | string | yes (or `$ARIZE_DEFAULT_PROJECT`) | Project ID |
| `--days` | int | no | Lookback window (default: 30) |
| `--start-time` | string | no | Override start (ISO 8601) |
| `--end-time` | string | no | Override end (ISO 8601) |
| `--output-dir` | string | no | Output directory (default: `.`) |
| `--stdout` | bool | no | Print JSON to stdout instead of file |

Exactly one of `--trace-id`, `--span-id`, `--session-id` is required.

Output is a JSON array of span objects. File naming: `{type}_{id}_{timestamp}/spans.json`.

**NOTE:** If `ax spans export` is not available (older `arize-ax-cli` version), fall back to `ax spans list` with `--filter`:

```bash
ax spans list PROJECT_ID --filter "context.trace_id = 'TRACE_ID'" --limit 50 -o json
```

## Browse: `ax traces list`

Browse root spans (one row per trace). Output goes to stdout.

```bash
ax traces list PROJECT_ID --limit 15
ax traces list PROJECT_ID --filter "status_code = 'ERROR'" --limit 10
ax traces list PROJECT_ID --start-time 2026-03-01T00:00:00Z --limit 20
```

## Browse: `ax spans list`

Browse all spans with filters. Output goes to stdout.

```bash
ax spans list PROJECT_ID --limit 15
ax spans list PROJECT_ID --filter "name = 'ChatCompletion' AND latency_ms > 5000"
ax spans list PROJECT_ID --filter "status_code = 'ERROR'" -o json
```

### Shared flags for both browse commands

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `PROJECT_ID` | string | required (or `$ARIZE_DEFAULT_PROJECT`) | Positional argument |
| `--start-time` | string | 1 week ago | ISO 8601 |
| `--end-time` | string | now | ISO 8601 |
| `--filter` | string | none | SQL-like filter expression |
| `--limit` | int | 15 | Max results |
| `--cursor` | string | none | Pagination cursor |
| `-o, --output` | string | table | Output format: table, json, csv, parquet, or file path |

## Filter Syntax Reference

SQL-like expressions passed to `--filter`.

### Common filterable columns

| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| `name` | string | Span name | `'ChatCompletion'`, `'retrieve_docs'` |
| `status_code` | string | Status | `'OK'`, `'ERROR'`, `'UNSET'` |
| `latency_ms` | number | Duration in ms | `100`, `5000` |
| `parent_id` | string | Parent span ID | null for root spans |
| `context.trace_id` | string | Trace ID | |
| `context.span_id` | string | Span ID | |
| `attributes.session.id` | string | Session ID | |
| `attributes.openinference.span.kind` | string | Span kind | `'LLM'`, `'CHAIN'`, `'TOOL'`, `'AGENT'`, `'RETRIEVER'`, `'RERANKER'`, `'EMBEDDING'`, `'GUARDRAIL'`, `'EVALUATOR'` |
| `attributes.llm.model_name` | string | LLM model | `'gpt-4o'`, `'claude-3'` |
| `attributes.input.value` | string | Span input | |
| `attributes.output.value` | string | Span output | |
| `attributes.error.type` | string | Error type | `'ValueError'`, `'TimeoutError'` |
| `attributes.error.message` | string | Error message | |
| `event.attributes` | string | Error tracebacks | Use CONTAINS (not exact match) |

### Operators

`=`, `!=`, `<`, `<=`, `>`, `>=`, `AND`, `OR`, `IN`, `CONTAINS`, `LIKE`, `IS NULL`, `IS NOT NULL`

### Examples

```
status_code = 'ERROR'
latency_ms > 5000
name = 'ChatCompletion' AND status_code = 'ERROR'
attributes.llm.model_name = 'gpt-4o'
attributes.openinference.span.kind IN ('LLM', 'AGENT')
attributes.error.type LIKE '%Transport%'
event.attributes CONTAINS 'TimeoutError'
```

### Tips

- Prefer `IN` over multiple `OR` conditions: `name IN ('a', 'b', 'c')` not `name = 'a' OR name = 'b' OR name = 'c'`
- Start broad with `LIKE`, then switch to `=` or `IN` once you know exact values
- Use `CONTAINS` for `event.attributes` (error tracebacks) -- exact match is unreliable on complex text
- **IS NOT NULL gotcha**: Filters match at the trace level. A trace with one error span returns ALL spans from that trace. Add `AND attributes.error.type IS NOT NULL` if you only want spans that actually have the column.
- Always wrap string values in single quotes

## Workflows

### Debug a failing trace

1. `ax traces list PROJECT --filter "status_code = 'ERROR'" --limit 5`
2. Pick a trace_id from the results
3. `ax spans export --trace-id TRACE_ID --project PROJECT`
4. Read the output file, look for spans with `status_code: ERROR`
5. Check `attributes.error.type` and `attributes.error.message` on error spans

### Download a conversation session

1. `ax spans export --session-id SESSION_ID --project PROJECT`
2. Spans are ordered by `start_time`, grouped by `context.trace_id`
3. If you only have a trace_id, export that trace first, then look for `attributes.session.id` in the output to get the session ID

### Investigate slow LLM calls

1. `ax spans list PROJECT --filter "attributes.openinference.span.kind = 'LLM' AND latency_ms > 10000" --limit 20`
2. Examine `attributes.llm.model_name`, token counts, input sizes
3. For a specific slow trace: `ax spans export --trace-id TRACE_ID --project PROJECT`

### Iterative filter building

1. Start broad: `ax spans list PROJECT --filter "attributes.error.type LIKE '%Transport%'" --limit 10`
2. Examine results to discover exact values
3. Narrow down: `ax spans list PROJECT --filter "attributes.error.type IN ('TransportServerError', 'TransportQueryError')" --limit 20`
4. Export: `ax spans export --trace-id TRACE_ID --project PROJECT` for a specific result

### Export for offline analysis

```bash
ax spans export --trace-id TRACE_ID --project PROJECT --stdout | jq '.[]'
ax spans list PROJECT --filter "..." -o json > spans.json
```

## Span Column Reference (OpenInference Semantic Conventions)

### Core Identity and Timing

| Column | Description |
|--------|-------------|
| `name` | Span operation name (e.g., `ChatCompletion`, `retrieve_docs`) |
| `context.trace_id` | Trace ID -- all spans in a trace share this |
| `context.span_id` | Unique span ID |
| `parent_id` | Parent span ID. `null` for root spans (= traces) |
| `start_time` | When the span started (ISO 8601) |
| `end_time` | When the span ended |
| `latency_ms` | Duration in milliseconds |
| `status_code` | `OK`, `ERROR`, `UNSET` |
| `status_message` | Optional message (usually set on errors) |
| `attributes.openinference.span.kind` | `LLM`, `CHAIN`, `TOOL`, `AGENT`, `RETRIEVER`, `RERANKER`, `EMBEDDING`, `GUARDRAIL`, `EVALUATOR` |

### Where to Find Prompts and LLM I/O

**Generic input/output (all span kinds):**

| Column | What it contains |
|--------|-----------------|
| `attributes.input.value` | The input to the operation. For LLM spans, often the full prompt or serialized messages JSON. For chain/agent spans, the user's question. |
| `attributes.input.mime_type` | Format hint: `text/plain` or `application/json` |
| `attributes.output.value` | The output. For LLM spans, the model's response. For chain/agent spans, the final answer. |
| `attributes.output.mime_type` | Format hint for output |

**LLM-specific message arrays (structured chat format):**

| Column | What it contains |
|--------|-----------------|
| `attributes.llm.input_messages` | Structured input messages array (system, user, assistant, tool). **Where chat prompts live** in role-based format. |
| `attributes.llm.input_messages.roles` | Array of roles: `system`, `user`, `assistant`, `tool` |
| `attributes.llm.input_messages.contents` | Array of message content strings |
| `attributes.llm.output_messages` | Structured output messages from the model |
| `attributes.llm.output_messages.contents` | Model response content |
| `attributes.llm.output_messages.tool_calls.function.names` | Tool calls the model wants to make |
| `attributes.llm.output_messages.tool_calls.function.arguments` | Arguments for those tool calls |

**Prompt templates:**

| Column | What it contains |
|--------|-----------------|
| `attributes.llm.prompt_template.template` | The prompt template with variable placeholders (e.g., `"Answer {question} using {context}"`) |
| `attributes.llm.prompt_template.variables` | Template variable values (JSON object) |

**Finding prompts by span kind:**

- **LLM span**: Check `attributes.llm.input_messages` for structured chat messages, OR `attributes.input.value` for serialized prompt. Check `attributes.llm.prompt_template.template` for the template.
- **Chain/Agent span**: Check `attributes.input.value` for the user's question. Actual LLM prompts are on child LLM spans.
- **Tool span**: Check `attributes.input.value` for tool input, `attributes.output.value` for tool result.

### LLM Model and Cost

| Column | Description |
|--------|-------------|
| `attributes.llm.model_name` | Model identifier (e.g., `gpt-4o`, `claude-3-opus-20240229`) |
| `attributes.llm.invocation_parameters` | Model parameters JSON (temperature, max_tokens, top_p, etc.) |
| `attributes.llm.token_count.prompt` | Input token count |
| `attributes.llm.token_count.completion` | Output token count |
| `attributes.llm.token_count.total` | Total tokens |
| `attributes.llm.cost.prompt` | Input cost in USD |
| `attributes.llm.cost.completion` | Output cost in USD |
| `attributes.llm.cost.total` | Total cost in USD |

### Tool Spans

| Column | Description |
|--------|-------------|
| `attributes.tool.name` | Tool/function name |
| `attributes.tool.description` | Tool description |
| `attributes.tool.parameters` | Tool parameter schema (JSON) |

### Retriever Spans

| Column | Description |
|--------|-------------|
| `attributes.retrieval.documents` | Retrieved documents array |
| `attributes.retrieval.documents.ids` | Document IDs |
| `attributes.retrieval.documents.scores` | Relevance scores |
| `attributes.retrieval.documents.contents` | Document text content |
| `attributes.retrieval.documents.metadatas` | Document metadata |

### Reranker Spans

| Column | Description |
|--------|-------------|
| `attributes.reranker.query` | The query being reranked |
| `attributes.reranker.model_name` | Reranker model |
| `attributes.reranker.top_k` | Number of results |
| `attributes.reranker.input_documents.*` | Input documents (ids, scores, contents, metadatas) |
| `attributes.reranker.output_documents.*` | Reranked output documents |

### Session, User, and Custom Metadata

| Column | Description |
|--------|-------------|
| `attributes.session.id` | Session/conversation ID -- groups traces into multi-turn sessions |
| `attributes.user.id` | End-user identifier |
| `attributes.metadata.*` | Custom key-value metadata. Any key under this prefix is user-defined (e.g., `attributes.metadata.user_email`). Filterable. |

### Errors and Exceptions

| Column | Description |
|--------|-------------|
| `attributes.exception.type` | Exception class name (e.g., `ValueError`, `TimeoutError`) |
| `attributes.exception.message` | Exception message text |
| `event.attributes` | Error tracebacks and detailed event data. Use `CONTAINS` for filtering. |

### Evaluations and Annotations

| Column | Description |
|--------|-------------|
| `annotation.<name>.label` | Human or auto-eval label (e.g., `correct`, `incorrect`) |
| `annotation.<name>.score` | Numeric score (e.g., `0.95`) |
| `annotation.<name>.text` | Freeform annotation text |

### Embeddings

| Column | Description |
|--------|-------------|
| `attributes.embedding.model_name` | Embedding model name |
| `attributes.embedding.texts` | Text chunks that were embedded |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | Check `~/.local/bin/ax`; if missing: `uv tool install arize-ax-cli` (needs `required_permissions: ["all"]`) |
| `No profile found` | Create `~/.arize/config.toml` with `api_key = "${ARIZE_API_KEY}"` (see Prerequisites) |
| `No spans found` | Expand `--days` (default 30), verify project ID |
| `Filter error` | Check column name spelling, wrap string values in single quotes |
| `Timeout on large export` | Use `--days 7` to narrow the time range |
| `ax spans export` not found | Requires `arize-ax-cli` from branch `jlopatecki/ax-cli-export`. Fall back to `ax spans list --filter` |
