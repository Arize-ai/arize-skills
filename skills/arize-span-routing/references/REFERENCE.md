# Arize Span Routing Reference

Load this reference when implementing an Arize agent experiment endpoint or existing-provider integration, crossing concurrency boundaries, writing tests, or diagnosing skipped spans.

## Agent experiment endpoints

For an Arize agent experiment endpoint, use the official tracing-context guide for the request contract and distributed parent-context steps:

https://arize.com/docs/ax/improve/agent-tracing-context

That workflow requires both W3C `traceparent` propagation and per-request space/project routing. Follow the guide to extract and attach the incoming parent context, then apply the routing rules below before starting spans. This skill covers routing only; it does not replace parent-context propagation.

The guide describes environment defaults as one possible fallback. For a multi-tenant service, keep this skill's stricter default: missing or invalid routing must not send spans to another destination. Use a fallback only when the user explicitly requests one and confirms that cross-tenant data placement is acceptable.

## Runtime contract

`arize-otel>=0.11.0` exposes:

- `register_with_routing(...)`: creates a provider with one `ArizeRoutingSpanProcessor`.
- `ArizeRoutingSpanProcessor(...)`: attaches dynamic routing to a provider the application already owns.
- `set_routing_context(space_id, project_name)`: attaches both routing values to current OpenTelemetry context.

At span start, the processor copies context values into span attributes:

| Context value | Span attribute | Purpose |
|---|---|---|
| Space ID | `arize.space_id` | Selects destination space and its cached exporter processor |
| Project name | `arize.project.name` | Selects project inside destination space |

At span end, missing `arize.space_id` or `arize.project.name` causes that span to be skipped. One API key is reused for all destination-space exporters.

## Choosing initialization path

### No existing provider

Use `register_with_routing` once, before any instrumentor or LLM client is initialized. Let the app's existing config determine endpoint, transport, batching, and console logging.

### Existing provider

Add `ArizeRoutingSpanProcessor` to the provider. Do not call `trace.set_tracer_provider` again. Preserve unrelated processors, but stop constructing any fixed-destination Arize processor/exporter in the same provider or every routed span may also be copied there.

If the provider is hidden behind a framework integration, inspect its supported processor/exporter extension point. If no supported extension exists, report the integration gap rather than replacing the framework's provider.

### Existing fixed Arize registration

Replace the app's existing `register(space_id=..., project_name=...)` initialization with `register_with_routing(...)` only when every Arize-bound trace from that provider should use routing context. Make this change at initialization, before the global provider is installed. Preserve any unrelated custom processors by attaching them to the returned provider. Remove only fixed-destination arguments and imports made obsolete by this change.

## Mapping rules

The agent-builder platform remains source of truth. Prefer its existing registry, config service, or database lookup. The tracing integration should adapt the result, not own a duplicate routing table.

A valid result contains two non-empty strings:

```python
RoutingTarget(
    space_id="U3BhY2U6...",
    project_name="support-agent",
)
```

Do not confuse:

- Space name with base64 `space_id`
- Project display name with project ID
- Customer/tenant ID with either Arize identifier

If destinations must be resolved through Arize, use the existing authenticated profile without changing it:

```bash
ax spaces list -o json
ax projects list --space SPACE -l 100 -o json
```

Never persist a discovered mapping without user confirmation.

## Missing mapping behavior

Default behavior protects tenant isolation and application availability:

1. Emit a bounded warning containing the metadata field name or stable internal identifier, not sensitive contents.
2. Attach a fresh `opentelemetry.context.Context()` while business logic runs, then detach it in `finally`.
3. Allow the routing processor to skip spans that now have no routing attributes.
4. Do not use a default space or project.

Handle the resolver's documented lookup/configuration exceptions identically. Do not catch broad application exceptions. Merely running outside a new `set_routing_context` is unsafe because ambient context can still contain routing values inherited from an outer request or copied worker context.

Only implement a fallback destination when the user explicitly requests one and confirms that cross-tenant data placement is acceptable.

## Context and concurrency

`set_routing_context` uses OpenTelemetry context and reliably scopes ordinary nested spans. Verify boundaries where execution leaves current context:

- Async tasks created inside current context usually inherit it; test the app's actual task pattern.
- Thread-pool work may require `contextvars.copy_context()` or explicit target propagation.
- Queued/background jobs should carry stable routing input and resolve a fresh target in the worker.
- Detached callbacks must not retain a completed request's target.

Never store current target in a process-global mutable variable.

## Test design

Prefer behavior tests at the app's routing boundary. Avoid testing private `arize-otel` internals.

Required cases:

1. Known agent A resolves to space A/project A.
2. Known agent B resolves to space B/project B.
3. Child spans receive matching `arize.space_id` and `arize.project.name`.
4. Interleaved or concurrent A/B requests keep distinct values.
5. Unknown, incomplete, and empty mappings clear inherited routing and produce no routed export.
6. Expected resolver lookup failure clears inherited routing and does not break business execution.
7. Existing non-Arize processors/exporters remain active, with no fixed Arize export path.
8. Short-lived process flushes before shutdown.

Use an in-memory exporter or a recording processor for unit tests. Mock destination I/O, not the resolver or execution boundary under test.

## Live verification

Use two non-production destinations accessible by the same API key.

1. Emit a unique request/span name for target A.
2. Emit another unique name for target B.
3. Flush the provider when the app is short-lived.
4. Use `arize-trace` to inspect each project using the same credentials used for export.
5. Confirm A appears in A and not B; confirm B appears in B and not A.
6. Exercise unknown metadata and confirm neither destination receives it.

Do not use production spaces for autonomous verification.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Warning says `arize.space_id` is missing | Context not entered before span start, or lost across concurrency boundary | Move context outward or propagate/resolve in worker |
| Project-name warning and skipped span | Resolver returned incomplete target | Require both values before entering context |
| Every request routes to same destination | Fixed `register(...)` setup remains, or mapping ignores request metadata | Inspect initialization and resolver input |
| Traces appear in wrong tenant | Global mutable target, fallback destination, or context leak | Disable fallback; add concurrent isolation test |
| Existing telemetry disappears | Existing provider/exporter was replaced | Restore provider; attach routing processor instead |
| Authentication errors for some spaces | Shared API key lacks access to every target | Use an appropriately authorized key; do not add per-target secrets silently |
| Memory grows with tenants | High-cardinality space IDs create cached processors | Validate bounded space count; open SDK follow-up if eviction is needed |
| Short script emits nothing | Batch processor did not flush | Call `force_flush()` then `shutdown()` |

## Out of scope

- JavaScript/TypeScript parity
- Creating spaces, projects, or API keys
- Post-ingestion movement or historical backfills
- Per-destination API keys
- Arbitrary metadata transformation framework
- Changes to `arize-otel` runtime APIs
