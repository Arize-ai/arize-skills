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

Preferred path for AX UI history: from this installed skill's root run
`python scripts/migrate_vendor_traces.py --vendor langsmith --source-project PROJECT --arize-project DEST`.
That exports the most recent root runs (plus their children) via the LangSmith API/SDK and ingests OpenInference spans over OTLP
(with `output.value`, `session.id`, and parent links mapped). Install [helper dependencies](../scripts/requirements.txt) first.

LangSmith bulk export to S3/Parquet is for **customer archives**, not a turn-key AX importer.
Do not promise Parquet → AX trace UI ingest. Keep the archive; use the migrate script for
API-accessible history, then cut over live tracing for new traffic.

## Prompts → Arize AX Prompt Hub

LangSmith exposes prompts programmatically (docs: https://docs.langchain.com/langsmith/manage-prompts-programmatically):

- List: `client.list_prompts()`
- Versions: `client.list_prompt_commits("owner/repo")` or `GET /api/v1/commits/{owner}/{repo}`
- One version: pull / `GET /api/v1/commits/{owner}/{repo}/{commit}` where `{commit}` can be a hash, tag, or `latest`

Map into AX with `ax prompts create` / `ax prompts create-version` (or Python `client.prompts.create` / `create_version`), then `set_labels` for tags such as production.

Chat manifests → AX `messages` with roles `SYSTEM` / `USER` / `ASSISTANT` / `TOOL`. Prefer importing readable chat templates; note tool-only / non-chat commits the agent cannot flatten.

## Transform checklist (datasets)

1. Flatten `inputs` / `outputs` into example fields
1. Drop LangSmith example UUIDs and system timestamps from create payloads
1. Batch ≤1000 for `ax datasets create`; append the rest
1. Record a `manifest.json` (source id/name, counts, AX dataset id)
