---
name: arize-integrations
description: Manages Arize integrations of every type (LLM provider, agent endpoint, evaluator) through the unified ax integrations command group. Use when the user wants to list, inspect, create, update, or delete an LLM or agent integration, register a customer-hosted agent endpoint, find an EVALUATOR integration ID, set integration scopings, or choose between ax integrations and ax ai-integrations.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.39.0) and a configured Arize profile.
---

# Arize Integrations Skill

`ax integrations` manages every integration type in one group: `list`, `get`, `delete`, `create llm|agent`, `update llm|agent`. Run `ax integrations <sub> --help` (and `ax integrations create llm --help` for per-provider requirements) for flags.

## Concepts

- **Type** = `LLM` (stored provider credentials for a judge or playground model), `AGENT` (a customer-hosted HTTPS endpoint Arize calls for replay), or `EVALUATOR` (backs remote evaluators). Names are unique per type, not globally.
- **Integration ID** = base64 global ID; works in `get`, `update`, and `delete` without `--type`.
- **Scopings** = JSON array of visibility rules (organization and space IDs). Every `--scopings` value replaces the full existing list.

## Prerequisites

Run the needed `ax` command directly; troubleshoot only when it fails:

- `command not found` or version error → [ax setup](../arize-ai-provider-integration/references/ax-setup.md)
- `No active profile configured` or `401 Unauthorized` → run `ax profiles show`, then follow [ax profiles](../arize-ai-provider-integration/references/ax-profiles.md)
- **Security:** pass provider keys and header secrets as exported env vars (`--api-key "$OPENAI_API_KEY"`). Never read `.env` files, never ask the user to paste a secret into chat, and never echo raw secret values. When the var is not exported in this terminal, give the user the exact command to run in their own terminal.

## Which command group to use

| Observable need | Command |
|---|---|
| Agent endpoint integration | `ax integrations create agent` / `update agent` |
| Look up an `EVALUATOR` integration ID for a remote evaluator | `ax integrations get NAME --type EVALUATOR` |
| LLM integration with scopings set at create time | `ax integrations create llm --scopings ...` |
| `AZURE_OPEN_AI` provider, or `--auth-type` (proxy, bearer, OAuth2) | `ax ai-integrations create` (see arize-ai-provider-integration) |
| Bedrock / Vertex AI | Either: `create llm` takes `--auth` (Bedrock) and dedicated `--gcp-project-id`, `--gcp-location`, and `--project-access-label` flags (Vertex); `ax ai-integrations create` takes `--provider-metadata` |

`ax integrations create` offers only `llm` and `agent`. When no `EVALUATOR` integration exists, ask the user for an existing `EVALUATOR` integration ID.

## Finding an integration

1. With a known ID, run `ax integrations get ID -o json`.
2. With a known name, run `ax integrations get NAME --type LLM|AGENT|EVALUATOR -o json`. The `--type` help text names only LLM and AGENT, but `EVALUATOR` is accepted.
3. Only when the name is unknown, browse with `ax integrations list --name TEXT -o json`. Without `--type` the list merges every type and each row carries its type; it returns 15 rows by default, so follow `--cursor` before concluding an integration is absent. `list` is for browsing; prefer `get`.

`--space` on these commands is an optional visibility filter, not a required scope.

## Creating

1. Look up the name first (`get --type ...`) and reuse a suitable existing integration; names must be unique per type.
2. **LLM:** per-provider requirements are listed at the top of `ax integrations create llm --help`. Model and function-calling flags apply only to some providers.
3. **Agent:** `--endpoint` must be HTTPS and `--input-schema` is a Draft-07 JSON Schema for the request body. Pass large JSON (`--input-schema`, `--request-presets`, `--scopings`, `--headers`) as a file path rather than inline.
4. Add `-o json` and capture the returned `id` for downstream commands.

## Updating

- `update llm` and `update agent` are partial: omitted fields stay unchanged. Collection fields (`--headers`, `--scopings`, `--request-presets`, `--model-name`) replace the stored value, so run `get ... -o json` first and pass the complete desired list. `--headers null` clears headers.
- **Provider is immutable** in `update llm`, and config fields must match the stored provider (e.g. `--api-key` is rejected for Bedrock; use `--auth`). To change provider, create a new integration, repoint consumers to its ID, then delete the old one.
- Request presets in `update agent` are matched by name.

## Deleting

Deletion is irreversible, and evaluators or replays referencing the integration stop working. Before deleting: resolve the exact integration with `get` (pass `--type` when using a name), state its name, type, and ID to the user, and wait for explicit confirmation. Then run `ax integrations delete ID --force`; without `--force` the CLI blocks on an interactive prompt.

## Related Skills

- **arize-ai-provider-integration**: `ax ai-integrations` CRUD with per-provider examples for LLM credentials
- **arize-evaluator**: LLM-as-judge and remote evaluators that consume LLM and `EVALUATOR` integration IDs
