# Span columns and filter syntax

Column paths for `list_spans` and `list_traces`. OpenInference semantic conventions, plus the fixed span fields those tools always return. See [the trace skill](../SKILL.md) for the investigation workflow.

## Fixed fields and column selection

`list_spans` accepts `included_columns` or `excluded_columns` (not both). Each entry is a full dotted path such as `attributes.llm.model_name`. Unknown names are ignored with no error. If a path you requested is missing from the payload, it was either unknown or absent on that span. Fetch a small page with neither parameter before concluding the attribute does not exist.

These fields are always returned, even when `included_columns` is set:

`name`, `context`, `kind`, `parent_id`, `start_time`, `end_time`, `status_code`, `status_message`, `latency_ms`, `events`

`kind` here is the telemetry span kind. The OpenInference kind (`LLM`, `TOOL`, and the rest) is `attributes.openinference.span.kind`.

`truncate_string_length` shortens strings inside `attributes` only. Say so when you quote a truncated value. It does not shorten `events`.

## Core identity and timing

| Column | Description |
|--------|-------------|
| `name` | Span operation name (for example `ChatCompletion`, `retrieve_docs`) |
| `context.trace_id` | Trace ID. Every span in a trace shares it |
| `context.span_id` | Unique span ID |
| `parent_id` | Parent span ID. Null on a root span |
| `start_time` | When the span started (ISO 8601) |
| `end_time` | When the span ended |
| `latency_ms` | Duration in milliseconds |
| `status_code` | `OK`, `ERROR`, or `UNSET` |
| `status_message` | Optional message, usually set on errors |
| `attributes.openinference.span.kind` | `LLM`, `CHAIN`, `TOOL`, `AGENT`, `RETRIEVER`, `RERANKER`, `EMBEDDING`, `GUARDRAIL`, `EVALUATOR` |

## Prompts and LLM input/output

Generic input and output (any span kind):

| Column | What it contains |
|--------|------------------|
| `attributes.input.value` | Input to the operation. On LLM spans, often the prompt or serialized messages. On chain or agent spans, often the user question |
| `attributes.input.mime_type` | Format hint: `text/plain` or `application/json` |
| `attributes.output.value` | Output. On LLM spans, the model response. On chain or agent spans, the final answer |
| `attributes.output.mime_type` | Format hint for the output |

LLM message arrays:

| Column | What it contains |
|--------|------------------|
| `attributes.llm.input_messages` | Structured input messages (system, user, assistant, tool). Where chat prompts live |
| `attributes.llm.input_messages.roles` | Roles: `system`, `user`, `assistant`, `tool` |
| `attributes.llm.input_messages.contents` | Message content strings |
| `attributes.llm.output_messages` | Structured messages from the model |
| `attributes.llm.output_messages.contents` | Model response content |
| `attributes.llm.output_messages.tool_calls.function.names` | Tool calls the model requested |
| `attributes.llm.output_messages.tool_calls.function.arguments` | Arguments for those tool calls |

Prompt templates:

| Column | What it contains |
|--------|------------------|
| `attributes.llm.prompt_template.template` | Template with placeholders |
| `attributes.llm.prompt_template.variables` | Template variable values |

Where to look, by kind:

- **LLM:** `attributes.llm.input_messages`, or `attributes.input.value` when the prompt is a single string. `attributes.llm.prompt_template.template` holds the template.
- **Chain or agent:** `attributes.input.value` is usually the user question. The model prompt is on a child LLM span.
- **Tool:** `attributes.input.value` is the tool input and `attributes.output.value` is the tool result. Proposed tool calls can also appear on the parent LLM span under `attributes.llm.output_messages`.

## Model and cost

| Column | Description |
|--------|-------------|
| `attributes.llm.model_name` | Model identifier |
| `attributes.llm.invocation_parameters` | Parameters such as temperature and max tokens |
| `attributes.llm.token_count.prompt` | Input token count |
| `attributes.llm.token_count.completion` | Output token count |
| `attributes.llm.token_count.total` | Total tokens |
| `attributes.llm.cost.prompt` | Input cost in USD |
| `attributes.llm.cost.completion` | Output cost in USD |
| `attributes.llm.cost.total` | Total cost in USD |

## Tool spans

| Column | Description |
|--------|-------------|
| `attributes.tool.name` | Tool or function name |
| `attributes.tool.description` | Tool description |
| `attributes.tool.parameters` | Parameter schema |

A tool call is a span with `attributes.openinference.span.kind = 'TOOL'`, or any span where `attributes.tool.name` is present. For one call, report `context.span_id`, `parent_id`, `name`, `attributes.tool.name`, `attributes.tool.parameters`, `attributes.input.value`, `attributes.output.value`, and the related LLM messages when they are present. If a field is missing on that span, say it is missing.

## Retriever spans

| Column | Description |
|--------|-------------|
| `attributes.retrieval.documents` | Retrieved documents |
| `attributes.retrieval.documents.ids` | Document IDs |
| `attributes.retrieval.documents.scores` | Relevance scores |
| `attributes.retrieval.documents.contents` | Document text |
| `attributes.retrieval.documents.metadatas` | Document metadata |

## Reranker spans

| Column | Description |
|--------|-------------|
| `attributes.reranker.query` | Query being reranked |
| `attributes.reranker.model_name` | Reranker model |
| `attributes.reranker.top_k` | Number of results kept |
| `attributes.reranker.input_documents.*` | Input documents (ids, scores, contents, metadatas) |
| `attributes.reranker.output_documents.*` | Reranked documents |

## Session, user, and metadata

| Column | Description |
|--------|-------------|
| `attributes.session.id` | Session or conversation ID. Groups traces into a multi-turn session |
| `attributes.user.id` | End-user identifier |
| `attributes.metadata.*` | Custom metadata. Any key under this prefix is user-defined and filterable |

## Errors

| Column | Description |
|--------|-------------|
| `attributes.error.type` | Error type on the span |
| `attributes.error.message` | Error message on the span |
| `attributes.exception.type` | Exception class name |
| `attributes.exception.message` | Exception message |
| `events` | Fixed field. Event payloads, including error detail. Use `CONTAINS` when filtering `event.attributes` |
| `status_code` / `status_message` | `ERROR` plus the status message |

Check `status_code`, `attributes.error.type`, and `attributes.error.message` first. If those are empty, check `attributes.exception.*` and `events`. Do not invent an error message when none of these fields contain one.

## Annotations on a span

| Column | Description |
|--------|-------------|
| `annotation.<name>.label` | Label for annotation config `<name>` |
| `annotation.<name>.score` | Numeric score |
| `annotation.<name>.text` | Free-text note |

`<name>` must already be an annotation config in the project space. Reading these columns does not list configs; `list_annotation_configs` does.

## Embeddings

| Column | Description |
|--------|-------------|
| `attributes.embedding.model_name` | Embedding model name |
| `attributes.embedding.texts` | Text chunks that were embedded |

## Filter syntax

`filter` on `list_spans` and `list_traces` is a SQL-like expression over span columns. The same expression language applies to both tools. On `list_traces`, a trace matches when any of its spans matches.

Wrap string values in single quotes. Copy IDs exactly. Do not invent an escape syntax if a value contains a quote; report the tool error.

### Operators

`=`, `!=`, `<`, `<=`, `>`, `>=`, `AND`, `OR`, `IN`, `CONTAINS`, `LIKE`, `IS NULL`, `IS NOT NULL`

### Examples

```
status_code = 'ERROR'
latency_ms > 5000
name = 'ChatCompletion' AND status_code = 'ERROR'
attributes.llm.model_name = 'gpt-4o'
attributes.openinference.span.kind IN ('LLM', 'AGENT')
attributes.openinference.span.kind = 'TOOL'
context.trace_id = 'TRACE_ID'
context.span_id = 'SPAN_ID'
attributes.session.id = 'SESSION_ID'
parent_id IS NULL
attributes.error.type LIKE '%Timeout%'
event.attributes CONTAINS 'TimeoutError'
```

### Tips

- Prefer `IN` over a chain of `OR`.
- Start with `LIKE` or `CONTAINS` for free text, then switch to `=` once the exact value is known.
- Use `CONTAINS` for `event.attributes`. Exact match is unreliable on traceback text.
- A filter error usually means a misspelled column or a string that is not single-quoted. Compare the path with the tables above.
