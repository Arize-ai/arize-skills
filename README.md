# Arize Skills

Agent skills for [Arize](https://arize.com) — datasets, experiments, and traces via the `ax` CLI.

Works with Cursor, Claude Code, Codex, Windsurf, and [40+ other agents](https://github.com/nicepkg/agent-skills).

## Quick Start

### Option 1: npx (recommended)

```bash
npx skills add Arize-ai/arize-skills --skill '*' --yes
```

This auto-detects your agent (Cursor, Claude Code, Codex, etc.) and symlinks skills into place.

### Option 2: git clone

```bash
git clone https://github.com/Arize-ai/arize-skills.git
cd arize-skills
./install.sh --project ~/my-project
```

The `--project` flag tells the installer where to symlink skills. It detects installed agents and optionally installs the `ax` CLI. Use `--global` instead to install to `~/.<agent>/skills/`.

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

### On-prem / self-hosted Arize

Point the CLI at your deployment with a **single-endpoint** profile (hostname and HTTPS port, usually `443`). Replace the host with the value your operations team provides:

```bash
ax profiles create my-onprem --api-key <key> --single-host arize.yourcompany.com --single-port 443
ax profiles use my-onprem
ax profiles validate
```

For interactive setup, `ax profiles create` also offers **Advanced → Single endpoint**. More options (TOML, Flight/OTLP splits) are documented in the [arize-ax-cli README](https://github.com/Arize-ai/arize-ax-cli/blob/main/README.md#on-premise-deployments).

## Available Skills

| Skill | Description |
|-------|-------------|
| [arize-trace](skills/arize-trace/SKILL.md) | Export traces and spans by trace ID, span ID, or session ID. Debug LLM application issues. |
| [arize-instrumentation](skills/arize-instrumentation/SKILL.md) | Add Arize AX tracing to an app. Two-phase flow: analyze codebase, then implement instrumentation (uses [Agent-Assisted Tracing](https://arize.com/docs/ax/alyx/tracing-assistant)). |
| [arize-dataset](skills/arize-dataset/SKILL.md) | Create, manage, and download datasets and examples. |
| [arize-experiment](skills/arize-experiment/SKILL.md) | Run and analyze experiments against datasets. |
| [arize-prompt-optimization](skills/arize-prompt-optimization/SKILL.md) | Optimize prompts using trace data, experiments, and meta-prompting. |
| [arize-link](skills/arize-link/SKILL.md) | Generate deep links to traces, spans, and sessions in the Arize UI. |

## install.sh Flags

| Flag | Description |
|------|-------------|
| `--project <dir>` | **Required.** Target project directory for skill symlinks |
| `--global` | Install to `~/.<agent>/skills/` instead (alternative to `--project`) |
| `--copy` | Copy files instead of symlinking |
| `--force` | Overwrite existing skills |
| `--skip-cli` | Don't install `ax` CLI even if missing |
| `--agent <name>` | Manually specify agent (cursor, claude, codex) — repeatable |
| `--yes` | Skip confirmation prompts |
| `--uninstall` | Remove previously installed skill symlinks |

## Updating

- **npx path:** `npx skills update`
- **git clone path:** `cd arize-skills && git pull` (symlinks update automatically)

## Links

- [Arize Documentation](https://docs.arize.com)
- [Arize REST API Reference](https://docs.arize.com/arize/api-reference/rest-api)
- [ax CLI (arize-ax-cli)](https://github.com/Arize-ai/arize-ax-cli)
- [OpenInference Semantic Conventions](https://github.com/Arize-ai/openinference)

## License

Apache 2.0
