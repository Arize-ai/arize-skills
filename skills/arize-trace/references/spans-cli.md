# `ax spans` / `ax traces` — Filter Syntax Reference

`--filter` syntax for `ax spans export`, `ax traces export`, `ax traces list`, and `ax spans annotate`. Run `ax spans export --help` / `ax traces export --help` / `ax spans annotate --help` for flags — not documented here. See [SKILL.md](../SKILL.md) for workflows and export strategy, and [span-columns.md](span-columns.md) for the full span attribute reference.

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
