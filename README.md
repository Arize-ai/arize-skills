# Arize Skills

Agent skills for [Arize](https://arize.com) — datasets, experiments, and traces via the `ax` CLI.

Works with Cursor, Claude Code, Codex, Windsurf, and [40+ other agents](https://github.com/nicepkg/agent-skills).

## Quick Start

### Option 1: npx (recommended)

```bash
npx skills add Arize-ai/arize-skills --skill "*" --yes
```

This auto-detects your agent (Cursor, Claude Code, Codex, etc.) and symlinks skills into place.

### Option 2: git clone

**macOS / Linux:**
```bash
git clone https://github.com/Arize-ai/arize-skills.git
cd arize-skills
./install.sh --project ~/my-project
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/Arize-ai/arize-skills.git
cd arize-skills
.\install.ps1 -Project ~\my-project
```

The installer detects installed agents and optionally installs the `ax` CLI. Use `--global` / `-Global` instead to install to `~/.<agent>/skills/`.

## Prerequisites

### Arize CLI (`ax`)

The skills use the `ax` CLI to interact with the Arize API. Install it if you don't have it:

```bash
# Preferred (isolated environment)
uv tool install arize-ax-cli
# or
pipx install arize-ax-cli
# Fallback
pip install arize-ax-cli
```

### API Key

Set up authentication with a profile:

```bash
ax profiles create
```

Or set the `ARIZE_API_KEY` environment variable directly.

## Available Skills

| Skill | Description |
|-------|-------------|
| [arize-trace](skills/arize-trace/SKILL.md) | Export traces and spans by trace ID, span ID, or session ID. Debug LLM application issues. |
| [arize-instrumentation](skills/arize-instrumentation/SKILL.md) | Add Arize AX tracing to an app. Two-phase flow: analyze codebase, then implement instrumentation (uses [Agent-Assisted Tracing](https://arize.com/docs/ax/alyx/tracing-assistant)). |
| [arize-dataset](skills/arize-dataset/SKILL.md) | Create, manage, and download datasets and examples. |
| [arize-experiment](skills/arize-experiment/SKILL.md) | Run and analyze experiments against datasets. |
| [arize-prompt-optimization](skills/arize-prompt-optimization/SKILL.md) | Optimize prompts using trace data, experiments, and meta-prompting. |
| [arize-link](skills/arize-link/SKILL.md) | Generate deep links to traces, spans, and sessions in the Arize UI. |

## Installer Flags

**Bash (`install.sh`):**

| Flag | Description |
|------|-------------|
| `--project <dir>` | **Required.** Target project directory for skill symlinks |
| `--global` | Install to `~/.<agent>/skills/` instead (alternative to `--project`) |
| `--copy` | Copy files instead of symlinking |
| `--force` | Overwrite existing skills |
| `--skip-cli` | Don't install `ax` CLI even if missing |
| `--agent <name>` | Manually specify agent (cursor, claude, codex) — repeatable |
| `--skill <name>` | Only install/uninstall specific skills — repeatable |
| `--yes` | Skip confirmation prompts |
| `--uninstall` | Remove previously installed skill symlinks |
| `--list` | List all available skills and exit |

**PowerShell (`install.ps1`):**

| Flag | Description |
|------|-------------|
| `-Project <dir>` | **Required.** Target project directory for skill symlinks |
| `-Global` | Install to `~/.<agent>/skills/` instead (alternative to `-Project`) |
| `-Copy` | Copy files instead of symlinking |
| `-Force` | Overwrite existing skills |
| `-SkipCli` | Don't install `ax` CLI even if missing |
| `-Agent <name>` | Manually specify agent (cursor, claude, codex) — repeatable |
| `-Skill <name>` | Only install/uninstall specific skills — repeatable |
| `-Yes` | Skip confirmation prompts |
| `-Uninstall` | Remove previously installed skill symlinks |
| `-List` | List all available skills and exit |

## Updating

- **npx path:** `npx skills update`
- **git clone path:** `cd arize-skills && git pull` (symlinks update automatically)

## Links

- [Arize Documentation](https://docs.arize.com)
- [Arize REST API Reference](https://docs.arize.com/arize/api-reference/rest-api)
- [ax CLI (arize-ax-cli)](https://github.com/Arize-ai/arize-ax-cli)
- [OpenInference Semantic Conventions](https://github.com/Arize-ai/openinference)

## License

MIT
