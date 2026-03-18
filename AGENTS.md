# Authoring Guidelines for AI Agents

## Skill files are read by AI, not humans

Skill files (SKILL.md, EXAMPLES.md, etc.) are loaded as context for AI agents, not rendered in a browser. Follow these rules when editing them:

- **No markdown links** — do not use `[text](url)` syntax. Write plain filenames and URLs as literal text. Clickable links add noise and imply browser rendering.
- **No relative path links** — reference sibling files by name only (e.g., `See EXAMPLES.md`, not `[EXAMPLES.md](EXAMPLES.md)`).
