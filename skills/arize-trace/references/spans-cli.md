# `ax spans` / `ax traces` — Flag and Filter Reference

Flag tables (verified against `--help` on arize-ax-cli 0.32.0) and `--filter` syntax. See [SKILL.md](../SKILL.md) for workflows and export strategy, and [span-columns.md](span-columns.md) for the full span attribute reference.

## `ax spans export`

| Flag | Default | Description |
|------|---------|-------------|
| `PROJECT` (positional) | `$ARIZE_DEFAULT_PROJECT` | Project name or base64 ID |
| `--trace-id` | — | Filter by `context.trace_id` (mutex with other ID flags) |
| `--span-id` | — | Filter by `context.span_id` (mutex with other ID flags) |
| `--session-id` | — | Filter by `attributes.session.id` (mutex with other ID flags) |
| `--filter` | — | SQL-like filter; combinable with any ID flag |
| `--limit, -l` | 100 | Max spans (REST); ignored with `--all` |
| `--space, -s` | — | Required when using `--all` (Arrow Flight); not needed for project name in spans export |
| `--days` | 30 | Lookback window; ignored if `--start-time`/`--end-time` set |
| `--start-time` / `--end-time` | — | ISO 8601 time range override |
| `--output-dir` | `.` (current directory) | Output directory — the SKILL.md workflow always passes `--output-dir .arize-tmp-traces` explicitly, don't rely on this default |
| `--stdout` | false | Print JSON to stdout instead of file |
| `--all` | false | Unlimited bulk export via Arrow Flight |

## `ax traces export`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `PROJECT` | string | required | Project name or base64 ID (positional arg) |
| `--filter` | string | none | Filter expression for phase-1 span lookup |
| `--space, -s` | string | none | Space name or ID; required when `PROJECT` is a name or when using `--all` (Arrow Flight) |
| `--limit, -l` | int | 50 | Max number of traces to export |
| `--days` | int | 30 | Lookback window in days |
| `--start-time` | string | none | Override start (ISO 8601) |
| `--end-time` | string | none | Override end (ISO 8601) |
| `--output-dir` | string | `.` | Output directory |
| `--stdout` | bool | false | Print JSON to stdout instead of file |
| `--all` | bool | false | Use Arrow Flight for both phases |

## `ax spans annotate`

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `PROJECT` | string | yes | Project name or base64 ID (positional) |
| `--file, -f` | path | yes | Annotation file: JSON, JSONL, CSV, or Parquet (use `-` for stdin) |
| `--space, -s` | string | no | Space name or ID (required when `PROJECT` is a name) |
| `--start-time` | string | no | ISO 8601 start of annotation window |
| `--end-time` | string | no | ISO 8601 end of annotation window (defaults to now) |
| `--days` | int | no | Lookback window in days, alternative to `--start-time` |

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
