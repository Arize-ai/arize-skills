# Authoring Guidelines for AI Agents

## Skill files are read by AI, not humans

Skill files (SKILL.md, references/, etc.) are loaded as context for AI agents, not rendered in a browser. Follow these rules when editing them:

- **No markdown links** — do not use `[text](url)` syntax. Write plain filenames and URLs as literal text. Clickable links add noise and imply browser rendering.
- **Use relative paths from skill root** — reference files using relative paths (e.g., `See references/EXAMPLES.md`, not `[EXAMPLES.md](EXAMPLES.md)`).
- **Additional documentation goes in `references/`** — supplementary docs (e.g., `ax-profiles.md`, `ax-setup.md`, `EXAMPLES.md`) belong in the `references/` subdirectory, per the Agent Skills specification.
