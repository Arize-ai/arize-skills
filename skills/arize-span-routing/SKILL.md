---
name: arize-span-routing
description: Routes Python OpenTelemetry spans from custom agent builders or multi-tenant applications to different Arize spaces and projects using application metadata. Use when one service must dynamically select an Arize destination per agent, tenant, team, or request, or when the user mentions register_with_routing, set_routing_context, multi-space tracing, or custom span routing.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires Python, arize-otel 0.11.0 or newer, and one Arize API key authorized for every destination space.
---

# Arize Span Routing Skill

Use this skill to add dynamic, pre-export routing to a Python application. Each traced operation must resolve to exactly one Arize `space_id` and `project_name` before its first span starts.

Do not use this skill for ordinary single-project tracing; use `arize-instrumentation`. This skill does not reroute spans after export, backfill historical spans, create Arize spaces/projects, or invent a customer-specific metadata mapping.

## Safety rules

- Never guess a destination or silently use another tenant's destination.
- Never embed API keys in code or ask users to paste keys into chat. Read `ARIZE_API_KEY` from the environment.
- Preserve existing non-Arize exporters and processors. Remove or replace a fixed-destination Arize export path so routed spans are not also copied to that destination.
- Missing, invalid, or unavailable routing metadata must leave the business operation running but its spans unexported to Arize. Run that operation under a fresh OpenTelemetry context so stale routing values cannot leak across tenants. Log a warning without including secrets or sensitive metadata values.
- Use one API key that is authorized for every destination space. Stop and report a credential blocker if that is not true.

## Phase 1: Inspect and define the contract

Read only until the routing contract is clear.

1. Identify the exact Python service and entrypoint to change.
2. Find current tracing initialization, provider/exporters, instrumentors, and client creation order.
3. Find the request or agent-execution boundary that owns destination metadata.
4. Identify the stable metadata field(s) and existing source of truth that resolve to:
   - Arize `space_id`
   - Arize `project_name`
5. Check async tasks, thread pools, queues, or background workers that may outlive the request context.
6. Find the app's test command and existing test style.

Inspect only the target app's configuration. Do not search unrelated repositories, sibling services, shell startup files, or arbitrary `.env` files for credentials.

If service scope, metadata fields, mapping source, or destination behavior is ambiguous, stop and ask the minimum question needed. Do not install packages or edit code first. If the user requested implementation and all four are clear, summarize the contract briefly and continue.

## Phase 2: Implement

### 1. Ensure routing support exists

Use the project's package manager to require `arize-otel>=0.11.0`. Do not change unrelated dependencies.

### 2. Initialize routing once

For an app without an existing OpenTelemetry provider, initialize routing before instrumentors and LLM clients:

```python
import os

from arize.otel import register_with_routing

tracer_provider = register_with_routing(
    api_key=os.environ["ARIZE_API_KEY"],
)
```

If the app already owns a provider with non-Arize telemetry, keep it and add the routing processor:

```python
import os

from arize.otel import ArizeRoutingSpanProcessor, Endpoint, Transport

tracer_provider.add_span_processor(
    ArizeRoutingSpanProcessor(
        api_key=os.environ["ARIZE_API_KEY"],
        endpoint=Endpoint.ARIZE,
        transport=Transport.GRPC,
    )
)
```

Reuse the app's configured endpoint and transport when present. Never call `register_with_routing` after another global provider has already been installed. If the provider also has a fixed Arize processor/exporter, remove that fixed path in its initialization before adding routing; OpenTelemetry processors cannot be safely removed after startup.

### 3. Resolve one routing target

Adapt the app's existing metadata model; do not introduce a framework for one lookup. The resolver must return both non-empty values or no target. Keep mapping data in its existing source of truth rather than duplicating it in tracing code.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingTarget:
    space_id: str
    project_name: str
```

Use this type only when the codebase lacks an equivalent. Validate the result before any traced work begins.

### 4. Set context around the complete operation

Enter routing context at the highest boundary that has the metadata and encloses every child span:

Replace `RoutingLookupError` below with the resolver's specific existing lookup/configuration exception.

```python
from opentelemetry import context as context_api
from arize.otel import set_routing_context


def run_without_arize_routing(request):
    token = context_api.attach(context_api.Context())
    try:
        return run_agent(request)
    finally:
        context_api.detach(token)


def handle_agent_request(request):
    try:
        target = resolve_routing_target(request.agent_metadata)
    except RoutingLookupError:
        logger.warning("Arize routing lookup failed; spans will not be exported")
        return run_without_arize_routing(request)

    if target is None or not target.space_id or not target.project_name:
        logger.warning("No Arize routing target; spans will not be exported")
        return run_without_arize_routing(request)

    with set_routing_context(
        space_id=target.space_id,
        project_name=target.project_name,
    ):
        return run_agent(request)
```

Catch only the resolver's expected lookup/configuration exceptions; do not hide unrelated application failures. A fresh context on the no-target path intentionally prevents inherited routing values from reaching Arize. It may start a new trace for other exporters; tenant isolation takes priority. If preserving the distributed parent is mandatory, report the missing public routing-clear API as an SDK follow-up rather than using private context keys.

All auto-instrumented and manual child spans created inside the routing context inherit `arize.space_id` and `arize.project.name`. Do not set routing after spans have started.

For background work, propagate the OpenTelemetry context explicitly or resolve and enter a new routing context in the worker. Never rely on request-local context after a queue or thread boundary.

See `references/REFERENCE.md` for existing-provider details, concurrency rules, testing, verification, and troubleshooting.

## Verification

1. Run focused unit tests for the resolver and execution boundary.
2. Prove two different metadata values produce two different space/project pairs.
3. Prove child spans inherit the selected pair.
4. Prove concurrent operations cannot leak routing context.
5. Prove unknown metadata and resolver failures clear inherited routing, export no spans to any fallback destination, and leave business logic running.
6. Prove pre-existing non-Arize exporters/processors remain attached and no fixed Arize path remains.
7. Trigger one uniquely named trace per target in non-production spaces.
8. Use `arize-trace` with the same credential context to confirm each trace exists only in its intended destination.

For short-lived scripts, call `force_flush()` and `shutdown()` before exit. Finish as **confirmed**, **confirmed with warnings**, or a precise blocker; never report completion from unit tests alone when live verification was requested.

## Guardrails and limits

- Both routing values are required. Spans missing either value are skipped.
- `ArizeRoutingSpanProcessor` creates and caches one processor per unique space. Flag unbounded or high-cardinality space IDs before implementation.
- Routing selects spaces and projects only; other customer metadata still belongs in normal OpenInference attributes.
- If dogfooding exposes a missing `arize-otel` capability, stop and propose a separate SDK change instead of adding a compatibility hack.

## Related skills

- `arize-instrumentation`: first-time or single-destination tracing
- `arize-trace`: post-export verification and debugging
- `arize-admin`: inspect or manage authorized spaces and API keys
