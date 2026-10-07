# Braintrust ↔ Arize AX concept mapping

| Braintrust | Arize AX | Notes |
|------------|----------|-------|
| Organization | Account / organization | |
| Project | Tracing project | AX `project_name` on tracer resource |
| Span / log row | Span | Prefer OpenInference kinds after cutover |
| Trace (span tree) | Trace | BT often stores a whole conversation as one trace. On import, emit **one AX trace per `chat.request` turn** and keep `span_parents` as child links |
| Conversation / `metadata.session_id` | Session | `attributes.session.id` groups turns |
| Dataset | Dataset | Export via BTQL / API |
| Dataset record (`input`, `expected`, `metadata`) | Example | Flatten to user fields |
| Experiment | Experiment | Re-run in AX |
| Score / scorer | Evaluator | Recreate; do not import old score columns as AX experiment truth |
| Prompt / prompt function | Prompt hub | Recreate versions |
| `bt sync` NDJSON | — | Braintrust-native format; convert before AX dataset import |

## Dataset field mapping tips

Braintrust rows often look like:

```json
{
  "id": "...",
  "input": {"question": "..."},
  "expected": {"answer": "..."},
  "metadata": {"tag": "gold"}
}
```

AX examples:

```json
{
  "question": "...",
  "answer": "...",
  "tag": "gold"
}
```

String `input` / `expected` can map directly to `input` / `expected`.