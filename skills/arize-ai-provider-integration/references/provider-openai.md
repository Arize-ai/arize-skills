# OpenAI Provider

`ax ai-integrations create` example for the `OPEN_AI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My OpenAI Integration" \
  --provider OPEN_AI \
  --api-key $OPENAI_API_KEY \
  --enable-default-models
```

`--enable-default-models` is required unless you pass `--model-name` instead: the server rejects an integration with no model source.
