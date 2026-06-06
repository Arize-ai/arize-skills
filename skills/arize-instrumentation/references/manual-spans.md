# Manual Spans for Tool Use and Agent Loops

Consult this when the app uses LLM tool/function calling and you need to add CHAIN + TOOL spans so tool calls and results appear in the trace.

## Why auto-instrumentors don't capture tool execution

**Provider instrumentors (Anthropic, OpenAI, etc.) only wrap the LLM *client* — the code that sends HTTP requests and receives responses.** They see:

- One span per API call: request (messages, system prompt, tools) and response (text, tool_use blocks, etc.).

They **cannot** see what happens *inside your application* after the response:

- **Tool execution** — Your code parses the response, calls `run_tool("check_loan_eligibility", {...})`, and gets a result. That runs in your process; the instrumentor has no hook into your `run_tool()` or the actual tool output. The *next* API call (sending the tool result back) is just another `messages.create` span — the instrumentor doesn't know that the message content is a tool result or what the tool returned.
- **Agent/chain boundary** — The idea of "one user turn → multiple LLM calls + tool calls" is an *application-level* concept. The instrumentor only sees separate API calls; it doesn't know they belong to the same logical "run_agent" run.

So TOOL and CHAIN spans have to be added **manually** (or by a *framework* instrumentor like LangChain/LangGraph that knows about tools and chains). Once you add them, they appear in the same trace as the LLM spans because they use the same TracerProvider.

## Adding manual spans

To avoid sparse traces where tool inputs/outputs are missing:

1. **Detect** agent/tool patterns: a loop that calls the LLM, then runs one or more tools (by name + arguments), then calls the LLM again with tool results.
2. **Add manual spans** using the same TracerProvider (e.g. `opentelemetry.trace.get_tracer(...)` after `register()`):
   - **CHAIN span** — Wrap the full agent run (e.g. `run_agent`): set `openinference.span.kind` = `"CHAIN"`, `input.value` = user message, `output.value` = final reply.
   - **TOOL span** — Wrap each tool invocation: set `openinference.span.kind` = `"TOOL"`, `input.value` = JSON of arguments, `output.value` = JSON of result. Use the tool name as the span name (e.g. `check_loan_eligibility`).

## OpenInference attributes

**Core attributes (all span kinds):**

| Attribute | Use |
|-----------|-----|
| `openinference.span.kind` | Pick the right value: `"LLM"` for raw provider API calls (OpenAI, Anthropic, etc.); `"CHAIN"` for orchestration / agent-loop boundaries; `"TOOL"` for tool/function execution; `"RETRIEVER"` for vector-store / search lookups; `"EMBEDDING"` for embedding API calls; `"AGENT"` for an autonomous sub-agent run nested inside a larger chain; `"RERANKER"` for rerank API calls; `"GUARDRAIL"` for guardrail/policy checks; `"EVALUATOR"` for online eval calls. |
| `input.value` | string (e.g. user message or JSON of tool args) |
| `output.value` | string (e.g. final reply or JSON of tool result) |

**LLM-span attributes (set in addition to the three above for actual LLM calls):**

| Attribute | Use |
|-----------|-----|
| `llm.model_name` | model identifier (e.g. `"gpt-4o-mini"`) |
| `llm.provider` / `llm.system` | provider name (e.g. `"openai"`, `"anthropic"`) |
| `llm.input_messages.{i}.message.role` | `"system"` / `"user"` / `"assistant"` / `"tool"` for the i-th input message |
| `llm.input_messages.{i}.message.content` | text content of the i-th input message |
| `llm.output_messages.{i}.message.role` | role of the i-th output message |
| `llm.output_messages.{i}.message.content` | text content of the i-th output message |
| `llm.token_count.prompt` | int — prompt/input tokens |
| `llm.token_count.completion` | int — completion/output tokens |
| `llm.token_count.total` | int — total tokens |

All three languages expose these names as constants via their respective `openinference-semantic-conventions` packages — `from openinference.semconv.trace import SpanAttributes` in Python, `@arizeai/openinference-semantic-conventions` in TypeScript, and `semconv "github.com/Arize-ai/openinference/go/openinference-semantic-conventions"` in Go (e.g. `semconv.LLMModelName`, `semconv.LLMProvider`, `semconv.LLMTokenCountPrompt`).

## Python pattern

Get the global tracer (same provider as Arize), then use context managers so tool spans are children of the CHAIN span:

```python
from opentelemetry.trace import get_tracer

tracer = get_tracer("my-app", "1.0.0")

# In your agent entrypoint:
with tracer.start_as_current_span("run_agent") as chain_span:
    chain_span.set_attribute("openinference.span.kind", "CHAIN")
    chain_span.set_attribute("input.value", user_message)
    # ... LLM call ...
    for tool_use in tool_uses:
        with tracer.start_as_current_span(tool_use["name"]) as tool_span:
            tool_span.set_attribute("openinference.span.kind", "TOOL")
            tool_span.set_attribute("input.value", json.dumps(tool_use["input"]))
            result = run_tool(tool_use["name"], tool_use["input"])
            tool_span.set_attribute("output.value", result)
        # ... append tool result to messages, call LLM again ...
    chain_span.set_attribute("output.value", final_reply)
```

## Go pattern

Get a tracer from the global TracerProvider (registered via `otel.SetTracerProvider`), then nest spans with `tracer.Start` so tool spans become children of the CHAIN span.

> **Critical for short-lived processes:** never call `log.Fatalf` / `os.Exit` after a span has started — they skip the deferred `tp.Shutdown(ctx)` and the in-flight CHAIN/LLM spans never flush. Use `log.Printf` + `return` from `main` instead, and keep `tp.Shutdown(ctx)` deferred at the top of `main`.

```go
import (
    "context"
    "encoding/json"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/codes"

    semconv "github.com/Arize-ai/openinference/go/openinference-semantic-conventions"
)

var tracer = otel.Tracer("my-app")

func runAgent(ctx context.Context, userMessage string) string {
    ctx, chainSpan := tracer.Start(ctx, "run_agent")
    defer chainSpan.End()
    chainSpan.SetAttributes(
        attribute.String(semconv.OpenInferenceSpanKind, semconv.SpanKindChain),
        attribute.String(semconv.InputValue, userMessage),
    )

    // ... LLM call (auto-instrumented by openaiotel/anthropicotel if used) ...
    for _, toolUse := range toolUses {
        _, toolSpan := tracer.Start(ctx, toolUse.Name)
        argsJSON, err := json.Marshal(toolUse.Input)
        if err != nil {
            toolSpan.RecordError(err)
            toolSpan.SetStatus(codes.Error, err.Error())
        }
        toolSpan.SetAttributes(
            attribute.String(semconv.OpenInferenceSpanKind, semconv.SpanKindTool),
            attribute.String(semconv.InputValue, string(argsJSON)),
        )
        result := runTool(toolUse.Name, toolUse.Input)
        toolSpan.SetAttributes(attribute.String(semconv.OutputValue, result))
        toolSpan.End()
        // ... append tool result to messages, call LLM again ...
    }

    chainSpan.SetAttributes(attribute.String(semconv.OutputValue, finalReply))
    return finalReply
}
```

### Session, user, metadata, tags, suppression (Go)

When the customer asks for session-aware tracing or wants evaluator calls excluded, use the `openinference-instrumentation` package's context helpers — the per-provider instrumentors (openai, anthropic) apply them automatically to every LLM span:

```go
import instrumentation "github.com/Arize-ai/openinference/go/openinference-instrumentation"

ctx = instrumentation.WithSession(ctx, sessionID)
ctx = instrumentation.WithUser(ctx, userID)
ctx = instrumentation.WithMetadata(ctx, metadataJSON)   // caller JSON-encodes the map
ctx = instrumentation.WithTags(ctx, "prod", "canary")
// openai/openai-go:
resp, _ := client.Chat.Completions.New(ctx, params)     // span carries all four
// anthropics/anthropic-sdk-go:
// resp, _ := client.Messages.New(ctx, params)

// Off-trace evaluator calls:
suppressedCtx := instrumentation.WithSuppression(ctx)
_, _ = evalClient.Chat.Completions.New(suppressedCtx, params)   // no span emitted
```

For manual spans you author yourself, call `instrumentation.ApplyContextAttributes(ctx, span)` right after `tracer.Start` to copy the same context attributes onto the span. (These values ride `context.Context` via unexported keys — not OTel baggage — so they do not leak out as `baggage` HTTP headers on downstream calls.)

See [Manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation) for more span kinds and attributes.
