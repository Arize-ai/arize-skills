# `ax spans` / `ax traces` — Gotchas and Filter Reference

For the full flag list, run `ax spans export --help`, `ax traces export --help`, or `ax spans annotate --help` — those are authoritative and always current. This file covers only what `--help` doesn't: non-obvious defaults/behavior and the `--filter` syntax. See [SKILL.md](../SKILL.md) for workflows and export strategy, and [span-columns.md](span-columns.md) for the full span attribute reference.

## Gotchas

- `ax spans export`: `--output-dir` defaults to the current directory — the SKILL.md workflow always passes `--output-dir .arize-tmp-traces` explicitly, don't rely on the default. `--trace-id`/`--span-id`/`--session-id` are mutually exclusive with each other but combinable with `--filter`. `--space` is only required when using `--all` (Arrow Flight), not for a project name lookup.
- `ax traces export`: `--space` is required when `PROJECT` is a name (not a base64 ID) or when using `--all`.
- `ax spans annotate`: `--space` is required when `PROJECT` is a name (not a base64 ID).

---

## Filter Syntax

SQL-like expressions passed to `--filter`.

### Common filterable columns

Full column list in [span-columns.md](span-columns.md). The most frequently filtered:

| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| `name` | string | Span name | `'ChatCompletion'`, `'retrieve_docs'` |
| `status_code` | string | Status | `'OK'`, `'ERROR'`, `'UNSET'` |
| `latency_ms` | number | Duration in ms | `100`, `5000` |
| `parent_id` | string | Parent span ID | null for root spans |
| `context.trace_id` | string | Trace ID | |
| `context.span_id` | string | Span ID | |
| `attributes.session.id` | string | Session ID | |
| `attributes.openinference.span.kind` | string | Span kind | `'LLM'`, `'CHAIN'`, `'TOOL'`, `'AGENT'`, `'RETRIEVER'`, `'RERANKER'`, `'EMBEDDING'`, `'GUARDRAIL'`, `'EVALUATOR'` |
| `attributes.llm.model_name` | string | LLM model | `'gpt-4o'`, `'claude-3'` |
| `attributes.input.value` | string | Span input | |
| `attributes.output.value` | string | Span output | |
| `attributes.error.type` | string | Error type | `'ValueError'`, `'TimeoutError'` |
| `attributes.error.message` | string | Error message | |
| `event.attributes` | string | Error tracebacks | Use CONTAINS (not exact match) |

### Operators

`=`, `!=`, `<`, `<=`, `>`, `>=`, `AND`, `OR`, `IN`, `CONTAINS`, `LIKE`, `IS NULL`, `IS NOT NULL`

### Examples

```
status_code = 'ERROR'
latency_ms > 5000
name = 'ChatCompletion' AND status_code = 'ERROR'
attributes.llm.model_name = 'gpt-4o'
attributes.openinference.span.kind IN ('LLM', 'AGENT')
attributes.error.type LIKE '%Transport%'
event.attributes CONTAINS 'TimeoutError'
```

### Tips

- Prefer `IN` over multiple `OR` conditions: `name IN ('a', 'b', 'c')` not `name = 'a' OR name = 'b' OR name = 'c'`
- Start broad with `LIKE`, then switch to `=` or `IN` once you know exact values
- Use `CONTAINS` for `event.attributes` (error tracebacks) — exact match is unreliable on complex text
- Always wrap string values in single quotes
