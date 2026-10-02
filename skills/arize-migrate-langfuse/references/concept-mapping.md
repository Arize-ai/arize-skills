# Langfuse ↔ Arize AX concept mapping

| Langfuse | Arize AX | Notes |
|----------|----------|-------|
| Project (API key scoped) | Tracing project / model | AX project name is set on the tracer resource (`project_name` / `openinference.project.name`) |
| Organization | Account / organization | AX **space** is the usual tenant boundary for datasets |
| Trace | Trace | Tree of spans sharing a trace id |
| Observation (generation, span, event) | Span | Prefer OpenInference `openinference.span.kind` (LLM, CHAIN, TOOL, RETRIEVER, AGENT) |
| Dataset | Dataset | Versioned example collection in a space |
| Dataset item | Example | Flat JSON fields; AX auto-manages `id` / timestamps |
| Dataset run / experiment | Experiment | Re-run in AX; do not import old scores as truth |
| Score | Evaluation / annotation | Recreate judges; optional human annotations later |
| Prompt (Prompt management) | Prompt hub | Labels/versions — recreate, do not assume 1:1 CLI parity |
| Session | Session | AX uses `attributes.session.id` when present |

## Field mapping tips (datasets)

Langfuse dataset items often look like:

```json
{
  "id": "...",
  "input": {"question": "..."},
  "expectedOutput": {"answer": "..."},
  "metadata": {"source": "..."}
}
```

AX create/append examples should be flat user fields only, for example:

```json
{
  "question": "...",
  "answer": "...",
  "source": "..."
}
```

If `input` / `expectedOutput` are strings, map to `input` / `expected` (or `answer`) rather than nesting.