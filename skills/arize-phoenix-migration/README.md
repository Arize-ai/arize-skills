# Phoenix to AX migration setup

Ask your coding agent to migrate Phoenix to AX using the Phoenix migration skill and give it the path to your local configuration. The agent inventories the source, helps you choose the scope and destination names, then handles setup, upload, and verification after you say `go`.

You can simply provide the local configuration and ask to migrate Phoenix to AX. The agent reads Phoenix, resolves the configured AX space to its name, and checks proposed destination names without creating anything. It presents a short `Found in Phoenix` and `Will write to AX` summary, followed by one bold, underlined decision question with copyable answers. Reply `go` to accept all supported discovered data and the proposed AX space/project/prefix, or name a subset and say `go`. The agent then completes and verifies the migration without another confirmation.

## Local credentials

If credentials are not already configured, the agent asks for the Phoenix URL, Phoenix project name, Phoenix API key when required, and AX API key in one short action block. You may provide the values directly; the agent creates and protects the local `.env`, discovers accessible AX spaces, and does the remaining setup. If you already have an `.env`, you can provide its path instead.

```dotenv
PHOENIX_BASE_URL=https://app.phoenix.arize.com/s/your-space
PHOENIX_PROJECT_NAME=your-source-project
PHOENIX_API_KEY=
ARIZE_API_KEY=
ARIZE_SPACE_ID=
ARIZE_PROJECT_NAME=your-fresh-destination
```

Public unauthenticated Phoenix does not require a Phoenix key. Your AX key needs span ingestion and project/span read permissions. The agent discovers the destination space, so you do not need to find an opaque space ID. No GraphQL connector or button deployment is needed.

## Example request

> Use the Phoenix migration skill. My configuration is in the local .env. Migrate the historical traces into a fresh AX project named phoenix-migration-test. Also migrate all Phoenix datasets, experiments, and stored evaluation results with the prefix migrated-. Verify every imported data type.

Requires Python 3.10 or later and network access to Phoenix and AX. Setup and migration can take several minutes; indexing and verification can take 15 minutes or longer. Historical traces may require a historical date filter in the AX UI.

The skill migrates stored experiment evaluation results without executing evaluators or making model calls. It preserves nested dataset values as JSON and verifies every recreated dataset version, example snapshot, experiment run, and evaluation result. Evaluator definitions, prompts, tags, attachments, and span/trace/session annotations are currently outside its scope.

An existing configured ax CLI can help discover your space via `ax spaces list -o json`; it is optional. For custom deployments, set the appropriate region, API host/port, single host/port, or base domain in local configuration. The helper uses the SDK's resolved configuration for both upload and readback.
