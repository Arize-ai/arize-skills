---
name: arize-trace
description: "INVOKE THIS SKILL when downloading or exporting Arize traces and spans. Covers exporting traces by ID, sessions by ID, and debugging LLM application issues using the ax CLI."
---

# Arize Trace Skill

## Concepts

- **Trace** = a tree of spans sharing a `context.trace_id`, rooted at a span with `parent_id = null`
- **Span** = a single operation (LLM call, tool call, retriever, chain, agent)
- **Session** = a group of traces sharing `attributes.session.id` (e.g., a multi-turn conversation)

Use `ax spans export` to download trace data. This is the only supported command for retrieving spans.

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

### Resolve credentials and project

**Credentials** -- resolve in this order, stop at the first success:

1. `ax profiles show --expand 2>&1` -- if it prints auth details without error, you're good.
2. Source a workspace `.env` that has the key, then retry:
   ```bash
   for f in scripts/playground-tests/.env .cursor/skills/alyx-traces/.env .agents/skills/arize-cli/.env; do
     [ -f "$f" ] && grep -q ARIZE_API_KEY "$f" && source "$f" && export ARIZE_API_KEY && break
   done
   ```
3. If still missing, **AskQuestion**: "I need your Arize API key (find it at https://app.arize.com/admin > API Keys)."

Once resolved, write the literal value to config so it works in any shell:

```bash
mkdir -p ~/.arize && cat > ~/.arize/config.toml << EOF
[profile]
name = "default"

[auth]
api_key = "$ARIZE_API_KEY"
EOF
```

**Project** -- resolve in this order:

1. `$ARIZE_DEFAULT_PROJECT` env var -- use it silently if set.
2. Project name/ID mentioned in the user's message.
3. Otherwise run `ax projects list -o json --limit 30` and **AskQuestion** with the project names as selectable options.

## Export Spans: `ax spans export`

The only command for downloading trace data.

### Choosing `--stdout` vs file export

- **Use `--stdout`** when you expect ~10 or fewer spans and want to quickly inspect them inline. This prints JSON directly to the terminal.
- **Use file export (the default)** for anything larger. Writing to the file system avoids bloating the context window and makes it easy to read, search, or re-process the data later.

When in doubt, omit `--stdout` and let the export write to a file -- you can always read the file afterward.

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

### Print to stdout (small results only)

```bash
ax spans export --trace-id TRACE_ID --project PROJECT_ID --stdout
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
| `--stdout` | bool | no | Print JSON to stdout instead of saving to file. Only use for small results (~10 spans or fewer). |

Exactly one of `--trace-id`, `--span-id`, `--session-id` is required.

Output is a JSON array of span objects. File naming: `{type}_{id}_{timestamp}/spans.json`.

## Workflows

### Debug a single span

1. `ax spans export --span-id SPAN_ID --project PROJECT --stdout` (single span, fine for stdout)
2. Check `status_code`, `attributes.error.type`, and `attributes.error.message`

### Debug a failing trace

1. `ax spans export --trace-id TRACE_ID --project PROJECT`
2. Read the output file, look for spans with `status_code: ERROR`
3. Check `attributes.error.type` and `attributes.error.message` on error spans

### Download a conversation session

1. `ax spans export --session-id SESSION_ID --project PROJECT`
2. Read the output file -- spans are ordered by `start_time`, grouped by `context.trace_id`
3. If you only have a trace_id, export that trace first, then look for `attributes.session.id` in the output to get the session ID

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
| `No profile found` | Follow "Resolve credentials" in Prerequisites to auto-discover or prompt for the API key |
| `No spans found` | Expand `--days` (default 30), verify project ID |
| `Timeout on large export` | Use `--days 7` to narrow the time range |
