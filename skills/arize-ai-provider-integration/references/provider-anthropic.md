# Anthropic Provider

`ax ai-integrations create` example for the `ANTHROPIC` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My Anthropic Integration" \
  --provider ANTHROPIC \
  --api-key $ANTHROPIC_API_KEY \
  --enable-default-models
```

`--enable-default-models` is required unless you pass `--model-name` instead: the server rejects an integration with no model source. `--base-url` is optional; omit it to use the public Anthropic API.
