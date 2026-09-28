# Azure OpenAI Provider

`ax ai-integrations create` example for the `AZURE_OPEN_AI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Azure OpenAI Integration" \
  --provider AZURE_OPEN_AI \
  --api-key $AZURE_OPENAI_API_KEY \
  --base-url "https://my-resource.openai.azure.com/"
```
