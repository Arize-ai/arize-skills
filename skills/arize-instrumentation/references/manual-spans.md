# Manual Spans for Tool Use and Agent Loops

Consult this when the app uses LLM tool/function calling and you need to add CHAIN + TOOL spans so tool calls and results appear in the trace.

> **The OpenAI and Anthropic SDK auto-instrumentors trace only the LLM API call — NOT your tool executions or the agent-loop boundary.** If a raw OpenAI- or Anthropic-SDK app runs tools (parses a `tool_use` / tool-call, executes it, feeds the result back on the next call), you **must** create the CHAIN and TOOL spans manually as shown below — otherwise the tool calls, their inputs, and their outputs never appear in the trace; you get only a flat series of LLM API spans. *Framework* instrumentors (LangChain, LangGraph, CrewAI, OpenAI Agents SDK, …) already capture tools and chains, so apps built on those do **not** need manual tool spans.

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

## TypeScript / JavaScript pattern

Get a tracer, then use `startActiveSpan` so tool spans nest as children of the CHAIN span. Span kind uses `SemanticConventions.OPENINFERENCE_SPAN_KIND` + the `OpenInferenceSpanKind` enum; `INPUT_VALUE`/`OUTPUT_VALUE` are direct exports of `@arizeai/openinference-semantic-conventions`.

```typescript
import { trace, SpanStatusCode } from "@opentelemetry/api";
import {
  INPUT_VALUE,
  OUTPUT_VALUE,
  SemanticConventions,
  OpenInferenceSpanKind,
} from "@arizeai/openinference-semantic-conventions";

const tracer = trace.getTracer("my-app");

await tracer.startActiveSpan("run_agent", async (chainSpan) => {
  chainSpan.setAttribute(SemanticConventions.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKind.CHAIN);
  chainSpan.setAttribute(INPUT_VALUE, userMessage);
  // ... LLM call ...
  for (const toolUse of toolUses) {
    await tracer.startActiveSpan(toolUse.name, async (toolSpan) => {
      toolSpan.setAttribute(SemanticConventions.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKind.TOOL);
      toolSpan.setAttribute(INPUT_VALUE, JSON.stringify(toolUse.input));
      const result = await runTool(toolUse.name, toolUse.input);
      toolSpan.setAttribute(OUTPUT_VALUE, JSON.stringify(result));
      toolSpan.setStatus({ code: SpanStatusCode.OK });
      toolSpan.end();
    });
    // ... append tool result to messages, call the LLM again ...
  }
  chainSpan.setAttribute(OUTPUT_VALUE, finalReply);
  chainSpan.setStatus({ code: SpanStatusCode.OK });
  chainSpan.end();
});
```

## Java pattern (annotation-based)

Java manual tracing is **annotation-driven**, not imperative span-building like the others: annotate methods and a ByteBuddy agent creates the spans at class load, auto-capturing parameters as `input.value` and the return value as `output.value`. Deps: `com.arize:openinference-instrumentation-annotation` + `com.arize:openinference-semantic-conventions`. Annotate the agent-loop method `@Chain` (or `@Agent`) and each tool method `@Tool`:

```java
import com.arize.instrumentation.annotation.Agent;
import com.arize.instrumentation.annotation.Chain;
import com.arize.instrumentation.annotation.Tool;
import com.arize.instrumentation.annotation.ExcludeFromSpan;

@Chain(name = "run_agent")                       // CHAIN span; or @Agent for the top-level boundary
public String runAgent(String userMessage) { ... }

@Tool(name = "check_loan_eligibility", description = "Checks eligibility")   // TOOL span
public Map<String, Object> checkLoanEligibility(String applicantId) { ... }
```

`@LLM` marks a model call, `@Agent` a top-level orchestration method; `@ExcludeFromSpan` drops a parameter from `input.value`. Setup requires installing the ByteBuddy agent **before any annotated class loads**, then an `OITracer` registered via `OpenInferenceAgent.register(tracer)` — see [java/annotation/annotation-tracing](https://arize.com/docs/ax/integrations/java/annotation/annotation-tracing) for the exact startup sequence. Annotations only trace on the calling thread; across `CompletableFuture`/executors/reactive frameworks, propagate context explicitly or use the programmatic span API from that doc.

## Go pattern

Go manual-span patterns — the CHAIN/TOOL nesting example, the `WithSession`/`WithUser`/`WithMetadata`/`WithTags`/`WithSuppression` context helpers, and `semconv` constants — live in [go.md](go.md), alongside Go setup and wiring.

See [Manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation) for more span kinds and attributes.
