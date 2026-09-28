# Gemini Provider

`ax ai-integrations create` example for the `GEMINI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Gemini Integration" \
  --provider GEMINI \
  --api-key $GEMINI_API_KEY \
  --enable-default-models
```

`--enable-default-models` is required unless you pass `--model-name` instead: the server rejects an integration with no model source.
