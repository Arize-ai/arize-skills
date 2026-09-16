---
name: arize-phoenix-migration
description: Migrate existing Phoenix (PX) traces, datasets, experiments, and stored evaluation results into Arize AX and verify the imported records. Use when users ask to move or copy historical Phoenix data to AX; not for adding live instrumentation or exporting AX data alone.
metadata:
  author: arize
  version: "1.0"
---

# Phoenix to AX migration

Help the user migrate a Phoenix project to AX using the bundled helper. Handle setup and commands yourself; the user should only need to supply their source and destination details.

Requires Python 3.10 or later, shell access, and network access to Phoenix and AX. No particular coding agent, ax CLI, or AX Phoenix connector is required.

## Discover the source and gather missing details

Reuse details from the request and configured environment. First ask only for the Phoenix host, source project, and Phoenix API key when authentication is required. Then inspect the source before asking the user to choose a migration scope.

Create owner-only, Git-ignored trace and data manifests in a local working directory. Run the trace `export` command and the data `export` command independently, without destination credentials or upload commands, so failure in one inventory does not discard the other result. These source reads are the inventory and can take a little time on large projects. Report the discovered counts for traces, spans, datasets, versions, example snapshots, experiments, and stored evaluation results. Preserve these manifests so the selected migration can reuse the same fixed snapshots.

Present one compact decision after inventory. Include:

- The discovered counts for each supported resource group and any group that could not be inventoried. An inventory error means unknown, not zero; preserve successful inventory results and explain the failed group without exposing server response bodies.
- The choices: all supported discovered data; traces only; all dataset/experiment data; or named trace IDs/datasets.
- A suggested fresh trace project name and dataset/experiment prefix derived from the source name when the request or environment does not already provide them. State the suggestions so a plain `go` can accept them.
- The current exclusions: evaluator definitions, prompts, tags, attachments, and span/trace/session annotations.
- The time expectation: upload can take several minutes and AX indexing/verification can take 15 minutes or longer.

End with one question, such as: "Would you like all supported data, traces only, dataset/experiment data only, or a selection? Reply `go` to migrate everything listed above using the suggested destinations, or name what you want and say `go`."

If the original request already names the resources, present those as the selected scope and ask the user to say `go` or correct it. After this inventory message, treat `go`, `migrate all`, or equivalent unqualified approval as authorization to migrate all supported discovered data using the stated destination suggestions. Treat a qualified response such as `datasets only, go` as both the selection and authorization. Do not ask a second confirmation when the response includes approval. Ask only for destination credentials or choices that are still missing and cannot be safely suggested.

If the user selects individual traces or datasets after the inventory, rerun the applicable export with repeated `--trace-id` or `--dataset` arguments into a new manifest. Do not edit the all-source manifest by hand.

Explain how to configure missing credentials locally in environment variables or a Git-ignored `.env`. Never echo credentials, place them in command arguments, or copy them to reports. Prefer a user-created existing `.env` and request its path. Never embed literal keys in displayed tool requests or generated shell/Python commands, including heredocs; writing to a file without stdout still exposes command contents. Avoid patch/edit tools that echo secret values. If your available tools cannot write secrets without displaying them, ask the user to configure the local file themselves. Keep the file owner-only (for example, `chmod 600` on Unix). Load an explicitly chosen environment file through the helper; do not print or source its contents. See [configuration and migration details](references/migration.md) for variable names and examples.

If the user only supplies a space name, optionally use an already configured ax CLI for discovery: `ax spaces list -o json` or `ax spaces get "<space-name>" -o json`. Run `ax spaces --help` if command syntax differs. Reuse the user's configured CLI authentication; never put keys in CLI arguments. Without the CLI, resolve the name through AX APIs. Ask the user to choose if multiple spaces match. Use a fresh destination project; suggest a source-derived name when none is specified and establish that destination with the user. Do not ask about the separate AX button, feature flags, or browser tokens.

## Wait for the migration decision

Include the time expectation in the inventory-and-scope question above, before running any destination preflight or upload command. Verification may wait up to 15 minutes for indexing, and readback or larger projects can take longer; do not promise a fixed completion time.

For example: "I found 1,107 traces and one dataset with two versions, one experiment, and three stored evaluations. Upload can take several minutes, and AX indexing and verification can take 15 minutes or longer. Reply `go` to migrate all supported data using project `source-ax-migration` and prefix `source-ax-`, or tell me which listed resources to migrate and say `go`."

Wait for the user's decision and approval before accessing AX or starting import commands. Local dependency setup and read-only Phoenix inventory are allowed before this approval because they are needed to present the choice. The initial request to migrate authorizes the inventory but does not authorize destination writes. Once the user says `go` as described above, proceed through preflight, import, and verification without another confirmation. A read-only planning request stops after inventory.

## Run the migration

Locate this installed skill's root and run its bundled commands by absolute path, so they work from any workspace. Check the chosen interpreter is Python 3.10 or later before creating an isolated environment or installing the [helper dependencies](scripts/requirements.txt). Use an available compatible interpreter if the default is older.

1. Run `scripts/migrate.py preflight` with the user's local configuration and chosen trace destination. Present a short source/destination summary. Missing configuration returns `needs_input`; ask for those fields. A dry-run or planning request has already stopped after source inventory and does not access AX.
2. For traces, reuse the applicable inventory manifest and run `scripts/migrate.py import`, then `verify`. The export captured every page under a fixed snapshot boundary. For selected complete traces, use the newly filtered manifest created with repeated `--trace-id` arguments.
3. For datasets and experiment evaluations, reuse the applicable inventory manifest and run `scripts/migrate_data.py import`, then `verify`. Use the newly filtered manifest created with repeated `--dataset <name-or-id>` arguments when the user selected datasets. Use `--prefix <value>` during import to avoid destination name collisions.
4. Only report a nonempty migration complete when both applicable verification commands return `verified`. Keep original manifests for evidence and recovery. Report unsupported or differing records explicitly.

Use `--env-file <path>` on each command when the user has configured a local file. Use `--project <name>` to set the destination without modifying their environment. See the [migration reference](references/migration.md) for resume and troubleshooting.

While running, keep the user informed at stage changes and during long waits. Distinguish installing dependencies, exporting, uploading, waiting for AX indexing, and verifying readback. The verify command emits redacted progress JSON on stderr and final results on stdout. Report available elapsed time and found/expected counts; partial counts describe completed readback windows, not total indexed spans. If there is no new progress, do not invent counts or imply verified success. Do not retry uploads just because verification is slow.

## Preserve and report

Preserve original span/trace IDs, parents, historical timestamps, span kinds, input/output, sessions, token counts, and attributes. The trace helper stores original attributes, events, and timestamp strings in AX metadata for preservation checks.

The data helper preserves each Phoenix dataset revision as an AX dataset version, keeps nested input/output/metadata as canonical JSON rather than flattening it, maps source example IDs to AX-assigned IDs, and imports historical experiment task outputs plus stored evaluation score, label, explanation, and provenance metadata. It does not rerun evaluators or call an LLM. Phoenix evaluator definitions, prompts, dataset/experiment tags, arbitrary attachments, and span/trace/session annotations are not yet migrated. Experiments whose referenced examples are absent from the imported latest dataset stop with an explicit error.

Do not change historical timestamps to make traces appear in a recent-time UI filter. Do not label a successful upload as a verified migration. The helper does not guarantee server-side ingestion idempotency: reconcile uncertain submissions through readback rather than blindly retrying them.

Summarize source and destination, exported/imported/verified counts, and any differences or unverified outcomes. Keep raw exports, manifests, and credentials local and ignored by version control. Report core fields stored in AX separately from values preserved only in metadata.
