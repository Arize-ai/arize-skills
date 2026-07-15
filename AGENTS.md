# Authoring Guidelines for AI Agents

## Skill files are read by AI, not humans

Skill files (SKILL.md, references/, etc.) are loaded as context for AI agents. Follow these rules when editing them, per the [Agent Skills specification](https://agentskills.io/specification):

- **Reference files with relative paths from the skill root, kept one level deep** — e.g. `references/EXAMPLES.md`. Both Markdown-link syntax (`See [the reference guide](references/REFERENCE.md)`, as in the spec's File references example) and bare literal paths (`scripts/extract.py`) are acceptable; the spec places no format restrictions on the body. Use whichever reads clearly, but keep the path relative and shallow. Avoid deeply nested reference chains.
- **Additional documentation goes in `references/`** — supplementary docs (e.g., `ax-profiles.md`, `ax-setup.md`, `EXAMPLES.md`) belong in the `references/` subdirectory, per the Agent Skills specification.
- **Keep `SKILL.md` focused** — the full body loads on activation; the spec recommends staying under ~5000 tokens / 500 lines and moving detail into `references/`.
