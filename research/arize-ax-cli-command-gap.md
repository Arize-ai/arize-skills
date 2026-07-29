# arize-ax-cli command coverage gap report

Research date: 2026-07-28

## Scope and methodology

This report compares the published `arize-ax-cli` command reference with every
Markdown file below `skills/` in this repository. A command is **covered** when
its executable command path appears in a skill or that skill's `references/`
files; it is **missing** when the current PyPI reference documents the command
but no such local occurrence exists. This is documentation coverage, not a
claim that an agent could never infer or construct a command.

The published package assessed is `arize-ax-cli` 0.27.0, uploaded 2026-07-22.
PyPI identifies the wheel and source distribution as version 0.27.0 and gives
the source-distribution SHA-256 below. The PyPI project description is the
first-party command reference used for the command inventory.

Primary published sources:

- https://pypi.org/project/arize-ax-cli/ (version 0.27.0, upload date, command reference)
- https://pypi.org/project/arize-ax-cli/#files (PyPI source artifact `arize_ax_cli-0.27.0.tar.gz`; SHA-256 `a293fad0e91392e8815427b5f1930ae7225a6140fecf53b95bf8a473932148d7` as published by PyPI)
- https://github.com/Arize-ai/arize-ax-cli (first-party source repository linked by PyPI)

Local inventory method: `rg` across `skills/**/*.md`, including reference
files. The repository's own compatibility notes establish that most skills
only require CLI >=0.19.0, rather than pinning to the assessed 0.27.0 release;
see `skills/arize-admin/SKILL.md:7` and
`skills/arize-dataset/references/ax-setup.md:7-24`.

## Published command taxonomy

The 0.27.0 reference documents these command families: profiles; AI
integrations; annotation configs; annotation queues; API keys; cache; resource
restrictions; datasets; evaluators; experiments; organizations; projects;
prompts; roles; spaces; skills; spans; tasks; traces; and users. The PyPI
reference groups its primary command documentation at:

- configuration/profiles: https://pypi.org/project/arize-ax-cli/#configuration
- annotation queues, API keys, cache, resource restrictions, datasets:
  https://pypi.org/project/arize-ax-cli/#commands
- evaluators and experiments:
  https://pypi.org/project/arize-ax-cli/#evaluators
- organizations, projects, prompts:
  https://pypi.org/project/arize-ax-cli/#organizations
- roles, spaces, skills, spans, tasks, traces, users:
  https://pypi.org/project/arize-ax-cli/#roles

## Exact missing commands

The following documented executable command paths have no occurrence anywhere
under local `skills/` at the research date:

| Family | Missing command path(s) | Published evidence |
| --- | --- | --- |
| Profiles | `ax profiles list`; `ax profiles use`; `ax profiles delete` | PyPI configuration command table: https://pypi.org/project/arize-ax-cli/#configuration |
| Annotation configs | `ax annotation-configs update freeform`; `ax annotation-configs update continuous`; `ax annotation-configs update categorical` | PyPI documents the three typed `update` leaf commands: https://pypi.org/project/arize-ax-cli/#annotation-configs |
| Annotation queues | `ax annotation-queues add-records` | PyPI queue commands: https://pypi.org/project/arize-ax-cli/#annotation-queues |
| Cache | `ax cache clear` | PyPI cache section: https://pypi.org/project/arize-ax-cli/#cache |
| Resource restrictions | `ax resource-restrictions list` | PyPI resource-restrictions section: https://pypi.org/project/arize-ax-cli/#resource-restrictions |
| Datasets | `ax datasets update-examples`; `ax datasets delete-examples` | PyPI dataset examples commands: https://pypi.org/project/arize-ax-cli/#datasets |
| Experiments | `ax experiments run`; `ax experiments list-runs` | PyPI experiments section: https://pypi.org/project/arize-ax-cli/#experiments |
| Organizations | `ax organizations delete` | PyPI organizations section: https://pypi.org/project/arize-ax-cli/#organizations |
| Projects | `ax projects update` | PyPI projects section: https://pypi.org/project/arize-ax-cli/#projects |
| Skills installer | `ax skills install`; `ax skills clear` | PyPI skills section: https://pypi.org/project/arize-ax-cli/#skills |
| Spans | `ax spans delete` | PyPI spans section: https://pypi.org/project/arize-ax-cli/#spans |

This yields 18 missing executable leaf-command paths. These are the actionable
gaps. The most material ones are example-level dataset
mutation, local experiment execution, profile switching, cache management, and
the CLI's own context-skill installer.

Two published top-level options are also absent from `skills/`, but are not
counted as commands: `ax --install-completion` and `ax --show-completion`.

## Matched command coverage

The principal CRUD and operational paths are already represented locally:

| Family | Local evidence | Coverage result |
| --- | --- | --- |
| AI integrations | `skills/arize-ai-provider-integration/SKILL.md:184-256` | list, get, create, update, delete |
| Annotation configs and queues | `skills/arize-annotation/SKILL.md:61-221` | config list/create/get/delete; queue list/get/create/update/delete/list-records/annotate/assign/delete-records |
| API keys | `skills/arize-admin/SKILL.md:236-258` | list, create, create-service-key, refresh, revoke |
| Dataset core CRUD | `skills/arize-dataset/SKILL.md` (command occurrences at 100-231) | list, get, create, append, update, delete, export |
| Evaluators | `skills/arize-evaluator/references/cli-reference.md:28-302` | evaluator CRUD, versions, template evaluators, and code evaluators |
| Tasks | `skills/arize-evaluator/references/cli-reference.md:335-404` | list/get/create/create-evaluation/create-run-experiment/update/delete/trigger/list-runs/get-run/wait/cancel |
| Admin hierarchy | `skills/arize-admin/SKILL.md:91-293` | users; organization list/get/create/update/membership; spaces; roles; role bindings; restriction mutations; project list/get/create/delete |
| Prompts | `skills/arize-prompts/SKILL.md:82-321` | prompt CRUD, versions, labels, duplication |
| Traces and exports | `skills/arize-prompt-optimization/SKILL.md:394`; `skills/arize-trace/SKILL.md` | `ax traces list` plus existing span/trace export workflows |

## Ambiguous or intentionally excluded cases

1. **`ax auth login` / `ax auth logout`.** These occur in both
   `skills/arize-admin/SKILL.md:87` and
   `skills/arize-instrumentation/SKILL.md:137`. They are covered locally, but
   the PyPI README's command taxonomy does not give them a dedicated section.
   They are therefore excluded from the gap list.

2. **`ax role-bindings list`.** The local admin skill documents create/get/
   update/delete (`skills/arize-admin/SKILL.md:194-215`) but not `list`.
   The assessed PyPI 0.27.0 command reference also omits a Role Bindings
   section, so it cannot be classified as a published-command gap from this
   artifact. Verify against `ax role-bindings --help` in a 0.27.0 installation
   before adding it.

3. **Annotation-queue `add-records`.** Local queue creation accepts initial
   records (`skills/arize-annotation/SKILL.md:151-166`), but that is not the
   separate published command to add records after queue creation; it remains
   a real command-path gap.

4. **Examples versus command paths.** The report does not treat missing flag
   combinations or examples as missing commands. For example, local skills
   cover `ax spans export` and `ax traces list`, though they do not reproduce
   every filtering/output option in the PyPI reference.

5. **Version drift.** Local skill compatibility floors (generally 0.19.0) mean
   agents may encounter installations older than the 0.27.0 commands assessed
   here. Any implementation should state the required minimum version for a
   newly added command rather than assuming all installed CLIs are current.

6. **Global completion options.** `ax --install-completion` and
   `ax --show-completion` are published root options rather than subcommands.
   They are reported separately above so the command-gap count remains about
   executable command paths.

## Recommended follow-up

Add focused reference sections rather than broad command dumps: put the
dataset-example mutations in `arize-dataset`, local execution and run listing
in `arize-experiment`, profile and cache operations in a shared setup
reference, queue additions in `arize-annotation`, span deletion in
`arize-trace`, organization deletion and project updates in `arize-admin`, and
installer guidance in the repository README or a dedicated CLI-management
skill.
