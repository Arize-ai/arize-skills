# AWS Bedrock Provider

`ax ai-integrations create` example for the `AWS_BEDROCK` provider. Referenced from `SKILL.md`. Reference env var names, never raw key values.

AWS Bedrock uses IAM role-based auth. Provide the ARN of the role Arize should assume via `--provider-metadata`:

```bash
ax ai-integrations create \
  --name "My Bedrock Integration" \
  --provider AWS_BEDROCK \
  --provider-metadata '{"role_arn": "arn:aws:iam::123456789012:role/ArizeBedrockRole"}'
```
