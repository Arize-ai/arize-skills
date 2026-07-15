---
name: arize-instrumentation
description: Adds Arize AX tracing to an LLM application for the first time. Detects the stack, routes to the single matching integration doc, wires auto-instrumentation after user confirmation, and verifies traces land. Use when the user wants to instrument their app, add tracing from scratch, set up LLM observability, integrate OpenTelemetry or openinference, or get started with Arize tracing.
metadata:
  author: arize
  version: "2.0"
---

# Arize Instrumentation Skill

Add **Arize AX tracing** to an app for the first time: **detect the stack → fetch the one matching integration doc → wire auto-instrumentation → verify a trace lands.**

**Route locally.** Map the detected stack to a single doc page via [references/integration-routing.md](references/integration-routing.md) (exhaustive for tracing integrations) and fetch **only that page**. If the stack isn't listed there, it has no dedicated integration — use [manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation). Never bulk-fetch the [PROMPT.md](https://arize.com/docs/PROMPT.md)/[llms.txt](https://arize.com/docs/llms.txt) aggregates.

**Rules:** inspect before mutating; tracing is additive, never change business logic; follow existing style; no secrets in code (reference `ARIZE_API_KEY`/`ARIZE_SPACE_ID` env vars only); ask before persistent local state (`ax` profiles, `.zshrc`, env vars) — see [references/ax-profiles.md](references/ax-profiles.md).

## Phase 1: Analysis (read-only — no code/files)

Detect from manifests + imports: language, package manager, LLM providers, frameworks, existing tracing (`TracerProvider`, `register()`, `ARIZE_*`/`OTEL_*`, Datadog/Honeycomb), and whether the app runs tools / an agent loop (manual CHAIN/TOOL spans only if the matched framework instrumentor doesn't already cover them — decided in Phase 2). **Confirm scope first** — a monorepo, multiple services, or multiple frameworks needs a "which one?" question before touching anything; don't pick for the user.

Output a short summary (stack, proposed integration, existing tracing, scope). If the target is clear and the user asked to instrument now, continue; if ambiguous or analysis-only was requested, stop and confirm.

## Phase 2: Implementation (after the target is confirmed)

1. **Fetch the matched integration doc** and follow its install + wiring verbatim.
2. **Install** with the detected package manager, before writing code — exact packages come from the matched doc. Python base: `arize-otel` (latest **0.13.0**, verify on PyPI) + `openinference-instrumentation-{name}` (package hyphens, import underscores). TS/JS: `@opentelemetry/sdk-trace-node` + the matched `@arizeai/openinference-*` (or a first-party exporter, e.g. Mastra's `@mastra/arize`). Go has **no integration doc** — see [references/go.md](references/go.md) for install, wiring, flush, and manual spans.
3. **Credentials** — app needs an API key + Space. Inspect only the target app's own config; never scan sibling repos/shell files, surface secrets, or accept a pasted key. See [references/credentials-and-config.md](references/credentials-and-config.md) and [references/ax-profiles.md](references/ax-profiles.md).
4. **Centralize** init in one module, **before** any LLM client is created. Existing OTel → add Arize as an *additional* exporter; don't replace it.

**Auto vs manual:** prefer the auto-instrumentor — do **not** hand-roll spans it already covers (duplicates spans, drifts from semconv). Add manual spans only for logic no instrumentor sees, or when the stack has no instrumentor at all. **The OpenAI and Anthropic SDK instrumentors capture the LLM call — including the model's tool-call request (name + args) — but NOT the tool's execution, its return value, or the agent/chain boundary. A raw-SDK app with its own tool-calling loop MUST add a manual TOOL span per execution (to capture the result) and a CHAIN span to group the turn**, or those never appear. Framework instrumentors (LangChain/LangGraph/OpenAI Agents SDK) *typically* cover tools and chains — verify in the matched doc before skipping manual spans. Keep `register()`/`arize-otel-go` for setup; see [references/manual-spans.md](references/manual-spans.md) and [manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation).

**Cross-cutting (every stack):**
- **Project name is required** — missing it → HTTP 500 (`service.name` alone fails). Set as a resource attribute: Python `register(project_name=…)`; TS `SEMRESATTRS_PROJECT_NAME`/`model_id`; Go `Options{ProjectName}` or `openinference.project.name`.
- **Don't hand-roll a `TracerProvider`/exporter** — use `register()`/`arize-otel-go`; raw OTel only when integrating an existing provider.
- **Order:** register tracer → instrumentors → clients.
- **Flush before exit** (CLI/scripts/notebooks) or async exports drop: Python `force_flush()`+`shutdown()`, TS `shutdown()`, Go `defer tp.Shutdown(ctx)` (never `log.Fatalf`/`os.Exit` mid-span). See [references/session-tracking.md](references/session-tracking.md) (also covers `session.id` for multi-turn).
- **Never silently override** the app's project/space/IDs/endpoint — surface mismatches.

## Verification

Done only when: app builds/typechecks, starts with tracing, emits ≥1 real request, and you confirm the trace in Arize **or** give a precise app-vs-Arize blocker. Trigger an LLM call, then use the **`arize-trace`** skill to confirm spans (kind, `input.value`/`output.value`, parent-child; CHAIN+TOOL if tools run). No traces → check `ARIZE_SPACE_ID`/`ARIZE_API_KEY`, init order, `otlp.arize.com:443`, exporter logs (`GRPC_VERBOSITY=debug`); common causes: missing project name (500), unflushed short-lived process, or export/verify **credential-context mismatch** (report it, don't rewrite config — [references/credentials-and-config.md](references/credentials-and-config.md)).

## After a confirmed trace

Emit milestones (install → wiring → run → export → verify); mark recovered errors resolved; end separating done from blockers. Then briefly offer the next step: **`arize-trace`** (inspect/debug), **`arize-dataset`** (curate), **`arize-evaluator`** (evals), **`arize-experiment`** (compare), **`arize-prompt-optimization`** (improve prompt). Quality issues → **`arize-trace`** first.

## References

[integration-routing](references/integration-routing.md) (the router) · [credentials-and-config](references/credentials-and-config.md) · [ax-profiles](references/ax-profiles.md) · [manual-spans](references/manual-spans.md) · [go](references/go.md) (Go — no doc page exists) · [session-tracking](references/session-tracking.md) · [tracing-assistant-mcp](references/tracing-assistant-mcp.md).
