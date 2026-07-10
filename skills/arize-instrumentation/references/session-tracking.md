# Session tracking (`session.id`) and flushing

Consult this when the user wants multi-turn session tracking, or when spans emit locally but never reach Arize from a short-lived process.

## Emitting `session.id` for multi-turn session tracking

For session-level evaluations in Arize (e.g. the `{conversation}` template variable in `arize-evaluator`), spans must carry `attributes.session.id`.

**Pattern (Python / OpenTelemetry):**

```python
from typing import Optional
import uuid

def chat(question: str, session_id: str, chat_history: Optional[list] = None) -> str:
    with tracer.start_as_current_span("chat") as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("input.value", question)
        span.set_attribute("session.id", session_id)
        answer = your_llm_call(question)  # replace with the actual LLM call
        span.set_attribute("output.value", answer)
        return answer
```

Generate `session_id` once per conversation and pass it in from the caller:

```python
session_id = str(uuid.uuid4())  # generate once per conversation, not per turn

for user_message in conversation:
    reply = chat(user_message, session_id=session_id)
```

Rules:
- **Same `session_id` for every turn in one conversation.** Each call produces its own span, but all spans share the same `session_id` so Arize groups them.
- **New `session_id` when a fresh conversation starts.** Generate a new UUID at the start of each session, not at each turn.
- **Pass `session_id` in from the caller** — the caller (request handler, notebook cell, app frontend) owns the session boundary.

**Auto-instrumentation note:** If using OpenInference auto-instrumentation (e.g. for LiteLLM or OpenAI), you do not control span creation directly. Wrap the LLM call in a manually-created CHAIN span and set `session.id` there — the auto-instrumented LLM spans will nest under it as children. (Go: use `instrumentation.WithSession(ctx, sessionID)` — the provider instrumentors apply it automatically. See references/manual-spans.md.)

## Flushing spans (Jupyter notebooks and short-lived scripts)

The OTLP batch exporter holds spans in memory and ships them on a timer or when the buffer fills. In a Jupyter notebook or short-lived script the process may end before the buffer flushes — spans emit correctly locally but never reach Arize.

Call `force_flush()` after finishing a conversation you want to inspect:

```python
tracer_provider.force_flush()   # ships buffered spans immediately
```

Call `shutdown()` only when done tracing entirely — it closes the exporter and cannot be reversed without re-initializing:

```python
tracer_provider.force_flush()
tracer_provider.shutdown()
```

(TS: `provider.shutdown()`; Go: keep `defer tp.Shutdown(ctx)` and never call `log.Fatalf`/`os.Exit` after a span has started, or in-flight spans are dropped.)

## Checklist before debugging missing session data in Arize
1. Is `session.id` set on the CHAIN span? If using auto-instrumentation, wrap the LLM call in a manual CHAIN span and set it there.
2. Is the same `session_id` passed to every turn in the conversation?
3. Was `force_flush()` called after the conversation ended?
4. Did you wait ~30 seconds for ingestion before checking the Arize UI?
