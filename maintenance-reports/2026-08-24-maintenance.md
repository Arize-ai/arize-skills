# Skills Maintenance Report — 2026-08-24

**Repo:** [Arize-ai/arize-skills](https://github.com/Arize-ai/arize-skills) @ `5dfbe64` (main)
**CLI audited against:** `arize-ax-cli` **0.31.1** (latest on PyPI), installed and interrogated via recursive `ax --help`
**Skills before:** 14 · **Skills after:** 15

All local quality checks pass after the changes: `scripts/validate_skills.py`, `scripts/validate_manifests.py`, codespell, line endings, and Vally lint (15/15 skills).

---

## 1. Broken / outdated skills

### Fixed: nonexistent `-p` profile flag documented in 10 skills

`references/ax-profiles.md` told agents that any `ax` command accepts a `-p NAME` flag to select a profile, with the example `ax spans export PROJECT -p work`. **No such flag exists** — verified against `ax --help` and `ax spans export --help` on 0.31.1. There is no global `--profile`/`-p` option and no per-command equivalent; profile selection is stateful via `ax profiles use`. Any agent copying this example would have failed with an unrecognized-option error.

Replaced with the correct stateful form in all 10 copies:

```bash
ax profiles use work
ax spans export PROJECT
```

Files: `skills/{arize-admin,arize-ai-provider-integration,arize-annotation,arize-dataset,arize-evaluator,arize-experiment,arize-instrumentation,arize-prompt-optimization,arize-prompts,arize-trace}/references/ax-profiles.md`

### Fixed: wrong flag name in arize-evaluator

`skills/arize-evaluator/SKILL.md` used `--include-explanations` (plural) in two places while every working example and `references/cli-reference.md` used the singular `--include-explanation`. The CLI accepts the **singular** form. Fixed both occurrences:

- `skills/arize-evaluator/SKILL.md:380` (Best Practices §5 heading)
- `skills/arize-evaluator/SKILL.md:421` (troubleshooting row)

### Fixed: drift between duplicated reference copies

- `skills/arize-admin/references/ax-setup.md` had drifted from the 9 identical sibling copies (cosmetic wording only). Re-synced to the canonical text — all 10 copies are now byte-identical.
- `skills/arize-instrumentation/references/ax-profiles.md` carried a vaguer API-key location ("navigating to the settings page") and omitted `ax profiles validate` from its verify step. Both corrected. This file is *intentionally* specialized (it covers `arize-otel` SDK env vars and links to its own `regions-and-endpoints.md`), so the specialization was preserved — only the two factual gaps were closed.

### Checked clean

Every Markdown link and relative path across all 15 skills resolves. No `scripts/` directories exist under any skill, so there was nothing to check for runnability. External `arize.com/docs/...` links are well-formed with no stale version paths. Every other `ax <group> <subcommand>` and spot-checked flag used anywhere in the repo exists in 0.31.1.

---

## 2. CLI commands not yet covered by a skill

This was the top-priority output of the audit. Full 0.31.1 command tree mapped against all skills.

### Fixed — new skill written: `ax integrations`

**`ax integrations` had zero coverage across all 14 skills.** This is a genuinely new top-level command group: comparing PyPI wheels, `ax/commands/integrations.py` does not exist in 0.29.0 and does exist in 0.31.1 — it landed in the four releases since the repo's last CLI sync. It is *distinct* from `ax ai-integrations` (which `arize-ai-provider-integration` owns): `ai-integrations` stores LLM provider credentials for evaluators, while `integrations` manages account-level `LLM` and `AGENT` integrations, the latter registering a customer-hosted agent endpoint Arize calls for replay.

Added **`skills/arize-integrations/`** (`SKILL.md` + `references/ax-profiles.md` + `references/ax-setup.md`), covering `list`, `get`, `create llm`, `create agent`, `update llm`, `update agent`, and `delete`, with provider-conditional flag requirements, the per-type name-uniqueness rule (`--type` needed when addressing by name), and an explicit disambiguation block against `ax ai-integrations` at the top. 132 lines / ~895 words. Registered in the README skill table.

### Fixed — `ax traces list` now documented

`arize-trace` documented `ax traces export` exhaustively but never mentioned `ax traces list`, despite `arize-trace` being the designated tracing skill; the command's only appearance in the whole repo was one unexplained line in an unrelated skill. Added a **Browse Traces** section to `skills/arize-trace/SKILL.md` positioning it as the cheap "find a trace ID first" step ahead of an export, with its flags and the list → export flow.

### Fixed — the two "run an experiment" paths are now connected

`ax experiments run` (local Python task, in `arize-experiment`) and `ax tasks create-run-experiment` (platform-side hosted task, in `arize-evaluator/references/cli-reference.md`) are two different ways to run an experiment that no skill reconciled — an agent reading either one would not know the other existed. Added a disambiguation callout to `skills/arize-experiment/SKILL.md` explaining which to pick and pointing at the other route.

### Deliberately left uncovered (not defects)

- **`ax skills install` / `ax skills clear`** — already documented in `README.md:62-65`. These are install-time actions a human takes to set up this repo, not workflows an agent should invoke mid-task; a skill telling an agent to install skills for itself would be actively wrong.
- **`ax auth login` / `ax auth logout`** — `arize-admin` correctly tells agents to inform the user of this option and *not* run it themselves. Browser-based OAuth is a human action; that is the right security posture, not a gap.
- **`ax upgrade`** — covered where it is actually needed, in the `references/ax-setup.md` troubleshooting path.

### Remaining partial coverage (not addressed this run — candidates for next audit)

These subcommands exist and work, but are documented thinly. None are broken; each is a depth gap rather than a correctness problem:

| Command | State |
|---------|-------|
| `ax evaluators create-code-evaluator` (+ `-version`, `update`, `delete`, `list-versions`, `get-version`) | `arize-evaluator`'s two main workflows walk through **template/LLM-judge** evaluators only; code evaluators get one conceptual paragraph. The largest remaining gap. |
| `ax annotation-queues assign-record` / `delete-records` | One-line examples each, no flag detail or assignment semantics |
| `ax datasets update-examples` / `delete-examples` | `arize-dataset` labels both "uncommon" and defers to `--help` |
| `ax tasks update` / `delete` / `wait-for-run` | Exist only in `arize-evaluator/references/cli-reference.md`, never surfaced in a SKILL.md workflow |
| `ax profiles list` / `use` / `delete` | Now correct after the `-p` fix above, but the shared reference still centers on initial setup rather than multi-profile management |

### Duplicate / overlapping coverage

The repo is well-factored here. The three batch-annotate commands (`ax spans annotate`, `ax datasets annotate-examples`, `ax experiments annotate-runs`) are each fully documented in exactly one owning skill, with `arize-annotation` tabulating and linking rather than restating — a clean split. Only minor redundancy found: `arize-evaluator` re-derives a small table of span attribute paths that `arize-trace`'s span column reference already owns authoritatively. Low risk (not contradictory), left as-is.

---

## 3. Version drift

**No incorrect version floors found.** Every `compatibility:` floor with an explicit version was checked against actual CLI command history by diffing wheels from 0.20.0 → 0.31.1, and each either maps precisely to the feature it gates or is harmlessly conservative:

| Skill | Floor | Verdict |
|-------|-------|---------|
| `arize-trace` | ≥ 0.23.0 | Exact — `ax spans delete` landed in 0.23.0 |
| `arize-admin` | ≥ 0.27.0 | Exact — `ax resource-restrictions list` landed in 0.27.0 |
| `arize-annotation` | ≥ 0.27.0 | Exact — `annotation-configs update` landed in 0.27.0 |
| `arize-dataset` | ≥ 0.27.0 | Exact — `datasets update-examples` landed in 0.27.0 |
| `arize-experiment` | ≥ 0.27.0 | Conservative — nothing in the skill requires 0.27.0; floor looks copied from a sibling. Harmless, left alone. |
| `arize-evaluator`, `arize-ai-provider-integration`, `arize-prompt-optimization`, `arize-instrumentation-health` | none stated | Vague but not wrong |
| `arize-span-routing` | `arize-otel ≥ 0.11.0` | Different dependency, out of scope |

`version.txt` (1.2.0) is the skills-repo package version, not a CLI version, and is consistent across all plugin manifests — release-please keeps these in sync.

**The real drift is coverage, not floor numbers.** The last repo-wide "sync all skills for ax CLI" changelog entry ([CHANGELOG.md:37](../CHANGELOG.md), release 1.1.0) targeted **v0.21.0**, and no floor references anything past 0.27.0, while PyPI is at **0.31.1**. The concrete consequence of that lag was the entirely-missing `ax integrations` group, now fixed. The new `arize-integrations` skill states `≥ 0.31.1`, the release the command appeared in.

---

## 4. Token footprint

All 15 SKILL.md files were already under the 500-line cap the validator enforces, but the heaviest exceeded the ~5000-token guidance in `AGENTS.md` because they use dense table/code lines rather than short prose — line count understated their real load cost. Two heaviest were trimmed by moving always-loaded reference material into on-demand `references/`.

### Ranked, with changes applied

| Skill | Words before | Words after | Change |
|-------|-------------|-------------|--------|
| **arize-trace** | 3726 (389 ln) | **3051 (310 ln)** | **−18%** |
| **arize-experiment** | 3559 (485 ln) | **2779 (380 ln)** | **−22%** |
| arize-evaluator | 3502 (448 ln) | 3502 | not trimmed — see below |
| arize-prompts | 2978 (403 ln) | 2978 | borderline, left |
| arize-prompt-optimization | 2859 (469 ln) | 2859 | borderline, left |
| arize-dataset | 2617 | 2617 | ok |
| arize-compliance-audit | 2544 | 2544 | ok |
| arize-admin | 2058 | 2058 | ok |
| arize-annotation | 1826 | 1826 | ok |
| arize-ai-provider-integration | 1567 | 1567 | ok |
| arize-instrumentation | 1119 | 1119 | ok |
| arize-span-routing | 1106 | 1106 | ok |
| *arize-integrations (new)* | — | *895* | new, deliberately lean |
| arize-link | 719 | 719 | ok |
| arize-instrumentation-health | 713 | 713 | ok |

`arize-experiment` also dropped 105 lines, moving it well clear of the 500-line cap it was approaching (485).

### What was moved out

**`arize-trace`** → new `skills/arize-trace/references/spans-cli.md`:
- `ax spans export` flags table
- `ax traces export` flags table
- `ax spans annotate` flags table
- the entire **Filter Syntax Reference** section (column table, operators, examples, tips), whose column list substantially duplicated the existing `references/span-columns.md`. SKILL.md keeps a 2-line filter summary with the three most common expressions and a pointer.

Net: the new section documenting `ax traces list` was added *and* the file still shrank 18%.

**`arize-experiment`** → new `skills/arize-experiment/references/experiments-cli.md`:
- flag tables for all 8 subcommands (`list`, `get`, `export`, `create`, `run`, `list-runs`, `delete`, `annotate-runs`), plus the `get` response-field table

→ new `skills/arize-experiment/references/inference-template.py`:
- the 30-line inline multi-provider Python inference template, now a real file an agent can copy directly rather than transcribe out of prose

Workflows, schemas, the silent-failure warnings about `example_id` / inline evaluations, and troubleshooting all stayed in SKILL.md — those are the parts an agent needs without a second fetch.

### Cross-skill duplication — assessed, deliberately not consolidated

`references/ax-profiles.md` is byte-identical across 10 skills and `references/ax-setup.md` across 10. Consolidating them into a shared `skills/_shared/` directory was considered and **rejected as unsafe**: `install.sh` symlinks or copies each skill directory *individually* (`install_skill()`, install.sh:206-225), and `ax skills install` does the same per-skill. A `../_shared/…` link would dangle the moment a single skill is installed, and `scripts/validate_skills.py` requires relative link targets to resolve inside the skill directory. Per-skill self-containment is a deliberate constraint of the distribution model, so the duplication is the correct trade-off.

The mitigation applied instead was **fixing the drift** (see §1) so the copies stay identical. A `scripts/check.sh` assertion that all copies of a shared reference file are byte-identical would catch future divergence automatically — worth considering, not added this run.

Similarly, the ~2-line Prerequisites/Security block repeated in 7 SKILL.md files was left in place: it is a security instruction ("never read `.env` files", "never ask the user to paste secrets into chat") whose value depends on being in the always-loaded body rather than behind an on-demand fetch. ~14 lines total is a cheap price for that.

---

## Summary of changes

**Added**
- `skills/arize-integrations/` — new skill for the uncovered `ax integrations` command group
- `skills/arize-trace/references/spans-cli.md` — extracted flag + filter reference
- `skills/arize-experiment/references/experiments-cli.md` — extracted flag reference
- `skills/arize-experiment/references/inference-template.py` — extracted inference template
- `ax traces list` section in `skills/arize-trace/SKILL.md`
- `ax experiments run` vs `ax tasks create-run-experiment` disambiguation in `skills/arize-experiment/SKILL.md`
- README skill-table row for `arize-integrations`

**Fixed**
- nonexistent `-p` profile flag in 10 × `references/ax-profiles.md`
- `--include-explanations` → `--include-explanation` (2 ×, `arize-evaluator/SKILL.md`)
- drift in `arize-admin/references/ax-setup.md` and `arize-instrumentation/references/ax-profiles.md`

**Trimmed**
- `arize-trace/SKILL.md` −18% words / −79 lines
- `arize-experiment/SKILL.md` −22% words / −105 lines

**Removed/deprecated:** nothing. No skill was found obsolete or duplicative enough to retire.
