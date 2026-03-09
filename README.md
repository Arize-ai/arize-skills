# Arize Skills

Skills that guide AI coding agents to help you add observability, run experiments, and optimize prompts for your LLM applications.

These skills encode the workflows we've refined building the [Arize](https://arize.com) platform and helping teams debug LLM apps in production. They handle the `ax` CLI flags, data shape quirks, and multi-step recipes so you don't have to.

Works with Cursor, Claude Code, Codex, Windsurf, and [40+ other agents](https://github.com/nicepkg/agent-skills).

## New to Arize? Start Here

**Adding tracing to your app** — give your coding agent this prompt:

> Follow the instructions from https://arize.com/docs/PROMPT.md and ask me questions as needed.

This walks through a two-phase flow: analyze your codebase for LLM providers and frameworks, then add Arize AX tracing with the right instrumentors. No skill installation needed.

**Already have traces?** Install the skills below, then start with `arize-trace` to export and debug spans, or `arize-experiment` to run evals against a dataset.

## Installation

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

### Option 3: Claude Code plugin

```
/plugin add https://github.com/Arize-ai/arize-skills
```

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

### Authentication

**Option A — Environment variables** (CI/CD, quick start):
```bash
export ARIZE_API_KEY="your-api-key"       # from https://app.arize.com/admin > API Keys
export ARIZE_SPACE_ID="U3BhY2U6..."       # base64 space ID from your Arize URL
```

**Option B — Interactive profile** (persistent):
```bash
ax profiles create
```

**Option C — Direct TOML file** (scripted/non-interactive):
```bash
mkdir -p ~/.arize && cat > ~/.arize/config.toml << 'EOF'
[profile]
name = "default"

[auth]
api_key = "your-api-key"

[output]
format = "table"
EOF
```

> **Note:** `ax profiles create` is interactive-only — no `--api-key` flag exists. For CI/CD or scripted setup, use Option A or C.

### Verify

```bash
ax --version && ax profiles show 2>&1
```

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
| `--skill <name>` | Only install specific skills — repeatable (e.g. `--skill arize-trace --skill arize-dataset`) |
| `--yes` | Skip confirmation prompts |
| `--list` | List all available skills and exit |
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
