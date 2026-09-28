# LiteLLM Provider

`ax ai-integrations create` example for the `LITELLM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My LiteLLM Integration" \
  --provider LITELLM \
  --base-url "https://my-litellm-proxy.example.com" \
  --api-key $LITELLM_API_KEY
```

Both `--base-url` and `--api-key` are needed: LiteLLM is self-hosted, so there is no default endpoint, and the virtual key scopes which models Arize can resolve. No `--model-name` is needed, because Arize resolves models from the proxy.
