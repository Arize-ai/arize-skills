# Authoring Guidelines for AI Agents

## Skill files are read by AI, not humans

Skill files (SKILL.md, references/, etc.) are loaded as context for AI agents. Follow these rules when editing them, per the [Agent Skills specification](https://agentskills.io/specification):

- **Use Markdown links for every file and doc reference** — write `See [the reference guide](references/REFERENCE.md)`, not a bare path or URL. This is the syntax in the spec's File references example; standardize on it repo-wide for consistency. Keep the target a relative path from the skill root, one level deep (e.g. `references/EXAMPLES.md`), and avoid deeply nested reference chains. (Runnable commands and code stay literal — `scripts/extract.py` in a run instruction, `go get …`, code blocks — they are commands, not links.)
- **Additional documentation goes in `references/`** — supplementary docs (e.g., `ax-profiles.md`, `ax-setup.md`, `EXAMPLES.md`) belong in the `references/` subdirectory, per the Agent Skills specification.
- **Keep `SKILL.md` focused** — the full body loads on activation; the spec recommends staying under ~5000 tokens / 500 lines and moving detail into `references/`.

## Quality checks

CI ([.github/workflows/quality-checks.yml](.github/workflows/quality-checks.yml)) runs these on every PR. Run the no-Node subset locally with `bash scripts/check.sh` before pushing:

- **`scripts/validate_skills.py`** — per-skill structure: frontmatter, `name` (kebab-case, 3–64 chars, matches the folder, unique), `description` length, declared `assets` exist and are ≤5 MB, Markdown links with relative targets resolve, `SKILL.md` ≤500 lines, and a warning for bare doc paths that should be Markdown links (the rule above).
- **`scripts/validate_manifests.py`** — `version.txt` matches every plugin manifest (release-please keeps them in sync; this proves they never drift) and metadata (`name`, `description`, `keywords`, `license`, `repository`) is consistent and within limits.
- **codespell** ([.codespellrc](.codespellrc)) and **line endings** ([scripts/check_line_endings.sh](scripts/check_line_endings.sh)) — spelling and LF hygiene.
- **Vally lint** ([eng/vally-lint.mjs](eng/vally-lint.mjs)) — `@microsoft/vally`'s static skill lint (spec-compliance + valid references). Needs Node: `npm install --no-save @microsoft/vally@0.10.0 && node eng/vally-lint.mjs`.
- **Plugin install smoke test** — `claude plugin validate .` plus a marketplace add/install of the plugin.
