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

**Exploratory export rule:** When exporting spans or traces **without** a specific `--trace-id`, `--span-id`, or `--session-id` (i.e., browsing/exploring a project), always start with `-n 50` to pull a small sample first. Summarize what you find, then pull more data only if the user asks or the task requires it. This avoids slow queries and overwhelming output on large projects.

**Default output directory:** Always use `--output-dir .arize-tmp-traces` on every `ax spans export` call. The CLI automatically creates the directory and adds it to `.gitignore`.

## Prerequisites

Three things are needed: `ax` CLI, an API key (env var or profile), and a space ID. A project name is also needed but usually comes from the user's message.

### Install ax

Verify `ax` is installed and working before proceeding:

1. Check if `ax` is on PATH: `command -v ax` (Unix) or `where ax` (Windows)
2. If not found, check common install locations:
   - macOS/Linux: `test -x ~/.local/bin/ax && export PATH="$HOME/.local/bin:$PATH"`
   - Windows: check `%APPDATA%\Python\Scripts\ax.exe` or `%LOCALAPPDATA%\Programs\Python\Scripts\ax.exe`
3. If still not found, install it (**requires `required_permissions: ["all"]`** in Cursor sandbox):
   - Preferred: `uv tool install arize-ax-cli`
   - Alternative: `pipx install arize-ax-cli`
   - Fallback: `pip install arize-ax-cli`
4. After install, if `ax` is not on PATH:
   - macOS/Linux: `export PATH="$HOME/.local/bin:$PATH"`
   - Windows (PowerShell): `$env:PATH = "$env:APPDATA\Python\Scripts;$env:PATH"`
5. If `ax --version` fails with an SSL/certificate error:
   - macOS: `export SSL_CERT_FILE=/etc/ssl/cert.pem`
   - Linux: `export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`
   - Windows (PowerShell): `$env:SSL_CERT_FILE = "C:\Program Files\Common Files\SSL\cert.pem"` (or use `python -c "import certifi; print(certifi.where())"` to find the cert bundle)
6. `ax --version` must succeed before proceeding. If it doesn't, stop and ask the user for help.

### Verify environment

Run a quick check for credentials:

```bash
ax --version && echo "--- env ---" && echo "ARIZE_API_KEY: ${ARIZE_API_KEY:-(not set)}" && echo "ARIZE_SPACE_ID: ${ARIZE_SPACE_ID:-(not set)}" && echo "--- profiles ---" && ax profiles show 2>&1
```

**Read the output and proceed immediately** if either the env var or the profile has an API key. Only ask the user if **both** are missing. Resolve failures:

- No API key in env **and** no profile → **AskQuestion**: "Arize API key (https://app.arize.com/admin > API Keys)"
- Space ID unknown → **AskQuestion**, or run `ax projects list -o json --limit 100 --space-id $ARIZE_SPACE_ID` and present as selectable options
- Project unclear → ask, or run `ax projects list -o json --limit 100` and search for a match

**IMPORTANT:** `--space-id` is required when using a human-readable project name as the `PROJECT` positional argument. It is not needed when using a base64-encoded project ID.

## Export Spans: `ax spans export`

The primary command for downloading trace data to a file.

### By trace ID

```bash
# Using project name (requires --space-id)
ax spans export PROJECT_NAME --trace-id TRACE_ID --space-id SPACE_ID --output-dir .arize-tmp-traces

# Using base64 project ID (no --space-id needed)
ax spans export PROJECT_ID --trace-id TRACE_ID --output-dir .arize-tmp-traces
```

### By span ID

```bash
ax spans export PROJECT_NAME --span-id SPAN_ID --space-id SPACE_ID --output-dir .arize-tmp-traces
```

### By session ID

```bash
ax spans export PROJECT_NAME --session-id SESSION_ID --space-id SPACE_ID --output-dir .arize-tmp-traces
```

### Flags

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--trace-id` | string | mutex | Filter: `context.trace_id = 'X'` |
| `--span-id` | string | mutex | Filter: `context.span_id = 'X'` |
| `--session-id` | string | mutex | Filter: `attributes.session.id = 'X'` |
| `PROJECT` | string (positional) | yes (or `$ARIZE_DEFAULT_PROJECT`) | Project name or base64 ID (positional arg, not a flag) |
| `--space-id` | string | yes (when `PROJECT` is a name) | Space ID; required to resolve project names |
| `--days` | int | no | Lookback window (default: 30) |
| `--start-time` | string | no | Override start (ISO 8601) |
| `--end-time` | string | no | Override end (ISO 8601) |
| `--output-dir` | string | no | Output directory (default: `.arize-tmp-traces`; ensure it is gitignored — see above) |
| `--stdout` | bool | no | Print JSON to stdout instead of file |
| `--all` | bool | no | Use Arrow Flight for bulk export (see below) |

Exactly one of `--trace-id`, `--span-id`, `--session-id` is required.

Output is a JSON array of span objects. File naming: `{type}_{id}_{timestamp}/spans.json`.

### Bulk export with `--all` (Arrow Flight)

By default, `ax spans export` uses the REST API which is limited to 500 spans per page and capped by `--limit`. Pass `--all` to switch to Arrow Flight for streaming bulk export with no span limit.

```bash
ax spans export PROJECT_NAME --space-id SPACE_ID --filter "status_code = 'ERROR'" --all --output-dir .arize-tmp-traces
```

**REST vs Flight trade-offs:**
- **REST** (default): Lower friction -- no Arrow/Flight dependency needed, uses standard HTTPS ports, works through any corporate proxy or firewall. Limited to 500 spans per page.
- **Flight** (`--all`): Required for bulk export beyond 500 spans. Uses gRPC+TLS on a separate host/port which some corporate networks may block.

**When to use `--all`:**
- Exporting more than 500 spans
- Downloading full traces with many child spans
- Large time-range exports

**Agent auto-escalation rule:** If a REST export returns exactly the number of spans requested by `-n` (or 500 if no limit was set), the result is likely truncated. Increase `-n` or re-run with `--all` to get the full dataset — but only when the user asks or the task requires more data.

**Requirements for `--all`:**
- `--space-id` is required (Flight uses `space_id` + `project_name`, not `project_id`)
- `--limit` is ignored when `--all` is set

**Networking notes for `--all`:**
Arrow Flight connects to `flight.arize.com:443` via gRPC+TLS -- this is a different host from the REST API (`api.arize.com`). On internal or private networks, the Flight endpoint may use a different host/port. Configure via:
- ax profile: `flight_host`, `flight_port`, `flight_scheme`
- Environment variables: `ARIZE_FLIGHT_HOST`, `ARIZE_FLIGHT_PORT`, `ARIZE_FLIGHT_SCHEME`

The `--all` flag is also available on `ax traces export`, `ax datasets export`, and `ax experiments export` with the same behavior (REST by default, Flight with `--all`).

## Export Traces: `ax traces export`

Export full traces -- all spans belonging to traces that match a filter. Uses a two-phase approach:

1. **Phase 1:** Find spans matching `--filter` (up to `--limit` via REST, or all via Flight with `--all`)
2. **Phase 2:** Extract unique trace IDs, then fetch every span for those traces

```bash
# Explore recent traces (start small with -n 50, pull more if needed)
ax traces export PROJECT_NAME --space-id SPACE_ID -n 50 --output-dir .arize-tmp-traces

# Export traces with error spans (REST, up to 500 spans in phase 1)
ax traces export PROJECT_NAME --space-id SPACE_ID --filter "status_code = 'ERROR'" --stdout

# Export all traces matching a filter via Flight (no limit)
ax traces export PROJECT_NAME --space-id SPACE_ID --filter "status_code = 'ERROR'" --all
```

### Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `PROJECT` | string | required | Positional argument (name or base64 ID) |
| `--filter` | string | none | Filter expression for phase-1 span lookup |
| `--space-id` | string | none | Space ID; required when PROJECT is a name or when using `--all` |
| `--limit, -n` | int | 500 | Max spans in phase-1 lookup (REST page max) |
| `--days` | int | 30 | Lookback window in days |
| `--start-time` | string | none | Override start (ISO 8601) |
| `--end-time` | string | none | Override end (ISO 8601) |
| `--output-dir` | string | `.` | Output directory |
| `--stdout` | bool | false | Print JSON to stdout instead of file |
| `--all` | bool | false | Use Arrow Flight for both phases (see spans `--all` docs above) |
| `-p, --profile` | string | default | Configuration profile |

### How it differs from `ax spans export`

- `ax spans export` exports individual spans matching a filter
- `ax traces export` exports complete traces -- it finds spans matching the filter, then pulls ALL spans for those traces (including siblings and children that may not match the filter)

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
- Always wrap string values in single quotes

## Workflows

### Debug a failing trace

1. `ax traces export PROJECT --space-id SPACE_ID --filter "status_code = 'ERROR'" -n 50 --output-dir .arize-tmp-traces`
2. Read the output file, look for spans with `status_code: ERROR`
3. Check `attributes.error.type` and `attributes.error.message` on error spans

### Download a conversation session

1. `ax spans export PROJECT --session-id SESSION_ID --space-id SPACE_ID --output-dir .arize-tmp-traces`
2. Spans are ordered by `start_time`, grouped by `context.trace_id`
3. If you only have a trace_id, export that trace first, then look for `attributes.session.id` in the output to get the session ID

### Export for offline analysis

```bash
ax spans export PROJECT --trace-id TRACE_ID --space-id SPACE_ID --output-dir .arize-tmp-traces --stdout | jq '.[]'
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
| `ax: command not found` | Check `~/.local/bin/ax`; if missing: `uv tool install arize-ax-cli` (needs `required_permissions: ["all"]`). Then `export PATH="$HOME/.local/bin:$PATH"` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | macOS: `export SSL_CERT_FILE=/etc/ssl/cert.pem`. Linux: `export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`. Windows: `$env:SSL_CERT_FILE = (python -c "import certifi; print(certifi.where())")` |
| `No such command` on a subcommand that should exist | The installed `ax` is outdated. Reinstall from the local workspace: `uv tool install --force --reinstall /path/to/arize/sdk/python/arize-ax-cli` (needs `required_permissions: ["all"]`) |
| `No profile found` | Follow "Resolve credentials" in Prerequisites to auto-discover or prompt for the API key |
| `401 Unauthorized` with valid API key | You are likely using a project name (e.g., `copilot-prod`) without `--space-id`. Add `--space-id SPACE_ID` or use the base64 project ID instead |
| `No spans found` | Expand `--days` (default 30), verify project ID |
| `Filter error` | Check column name spelling, wrap string values in single quotes |
| `Timeout on large export` | Use `--days 7` to narrow the time range |

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any of the following during this conversation (via AskQuestion response, pasted text, or inline values) **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them for future use.

| Credential | Where it gets saved |
|------------|---------------------|
| API key | `ax` profile at `~/.arize/config.toml` |
| Space ID | Shell config (`~/.zshrc` or `~/.bashrc`) as `export ARIZE_SPACE_ID="..."` |

**Skip this entirely if:**
- The API key was already loaded from an existing profile or `ARIZE_API_KEY` env var
- The space ID was already set via `ARIZE_SPACE_ID` env var
- The user only used base64 project IDs (no space ID was needed)

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — Check if `~/.arize/config.toml` exists. If it does, read it and update the `[auth]` section. If not, create it with this minimal content:

   ```toml
   [profile]
   name = "default"

   [auth]
   api_key = "THE_API_KEY"

   [output]
   format = "table"
   ```

   Verify with: `ax profiles show`

2. **Space ID** — Detect the user's shell config file (`~/.zshrc` for zsh, `~/.bashrc` for bash). Append:

   ```bash
   export ARIZE_SPACE_ID="THE_SPACE_ID"
   ```

   Tell the user to run `source ~/.zshrc` (or restart their terminal) for it to take effect.
