---
name: arize-integrations
description: Manages the `ax integrations` command — LLM and agent integrations registered at the account level (distinct from `ax ai-integrations`, which stores LLM provider credentials for evaluators; see arize-ai-provider-integration for that). Use when the user mentions agent integration, agent replay endpoint, connecting a customer-hosted agent to Arize, or asks to list/create/update/delete an integration via `ax integrations` (not `ax ai-integrations`).
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (>= 0.31.1) and a configured Arize profile.
---

# Arize Integrations Skill

> **Not the same command as `ax ai-integrations`.** `ax ai-integrations` stores LLM provider credentials used by evaluators — see the **arize-ai-provider-integration** skill for that. `ax integrations` (this skill) is a separate, newer command that manages two integration **types**: `LLM` (a lighter-weight LLM connection, not tied to evaluators) and `AGENT` (a customer-hosted agent endpoint Arize can call for replay). If the user's goal is "give my evaluator an LLM to judge with," use **arize-ai-provider-integration** instead.

> **`SPACE`** — `--space` flags accept a space **name** or a base64 space **ID**. Find yours with `ax spaces list`.
> Integration names are unique **per type**, not globally — a `--type` flag (or `--space`, for list) disambiguates when using a name instead of an ID.

## Concepts

- **Integration** = an account-level resource registered via `ax integrations`, either type `LLM` or `AGENT`
- **LLM integration** = a connection to a model provider (`OPEN_AI`, `ANTHROPIC`, `GEMINI`, `AWS_BEDROCK`, `VERTEX_AI`, `CUSTOM`, `NVIDIA_NIM`)
- **Agent integration** = an HTTPS endpoint for a customer-hosted agent that Arize calls to **replay** a request (e.g., re-run a traced interaction against the live agent)
- **Integration ID** = the identifier returned on create; use it for downstream `get`/`update`/`delete` when names collide

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `401 Unauthorized` / missing API key → follow [references/ax-profiles.md](references/ax-profiles.md)
- `Unknown command 'integrations'` → the installed CLI predates 0.31.1; see [references/ax-setup.md](references/ax-setup.md) to upgrade
- Space unknown → run `ax spaces list` to pick by name, or ask the user
- **Security:** Never read `.env` files or search the filesystem for credentials. Never ask the user to paste secrets into chat — reference them by environment variable name (e.g. `$OPENAI_API_KEY`).

---

## List Integrations

```bash
ax integrations list                          # every type, merged, each item carries its type
ax integrations list --type LLM
ax integrations list --type AGENT
ax integrations list --name "prod" --space SPACE
```

## Get an Integration

```bash
ax integrations get NAME_OR_ID --type LLM      # --type required when using a name (names are unique per type, not globally)
ax integrations get INTEGRATION_ID             # --type not needed when using the ID directly
```

---

## Create an LLM Integration

Required flags depend on `--provider`:

| Provider | Required extra flags |
|----------|----------------------|
| `OPEN_AI` / `ANTHROPIC` / `GEMINI` | `--api-key` |
| `AWS_BEDROCK` | `--auth '{"auth_type": "DEFAULT", "role_arn": "arn:..."}'` |
| `CUSTOM` | `--base-url` |
| `VERTEX_AI` | `--gcp-project-id`, `--gcp-location`, `--project-access-label` |
| `NVIDIA_NIM` | none required, but needs `--model-name` or `--enable-default-models` |

```bash
ax integrations create llm \
  --name "My OpenAI Integration" \
  --provider OPEN_AI \
  --api-key $OPENAI_API_KEY
```

Optional for any provider: `--model-name` (repeatable), `--enable-default-models`, `--function-calling-enabled`, `--headers`, `--scopings`. Never pass `--api-key`, `--auth`, or `--headers` values inline from user-pasted secrets — reference an environment variable the user exported themselves.

## Create an Agent Integration

Connects a customer-hosted agent exposed at an HTTPS endpoint that Arize calls for replay:

```bash
ax integrations create agent \
  --name "My Support Agent" \
  --endpoint "https://my-agent.example.com/replay" \
  --input-schema '{"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}'
```

`--input-schema` is a JSON Schema (Draft-07) for the request body Arize will POST to `--endpoint`; accepts inline JSON or a file path. Optional: `--description`, `--headers` (auth headers Arize sends with each call), `--request-presets` (named example payloads), `--scopings`.

---

## Update an Integration

Partial update — only the flags you pass change; omitted fields stay as-is. The `llm`/`agent` subcommand and `--type` follow the same split as `create`/`get`:

```bash
# LLM: rotate a key
ax integrations update llm NAME_OR_ID --api-key $OPENAI_API_KEY

# LLM: swap allowed models (replaces the full list)
ax integrations update llm NAME_OR_ID --model-name gpt-4o --model-name gpt-4o-mini

# Agent: point at a new endpoint
ax integrations update agent NAME_OR_ID --endpoint "https://my-agent.example.com/v2/replay"
```

The LLM integration's `--provider` is immutable — delete and recreate to change it. `--headers`, `--request-presets`, and `--scopings` are full replacements, not merges.

## Delete an Integration

```bash
ax integrations delete NAME_OR_ID --type LLM --force
ax integrations delete NAME_OR_ID --force          # ID form, --type not needed
```

Irreversible. Omit `--force` for a confirmation prompt.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See [references/ax-setup.md](references/ax-setup.md) |
| `Unknown command 'integrations'` | CLI predates 0.31.1 — run `ax upgrade` |
| `401 Unauthorized` | See [references/ax-profiles.md](references/ax-profiles.md) |
| `Integration not found` by name | Names are unique per type — add `--type LLM` or `--type AGENT` |
| Agent replay never reaches the endpoint | Confirm `--endpoint` is reachable over HTTPS and `--headers` includes any required auth |

## Related Skills

- **arize-ai-provider-integration**: LLM provider credentials for evaluators (`ax ai-integrations`, a different command) → use that skill instead if the goal is giving an evaluator a judge model
- **arize-evaluator**: Evaluators consume `ai-integrations`, not `integrations` — do not mix the two up when wiring a judge model
