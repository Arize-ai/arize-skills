# LangSmith ↔ Arize AX concept mapping

| LangSmith | Arize AX | Notes |
|-----------|----------|-------|
| Workspace / tenant | Account + space | Datasets and projects live under an AX space |
| Tracing project (session) | Tracing project | Set via `project_name` on Arize tracer resource |
| Run | Span | LangSmith run trees → OpenInference span trees |
| Trace (root run + children) | Trace | Shared trace id |
| Dataset | Dataset | Export examples, then `ax datasets create` |
| Example (`inputs` / `outputs`) | Example | Flatten to user-defined fields |
| Experiment | Experiment | Re-run in AX |
| Feedback / scores | Evaluations / annotations | Recreate criteria; do not bulk-import old scores as AX truth |
| Prompt Hub prompt | Prompt hub | Recreate versions/labels |
| Thread | Session | Map to `attributes.session.id` when present |

## Dataset field mapping tips

LangSmith examples often look like:

```json
{
  "inputs": {"question": "..."},
  "outputs": {"answer": "..."},
  "metadata": {"split": "test"}
}
```

AX examples:

```json
{
  "question": "...",
  "answer": "...",
  "split": "test"
}
```

If `inputs` is a single string field, store as `input`. Preserve nested structures only when the user's eval code expects them — prefer flat columns for AX dataset UX.