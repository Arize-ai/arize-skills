---
name: arize-ai-provider-integration
description: "INVOKE THIS SKILL when creating, reading, updating, or deleting Arize AI integrations. Covers listing integrations, creating integrations for any supported LLM provider (OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, Vertex AI, Gemini, NVIDIA NIM, custom), updating credentials or metadata, and deleting integrations using the ax CLI."
---

# Arize AI Integration Skill

## Concepts

- **AI Integration** = stored LLM provider credentials registered in Arize; used by evaluators to call a judge model and by other Arize features that need to invoke an LLM on your behalf
- **Provider** = the LLM service backing the integration (e.g., `openAI`, `anthropic`, `awsBedrock`)
- **Integration ID** = a base64-encoded global identifier for an integration (e.g., `TGxtSW50ZWdyYXRpb246MTI6YUJjRA==`); required for evaluator creation and other downstream operations
- **Scoping** = visibility rules controlling which spaces or users can use an integration
- **Auth type** = how Arize authenticates with the provider: `default` (provider API key), `proxy_with_headers` (proxy via custom headers), or `bearer_token` (bearer token auth)

## Prerequisites

Three things are needed: `ax` CLI, an API key (env var or profile), and a space ID.

### Install ax

If `ax` is not installed, not on PATH, or below version `0.7.1`, see ax-setup.md.

### Verify environment

Run a quick check for credentials:

**macOS/Linux (bash):**
```bash
ax --version && echo "--- env ---" && if [ -n "$ARIZE_API_KEY" ]; then echo "ARIZE_API_KEY: (set)"; else echo "ARIZE_API_KEY: (not set)"; fi && echo "ARIZE_SPACE_ID: ${ARIZE_SPACE_ID:-(not set)}" && echo "--- profiles ---" && ax profiles show 2>&1
```

**Windows (PowerShell):**
```powershell
ax --version; Write-Host "--- env ---"; Write-Host "ARIZE_API_KEY: $(if ($env:ARIZE_API_KEY) { '(set)' } else { '(not set)' })"; Write-Host "ARIZE_SPACE_ID: $env:ARIZE_SPACE_ID"; Write-Host "--- profiles ---"; ax profiles show 2>&1
```

**Read the output and proceed immediately** if either the env var or the profile has an API key. Only ask the user if **both** are missing. Resolve failures:

- No API key in env **and** no profile → **AskQuestion**: "Arize API key (https://app.arize.com/admin > API Keys)"
- Space ID unknown → run `ax spaces list -o json` to list all accessible spaces and pick the right one, or **AskQuestion** if the user prefers to provide it directly

---

## List AI Integrations

List all integrations accessible in a space:

```bash
ax ai-integrations list --space-id SPACE_ID
```

Filter by name (case-insensitive substring match):

```bash
ax ai-integrations list --space-id SPACE_ID --name "openai"
```

Paginate large result sets:

```bash
# Get first page
ax ai-integrations list --space-id SPACE_ID --limit 20 -o json

# Get next page using cursor from previous response
ax ai-integrations list --space-id SPACE_ID --limit 20 --cursor CURSOR_TOKEN -o json
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--space-id` | Space to list integrations in |
| `--name` | Case-insensitive substring filter on integration name |
| `--limit` | Max results (1–100, default 50) |
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
| `auth_type` | Authentication method: `default`, `proxy_with_headers`, or `bearer_token` |

---

## Get a Specific Integration

```bash
ax ai-integrations get INT_ID
ax ai-integrations get INT_ID -o json
```

Use this to inspect an integration's full configuration or to confirm its ID after creation.

---

## Create an AI Integration

Before creating, always list integrations first — the user may already have a suitable one:

```bash
ax ai-integrations list --space-id SPACE_ID
```

If no suitable integration exists, create one. The required flags depend on the provider.

### OpenAI

```bash
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider openAI \
  --api-key "sk-..."
```

### Anthropic

```bash
ax ai-integrations create \
  --name "My Anthropic Integration" \
  --provider anthropic \
  --api-key "sk-ant-..."
```

### Azure OpenAI

```bash
ax ai-integrations create \
  --name "My Azure OpenAI Integration" \
  --provider azureOpenAI \
  --api-key "AZURE_API_KEY" \
  --base-url "https://my-resource.openai.azure.com/"
```

### AWS Bedrock

AWS Bedrock uses IAM role-based auth instead of an API key. Provide the ARN of the role Arize should assume:

```bash
ax ai-integrations create \
  --name "My Bedrock Integration" \
  --provider awsBedrock \
  --role-arn "arn:aws:iam::123456789012:role/ArizeBedrockRole"
```

### Vertex AI

Vertex AI uses GCP service account credentials. Provide the GCP project and region:

```bash
ax ai-integrations create \
  --name "My Vertex AI Integration" \
  --provider vertexAI \
  --project-id "my-gcp-project" \
  --location "us-central1"
```

### Gemini

```bash
ax ai-integrations create \
  --name "My Gemini Integration" \
  --provider gemini \
  --api-key "AIza..."
```

### NVIDIA NIM

```bash
ax ai-integrations create \
  --name "My NVIDIA NIM Integration" \
  --provider nvidiaNim \
  --api-key "nvapi-..." \
  --base-url "https://integrate.api.nvidia.com/v1"
```

### Custom (OpenAI-compatible endpoint)

```bash
ax ai-integrations create \
  --name "My Custom Integration" \
  --provider custom \
  --base-url "https://my-llm-proxy.example.com/v1" \
  --api-key "optional-key-if-needed"
```

### Supported Providers

| Provider | Required extra flags |
|----------|---------------------|
| `openAI` | `--api-key <key>` |
| `anthropic` | `--api-key <key>` |
| `azureOpenAI` | `--api-key <key>`, `--base-url <azure-endpoint>` |
| `awsBedrock` | `--role-arn <arn>` |
| `vertexAI` | `--project-id <gcp-project>`, `--location <region>` |
| `gemini` | `--api-key <key>` |
| `nvidiaNim` | `--api-key <key>`, `--base-url <nim-endpoint>` |
| `custom` | `--base-url <endpoint>` |

### Optional flags for any provider

| Flag | Description |
|------|-------------|
| `--model-names` | Comma-separated list of allowed model names; omit to allow all models |
| `--enable-default-models` / `--no-default-models` | Enable or disable the provider's default model list |
| `--function-calling` / `--no-function-calling` | Enable or disable tool/function calling support |

### After creation

Capture the returned integration ID (e.g., `TGxtSW50ZWdyYXRpb246MTI6YUJjRA==`) — it is needed for evaluator creation and other downstream commands. If you missed it, retrieve it:

```bash
ax ai-integrations list --space-id SPACE_ID -o json
# or, if you know the ID:
ax ai-integrations get INT_ID
```

---

## Update an AI Integration

`update` is a partial update — only the flags you provide are changed. Omitted fields stay as-is.

```bash
# Rename
ax ai-integrations update INT_ID --name "New Name"

# Rotate the API key
ax ai-integrations update INT_ID --api-key "sk-new-key..."

# Change the model list
ax ai-integrations update INT_ID --model-names "gpt-4o,gpt-4o-mini"

# Update base URL (for Azure, custom, or NIM)
ax ai-integrations update INT_ID --base-url "https://new-endpoint.example.com/v1"
```

Any flag accepted by `create` can be passed to `update`.

---

## Delete an AI Integration

**Warning:** Deletion is permanent. Evaluators that reference this integration will no longer be able to run.

```bash
ax ai-integrations delete INT_ID --force
```

Omit `--force` to get a confirmation prompt instead of deleting immediately.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | See ax-setup.md |
| `401 Unauthorized` | API key may not have access to this space. Verify key and space ID at https://app.arize.com/admin > API Keys |
| `No profile found` | Run `ax profiles show --expand`; set `ARIZE_API_KEY` env var or write `~/.arize/config.toml` |
| `Integration not found` | Verify with `ax ai-integrations list --space-id SPACE_ID` |
| `has_api_key: false` after create | Credentials were not saved — re-run `update` with the correct `--api-key` or `--role-arn` |
| Evaluator runs fail with LLM errors | Check integration credentials with `ax ai-integrations get INT_ID`; rotate the API key if needed |
| `provider` mismatch | Cannot change provider after creation — delete and recreate with the correct provider |

---

## Related Skills

- **arize-evaluator**: Create LLM-as-judge evaluators that use an AI integration → use `arize-evaluator`
- **arize-experiment**: Run experiments that use evaluators backed by an AI integration → use `arize-experiment`

---

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any of the following during this conversation (via AskQuestion response, pasted text, or inline values) **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them for future use.

| Credential | Where it gets saved |
|------------|---------------------|
| API key | `ax` profile at `~/.arize/config.toml` |
| Space ID | **macOS/Linux:** shell config (`~/.zshrc` or `~/.bashrc`) as `export ARIZE_SPACE_ID="..."`. **Windows:** user environment variable via `[System.Environment]::SetEnvironmentVariable('ARIZE_SPACE_ID', '...', 'User')` |

**Skip this entirely if:**
- The API key was already loaded from an existing profile or `ARIZE_API_KEY` env var
- The space ID was already set via `ARIZE_SPACE_ID` env var

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — Check if `~/.arize/config.toml` exists. If it does, read it and update the `[auth]` section. If not, create it:

   ```toml
   [profile]
   name = "default"

   [auth]
   api_key = "THE_API_KEY"

   [output]
   format = "table"
   ```

   Verify with: `ax profiles show`

2. **Space ID** — Persist as an environment variable:

   **macOS/Linux** — Detect the user's shell config file (`~/.zshrc` for zsh, `~/.bashrc` for bash). Append:

   ```bash
   export ARIZE_SPACE_ID="THE_SPACE_ID"
   ```

   Tell the user to run `source ~/.zshrc` (or restart their terminal) for it to take effect.

   **Windows (PowerShell):**

   ```powershell
   [System.Environment]::SetEnvironmentVariable('ARIZE_SPACE_ID', 'THE_SPACE_ID', 'User')
   ```
