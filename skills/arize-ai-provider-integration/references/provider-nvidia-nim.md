# NVIDIA NIM Provider

`ax ai-integrations create` example for the `NVIDIA_NIM` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

```bash
ax ai-integrations create \
  --name "My NVIDIA NIM Integration" \
  --provider NVIDIA_NIM \
  --api-key $NVIDIA_API_KEY \
  --base-url "https://integrate.api.nvidia.com/v1"
```
