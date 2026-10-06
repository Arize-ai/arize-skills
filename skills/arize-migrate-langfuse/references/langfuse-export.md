# Langfuse export recipes

Ask the user for keys. Prefer env vars they set in the shell. Do not invent credentials. Do not read `.env` from disk.

## Auth

Basic auth: username = public key, password = secret key.

```bash
# Smoke test — replace BASE with LANGFUSE_BASE_URL
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_BASE_URL/api/public/projects"
```

Common bases:

- EU Cloud: `https://cloud.langfuse.com`
- US Cloud: `https://us.cloud.langfuse.com`
- Self-hosted: user-provided origin (no trailing path)

OpenAPI: `https://cloud.langfuse.com/generated/api/openapi.yml`

Python SDK alternative: `pip install langfuse` then `from langfuse import get_client; langfuse = get_client()`.

## List datasets

```bash
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_BASE_URL/api/public/v2/datasets?page=1&limit=100"
```

Paginate with `page` until empty.

## Dataset items

```bash
# By dataset name (v1 path still widely used)
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_BASE_URL/api/public/datasets/DATASET_NAME/items?page=1&limit=100"
```

Or via SDK namespaces: `langfuse.api.datasets.*` / `langfuse.api.dataset_items.*`.

Write raw pages under `.arize-tmp-migrate/langfuse/raw/` before transforming.

## Prompts → Arize AX Prompt Hub

```bash
# List names, versions, labels
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_BASE_URL/api/public/v2/prompts?page=1&limit=100"

# One version (version and label are mutually exclusive)
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_BASE_URL/api/public/v2/prompts/PROMPT_NAME?version=1"
```

Map Langfuse `text` / `chat` prompts into AX messages, then `ax prompts create` / `create_version` and `set_labels` for Langfuse labels (`production`, `staging`, …).

## Historical observations → Arize AX

Preferred path for AX UI history: from the arize-skills repo root run
`python scripts/migrate_vendor_traces.py --vendor langfuse --arize-project DEST`.
Optional `--tag TAG` limits import to traces with that Langfuse tag.
The script maps observation I/O → `input.value` / `output.value`, parents, and
trace `sessionId` / `userId` → `session.id` / `user.id`.

For manual inspection, use the Observations API with required `fromStartTime` / `toStartTime`
and pagination. Docs: https://langfuse.com/docs/api-and-data-platform/features/public-api

Very large blob-storage exports are for the customer's own archive — not a turn-key AX
importer. Use the migrate script for API-accessible history, then cut over live tracing
for new traffic.

## Transform checklist

1. Flatten `input` / `expectedOutput` into example fields
2. Drop Langfuse `id`, timestamps, and empty objects
3. Ensure every example has at least one property
4. Cap batches at 1000 for create; use append for the rest
5. Keep a `manifest.json` with source dataset name, item count, and AX dataset id after import