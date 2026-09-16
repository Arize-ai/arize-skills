# Phoenix to AX migration setup

Ask your coding agent to migrate Phoenix traces, datasets, experiments, and stored evaluation results using the Phoenix migration skill. Supply the Phoenix host/project, AX destination space, and a fresh destination project name for traces. The agent handles setup, export, upload, and verification after explaining the expected wait and asking you to continue.

You can request traces, datasets with experiments and stored evaluations, or both in plain English. The agent first reads Phoenix and reports what it finds, including counts for each supported resource. If the scope is ambiguous, it asks which discovered data you want migrated before it accesses AX or uploads anything.

## Local credentials

Create a Git-ignored `.env` yourself using your local editor, and provide its path to the agent. Keep keys out of chat, command arguments, scripts, and displayed tool requests. Use owner-only permissions, such as `chmod 600 .env` on Unix.

```dotenv
PHOENIX_BASE_URL=https://app.phoenix.arize.com/s/your-space
PHOENIX_PROJECT_NAME=your-source-project
PHOENIX_API_KEY=
ARIZE_API_KEY=
ARIZE_SPACE_ID=
ARIZE_PROJECT_NAME=your-fresh-destination
```

Fill in your keys and destination space ID privately. Public unauthenticated Phoenix does not require a Phoenix key. Your AX key needs span ingestion and project/span read permissions. No GraphQL connector or button deployment is needed.

## Example request

> Use the Phoenix migration skill. My configuration is in the local .env. Migrate the historical traces into a fresh AX project named phoenix-migration-test. Also migrate all Phoenix datasets, experiments, and stored evaluation results with the prefix migrated-. Verify every imported data type.

Requires Python 3.10 or later and network access to Phoenix and AX. Setup and migration can take several minutes; indexing and verification can take 15 minutes or longer. Historical traces may require a historical date filter in the AX UI.

The skill migrates stored experiment evaluation results without executing evaluators or making model calls. It preserves nested dataset values as JSON and verifies every recreated dataset version, example snapshot, experiment run, and evaluation result. Evaluator definitions, prompts, tags, attachments, and span/trace/session annotations are currently outside its scope.

An existing configured ax CLI can help discover your space via `ax spaces list -o json`; it is optional. For custom deployments, set the appropriate region, API host/port, single host/port, or base domain in local configuration. The helper uses the SDK's resolved configuration for both upload and readback.
