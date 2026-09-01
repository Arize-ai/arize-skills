---
name: arize-phoenix-migration
description: Migrates Phoenix traces into Arize AX and validates Phoenix import jobs using the FileImporter-backed AX tracing path. Use when the user asks to move Phoenix/PX traces to AX, test Phoenix connector imports, or debug Phoenix migration jobs.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires access to the source Phoenix instance, an Arize AX account/profile, and whichever Phoenix migration route is available in the target environment.
---

# Arize Phoenix Migration Skill

Use this skill for Phoenix-to-Arize AX trace migration, Phoenix connector setup, migration job testing, and migration debugging.

Before making changes or running a migration, read the current handoff in [working notes](references/working-notes.md). It records the latest known product route, PR context, test assumptions, and open questions.

## Route

Prefer the productized FileImporter route for current work:

`Phoenix REST spans -> durable Phoenix import work items -> Arrow ArizeSpans file -> FileImporter ImportFile -> AX tracing storage`

Do not revive the older direct OTLP receiver migration or the Python SDK batch logger path unless the user explicitly asks to investigate those historical approaches. The important historical lesson is still relevant: migrated trace queryability must be driven by the original Phoenix event timestamps, not by migration receipt time.

## Inputs

Collect only the inputs needed for the chosen route:

- Phoenix endpoint
- Phoenix API key, if the source requires auth
- source Phoenix project
- target AX space
- target AX project name
- Arize AX credentials through an `ax` profile or environment already configured by the user

Treat Phoenix and AX credentials as secrets. Never search `.env` files, never print raw API keys, and never include secrets in notes, logs, job events, request fingerprints, or test artifacts. If credentials are missing, ask the user to configure them through the relevant CLI/profile or UI path rather than pasting them into chat.

## Current Product Behavior

The FileImporter implementation uses Phoenix `GET /v1/projects/{project_identifier}/spans` as the page source, with cursor pagination and a job-level `snapshot_end_time`. A Phoenix page is the durable retry unit.

For AX import, Phoenix spans must be normalized into the AX `ArizeSpans` tracing schema:

- preserve `trace_id`, `span_id`, `parent_id`, name, status, start time, and end time
- map known OpenInference attributes into first-class tracing columns
- keep span kind values uppercase, e.g. `LLM` and `TOOL`
- preserve unsupported or unmapped Phoenix attributes in `attributes.metadata` where practical
- keep token counts numeric and costs as floats
- ensure `input.value`, `output.value`, and their MIME types survive when present

When using the PR route, expect GraphQL/UI surfaces for saved Phoenix connectors, project discovery, import job creation, import job listing, and synthesized job events.

## Validation

Use a small migration first. Verify all of these before calling a migration successful:

- the Phoenix connector can list source projects
- the import job returns an existing active job on duplicate create rather than creating duplicates
- work-item counts progress from discovered to completed
- retryable Phoenix/API/object-store failures schedule retries and terminal failures surface a useful error
- migrated spans are queryable in AX by the original Phoenix event-time window
- exported AX spans preserve representative OpenInference fields and unmapped metadata

For AX-side verification, use the installed `ax` CLI where available. Export a targeted trace or a small recent sample rather than bulk-exporting an unknown project.

## Environment Constraints

Cloud/productized imports may restrict Phoenix endpoints to a configured Phoenix origin and public HTTPS/443 reachability. Current worker-side hardening rejects unsafe hosts before sending the Phoenix API key, including loopback/private/link-local/metadata/CGNAT addresses and explicit non-443 ports.

If testing a local or private Phoenix instance, confirm the environment supports that path before assuming `localhost:6006` or private network URLs will work. A public HTTPS tunnel, dev-only bypass, or a different deployment profile may be required.

## Handoff

After each meaningful investigation or test run, update [working notes](references/working-notes.md) with:

- date and environment
- branch or PR revision inspected
- Phoenix source and AX target identifiers, excluding secrets
- commands or UI path used
- span/job counts
- first failing boundary, if any
- links to authoritative docs or PR review threads used for decisions
