# Vertex AI Provider

`ax ai-integrations create` example for the `VERTEX_AI` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

Vertex AI uses GCP service account credentials. Provide the GCP project and region via `--provider-metadata`:

```bash
ax ai-integrations create \
  --name "My Vertex AI Integration" \
  --provider VERTEX_AI \
  --provider-metadata '{"project_id": "my-gcp-project", "location": "us-central1", "project_access_label": "my-access-label"}'
```
