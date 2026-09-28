# Azure OpenAI Provider

`ax ai-integrations create` example for the `AZURE_OPEN_AI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Azure OpenAI Integration" \
  --provider AZURE_OPEN_AI \
  --api-key $AZURE_OPENAI_API_KEY \
  --base-url "https://my-resource.openai.azure.com/" \
  --model-name my-gpt-4o-deployment
```

Azure models are your own deployments, so pass each deployment name with `--model-name` (repeat for several). `--enable-default-models` also satisfies the model-source requirement, but only matches deployments named after the default models. Use your real resource URL: the server resolves the host on create and rejects one that does not exist (`DNS resolution failed`).
