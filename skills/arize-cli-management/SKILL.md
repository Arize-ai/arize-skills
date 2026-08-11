---
name: arize-cli-management
description: Manages the ax CLI itself — upgrading it (ax upgrade) and installing or removing the Arize skills bundle for AI coding agents (ax skills install / ax skills clear). Use when the user wants to upgrade ax, install/reinstall Arize's skills for Claude Code, Cursor, Codex, or Windsurf, or remove previously installed Arize skills. Not for Arize resource management (users, spaces, datasets, etc.) — see the other arize-* skills for that.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI.
---

# Arize CLI Management Skill

Manages the `ax` CLI tool itself, not Arize account resources: upgrading the CLI binary, and installing/removing this skills bundle for AI coding agents.

## Upgrade the CLI

```bash
ax upgrade              # auto-detects how ax was installed (pip/pipx/uv)
ax upgrade --pip         # force a specific installer
ax upgrade --pipx
ax upgrade --uv
```

Run this when a command fails with "Subcommand not recognized" or a version-floor error. Check the current version first with `ax --version`.

## Install Arize skills for a coding agent

Downloads skills from this repo (`Arize-ai/arize-skills`) and installs them into an agent's skills directory. Defaults to the current project directory.

```bash
ax skills install                                          # interactive
ax skills install --agent claude-code                      # interactive, one agent
ax skills install --agent claude-code --agent cursor --yes  # non-interactive, needs --agent
ax skills install --global                                  # ~/.claude/skills/ etc. instead of the project dir
ax skills install --force                                   # overwrite existing skills without prompting
```

`--agent` accepts `claude-code`, `cursor`, `codex`, `windsurf` (repeatable). `--yes` requires at least one `--agent`.

## Remove installed Arize skills

Only removes skill directories whose names start with `arize-`; user-created skills are untouched.

```bash
ax skills clear                       # interactive
ax skills clear --agent claude-code --yes
ax skills clear --global
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Subcommand not recognized` | Run `ax upgrade` |
| `ax skills install` finds no agent | Pass `--agent` explicitly; valid values are `claude-code`, `cursor`, `codex`, `windsurf` |
| Install skipped an existing skill | Re-run with `--force` |
