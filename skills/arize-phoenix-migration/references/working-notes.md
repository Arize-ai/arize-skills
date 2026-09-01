# Phoenix To AX Migration Working Notes

Last updated: 2026-09-01

This file is a disposable handoff log for the `arize-phoenix-migration` skill. Keep it current while building and testing the skill, and remove or replace it before publishing if it becomes stale.

## Current State

- Skill repo branch: `feat/phoenix-to-ax-migration-skill`
- New skill folder: `skills/arize-phoenix-migration`
- Product PR: [Arize PR 68637](https://github.com/Arize-ai/arize/pull/68637), `feat: PX to AX file importer`
- Product PR branch: `feat/61397-px-to-ax-fileimporter-route`
- Product PR status when inspected: open, updated 2026-08-26
- Local product checkout at [arize](</Users/datngo/IdeaProjects/arize>) was read-only for this pass. It is on `feat/61397-px-to-ax-fileimporter-route`, behind `origin/feat/61397-px-to-ax-fileimporter-route` by many commits, and has local modifications. Do not overwrite or reset that work.

## Source Notes Read

- User-provided current recommendation doc: [file-importer-route-changes-v2.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/file-importer-route-changes-v2.md>)
- Architecture note: [file-importer-route.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/file-importer-route.md>)
- Mapping note: [mapping-table.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/mapping-table.md>)
- Earlier batch-logger note: [px-to-ax-python-batch-logger.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/px-to-ax-python-batch-logger.md>)
- Mechanics note: [mechanics-of-px-to-ax-phthon-batch-logger.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/mechanics-of-px-to-ax-phthon-batch-logger.md>)
- Networking/security note: [networking-and-cilium-external-endpoints.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/networking-and-cilium-external-endpoints.md>)
- Nate review synthesis: [file-importer-nate-comments.md](</Users/datngo/IdeaProjects/arize/codex-notes/multi-ticket/umbrella-61397/file-importer-nate-comments.md>)

## External Docs Checked

- [Phoenix REST API overview](https://arize.com/docs/phoenix/sdk-api-reference/rest-api/overview): Phoenix REST endpoints live under `/v1`, use bearer auth when enabled, and list APIs follow `data` plus `next_cursor`.
- [Phoenix REST improvements release note](https://arize.com/docs/phoenix/release-notes/03-2026/03-13-2026-rest-api-improvements): Phoenix 13.15.0+ has project trace/span REST APIs with pagination, time filtering, sorting, and optional inline spans on trace listing.
- [Phoenix to Arize AX migration docs](https://arize.com/docs/phoenix/resources/phoenix-to-arize-ax-migration): existing public migration scripts support traces, datasets, experiments, annotations/evals, and warn that annotations should wait for trace indexing.
- [AX OpenTelemetry and OpenInference overview](https://arize.com/docs/ax/concepts/otel-openinference/overview): AX tracing is built on OpenTelemetry plus OpenInference semantic conventions.
- [AX OpenInference span kinds](https://arize.com/docs/ax/concepts/otel-openinference/span-kinds): AX expects `openinference.span.kind`, input/output fields, metadata, session/user IDs, and per-kind LLM/tool/retriever attributes.

## Product Route Summary

Current target architecture from PR 68637 and local notes:

`Phoenix REST pages -> Phoenix FileImporter connector/parser -> ArizeSpans Arrow payload -> FileImporter tracing path -> DruidImporter -> Druid`

This supersedes two older approaches:

- direct OTLP receiver migration
- online-tasks plus Python SDK batch logger

The Python batch-logger work is still useful as research because it validated the batch/FileImporter path and exposed the timestamp issue in the OTLP route.

## Product Implementation Details Observed

Remote PR changed files include:

- app route/nav/UI for Phoenix Connector settings
- GraphQL mutations and connections for Phoenix connectors/import jobs/job events
- DB access objects for Phoenix integrations/import jobs/work items
- migrations for `phoenix_integrations`, `phoenix_import_jobs`, and `phoenix_import_work_items`
- FileImporter coordinator and worker Go code
- worker proto additions for `ImportPhoenixWorkItem`
- feature flag and deployment/network policy changes

Important caveat: local checkout is behind the PR head. The local tree showed older migration numbering and some local modifications. Use GitHub PR data or update the product checkout only after confirming with the user.

## Runtime Model

- Phoenix connector stores endpoint plus encrypted API key.
- Connector/project discovery calls Phoenix `/v1/projects`.
- Import job creation supports only `importCategory = traces` for MVP.
- Import jobs are idempotent by SHA-256 request fingerprint over space, connector, source Phoenix project, target project, import category, and mode.
- Job mode is currently `one_time_migration`.
- Job creation records `snapshot_end_time`; page fetches pass that as Phoenix `end_time`.
- Each Phoenix page/cursor is a durable work item.
- Work item identity is deterministic from `{job_id, cursor_key}`.
- Staged Arrow object path is deterministic under `phoenix-import-jobs/{job_id}/{work_item_uuid}.arrow`.
- `TxnUuid` is deterministic per work item.
- Execution remains serial per job for now, with account-level fairness in runnable job selection.
- Coordinator poll limit is `10`; stale running work items use a lease timeout and can be reclaimed.
- Retry policy observed locally: max 5 attempts, base backoff 30 seconds, exponential backoff.

## Worker Mapping Behavior Observed Locally

Local file read: [phoenix.go](</Users/datngo/IdeaProjects/arize/go/pkg/fileimporter/worker/process/phoenix.go>).

The worker:

- fetches `GET /v1/projects/{phoenix_project_id}/spans`
- sends `limit=500`, optional `cursor`, and `end_time` from snapshot
- accepts response shapes with either `data` or `spans`
- maps core fields from `context.trace_id`, `context.span_id`, `parent_id`, `name`, `status_code` or `status.status_code`, `status_message` or `status.description`
- uppercases status code and `openinference.span.kind`
- writes Arrow using AX OpenInference tracing column constants
- uses `Schema_ArizeSpans_` and `TRACING` environment when calling `ImportFile`
- uses target project name as `ModelId`
- uses snapshot timestamp as model version when available
- preserves unmapped Phoenix attributes by merging them into `attributes.metadata`
- treats costs as float columns

Observed mapped column groups:

- string columns for trace/span IDs, parent span, name, status, exception fields, input/output, embedding model, LLM model/provider/invocation/template fields, tool fields, metadata, session/user, graph node, agent name, reranker query/model
- int columns for start/end nanos, token counts, and reranker top-k
- float columns for total/prompt/completion costs

Known gaps or areas to verify:

- complex nested fields such as events, embeddings, LLM messages, retrieval documents, reranker input/output documents, tools, and choices may still need explicit preservation or first-class mapping depending on current PR head.
- Need test fixtures from real PX traces to confirm whether Phoenix `/spans` shape carries all necessary fields or whether `/spans/otlpv1` fallback is needed.

## Security And Network Constraints

Connector creation/update:

- normalizes Phoenix endpoint
- enforces configured Phoenix origin in cloud mode
- rejects direct IP endpoints
- calls URL safety validation
- encrypts API key with external API key encryption config

Worker fetch:

- validates the Phoenix URL immediately before sending the bearer token
- rejects loopback, private, link-local, multicast, unspecified, metadata IP `169.254.169.254`, CGNAT `100.64.0.0/10`
- rejects explicit ports other than `443`

Implication for testing:

- local `http://localhost:6006` Phoenix will likely fail against the productized worker route unless using a dev-only path or public HTTPS tunnel.
- cloud imports may be limited to configured Phoenix Cloud origin unless product/networking explicitly broadens support.
- externalendpoints and Cilium policy need production-environment validation; mynamespace may not catch enforced policy failures.

## Review Themes From PR 68637

Nader architectural themes:

- use FileImporter architecture rather than ad hoc job rows
- durable page-level work items are the correctness boundary
- work-item identity, `TxnUuid`, and staged object path must be deterministic
- `phoenix_import_job_events` should be audit/logging only, not execution state
- state queries should follow the FileImporter prepared-statement and `query.go` pattern
- progress counters should derive from work items where possible
- worker-owned fetch/transform is the preferred end state
- tests should cover retries, idempotence, Arrow generation, metadata preservation, state transitions, and stale running recovery

Nate security/production themes:

- account-level fairness or queue controls are needed so one tenant cannot starve others
- worker must revalidate the URL before sending decrypted Phoenix API key
- externalendpoints egress and ingress must match the actual worker path
- on-prem should not be broken by missing encryption-key secret wiring
- global deployment flag and account-scoped `enablePhoenixMigration` backend gating are both needed
- delete/soft-delete semantics should be explicit about not cancelling already in-flight work

## Initial Test Plan For Skill Work

When user provides PX traces/API keys and AX test account:

1. Confirm which route we are testing: productized PR route, public migration scripts, or a local skill-only prototype.
2. Confirm whether Phoenix endpoint is Phoenix Cloud/public HTTPS or local/private.
3. Configure AX via `ax profiles`, not pasted secrets.
4. For productized route, create/list connector, fetch source projects, create one traces job, and poll job status/events.
5. Start with a tiny Phoenix project or a time-bounded project if possible.
6. Verify work items in DB or UI: discovered pages, completed pages, imported span count, last error.
7. Verify AX spans with `ax spans export` or `ax traces export` by original event-time window.
8. Inspect representative spans for trace IDs, span IDs, parent relationships, `openinference.span.kind`, `llm.model_name`, token counts, input/output, and metadata preservation.
9. Record every run in this file with run/job IDs, counts, and first failing boundary.

## Open Questions

- Should this skill ultimately drive the productized GraphQL/UI route only, or also include a fallback standalone script path for direct Phoenix-to-AX migration outside the product PR?
- Which AX environment and space should be used for joint testing?
- Are the PX traces in Phoenix Cloud or self-hosted/local Phoenix?
- Does the current PR head still use exactly the mapping observed in the local checkout, or has it changed since the local branch is behind remote?
- Should the skill include reusable scripts after the first joint test, or stay instructions-only and delegate execution to product/UI/CLI surfaces?
