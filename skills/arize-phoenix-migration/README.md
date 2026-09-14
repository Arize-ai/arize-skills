# Phoenix to AX migration setup

Ask your coding agent to migrate a Phoenix project using the Phoenix migration skill. Supply the Phoenix host/project, AX destination space, and a fresh destination project name. The agent handles setup, export, upload, and verification after explaining the expected wait and asking you to continue.

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

> Use the Phoenix migration skill. My configuration is in the local .env. Migrate into a fresh AX project named phoenix-migration-test, preserve the historical traces, and verify the result.

Requires Python 3.10 or later and network access to Phoenix and AX. Setup and migration can take several minutes; indexing and verification can take 15 minutes or longer. Historical traces may require a historical date filter in the AX UI.

An existing configured ax CLI can help discover your space via `ax spaces list -o json`; it is optional. For custom deployments, set the appropriate region, API host/port, single host/port, or base domain in local configuration. The helper uses the SDK's resolved configuration for both upload and readback.
