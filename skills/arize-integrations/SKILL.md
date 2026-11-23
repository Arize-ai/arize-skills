---
name: arize-integrations
description: Lists, inspects, creates, updates, and deletes Arize integrations of every type (LLM provider and agent endpoint) with the `ax integrations` command group. Use when the user mentions ax integrations, agent integration, register an agent endpoint, agent replay endpoint, request presets, integration scopings, Decision Judge providers, or managing LLM and agent integrations together.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.39.0) and a configured Arize profile.
---

# Arize Integrations Skill

`ax integrations` manages LLM and agent integrations in one group: `list`, `get`, `delete`, `create llm|agent`, `update llm|agent`. This skill covers sequencing and gotchas only. For flags, run the specific help page, e.g. `ax integrations create llm --help`.

## Prerequisites

Run the needed `ax` command directly. If it fails with a missing-profile or `401` error, run `ax profiles show` to inspect the active profile, then `ax profiles create` when none exists. Pass provider keys and agent header secrets as environment-variable references (e.g. `--api-key $OPENAI_API_KEY`); have the user export the value in their own terminal rather than pasting it into chat.

## Choosing `integrations` vs `ai-integrations`

- Use `ax integrations create agent` / `update agent` for an agent endpoint; only this group handles agents.
- Use `ax integrations` to view LLM and agent integrations together, filter by `--type`.
- Use `ax ai-integrations create` for `AZURE_OPEN_AI` or when `--auth-type` is needed; `ax integrations create llm` accepts neither.
- For provider-by-provider LLM setup (Bedrock role ARNs, Vertex labels, base URLs, model sources), follow the **arize-ai-provider-integration** skill and translate flags with `ax integrations create llm --help`: Bedrock takes `--auth` JSON and Vertex takes `--gcp-project-id`, `--gcp-location`, `--project-access-label` instead of `--provider-metadata`.

## ID discovery first

1. **Direct path (default):** when the name is known, run `ax integrations get NAME --type LLM -o json` (or `--type AGENT`). `--type` is required with a name because names are unique only per type; an ID works without it.
2. **Browsing:** `ax integrations list` is for human browsing or when the name is unknown. Narrow it with `--name TEXT`, `--type`, or `--provider`; it pages with `--limit`/`--cursor`. Without `--type`, every type comes back in one merged list, each item tagged with its type.
3. `TYPE_SAFE_AI`, `PERPLEXITY`, and `CLOUDFLARE` integrations appear in `list` only when `--provider` names that provider.
4. Carry the ID from `get` into `update` and `delete`; IDs remove the name/type ambiguity.

## Scoping

- Names must be unique within the account; `create` takes no `--space`.
- `--space` on `list`, `get`, `delete`, and `update` is an optional visibility filter, not a target.
- Visibility is set with `--scopings` (JSON array or file path) on create or update. Every `--scopings` call replaces all existing scopings: read the current set with `get -o json` and send the complete desired list.

## LLM vs agent integrations

| Aspect | `llm` | `agent` |
|---|---|---|
| Purpose | Stored model-provider credentials | Customer-hosted HTTPS endpoint that Arize calls for replay |
| Required on create | `--name`, `--provider`, plus the per-provider flags listed in `create llm --help` | `--name`, `--endpoint`, `--input-schema` (JSON Schema Draft-07) |
| Immutable | `--provider` | none listed in `--help` |
| Replace-on-update | `--scopings`, `--model-name` | `--headers`, `--request-presets` (matched by name), `--scopings` |

JSON-valued flags (`--input-schema`, `--headers`, `--auth`, `--request-presets`, `--scopings`) accept inline JSON or a file path; use a file for anything multi-line. `--headers null` clears headers.

## Updating

- Updates are partial: only passed flags change.
- Run `get -o json` first to read the stored provider. The server rejects `update llm` fields that do not apply to that provider.
- `update llm` accepts fewer per-provider fields than `create llm`. Check `ax integrations update llm --help` for the fields the stored provider accepts; to change any other field, or to change the provider, delete and recreate the integration. Per-provider applicability of `create llm` flags is listed in `ax integrations create llm --help`.

## Deleting (irreversible)

1. Resolve the exact ID and type with `get`.
2. Show the user the name, type, and ID; ask whether evaluators or other features still use it (`--help` reports no dependents); get explicit confirmation.
3. Run `ax integrations delete ID --force`. `--force` skips the interactive prompt, which an agent shell cannot answer.

## Related Skills

- **arize-ai-provider-integration**: LLM provider credential setup with `ax ai-integrations`
- **arize-evaluator**: LLM-as-judge evaluators that use an LLM integration
