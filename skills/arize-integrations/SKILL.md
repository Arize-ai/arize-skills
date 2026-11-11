---
name: arize-integrations
description: Creates, reads, updates, and deletes Arize integrations of type LLM, AGENT, and EVALUATOR with the `ax integrations` command group. Covers registering LLM providers with visibility scopings, connecting customer-hosted agent endpoints, and finding EVALUATOR integration IDs for remote evaluators. Use when the user mentions ax integrations, agent integration, agent endpoint, evaluator integration, integration ID for a remote evaluator, integration scopings, or listing integrations by type.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.39.0) and a configured Arize profile.
---

# Arize Integrations Skill

> **`SPACE`** — `--space` flags accept a space **name** or a base64 space **ID**. `create llm` and `create agent` take no `--space`: integrations are account-scoped, and visibility is set with `--scopings`.

## Concepts

- **Integration types**: `LLM` (provider credentials and models), `AGENT` (a customer-hosted HTTPS endpoint Arize calls for replay, described by a Draft-07 JSON Schema for the request body), and `EVALUATOR` (the endpoint a remote evaluator calls).
- **Names are unique per type**, not globally. IDs are globally unique.

## Choosing `ax integrations` vs `ax ai-integrations`

- Use `ax integrations` when the integration is an `AGENT` or `EVALUATOR`, or when scopings must be set at create time (`--scopings`).
- Use `ax ai-integrations create` (see the **arize-ai-provider-integration** skill) when the provider is `AZURE_OPEN_AI` or `--auth-type` is needed; `ax integrations create llm` accepts neither.
- AWS Bedrock and Vertex AI configuration differs between the groups: `ax integrations create llm` takes dedicated flags (`--auth`, `--gcp-*`, `--project-access-label`), while `ax ai-integrations create` takes `--provider-metadata`.

Template evaluators take `--ai-integration-id`; confirm an LLM integration is reachable there with `ax ai-integrations get NAME_OR_ID`.

## Prerequisites

Run the needed `ax` command directly. Troubleshoot on failure:

- `command not found` or version error → [references/ax-setup.md](references/ax-setup.md)
- `No active profile configured` or `401 Unauthorized` → run `ax profiles show`, then follow [references/ax-profiles.md](references/ax-profiles.md)
- Space unknown → [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files, search the filesystem for credentials (exception: the non-secret `ARIZE_SPACE_ID` line, see [Space](references/ax-profiles.md#space)), or ask the user to paste secrets into chat. API keys and header secrets are write-only; pass them from an exported shell variable or a JSON file path.

## Workflow

### 1. Find the integration (get first, list to browse)

When the name or ID is known, fetch it directly:

```bash
ax integrations get INTEGRATION_ID -o json
ax integrations get NAME --type LLM -o json    # --type required with a name
```

`ax integrations list` is paginated and meant for human browsing. Without `--type` it returns every type in one merged list, each item tagged with its type. Narrow with `--type` and `--name`:

```bash
ax integrations list --type AGENT --name support -o json
```

### 2. Create

- **LLM:** `ax integrations create llm`. Required flags depend on the provider, and the help page lists them per provider; run `ax integrations create llm --help` before composing the command.
- **Model flags are provider-limited.** `--model-name`, `--enable-default-models`, and `--function-calling-enabled` each apply to a different subset of providers, and `update llm` accepts model flags for fewer providers than `create llm`. When a model list must change on a provider that `update llm --help` excludes, delete and recreate, or use `ax ai-integrations update`.
- **AGENT:** `ax integrations create agent` with `--endpoint` (HTTPS) and `--input-schema`. Run `ax integrations create agent --help`.
- **EVALUATOR:** locate an existing one; see [Remote evaluators](#remote-evaluators).

### 3. Update

`ax integrations update llm` and `ax integrations update agent` change only the fields passed. Gotchas:

- **Provider is immutable** on `update llm`. To change provider, delete and recreate.
- The server rejects config fields that do not apply to the stored provider (for example `--api-key` on AWS Bedrock or Vertex AI; Bedrock takes `--auth`).
- `--headers`, `--scopings`, and (on agents) `--request-presets` **replace** existing values. Fetch current values with `get -o json` first and send the full merged collection. `--headers null` clears headers.
- Pass the ID from step 1 to avoid name ambiguity across types; `update` has no `--type` selector.

Run `ax integrations update llm --help` or `ax integrations update agent --help` for fields.

### 4. Delete

Deletion is irreversible; anything referencing the integration stops working. Before deleting:

1. Run `ax integrations get ID -o json` and show the user the name, type, and ID.
2. Ask the user to confirm explicitly.
3. Only after confirmation run `ax integrations delete ID --force`. With a name, add `--type`.

## Remote evaluators

`ax evaluators create-evaluator remote` and `ax evaluators create-evaluator-version remote` require `--integration-id` pointing to an existing `EVALUATOR` integration. Their help text says to create one with `ax integrations create --type EVALUATOR`, but that command fails (`No such option: --type`). Locate an existing one with the step 1 commands and `--type EVALUATOR`, then pass the returned `id` as `--integration-id`. When no `EVALUATOR` integration exists, ask the user for an existing integration ID or to create one outside the CLI. One `EVALUATOR` integration is shared by every evaluator version that references it, so updating or deleting it affects all of them. Remote evaluators also require the feature to be enabled on the account. Hand the evaluator creation itself to the **arize-evaluator** skill.

## Related Skills

- **arize-ai-provider-integration**: LLM provider credentials via `ax ai-integrations`, including Azure OpenAI and `--auth-type`
- **arize-evaluator**: Template, code, and remote evaluators that consume integration IDs
- **arize-experiment**: Experiments scored by evaluators backed by these integrations
