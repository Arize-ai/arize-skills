# Fireworks AI Provider

`ax ai-integrations create` example for the `FIREWORKS` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

Fireworks is a single hosted service, so the API key is the only credential. Do not pass `--base-url` or `--headers` — they are not used for this provider, and the CLI stores them without validation. Arize resolves the models the key can reach, so `--model-name` is only needed for fine-tunes or dedicated deployments that cannot be listed automatically.

```bash
ax ai-integrations create \
  --name "My Fireworks AI Integration" \
  --provider FIREWORKS \
  --api-key $FIREWORKS_API_KEY
```
