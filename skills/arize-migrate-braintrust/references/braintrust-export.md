# Braintrust export recipes

Ask the user for the API key. Do not invent credentials. Do not read `.env` from disk.

## Auth

```bash
# Default US data plane
export BRAINTRUST_API_URL="https://api.braintrust.dev"
# EU / self-hosted: use the URL the user provides

curl -sS "$BRAINTRUST_API_URL/v1/project" \
  -H "Authorization: Bearer $BRAINTRUST_API_KEY"
```

API overview: https://www.braintrust.dev/docs/api-reference

## SQL / BTQL export

POST `$BRAINTRUST_API_URL/btql` with JSON body. Prefer SQL syntax for new queries.

Docs: https://www.braintrust.dev/docs/reference/sql  
Export notes: https://www.braintrust.dev/docs/annotate/export

### Dataset rows

```bash
curl -sS -X POST "$BRAINTRUST_API_URL/btql" \
  -H "Authorization: Bearer $BRAINTRUST_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT input, expected, metadata FROM project_dataset('\''PROJECT_ID'\'', '\''DATASET_ID'\'') LIMIT 500",
    "fmt": "json"
  }'
```

Paginate with cursors when the response includes a `cursor` field. Raise limits carefully.

### Historical logs → Arize AX

Preferred path for AX UI history: from the arize-skills repo root run
`python scripts/migrate_vendor_traces.py --vendor braintrust --source-project PROJECT --arize-project DEST`.
The script uses BTQL (`span_parents`, `metadata`, etc.), maps `output` → `output.value`,
splits conversations into **one AX trace per turn**, and sets `session.id` from Braintrust metadata.

For manual field inspection:

```bash
curl -sS -X POST "$BRAINTRUST_API_URL/btql" \
  -H "Authorization: Bearer $BRAINTRUST_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT id, name, input, output, span_id, root_span_id, span_parents, metadata, created FROM project_logs('\''PROJECT_ID'\'') LIMIT 20",
    "fmt": "json"
  }'
```

Very large archives beyond BTQL page limits may need a custom export; do not promise unbounded
bulk history without pagination. After import, cut over live tracing for new traffic.

## CLI helpers

- `bt sql` — run SQL against Braintrust
- `bt sync` — Braintrust NDJSON sync between Braintrust orgs/projects; **not** an AX importer. If the user already has NDJSON from `bt sync pull`, transform records into AX example JSON before `ax datasets create`.

## Prompts → Arize AX Prompt Hub

Braintrust REST (https://www.braintrust.dev/docs/api-reference/prompts/list-prompts):

- List: `GET /v1/prompt` (filter with `project_name`, `slug`, …)
- Get: `GET /v1/prompt/{prompt_id}` with optional `version` / `environment`

Map `prompt_data` messages into AX Prompt Hub via `ax prompts create` / `create_version`, and map environments to AX labels when the user wants them. Skip tool/scorer functions unless explicitly requested.

## Transform checklist

1. Flatten `input` / `expected` / `metadata`
2. Drop Braintrust ids and system columns from create payloads
3. Batch ≤1000 for create; append remainder
4. Write `manifest.json` with source project/dataset ids and AX dataset id