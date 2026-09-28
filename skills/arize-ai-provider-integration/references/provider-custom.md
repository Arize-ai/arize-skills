# Custom (OpenAI-compatible endpoint) Provider

`ax ai-integrations create` example for the `CUSTOM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Custom Integration" \
  --provider CUSTOM \
  --base-url "https://my-llm-proxy.example.com/v1" \
  --api-key $CUSTOM_LLM_API_KEY \
  --model-name my-model
```

`--base-url` is required and must implement the OpenAI API shape; the server validates it and requires a public address. Pass the endpoint's model names with `--model-name` (repeat for several), or `--enable-default-models`: the server rejects an integration with no model source. `--api-key` is optional if the endpoint needs no key.
