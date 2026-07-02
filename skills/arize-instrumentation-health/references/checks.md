# Instrumentation health checks

Deterministic checks over an exported span sample grouped by trace. Each check has a **trigger** (when to flag), a **guardrail** (when to downgrade confidence because a benign cause is plausible), and a **fix direction**. Report a finding as high confidence only when the trigger fires and the guardrail does not apply.

## Span-kind classification precedence

When a check needs a span's kind, classify in this order and stop at the first match:

1. Customer-provided mapping (explicit source mapping in the project).
2. `openinference.span.kind` attribute (`LLM`, `AGENT`, `CHAIN`, `TOOL`, `RETRIEVER`, `EMBEDDING`, `RERANKER`, `GUARDRAIL`, `EVALUATOR`).
3. OTel GenAI attributes (`gen_ai.*`).
4. Arize built-in mappings.
5. Otherwise **unclassified**.

## Severity

- **critical** — breaks a core Arize workflow (evals, conversation view, cost/token dashboards, trace navigation) for most traces.
- **warning** — degrades usefulness for many traces; fixable in app code.
- **advisory** — a signal worth noting but plausibly intentional or low-impact.

## Checks

### 1. Orphaned spans
- **Trigger:** more than 5% of spans have a `parent_id`/`parent_span_id` with no matching parent span in the same exported trace.
- **Guardrail:** do not flag high-confidence when partial export, sampling, retention, or cross-service trace fragmentation plausibly explains the missing parents.
- **Fix direction:** preserve context across async tasks, threads, and service boundaries.
- **Min data:** ≥5 traces.

### 2. Flat trace structure
- **Trigger:** more than 80% of multi-span traces have depth 1 in a known multi-step framework or agent workflow.
- **Guardrail:** require framework or multi-step evidence — raw OTel flat traces can be intentional.
- **Fix direction:** initialize tracing and instrumentors **before** app imports and client initialization.

### 3. Uncategorized spans
- **Trigger:** fewer than 50% of spans classify to a known span kind (see precedence above).
- **Guardrail:** none beyond the classification precedence itself.
- **Fix direction:** add semantic attributes or configure source mappings.
- **Min data:** ≥5 traces.

### 4. Repeated span names
- **Trigger:** the top 3 span names account for more than 95% of spans, and the average trace has more than 3 spans.
- **Guardrail:** only warn when traces appear multi-step.
- **Fix direction:** give logical steps unique, descriptive span names.

### 5. Blank root input/output
- **Trigger:** more than 60% of root spans are missing `input.value` or `output.value`.
- **Guardrail:** root span only — child LLM I/O does not satisfy this check.
- **Fix direction:** set end-to-end user input and final response on the root span.

### 6. Root status unset
- **Trigger:** more than 80% of root spans are null/`UNSET` **and** there is impact evidence (child `ERROR` spans, or status-based eval/filter usage).
- **Guardrail:** if no impact signal exists, report as **advisory**.
- **Fix direction:** set root status to the final request outcome (`OK` or `ERROR`).

### 7. Missing token counts
- **Trigger:** more than 70% of confidently-classified LLM spans have null or zero `llm.token_count.total`.
- **Guardrail:** requires confident LLM-span classification (check 3 precedence).
- **Fix direction:** preserve provider usage, configure streaming usage collection, or set counts manually.

### 8. Missing child spans / likely payload truncation
- **Trigger:** P10 span count ≤ 2 and P90 span count ≥ 8, plus supporting evidence.
- **Guardrail:** without dropped-span counters, oversized-attribute evidence, exporter timeout patterns, or repeated same-shape traces losing children, report as **possible**, not confirmed.
- **Fix direction:** tune `BatchSpanProcessor`/export settings and truncate oversized attributes before export.

### 9. Duplicate spans
- **Trigger:** more than 20% of LLM spans appear duplicated by model, timestamp proximity, and distinct span IDs.
- **Guardrail:** require high confidence that stacked instrumentors are active — legitimate repeated/retried calls are not duplicates.
- **Fix direction:** remove redundant instrumentors (e.g. a framework and a provider instrumentor both wrapping the same call).

## Cause attribution

For every finding, label the likely cause:

- **app instrumentation** — fixable in the app's tracing code (missing attributes, context not propagated, stacked instrumentors, no flush).
- **instrumentor limitation** — the chosen instrumentor does not emit the attribute/span at all.
- **product/UI** — data is present but a dashboard/view renders it differently; not an app bug.

## Output format

- **Overall health status:** `healthy` (no triggers), `advisory` (only advisory findings), `warning` (≥1 warning), `critical` (≥1 critical), or `insufficient data` (below min-data thresholds for the requested checks).
- **Check window and data volume:** time range analyzed; trace and span counts.
- **Findings**, ordered by severity then confidence. Each finding includes: trigger value vs. threshold, evidence, affected trace/span example IDs, likely cause, and fix direction.
- **Next action:** `arize-instrumentation` (fix/re-instrument), `arize-trace` (inspect specific traces), or a framework-specific fix path.
