# Go instrumentation

Go has **no per-integration doc page** — this file is the source of truth. Go uses [`arize-otel-go`](https://github.com/Arize-ai/arize-otel-go) for exporter setup plus a per-provider auto-instrumentor (OpenAI, Anthropic), or manual spans for clients without one. Module floor: Go 1.25 (the openinference Go modules require it; `arize-otel-go` itself is 1.23+).

## Install

```
go get github.com/Arize-ai/arize-otel-go
go get github.com/Arize-ai/openinference/go/openinference-semantic-conventions
go get github.com/Arize-ai/openinference/go/openinference-instrumentation
# Plus exactly one per-provider instrumentor, matched to the detected client:
go get github.com/Arize-ai/openinference/go/openinference-instrumentation-openai-go        # openai/openai-go
go get github.com/Arize-ai/openinference/go/openinference-instrumentation-anthropic-sdk-go # anthropics/anthropic-sdk-go v1.43+
```

## Setup & wiring

`Register` once, before creating clients. It reads `ARIZE_SPACE_ID` / `ARIZE_API_KEY` / `ARIZE_PROJECT_NAME` / `ARIZE_COLLECTOR_ENDPOINT` from env when the matching `Options` fields are unset, and sets the required `openinference.project.name` resource attribute (avoids the HTTP 500). EU: `Endpoint: arizeotel.EndpointArizeEurope`.

```go
tp, err := arizeotel.Register(ctx, arizeotel.Options{ProjectName: "my-app"})
if err != nil { log.Printf("register tracer: %v", err); return }
defer func() {
    shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    _ = tp.Shutdown(shutdownCtx)
}()
```

Attach the instrumentor as client middleware:

```go
// openai/openai-go:
client := openai.NewClient(
    option.WithAPIKey(os.Getenv("OPENAI_API_KEY")),
    option.WithMiddleware(openaiotel.Middleware(otel.Tracer("my-app"))),
)
// anthropics/anthropic-sdk-go:
client := anthropic.NewClient(
    option.WithMiddleware(anthropicotel.Middleware(otel.Tracer("my-app"))),
)
```

Both instrumentors expose `WithTraceConfig(instrumentation.TraceConfig{...})` for in-code overrides of the `OPENINFERENCE_HIDE_*` masking env config.

## Cross-cutting rules

- **Project name** — handled by `Register` (sets `openinference.project.name` + `service.name`). If you wire `sdktrace.NewTracerProvider` directly instead (multi-exporter / on-prem collector), pass `attribute.String("openinference.project.name", "my-app")` to `resource.New(...)`.
- **Order:** `Register` → attach middleware → create clients.
- **Flush before exit (critical for CLI / short-lived):** keep `defer tp.Shutdown(ctx)` at the top of `main`, and **never call `log.Fatalf` / `os.Exit` after a span has started** — they skip the deferred shutdown and in-flight spans never flush. Use `log.Printf` + `return`.
- **Existing OTel:** add Arize as an additional exporter on the existing `TracerProvider` rather than replacing it.

## Manual spans (agent loops / tools / clients with no instrumentor)

Provider instrumentors wrap only the LLM client — one span per API call. Tool execution and the agent/chain boundary happen in your code and need manual spans. A client with no instrumentor also needs manual spans, built from [`openinference-semantic-conventions`](https://github.com/Arize-ai/openinference/tree/main/go/openinference-semantic-conventions) constants (`semconv.OpenInferenceSpanKind`, `semconv.SpanKindChain`/`SpanKindTool`, `semconv.InputValue`, `semconv.OutputValue`, `semconv.LLMModelName`, …).

Nest spans with `tracer.Start` so tool spans become children of the CHAIN span:

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

### Session, user, metadata, tags, suppression

For session-aware tracing or to exclude evaluator calls, use the `openinference-instrumentation` package's context helpers — the per-provider instrumentors apply them automatically to every LLM span:

```go
import instrumentation "github.com/Arize-ai/openinference/go/openinference-instrumentation"

ctx = instrumentation.WithSession(ctx, sessionID)
ctx = instrumentation.WithUser(ctx, userID)
ctx = instrumentation.WithMetadata(ctx, metadataJSON)   // caller JSON-encodes the map
ctx = instrumentation.WithTags(ctx, "prod", "canary")
resp, _ := client.Chat.Completions.New(ctx, params)     // span carries all four

// Off-trace evaluator calls:
suppressedCtx := instrumentation.WithSuppression(ctx)
_, _ = evalClient.Chat.Completions.New(suppressedCtx, params)   // no span emitted
```

For manual spans you author yourself, call `instrumentation.ApplyContextAttributes(ctx, span)` right after `tracer.Start` to copy these onto the span. (Values ride `context.Context` via unexported keys — not OTel baggage — so they don't leak as `baggage` HTTP headers downstream.)

See the cross-language attribute table in [manual-spans.md](manual-spans.md) and [Manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation) for more span kinds.
