# Arize Skills

Skills that guide AI coding agents to help you add observability, run experiments, and optimize prompts for your LLM applications.

These skills encode the workflows we've refined building the [Arize](https://arize.com) platform and helping teams debug LLM apps in production. They handle the `ax` CLI flags, data shape quirks, and multi-step recipes so you don't have to.

Works with Cursor, Claude Code, Codex, Windsurf, and [40+ other agents](https://github.com/nicepkg/agent-skills).

## New to Arize? Start Here

**Adding tracing to your app** — give your coding agent this prompt:

> Follow the instructions from https://arize.com/docs/PROMPT.md and ask me questions as needed.

This walks through a two-phase flow: analyze your codebase for LLM providers and frameworks, then add Arize AX tracing with the right instrumentors. No skill installation needed.

**Already have traces?** Give your agent this prompt to install the skills and start debugging:

> Install the Arize skills plugin from https://github.com/Arize-ai/arize-skills, then use the arize-trace skill to export and analyze recent traces from my project. Summarize any errors or latency issues you find.

## Installation

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

### Option 3: Claude Code plugin

```
/plugin marketplace add Arize-ai/arize-skills
/plugin install arize-skills@Arize-ai-arize-skills 
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

**Option B — Profile with flags** (persistent, agent-friendly):
```bash
# Create a new profile
ax profiles create --api-key YOUR_API_KEY

# Update an existing profile (patches only what you specify)
ax profiles update --api-key NEW_API_KEY
ax profiles update --region us-east-1b
```

Running `ax profiles create` without flags launches an interactive wizard instead.

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
| [arize-evaluator](skills/arize-evaluator/SKILL.md) | Create LLM-as-judge evaluators, run evaluation tasks, and set up continuous monitoring. |
| [arize-ai-provider-integration](skills/arize-ai-provider-integration/SKILL.md) | Create and manage LLM provider credentials (OpenAI, Anthropic, Azure, Bedrock, Vertex, and more). |
| [arize-annotation](skills/arize-annotation/SKILL.md) | Create and manage annotation configs (categorical, continuous, freeform); bulk-annotate project spans via the Python SDK. |
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
| `--skill <name>` | Only install/uninstall specific skills — repeatable (e.g. `--skill arize-trace --skill arize-dataset`) |
| `--yes` | Skip confirmation prompts |
| `--list` | List all available skills and exit |
| `--uninstall` | Remove previously installed skill symlinks |

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

## Testing Skills

`tests/run_skill.py` is an interactive test harness that runs a skill end-to-end using the Claude Agent SDK. It creates a temporary workspace, passes in your Arize credentials, and streams the agent's output.

```bash
python tests/run_skill.py --skill arize-trace --prompt "Export trace abc123"
```

> [!WARNING]
> **Configure `.claude/settings.json` before running the test harness**
>
> The test harness uses Claude Code's `bypassPermissions` mode, which **skips all interactive
> approval prompts**. This is safe because the agent runs in a sandboxed temporary workspace —
> but **only** if your `settings.json` has a denylist blocking dangerous shell commands.
>
> **Without this, `bypassPermissions` gives the agent unrestricted shell access.**
>
> Add the following to `.claude/settings.json` in this repo (create it if it doesn't exist):
>
> ```json
> {
>   "permissions": {
>     "deny": [
>       "Bash(rm -rf*)",
>       "Bash(curl*)",
>       "Bash(wget*)",
>       "Bash(ssh*)",
>       "Bash(scp*)",
>       "Bash(git push*)",
>       "Bash(sudo*)",
>       "Bash(chmod*)",
>       "Bash(chown*)"
>     ]
>   }
> }
> ```

## Links

- [Arize Documentation](https://docs.arize.com)
- [Arize REST API Reference](https://docs.arize.com/arize/api-reference/rest-api)
- [ax CLI (arize-ax-cli)](https://github.com/Arize-ai/arize-ax-cli)
- [OpenInference Semantic Conventions](https://github.com/Arize-ai/openinference)

## License

Apache 2.0
