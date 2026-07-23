# Verification

Use this reference after adding or changing instrumentation. It keeps trace-arrival verification deterministic and separates one-trace smoke checks from broader instrumentation-health audits.

## Deterministic trace lookup

Do not probe `ax` by trial and error. Follow this fixed sequence, and lean on the `arize-trace` skill for export/inspection details so you do not rediscover flags:

1. Run the app and trigger at least one LLM call or real request. Capture the project name and, if the app logs it, the trace ID from runtime logs or exported span context.
2. Prefer resolving the project to its base64 project ID once. `ax spans export` can use a project name, but the ID is faster and avoids ambiguity when names or spaces overlap.
3. Prefer a targeted lookup by trace ID, verifying against the same credential context the app exported to: same space, endpoint, and project.
4. Trace-ID lookups are immediately consistent once the trace is ingested. If the trace is not found after a few seconds, treat it as an emission/flush problem first, not index lag.

Treat known CLI quirks as expected, not bugs to debug: non-JSON banner/notice lines mixed into stdout, and the default `-l` 500-span cap.

## Emission vs. rejection

If no traces arrive, inspect app/runtime exporter logs to tell local emission from remote rejection. Use `GRPC_VERBOSITY=debug` or pass `log_to_console=True` to `register()` when that is available.

The common causes are:

- Missing project-name resource attribute: Arize rejects spans with HTTP 500 when the project name is missing. `service.name` alone is not enough.
- CLI/script process exits before the exporter flushes: call `provider.force_flush()` then `provider.shutdown()` for Python/TypeScript, or `tp.Shutdown(ctx)` for Go before exit.
- CLI-visible space/project disagrees with the collector-targeted space ID: report the mismatch instead of silently rewriting credentials.

## Classified blockers

If verification still fails, classify the cause and stop. Do not continue with unrelated probes. Use one of:

- **no local span emission** - exporter logs show nothing sent.
- **credential / project resolution** - wrong space, wrong endpoint, missing project, or ambiguous project name/ID context.
- **indexing delay** - emitted and accepted, but not queryable yet.
- **network** - cannot reach `otlp.arize.com:443`.
- **collector rejection** - remote reject, commonly missing project-name resource attribute.

Report: app instrumentation status, latest local trace/run ID when available, whether exporter logs show local emission, and which blocker class applies.

## Post-arrival smoke check

A trace can arrive and still be too sparse to be useful. After confirming arrival, run only a smoke check on the emitted trace before declaring success. This is not a full instrumentation-health audit. For the newly instrumented request/run, check:

1. **Semantic entrypoint:** when the app has a request/response boundary, the root or intended entrypoint span has `input.value`, `output.value`, and final status when known.
2. **Expected structure:** the flow contains the expected high-level span kinds, such as `AGENT`/`CHAIN`, `LLM`, and `TOOL` for an agent/tool flow.
3. **Local tool visibility:** tool spans carry tool input and output when the app runs local tools.
4. **Parent-child shape:** the trace tree is readable and the main agent/chain -> LLM/tool relationships are intact.
5. **Error status:** when a manual span wraps an operation that can fail (e.g. a tool that raised), a failure surfaces as an `ERROR` span with the exception recorded — not a silently `OK`/`UNSET` span.

Report both arrival and smoke-check status. If any smoke check fails, end with **confirmed with warnings**: list each warning and attribute its likely cause - **skill wiring** (fix here), **app code**, **framework/instrumentor limitation**, or **product/UI behavior** - then give the next fix step. Do not bury warnings under a generic success message.

For broader or repeated quality concerns - missing token counts across many traces, uncategorized spans, flat structures, orphaned spans, duplicate LLM spans, blank semantic roots, or project-wide health questions - hand off to `arize-instrumentation-health` when that skill is available. Otherwise stop at the smoke-check findings and say a full health audit is outside `arize-instrumentation`'s scope.
