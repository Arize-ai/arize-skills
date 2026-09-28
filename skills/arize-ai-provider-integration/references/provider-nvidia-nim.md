# NVIDIA NIM Provider

`ax ai-integrations create` example for the `NVIDIA_NIM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My NVIDIA NIM Integration" \
  --provider NVIDIA_NIM \
  --api-key $NVIDIA_API_KEY \
  --enable-default-models
```

`--base-url` and `--api-key` are both optional: omit `--base-url` to use NVIDIA's hosted endpoint, or set it to a self-hosted NIM endpoint (e.g. `--base-url "https://my-nim.example.com/v1"`). `--enable-default-models` is required unless you pass `--model-name` instead: the server rejects an integration with no model source.
