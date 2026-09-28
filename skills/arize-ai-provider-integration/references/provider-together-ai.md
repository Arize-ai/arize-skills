# Together AI Provider

`ax ai-integrations create` example for the `TOGETHER_AI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

Together AI is a single hosted service, so the API key is the only credential. Do not pass `--base-url` or `--headers` — they are not used for this provider, and the CLI stores them without validation. Arize resolves the models the key can reach, so `--model-name` is optional.

```bash
ax ai-integrations create \
  --name "My Together AI Integration" \
  --provider TOGETHER_AI \
  --api-key $TOGETHER_API_KEY
```
