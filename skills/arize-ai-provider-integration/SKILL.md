---
name: arize-ai-provider-integration
description: Creates, reads, updates, and deletes Arize AI integrations that store LLM provider credentials used by evaluators and other Arize features. Supports any LLM provider (e.g. OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, Vertex AI, Gemini, NVIDIA NIM, Fireworks AI, Together AI). Use when the user mentions AI integration, LLM provider credentials, create integration, list integrations, update credentials, delete integration, or connecting an LLM provider to Arize.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI and a configured Arize profile.
---

# Arize AI Integration Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.
> **Note:** `ai-integrations create` does **not** accept `--space` — AI integrations are account-scoped. Use `--space` only with `list`, `get`, `update`, and `delete`.

## Concepts

- **AI Integration** = stored LLM provider credentials registered in Arize; used by evaluators to call a judge model and by other Arize features that need to invoke an LLM on your behalf
- **Provider** = the LLM service backing the integration (e.g., `OPEN_AI`, `ANTHROPIC`, `AWS_BEDROCK`)
- **Integration ID** = a base64-encoded global identifier for an integration (e.g., `TGxtSW50ZWdyYXRpb246MTI6YUJjRA==`); required for evaluator creation and other downstream operations
- **Scoping** = visibility rules controlling which spaces or users can use an integration
- **Auth type** = how Arize authenticates with the provider: `DEFAULT` (provider API key), `PROXY_WITH_HEADERS` (proxy via custom headers), or `BEARER_TOKEN` (bearer token auth)

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `401 Unauthorized` / missing API key → run `ax profiles show` to inspect the current profile. If the profile is missing or the API key is wrong, follow [references/ax-profiles.md](references/ax-profiles.md) to create/update it. If the user doesn't have their key, direct them to https://app.arize.com/admin > API Keys
- Space unknown → run `ax spaces list` to pick by name, or ask the user
- LLM provider call fails (missing provider credentials) → run `ax ai-integrations list --space SPACE` to check for platform-managed credentials. If none exist:
  - **Preferred:** Give the user the exact `ax ai-integrations create` command from Supported Providers below (reference env var names like `$OPENAI_API_KEY`, never raw values). Ask them to export the provider key in **their own terminal** and run the command there — never paste the key into chat. Do not run the create command yourself unless the var is already exported in **this** terminal session.
  - **Bedrock/Vertex:** use `--provider-metadata` instead of `--api-key` (see Supported Providers below).
- **Security:** Never read `.env` files or search the filesystem for credentials. Use `ax profiles` for Arize credentials and `ax ai-integrations` for LLM provider keys. Never ask the user to paste secrets into chat. For missing credentials, see [references/ax-profiles.md](references/ax-profiles.md).

---

## List AI Integrations

List all integrations accessible in a space:

```bash
ax ai-integrations list --space SPACE
```

Filter by name (case-insensitive substring match):

```bash
ax ai-integrations list --space SPACE --name "openai"
```

Paginate large result sets:

```bash
# Get first page
ax ai-integrations list --space SPACE --limit 20 -o json

# Get next page using cursor from previous response
ax ai-integrations list --space SPACE --limit 20 --cursor CURSOR_TOKEN -o json
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--space` | Space name or ID to filter integrations |
| `--name` | Case-insensitive substring filter on integration name |
| `--limit` | Max results (1–100, default 15) |
| `--cursor` | Pagination token from a previous response |
| `-o, --output` | Output format: `table` (default) or `json` |

**Response fields:**

| Field | Description |
|-------|-------------|
| `id` | Base64 integration ID — copy this for downstream commands |
| `name` | Human-readable name |
| `provider` | LLM provider enum (see Supported Providers below) |
| `has_api_key` | `true` if credentials are stored |
| `model_names` | Allowed model list, or `null` if all models are enabled |
| `enable_default_models` | Whether default models for this provider are allowed |
| `function_calling_enabled` | Whether tool/function calling is enabled |
| `auth_type` | Authentication method: `DEFAULT`, `PROXY_WITH_HEADERS`, or `BEARER_TOKEN` |

---

## Get a Specific Integration

```bash
ax ai-integrations get NAME_OR_ID
ax ai-integrations get NAME_OR_ID -o json
ax ai-integrations get NAME_OR_ID --space SPACE   # required when using name instead of ID
```

Use this to inspect an integration's full configuration or to confirm its ID after creation.

---

## Create an AI Integration

Before creating, always list integrations first — the user may already have a suitable one:

```bash
ax ai-integrations list --space SPACE
```

If no suitable integration exists, create one. The required flags depend on the provider.

Every create command follows this shape; the provider-specific flags come from the table below:

```bash
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider OPEN_AI \
  --api-key $OPENAI_API_KEY \
  --enable-default-models
```

Every integration except LiteLLM, Fireworks AI and Together AI needs a model source: pass `--enable-default-models` (Arize's default model list for the provider) and/or one or more `--model-name` flags. Without either, the server rejects the create with `400: An integration must have at least one model available`.

For a provider's full example and notes (Bedrock/Vertex metadata, base URLs, flags to avoid), open only that provider's file from the **Details** column below.

### Supported Providers

| Provider | Required extra flags ("model source" = `--enable-default-models` or `--model-name`) | Key env var | Details |
|----------|---------------------|-------------|---------|
| `OPEN_AI` | `--api-key <key>`, model source | `$OPENAI_API_KEY` | [provider-openai.md](references/provider-openai.md) |
| `ANTHROPIC` | `--api-key <key>`, model source | `$ANTHROPIC_API_KEY` | [provider-anthropic.md](references/provider-anthropic.md) |
| `AZURE_OPEN_AI` | `--api-key <key>`, `--base-url <azure-endpoint>`, `--model-name <deployment>` | `$AZURE_OPENAI_API_KEY` | [provider-azure-openai.md](references/provider-azure-openai.md) |
| `AWS_BEDROCK` | `--provider-metadata '{"role_arn": "<arn>"}'` (no API key), model source | — | [provider-aws-bedrock.md](references/provider-aws-bedrock.md) |
| `VERTEX_AI` | `--provider-metadata '{"project_id": "<gcp-project>", "location": "<region>", "project_access_label": "<label>"}'` (no API key), model source | — | [provider-vertex-ai.md](references/provider-vertex-ai.md) |
| `GEMINI` | `--api-key <key>`, model source | `$GEMINI_API_KEY` | [provider-gemini.md](references/provider-gemini.md) |
| `NVIDIA_NIM` | model source; `--api-key` and `--base-url` optional (default: NVIDIA hosted) | `$NVIDIA_API_KEY` | [provider-nvidia-nim.md](references/provider-nvidia-nim.md) |
| `CUSTOM` | `--base-url <endpoint>`, model source | `$CUSTOM_LLM_API_KEY` | [provider-custom.md](references/provider-custom.md) |
| `LITELLM` | `--base-url <endpoint>`, `--api-key <key>` | `$LITELLM_API_KEY` | [provider-litellm.md](references/provider-litellm.md) |
| `FIREWORKS` | `--api-key <key>` only — no `--base-url` or `--headers` | `$FIREWORKS_API_KEY` | [provider-fireworks.md](references/provider-fireworks.md) |
| `TOGETHER_AI` | `--api-key <key>` only — no `--base-url` or `--headers` | `$TOGETHER_API_KEY` | [provider-together-ai.md](references/provider-together-ai.md) |

### Optional flags for any provider

| Flag | Description |
|------|-------------|
| `--model-name` | Allowed model name (repeat for multiple, e.g. `--model-name gpt-4o --model-name gpt-4o-mini`); satisfies the model-source requirement |
| `--enable-default-models` | Enable Arize's default model list for the provider; satisfies the model-source requirement |
| `--function-calling-enabled` | Enable tool/function calling support |
| `--auth-type` | Authentication type: `DEFAULT`, `PROXY_WITH_HEADERS`, `BEARER_TOKEN`, or `OAUTH2_CLIENT_CREDENTIALS` |
| `--headers` | Custom headers as JSON object or file path (for proxy auth) |
| `--provider-metadata` | Provider-specific metadata as JSON object or file path |

### After creation

Capture the returned integration ID (e.g., `TGxtSW50ZWdyYXRpb246MTI6YUJjRA==`) — it is needed for evaluator creation and other downstream commands. If you missed it, retrieve it:

```bash
ax ai-integrations list --space SPACE -o json
# or by name/ID directly:
ax ai-integrations get NAME_OR_ID
```

---

## Update an AI Integration

`update` is a partial update — only the flags you provide are changed. Omitted fields stay as-is.

```bash
# Rename
ax ai-integrations update NAME_OR_ID --name "New Name"

# Rotate the API key
ax ai-integrations update NAME_OR_ID --api-key $OPENAI_API_KEY

# Change the model list (replaces all existing model names)
ax ai-integrations update NAME_OR_ID --model-name gpt-4o --model-name gpt-4o-mini

# Update base URL (for Azure, custom, or NIM)
ax ai-integrations update NAME_OR_ID --base-url "https://new-endpoint.example.com/v1"

# Restrict visibility to specific spaces (full replace — lists all spaces that should have access)
ax ai-integrations update NAME_OR_ID \
  --scopings '[{"space_id": "SPACE_GLOBAL_ID", "scoping_type": "include"}]'
```

Add `--space SPACE` when using a name instead of ID. Any flag accepted by `create` can be passed to `update`.

**`--scopings` flag:** Controls which spaces can use this integration. Accepts a JSON array of scoping rules. Replaces all existing scopings on update. Use `ax spaces list -o json` to find space global IDs.

---

## Delete an AI Integration

**Warning:** Deletion is permanent. Evaluators that reference this integration will no longer be able to run.

```bash
ax ai-integrations delete NAME_OR_ID --force
ax ai-integrations delete NAME_OR_ID --space SPACE --force   # required when using name instead of ID
```

Omit `--force` to get a confirmation prompt instead of deleting immediately.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See [references/ax-setup.md](references/ax-setup.md) |
| `401 Unauthorized` | API key may not have access to this space. Verify key and space ID at https://app.arize.com/admin > API Keys |
| `No profile found` | Run `ax profiles show --expand`; set `ARIZE_API_KEY` env var or write `~/.arize/config.toml` |
| `Integration not found` | Verify with `ax ai-integrations list --space SPACE` |
| `has_api_key: false` after create | Credentials were not saved — re-run `update` with the correct `--api-key` or `--provider-metadata` |
| Evaluator runs fail with LLM errors | Check integration credentials with `ax ai-integrations get INT_ID`; rotate the API key if needed |
| `Invalid value for '--provider'` with `FIREWORKS` or `TOGETHER_AI` | The installed ax CLI predates these providers — upgrade the ax CLI (see [references/ax-setup.md](references/ax-setup.md)) |
| `An integration must have at least one model available` | Add `--enable-default-models` or at least one `--model-name` (required for every provider except LiteLLM, Fireworks AI and Together AI) |
| Integration has the wrong `provider` | `ax ai-integrations update NAME_OR_ID --provider NEW_PROVIDER` changes it, but other fields are kept as-is — pass the new provider's required flags (API key, base URL, model source) in the same call. When the two providers need very different settings, deleting and recreating is cleaner |

---

## Related Skills

- **arize-evaluator**: Create LLM-as-judge evaluators that use an AI integration → use `arize-evaluator`
- **arize-experiment**: Run experiments that use evaluators backed by an AI integration → use `arize-experiment`

---

## Save Credentials for Future Use

See [references/ax-profiles.md](references/ax-profiles.md) § Save Credentials for Future Use.
