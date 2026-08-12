# Span Column Reference (OpenInference Semantic Conventions)

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
