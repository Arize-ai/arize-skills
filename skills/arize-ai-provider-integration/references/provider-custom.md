# Custom (OpenAI-compatible endpoint) Provider

`ax ai-integrations create` example for the `CUSTOM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Custom Integration" \
  --provider CUSTOM \
  --base-url "https://my-llm-proxy.example.com/v1" \
  --api-key $CUSTOM_LLM_API_KEY
```
