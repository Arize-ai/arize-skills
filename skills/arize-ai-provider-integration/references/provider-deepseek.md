# DeepSeek Provider

`ax ai-integrations create` example for the `DEEP_SEEK` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

DeepSeek is a single hosted service, so the API key is the only credential. Do not pass `--base-url` or `--headers` — they are not used for this provider, and the CLI stores them without validation. Arize resolves the models the key can reach, so `--model-name` is optional. DeepSeek stores and processes data in the People's Republic of China; tell the user before you create the integration.

```bash
ax ai-integrations create \
  --name "My DeepSeek Integration" \
  --provider DEEP_SEEK \
  --api-key $DEEPSEEK_API_KEY
```
