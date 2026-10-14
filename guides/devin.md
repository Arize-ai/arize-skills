# Installing Arize Skills for Devin

[Devin](https://devin.ai) loads skills in the [Agent Skills](https://agentskills.io/specification) format, the same `SKILL.md` format this repo ships, and it can install a Claude Code plugin directly, which this repo is. So Arize skills work in Devin unchanged.

Setup depends on where Devin runs:

- **[Devin app](#devin-app)** (app.devin.ai): sessions run on Devin's cloud machine, so the `ax` CLI and your Arize key are configured in Devin's environment settings.
- **[Devin CLI](#devin-cli)**: sessions run on your own machine, so you install `ax` and set up your Arize key locally.

Plugins installed to your personal scope sync between the two, so if you use both, install once and then follow the credential setup for each.

## Devin app

### 1. Install the skills

1. Open [Customize → Plugins](https://app.devin.ai/customize).
2. Click **Add plugin → From repository**.
3. Enter `Arize-ai/arize-skills` and leave the subdirectory empty.
4. Pick a scope: **Personal** (just you), **Organization**, or **Enterprise**. Organization and enterprise installs require admin rights.

New sessions pick up the latest version from `main` automatically. To remove the skills, uninstall from the plugin's details sheet in Customize.

<details>
<summary>Alternative: commit the skills to one repository</summary>

Use this to pin a fixed version to a single codebase. Devin scans every connected repository for `.agents/skills/<name>/SKILL.md`:

```bash
git clone --depth 1 https://github.com/Arize-ai/arize-skills.git /tmp/arize-skills
mkdir -p .agents/skills
cp -R /tmp/arize-skills/skills/arize-* .agents/skills/
git add .agents/skills && git commit -m "Add Arize skills for Devin"
```

To install only some skills, copy just those folders. Copy the folders; don't symlink them. `install.sh` and `npx skills add` create symlinks to a local checkout, and those links break once committed. To update, run the copy again and commit the result. Mention a repository skill with `@skills:arize-trace`.

</details>

### 2. Install `ax` in Devin's environment

Add the [`ax` CLI](https://github.com/Arize-ai/arize-ax-cli) to the `initialize` section of your [blueprint](https://docs.devin.ai/onboard-devin/environment/blueprints) (**Settings → Environment → Blueprints**), so it's included in the snapshot every session starts from:

```yaml
initialize: |
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ~/.local/bin/uv tool install arize-ax-cli
```

If you skip this step, Devin installs `ax` itself the first time a skill needs it. That works, but it repeats in every session.

### 3. Add your Arize credentials as Devin Secrets

On the [Secrets page](https://app.devin.ai/secrets), create these raw [secrets](https://docs.devin.ai/product-guides/secrets):

| Secret | Value |
|--------|-------|
| `ARIZE_API_KEY` | An API key from [app.arize.com/admin](https://app.arize.com/admin) → **API Keys** |
| `ARIZE_SPACE` | Your space name or base64 space ID (find it with `ax spaces list -o json`) |
| `ARIZE_DEFAULT_PROJECT` | *(Optional)* The project to use when a prompt doesn't name one |

Use the **Personal** scope for a key tied to your own account. Use **Organization** only for a shared service key, because every member's sessions can use organization secrets. To limit a key to one repository, add it under that repository's blueprint **Secrets** tab instead.

### 4. Verify

Start a session and ask:

> Run `ax --version && ax profiles show` and confirm the Arize CLI can authenticate. Then use the arize-trace skill to export and summarize the most recent traces from my project.

## Devin CLI

### 1. Install the skills

Sign in with `devin auth login`, then:

```bash
devin plugins install Arize-ai/arize-skills          # personal scope: also available in the Devin app
devin plugins install Arize-ai/arize-skills --local  # or: this machine only
devin plugins info arize-skills                      # list the skills it provides
```

Plugin skills are namespaced: invoke one as `/arize-skills:arize-trace`, or describe the task and Devin picks the right skill. Update with `devin plugins update arize-skills` and remove with `devin plugins remove arize-skills`.

### 2. Install `ax`

```bash
uv tool install arize-ax-cli   # or: pipx install arize-ax-cli
```

### 3. Set up your Arize credentials

Create an `ax` profile once. It's stored locally and used by every session:

```bash
ax profiles create --api-key YOUR_API_KEY
export ARIZE_SPACE="my-workspace"   # add to ~/.zshrc or ~/.bashrc; find it with: ax spaces list -o json
```

Prefer environment variables? Export `ARIZE_API_KEY` and `ARIZE_SPACE` in your shell instead. See [Authentication](../README.md#authentication) in the README for all options, including on-prem deployments.

### 4. Verify

Run `ax --version && ax profiles show` in your terminal, then start `devin` in your project and ask:

> Use the arize-trace skill to export and summarize the most recent traces from my project.

## Troubleshooting

- **Skills don't appear in the Devin app.** Open the plugin's details sheet in Customize and check that the skills are listed. After a change, click **Plugin settings → Reindex plugins** and start a new session.
- **Skills don't appear in the CLI.** Run `devin plugins list`. If the plugin is missing, check that you're signed in (`devin auth login`). If it's stale, run `devin plugins update arize-skills`.
- **Plugin shows as blocked.** An organization or enterprise policy forbids it. Ask the policy owner to add `Arize-ai/arize-skills` to `optionalPlugins` or `requiredPlugins`.
- **`ax: command not found`.** In the Devin app, the blueprint step didn't run or `~/.local/bin` isn't on `PATH`; rebuild the snapshot. In the CLI, run `uv tool update-shell` and open a new terminal.
- **Authentication errors.** In the Devin app, a personal secret only works in sessions you start, and a repository secret only in its own repository. In the CLI, run `ax profiles show` to check which profile and key are active.

For how Devin finds and runs skills, see Devin's [Skills guide](https://docs.devin.ai/product-guides/skills) and [Plugins guide](https://docs.devin.ai/product-guides/plugins).
