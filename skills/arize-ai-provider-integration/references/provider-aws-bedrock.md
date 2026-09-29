# AWS Bedrock Provider

`ax ai-integrations create` example for the `AWS_BEDROCK` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

AWS Bedrock uses IAM role-based auth. Provide the ARN of the role Arize should assume via `--provider-metadata`. Add `"external_id"` to the metadata if the role's trust policy requires one:

```bash
ax ai-integrations create \
  --name "My Bedrock Integration" \
  --provider AWS_BEDROCK \
  --provider-metadata '{"role_arn": "arn:aws:iam::123456789012:role/ArizeBedrockRole"}' \
  --enable-default-models
```

`--enable-default-models` is required unless you pass `--model-name` instead: the server rejects an integration with no model source. No `--api-key` is used.
