# Instrumentation health checks

Deterministic checks over an exported span sample grouped by trace. Each check has a **trigger** (when to flag), a **guardrail** (when to downgrade confidence because a benign cause is plausible), and a **fix direction**. Report a finding as high confidence only when the trigger fires and the guardrail does not apply.

## Span-kind classification and expected attributes

When a check needs a span's kind, classify in this order and stop at the first match:

1. Customer-provided mapping (explicit source mapping in the project).
2. `openinference.span.kind` attribute (`LLM`, `AGENT`, `CHAIN`, `TOOL`, `RETRIEVER`, `EMBEDDING`, `RERANKER`, `GUARDRAIL`, `EVALUATOR`).
3. OTel GenAI attributes (`gen_ai.*`).
4. Arize built-in mappings.
5. Otherwise mark the span **uncategorized** and recommend setting `openinference.span.kind`; do not treat unknown span kind as healthy for AI/workflow spans.

Key attributes by span kind:

| Span kind | Expected attributes |
|-----------|---------------------|
| All AI/workflow spans | `openinference.span.kind`; meaningful `input.value` / `output.value` when the span represents an inspectable operation; parent-child linkage; status on completed operations. |
| `LLM` | `llm.model_name`; `llm.provider` or `llm.system`; input/output message attributes; `llm.token_count.prompt`, `llm.token_count.completion`, and `llm.token_count.total` when available. |
| `CHAIN` / `AGENT` | `input.value` for the user request or run input; `output.value` for the final response or run result; child `LLM`, `TOOL`, `RETRIEVER`, or nested `AGENT` spans for the internal steps. |
| `TOOL` | Tool name as the span name or an equivalent tool-name attribute; `input.value` containing arguments; `output.value` containing the tool result; error status when the tool fails. |
| `RETRIEVER` | Query/input value plus retrieved document ids, content/snippets, and scores when available. |
| `EMBEDDING` | Model name plus embedded text/chunks and vector metadata when emitted by the instrumentor. |
| `RERANKER` | Query/input value, candidate documents, ranked outputs, and scores when available. |
| `GUARDRAIL` / `EVALUATOR` | Input being checked, result/output, label/score/violation metadata, and error status when the check fails. |

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
- **Trigger:** any AI/workflow span cannot be classified to a known span kind after applying the precedence above; raise severity as the share of uncategorized semantic spans grows.
- **Guardrail:** do not require raw infrastructure spans (HTTP, DB, queue, cron, exporter internals) to carry OpenInference span kinds unless they are intended to appear as AI workflow steps.
- **Fix direction:** set `openinference.span.kind` and the expected attributes for the span kind, or configure source mappings.
- **Min data:** ≥5 traces.

### 4. Repeated span names
- **Trigger:** the top 3 span names account for more than 95% of spans, and the average trace has more than 3 spans.
- **Guardrail:** only warn when traces appear multi-step.
- **Fix direction:** give logical steps unique, descriptive span names.

### 5. Blank root input/output
- **Trigger:** more than 25% of semantic root spans are missing the expected `input.value` or `output.value`.
- **Semantic root evidence:** the root span represents a user-facing request, agent/chain/workflow run, eval case, or trace-level operation that someone would inspect as the entrypoint.
- **Guardrail:** skip or downgrade when the root is infrastructure-only, a background/maintenance job, intentionally redacted, partially exported, failed before producing output, or when a child span is intentionally the semantic entrypoint.
- **Fix direction:** set end-to-end user input and final response on the semantic root span, or make the semantic entrypoint explicit so infrastructure parent spans are not treated as missing payloads.

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
- **Trigger:** more than 20% of LLM spans, or more than 20% of traces with LLM activity, appear duplicated by model, timestamp proximity, distinct span IDs, and matching semantic payload.
- **LLM candidate evidence:** for this check, treat a span as an LLM candidate when it has `openinference.span.kind = LLM`, common LLM attributes such as `llm.model_name`, `llm.input_messages`, `llm.output_messages`, `llm.token_count.*`, or a provider span name such as `openai.chat.completions`. Do not skip duplicate detection just because check 3 also found missing span kinds.
- **High-confidence duplicate pattern:** sibling spans in the same trace with the same parent (or both attached to the same semantic root), same span name, same model, near-identical start/end times, and identical normalized request/response payloads. Normalize both OpenInference keys (`input.value`, `output.value`, `llm.input_messages`, `llm.output_messages`) and common ad-hoc keys (`prompt`, `completion`, `messages`, `response`) before comparing.
- **Guardrail:** do not flag legitimate retries, streaming chunks, parallel tool calls, or repeated user-requested model calls when retry metadata, different payloads, different attempts, different outputs, materially different timing, or error-to-success progression explains the repetition. If the only evidence is repeated span names without matching payloads, report under check 4 instead.
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
