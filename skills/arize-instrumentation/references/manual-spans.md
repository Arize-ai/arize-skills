# Manual Spans

Consult this when you need spans an auto-instrumentor won't create — tool executions and the agent/chain boundary in a tool loop, or RAG / reranker / guardrail / eval steps — so they appear in the trace with input/output.

> **The OpenAI and Anthropic SDK auto-instrumentors capture the LLM API call — including the model's tool-call *request* (the tool name + arguments it wants) and the tool *definitions* you passed — but NOT the tool's *execution*, its *return value*, or the agent-loop/chain boundary.** So if a raw OpenAI- or Anthropic-SDK app runs tools (parses the `tool_use` / tool-call, executes it, feeds the result back on the next call), you **must** add a TOOL span per execution (to capture the actual result) and a CHAIN span to group the turn — otherwise you get only a flat series of LLM spans with no tool results and no grouping. *Framework* instrumentors (LangChain, LangGraph, CrewAI, OpenAI Agents SDK, …) *typically* capture tools and chains — verify in the matched integration doc before skipping manual spans.

## Why auto-instrumentors miss it

Provider instrumentors wrap only the LLM *client* — they capture each API call's request (messages, tools) and response (text, `tool_use` blocks), but not what your code does next: running `run_tool(...)`, the tool's return value, or the fact that several API calls form one logical turn. Those are application-level, so the TOOL and CHAIN spans are yours to add (a *framework* instrumentor like LangChain/LangGraph adds them for you). Manual spans use the same TracerProvider, so they land in the same trace.

## Adding manual spans

Manual spans capture the parts of a request an auto-instrumentor can't see. The classic case is an agent/tool loop, but the same applies to a **RAG pipeline** (retrieval + embedding), **rerankers**, **guardrails**, and **eval calls** — each is its own span kind (see the span-kind table below).

**Python: prefer decorators.** Decorate the function with the matching kind — `@tracer.chain`, `@tracer.agent`, `@tracer.tool`, `@tracer.llm` — and it auto-captures arguments as `input.value`, the return as `output.value`, and sets the span kind (see the Python pattern below). Only those four decorators exist; for **RETRIEVER, EMBEDDING, RERANKER, GUARDRAIL, EVALUATOR** spans, use the context-manager form (also below) and set `openinference.span.kind` yourself. TS / Java / Go: use the patterns below.

Every manual span sets `openinference.span.kind`, `input.value`, and `output.value`; pick the kind from the table below. Common shapes:

- **Agent / tool loop:** a CHAIN (or AGENT) span for the turn; a TOOL span per tool execution (args → `input.value`, result → `output.value`).
- **RAG:** a CHAIN for the query; a RETRIEVER span for the vector lookup (query → `input.value`, retrieved chunks → `retrieval.documents.*`, and `output.value` for a readable summary); an EMBEDDING span if you embed the query yourself; then the LLM generation span (auto-instrumented if the client has an instrumentor). Add a RERANKER span if you rerank retrieved docs.

## OpenInference attributes

**Core attributes (all span kinds):**

| Attribute | Use |
|-----------|-----|
| `openinference.span.kind` | Pick the right value: `"LLM"` for raw provider API calls (OpenAI, Anthropic, etc.); `"CHAIN"` for orchestration / agent-loop boundaries; `"TOOL"` for tool/function execution; `"RETRIEVER"` for vector-store / search lookups; `"EMBEDDING"` for embedding API calls; `"AGENT"` for an autonomous sub-agent run nested inside a larger chain; `"RERANKER"` for rerank API calls; `"GUARDRAIL"` for guardrail/policy checks; `"EVALUATOR"` for online eval calls. |
| `input.value` | string (e.g. user message or JSON of tool args) |
| `output.value` | string (e.g. final reply or JSON of tool result) |
| span **status** | The OTel span status (not an OI attribute): set `OK` on success, and `ERROR` + record the exception on failure so failed spans surface in Arize. Python `span.set_status(StatusCode.ERROR)` + `span.record_exception(e)`; TS `span.setStatus({ code: SpanStatusCode.ERROR })`; Go `span.SetStatus(codes.Error, err.Error())` + `span.RecordError(err)`. The `@tracer.*` decorators set this automatically. |

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

**TOOL-span attributes (set with the kind + the three core attributes; `input.value` = call args, `output.value` = tool result):**

| Attribute | Use |
|-----------|-----|
| `tool.name` | tool name, e.g. `"check_loan_eligibility"` (also use as the span name) |
| `tool.description` | what the tool does |
| `tool.parameters` | JSON schema of the tool's parameters |
| `tool.id` | id linking this execution to the model's `tool_call.id`, when available |

The model's *request* to call a tool is captured by the provider instrumentor on the LLM span's output message as `message.tool_calls.{i}.tool_call.function.name` and `.tool_call.function.arguments`; your manual TOOL span records the *execution and result*.

**RAG / retrieval-span attributes (RETRIEVER, EMBEDDING, RERANKER — set with the kind + the three core attributes):**

| Attribute | Use |
|-----------|-----|
| `retrieval.documents.{i}.document.content` | content of the i-th retrieved document (RETRIEVER) |
| `retrieval.documents.{i}.document.id` | id of the i-th document |
| `retrieval.documents.{i}.document.score` | relevance score of the i-th document |
| `retrieval.documents.{i}.document.metadata` | JSON metadata for the i-th document |
| `embedding.model_name` | embedding model, e.g. `"text-embedding-3-small"` (EMBEDDING) |
| `embedding.embeddings.{i}.embedding.text` | text embedded |
| `embedding.embeddings.{i}.embedding.vector` | the embedding vector |
| `reranker.query` / `reranker.model_name` / `reranker.top_k` | rerank query, model, and K (RERANKER) |
| `reranker.input_documents` / `reranker.output_documents` | documents in/out of the reranker |

Python, TypeScript, and Go expose these names as constants via their respective `openinference-semantic-conventions` packages — `from openinference.semconv.trace import SpanAttributes` in Python, `@arizeai/openinference-semantic-conventions` in TypeScript, and `semconv "github.com/Arize-ai/openinference/go/openinference-semantic-conventions"` in Go (e.g. `semconv.LLMModelName`, `semconv.LLMProvider`, `semconv.LLMTokenCountPrompt`). Java sets them via annotations (see below), not these constants.

## Python pattern

**Prefer decorators where possible.** Wrap the Arize tracer provider in an `OITracer`, then decorate your agent/chain and tool functions with `@tracer.agent` / `@tracer.chain` / `@tracer.tool` / `@tracer.llm`. Each decorator auto-captures the function arguments as `input.value`, the return value as `output.value`, and sets the span kind; `@tracer.tool` also reads the name, docstring, and signature for the tool's name/description/parameters. Nesting follows the call graph automatically — a tool called inside an `@tracer.agent` function becomes a child TOOL span. See [manual instrumentation → decorators](https://arize.com/docs/ax/instrument/manual-instrumentation#use-decorators) for the current API.

```python
from arize.otel import register
from openinference.instrumentation import OITracer, TraceConfig

tracer_provider = register(project_name="my-app")   # space_id / api_key read from env
tracer = OITracer(tracer_provider.get_tracer(__name__), config=TraceConfig())

@tracer.tool
def get_stock_price(symbol: str, currency: str = "USD") -> str:
    """Look up the current price for a ticker symbol."""    # -> tool description on the span
    return fetch_price(symbol, currency)

@tracer.agent                # use @tracer.chain for a non-agentic pipeline step
def run_agent(user_message: str) -> str:
    # ... LLM call; call get_stock_price(...) etc. — the TOOL span nests automatically ...
    return final_reply
```

**Context-manager alternative** — use this when you can't decorate a function: a tool dispatched dynamically by name in a loop, or a span kind with no decorator (RETRIEVER, EMBEDDING, etc.). (For `session.id`, use `using_session` — see [session-tracking.md](session-tracking.md) — not a wrapper span.) Tool spans nest as children of the CHAIN span:

```python
from opentelemetry.trace import get_tracer

tracer = get_tracer("my-app")

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
