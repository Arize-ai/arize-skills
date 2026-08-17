# Skills Audit — 2026-08-17

Weekly maintenance audit of the skills repo against `arize-ax-cli` (published as `ax`). Verified against the real CLI (installed locally at v0.29.0, the current PyPI latest) rather than static inspection alone. All 14 skills pass `scripts/check.sh` (validate_skills, validate_manifests, codespell, line endings) before and after this pass.

## 1. Broken / outdated skills

**Fixed:**

- **`ax cache clear` referenced a nonexistent command.** All 9 copies of `references/ax-setup.md` (arize-admin, arize-ai-provider-integration, arize-annotation, arize-dataset, arize-evaluator, arize-experiment, arize-prompt-optimization, arize-prompts, arize-trace) told the agent to run `ax cache clear` for "stale or corrupted cache" — there is no `cache` command in the CLI (`ax cache --help` → `No such command 'cache'`). Removed the section from all 9 files.
- **Wrong evaluator flag name.** `skills/arize-evaluator/SKILL.md:156` and `skills/arize-evaluator/references/cli-reference.md:57,74,94` used `--include-explanation` (singular). The real flag, confirmed live against `ax evaluators create-template-evaluator --help`, is `--include-explanations` (plural). Fixed all 4 occurrences.
- **Misleading `assign-record` example.** `skills/arize-annotation/SKILL.md:251-256` showed `ax annotation-queues assign-record NAME_OR_ID RECORD_ID --space SPACE` with no `--email`. Per the live CLI, omitting `--email` entirely *clears* all assignments rather than assigning anyone — the example was a no-op disguised as the happy path. Added `--email reviewer@company.com` and a one-line note on the replace-vs-clear behavior.
- **README missing a skill.** The "Available Skills" table (`README.md`) listed 13 of 14 skills — `arize-instrumentation-health` had no row, description, or link anywhere in the README. Added it.
- **Inconsistent docs host in README.** `README.md` used `docs.arize.com` in the Links section (2 occurrences) while every other doc URL in the repo (15+ occurrences across README and skills) uses `arize.com/docs/...`. Changed the 2 outliers to match.

**Confirmed fine / already correct:**
- `scripts/validate_skills.py` and the internal reference-link scan found no other broken relative links or malformed frontmatter across any of the 14 skills.
- `arize-prompts/SKILL.md:339` explicitly (and correctly) notes there is no `ax prompts duplicate` command — verified absent from the real CLI, so this is the skill being accurate, not a bug.
- `ax auth login`/`ax auth logout` (OAuth PKCE) is documented once in `skills/arize-admin/SKILL.md:87` as an alternative to the API-key profile flow. Thin (one skill, one paragraph) but not missing.

## 2. CLI commands not yet covered by a skill

Full command tree enumerated live via `ax --help` recursively (v0.29.0, 21 top-level command groups, 100+ leaf subcommands) and cross-checked against all 14 skills' actual usage (not just topic-matching).

**Real gaps found (not fixed this round — flagged for a future skill-writing pass):**
- **`ax profiles validate`** — zero mentions anywhere in the repo except one line in `README.md` (on-prem setup section). No skill's `references/ax-profiles.md` troubleshooting flow mentions it, despite it being the command purpose-built to verify a profile; every credential-troubleshooting path instead just re-runs `profiles show`/`create`/`update`. Low effort, worth a follow-up one-line addition across the shared `ax-profiles.md` files.
- **`ax traces list`** — fixed this round. Was undocumented in `arize-trace` (the skill that owns trace workflows); only incidental mention was one example line in an unrelated skill (`arize-prompt-optimization/SKILL.md:394`). Added a short "List Traces" section to `skills/arize-trace/SKILL.md` right before "Export Traces."

**Correctly uncovered (no action needed):**
- `ax skills install` / `ax skills clear` / `ax upgrade` — CLI-lifecycle/meta commands about installing these skills or self-upgrading, not Arize-resource workflows. No skill should cover these.

## 3. Duplicate / overlapping skill coverage

No functional duplication found. The skills cross-reference rather than copy-paste command logic:
- `arize-annotation` defers bulk-annotate commands (`ax spans annotate`, `ax datasets annotate-examples`, `ax experiments annotate-runs`) to `arize-trace`/`arize-dataset`/`arize-experiment` via a pointer table instead of duplicating flag details.
- `arize-instrumentation-health` explicitly delegates all `spans export`/`traces export` usage to `arize-trace`.

The one true repetition is **structural boilerplate**, not conflicting coverage — covered in the token-footprint section below.

## 4. Version drift

Latest `arize-ax-cli` on PyPI: **0.29.0**. Skills repo's own release version (`version.txt`/`plugin.json`/manifests, managed by release-please — a separate number from the CLI): **1.2.0**, internally consistent.

**Fixed:**
- All 9 copies of `references/ax-setup.md` stated a minimum `ax` version of `0.19.0` — except `skills/arize-prompts/references/ax-setup.md`, which was an outlier at `0.14.0`. Normalized to `0.19.0` to match the other 8 (all 9 files are now byte-identical again).

**Flagged, not changed (uncertain without deeper feature-by-feature testing):**
- `compatibility:` frontmatter floors in `skills/arize-admin/SKILL.md:7`, `arize-annotation/SKILL.md:7`, `arize-dataset/SKILL.md:7`, `arize-experiment/SKILL.md:7` (all `≥ 0.27.0`) and `arize-trace/SKILL.md:7` (`≥ 0.23.0`) are 2-6 minor versions behind the current `0.29.0`. These are floor ("≥") constraints, so they won't break on newer CLIs — bumping them without confirming which specific feature justifies each floor risked overstating the real minimum, so left as-is with this note for a maintainer to confirm and bump deliberately.
- `arize-otel` (a different PyPI package — the OTel instrumentation SDK, not `arize-ax-cli`) is pinned at `≥0.11.0`/`0.13.0` in `arize-span-routing` and `arize-instrumentation` — out of scope for this CLI-version check, noted for awareness only.

## 5. Token footprint

Word/line counts measured as a token-cost proxy for each always-loaded `SKILL.md`.

**Before this pass**, three skills were within 30 lines of the CI-enforced 500-line cap (`scripts/validate_skills.py`, `MAX_SKILL_LINES = 500`) — one edit away from breaking CI:

| Skill | Lines before | Lines after | Change |
|---|---|---|---|
| `arize-trace` | 496 | 385 | extracted Span Column Reference (~125 lines) to `references/span-columns.md`; added a short `ax traces list` section (net -111 lines) |
| `arize-experiment` | 485 | 450 | extracted the `infer.py` provider template (~30 lines) to `references/infer-template.py` |
| `arize-prompt-optimization` | 469 | 397 | extracted the Optimization Meta-Prompt (~70 lines) to `references/meta-prompt-template.md` |

All three are now well clear of the cap. The extracted content is unchanged, just moved out of the always-loaded body into on-demand reference files (linked from `SKILL.md` per `AGENTS.md`'s Markdown-link convention).

**Also fixed:** the `ax cache clear` removal above trimmed ~7 lines from each of 9 `ax-setup.md` files (~60 lines repo-wide) as a side effect of the bug fix.

**Flagged, not changed this round** (would need more careful, skill-by-skill editing to avoid losing skill-specific safety instructions):
- **Duplicated Prerequisites boilerplate** — `arize-trace`, `arize-experiment`, `arize-evaluator`, `arize-prompt-optimization`, `arize-dataset`, and `arize-prompts` each ship a `## Prerequisites` section with a mostly-shared opening line and 3-5 near-identical bullets (command-not-found, 401, space-unknown, security). However, several of these sections also interleave skill-specific safety-critical bullets (e.g. `arize-experiment`'s "CRITICAL — Never fabricate outputs," `arize-evaluator`'s "CRITICAL — Never fabricate evaluation results") that must not be lost. A blind merge into a single generic pointer — as a first pass suggested — would risk deleting those warnings. Left for a manual pass that preserves the skill-specific bullets and only consolidates the truly identical ones.
- `arize-evaluator`'s Workflow A (project) and Workflow B (experiment) repeat nearly the same evaluator-creation steps and JSON examples (`SKILL.md:102-264` and `267-343`).
- `arize-prompts` repeats the same `ax prompts create`/`create-version` flag lists in ~5 places.
- `arize-compliance-audit`'s Phase 1 domain checklists (`SKILL.md:111-172`) duplicate content already in its own `references/*.md` files.
- `arize-dataset` repeats the same `--space` name-vs-ID caveat in ~6 flag tables instead of stating it once.

## Files changed this pass

- `README.md` — added missing skill row, fixed docs host inconsistency
- `skills/arize-evaluator/SKILL.md`, `skills/arize-evaluator/references/cli-reference.md` — flag name fix
- `skills/arize-annotation/SKILL.md` — assign-record example fix
- `skills/*/references/ax-setup.md` (9 files) — removed dead `ax cache clear` section, normalized version floor
- `skills/arize-trace/SKILL.md` — added `ax traces list` section, extracted span column reference
- `skills/arize-trace/references/span-columns.md` — new
- `skills/arize-experiment/SKILL.md` — extracted infer.py template
- `skills/arize-experiment/references/infer-template.py` — new
- `skills/arize-prompt-optimization/SKILL.md` — extracted meta-prompt template
- `skills/arize-prompt-optimization/references/meta-prompt-template.md` — new
