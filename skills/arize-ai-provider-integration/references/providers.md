# AI Provider Create Examples

Per-provider `ax ai-integrations create` commands and notes. Referenced from `SKILL.md`. Load only the section for the provider the user needs. Reference env var names (e.g. `$OPENAI_API_KEY`), never raw key values.

## OpenAI

```bash
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider OPEN_AI \
  --api-key $OPENAI_API_KEY
```

## Anthropic

```bash
ax ai-integrations create \
  --name "My Anthropic Integration" \
  --provider ANTHROPIC \
  --api-key $ANTHROPIC_API_KEY
```

## Azure OpenAI

```bash
ax ai-integrations create \
  --name "My Azure OpenAI Integration" \
  --provider AZURE_OPEN_AI \
  --api-key $AZURE_OPENAI_API_KEY \
  --base-url "https://my-resource.openai.azure.com/"
```

## AWS Bedrock

AWS Bedrock uses IAM role-based auth. Provide the ARN of the role Arize should assume via `--provider-metadata`:

```bash
ax ai-integrations create \
  --name "My Bedrock Integration" \
  --provider AWS_BEDROCK \
  --provider-metadata '{"role_arn": "arn:aws:iam::123456789012:role/ArizeBedrockRole"}'
```

## Vertex AI

Vertex AI uses GCP service account credentials. Provide the GCP project and region via `--provider-metadata`:

```bash
ax ai-integrations create \
  --name "My Vertex AI Integration" \
  --provider VERTEX_AI \
  --provider-metadata '{"project_id": "my-gcp-project", "location": "us-central1", "project_access_label": "my-access-label"}'
```

## Gemini

```bash
ax ai-integrations create \
  --name "My Gemini Integration" \
  --provider GEMINI \
  --api-key $GEMINI_API_KEY
```

## NVIDIA NIM

```bash
ax ai-integrations create \
  --name "My NVIDIA NIM Integration" \
  --provider NVIDIA_NIM \
  --api-key $NVIDIA_API_KEY \
  --base-url "https://integrate.api.nvidia.com/v1"
```

## Custom (OpenAI-compatible endpoint)

```bash
ax ai-integrations create \
  --name "My Custom Integration" \
  --provider CUSTOM \
  --base-url "https://my-llm-proxy.example.com/v1" \
  --api-key $CUSTOM_LLM_API_KEY
```

## LiteLLM

```bash
ax ai-integrations create \
  --name "My LiteLLM Integration" \
  --provider LITELLM \
  --base-url "https://my-litellm-proxy.example.com" \
  --api-key $LITELLM_API_KEY
```

## Fireworks AI

Fireworks is a single hosted service, so the API key is the only credential. Do not pass `--base-url` or `--headers` — they are not used for this provider, and the CLI stores them without validation. Arize resolves the models the key can reach, so `--model-name` is only needed for fine-tunes or dedicated deployments that cannot be listed automatically.

```bash
ax ai-integrations create \
  --name "My Fireworks AI Integration" \
  --provider FIREWORKS \
  --api-key $FIREWORKS_API_KEY
```

## Together AI

Together AI is a single hosted service, so the API key is the only credential. Do not pass `--base-url` or `--headers` — they are not used for this provider, and the CLI stores them without validation. Arize resolves the models the key can reach, so `--model-name` is optional.

```bash
ax ai-integrations create \
  --name "My Together AI Integration" \
  --provider TOGETHER_AI \
  --api-key $TOGETHER_API_KEY
```
