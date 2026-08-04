# Session tracking (`session.id`) and flushing

Consult this when the user wants multi-turn session tracking, or when spans emit locally but never reach Arize from a short-lived process.

## Emitting `session.id` for multi-turn session tracking

For session-level evaluations in Arize (e.g. the `{conversation}` template variable in `arize-evaluator`), spans must carry a `session.id` attribute. **The recommended way is the `using_session` context manager — it sets `session.id` on the OpenTelemetry Context so every span created inside the block, including auto-instrumented LLM spans, picks it up. Do NOT hand-roll a CHAIN span just to attach `session.id`.**

**Python:**

```python
from openinference.instrumentation import using_session

with using_session(session_id=session_id):
    # every span here — including auto-instrumented OpenAI/LiteLLM/etc. spans —
    # gets attribute session.id = session_id
    answer = your_llm_call(question)
```

**TypeScript / JavaScript:**

```typescript
import { context } from "@opentelemetry/api";
import { setSession } from "@arizeai/openinference-core";

context.with(setSession(context.active(), { sessionId }), () => {
  // spans created here carry session.id
});
```

**Go:** `ctx = instrumentation.WithSession(ctx, sessionID)` (from `openinference-instrumentation`) — the provider instrumentors apply it to every LLM span automatically. See [go.md](go.md).

Generate `session_id` once per conversation and open the block from the caller:

```python
import uuid
session_id = str(uuid.uuid4())  # once per conversation, not per turn

for user_message in conversation:
    with using_session(session_id=session_id):
        reply = chat(user_message)
```

Rules:
- **Same `session_id` for every turn in one conversation** — all spans share it so Arize groups them.
- **New `session_id` when a fresh conversation starts** — a new UUID per session, not per turn.
- **The caller owns the session boundary** (request handler, notebook cell, app frontend) — open the `using_session` block there.

**Direct attribute (fallback):** if you're already authoring a manual span (not relying on auto-instrumentation), set it on that span instead of using the context manager — `span.set_attribute("session.id", session_id)`. The attribute key is `session.id`.

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
1. Is the LLM call wrapped in `using_session(...)` (Python) / `setSession` (TS) / `WithSession` (Go), or `session.id` set on your manual span?
2. Is the same `session_id` passed to every turn in the conversation?
3. Was `force_flush()` called after the conversation ended?
4. Did you wait ~30 seconds for ingestion before checking the Arize UI?
