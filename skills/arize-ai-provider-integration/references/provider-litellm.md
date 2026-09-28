# LiteLLM Provider

`ax ai-integrations create` example for the `LITELLM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My LiteLLM Integration" \
  --provider LITELLM \
  --base-url "https://my-litellm-proxy.example.com" \
  --api-key $LITELLM_API_KEY
```
