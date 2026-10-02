# LangSmith export recipes

Ask the user for keys. Do not invent credentials. Do not read `.env` from disk.

## Auth

Header: `X-API-Key: $LANGSMITH_API_KEY`. Many endpoints also need `X-Tenant-Id: $LANGSMITH_WORKSPACE_ID`.

Default API host: `https://api.smith.langchain.com`. Self-hosted: user-provided URL.

## CLI (preferred when installed)

Docs: https://docs.langchain.com/langsmith/langsmith-cli

```bash
langsmith dataset list
langsmith dataset export DATASET_NAME ./data.json --limit 500
# Raise --limit or paginate for larger sets
```

```bash
langsmith run list --project PROJECT_NAME --limit 20 --format json
```

## REST / SDK

Python: `pip install langsmith` then `from langsmith import Client; client = Client()`.

List datasets and read examples via the Client helpers, or:

```bash
curl -sS "https://api.smith.langchain.com/api/v1/datasets" \
  -H "X-API-Key: $LANGSMITH_API_KEY" \
  -H "X-Tenant-Id: $LANGSMITH_WORKSPACE_ID"
```

Query runs (sample only): `POST /api/v2/runs/query` or SDK `list_runs` with a short time window and explicit `select` fields. See https://docs.langchain.com/langsmith/export-traces

## Historical runs → Arize AX

Preferred path for AX UI history: from the arize-skills repo root run
`python scripts/migrate_vendor_traces.py --vendor langsmith --source-project PROJECT --arize-project DEST`.
That exports recent runs via the LangSmith API/SDK and ingests OpenInference spans over OTLP
(with `output.value`, `session.id`, and parent links mapped).

LangSmith bulk export to S3/Parquet is for **customer archives**, not a turn-key AX importer.
Do not promise Parquet → AX trace UI ingest. Keep the archive; use the migrate script for
API-accessible history, then cut over live tracing for new traffic.

## Prompts

Use LangSmith Prompt Hub APIs / SDK to list and pull prompt templates and commit hashes. Save under `.arize-tmp-migrate/langsmith/prompts/`.

## Transform checklist

1. Flatten `inputs` / `outputs` into example fields
2. Drop LangSmith example UUIDs and system timestamps from create payloads
3. Batch ≤1000 for `ax datasets create`; append the rest
4. Record a `manifest.json` (source id/name, counts, AX dataset id)