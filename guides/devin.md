# Installing Arize Skills for Devin

[Devin](https://devin.ai) loads skills in the [Agent Skills](https://agentskills.io/specification) format, the same `SKILL.md` format this repo ships, so Arize skills work in Devin unchanged. There are two ways to install them:

| Method | Best for | Scope |
|--------|----------|-------|
| [Plugin](#option-1-install-as-a-plugin-recommended) (recommended) | Most users. Gets updates automatically. | Personal, organization, or enterprise. Works in cloud sessions, the Devin CLI, and Devin Desktop |
| [Commit to a repo](#option-2-commit-the-skills-to-a-repository) | Pinning a fixed version to one codebase | Sessions that work in that repository |

After installing, finish the [setup in Devin's environment](#set-up-the-ax-cli-and-credentials) so the skills can call the Arize API.

## Option 1: Install as a plugin (recommended)

Devin can install a Claude Code plugin directly, and this repo is one. Installing it adds every Arize skill at once.

**From the Devin web app:**

1. Open [Customize → Plugins](https://app.devin.ai/customize).
2. Click **Add plugin → From repository**.
3. Enter `Arize-ai/arize-skills` and leave the subdirectory empty.
4. Pick a scope: **Personal** (just you), **Organization**, or **Enterprise**. Organization and enterprise installs require admin rights.

**From the Devin CLI** (you need to be signed in with `devin auth login`):

```bash
devin plugins install Arize-ai/arize-skills          # adds it to your personal plugins (cloud + every machine you sign in to)
devin plugins install Arize-ai/arize-skills --local  # this machine only
devin plugins info arize-skills                      # list the skills it provides
```

Either way, the plugin is synced across cloud sessions, the CLI, and Devin Desktop. Plugin skills are namespaced: invoke one as `/arize-skills:arize-trace`, or just describe the task and Devin picks the right skill.

**Updating:** New cloud sessions pick up the latest `main` automatically. In the CLI, run `devin plugins update arize-skills`. **Removing:** run `devin plugins remove arize-skills`, or uninstall from the plugin's details sheet in Customize.

## Option 2: Commit the skills to a repository

Devin scans every connected repository for `.agents/skills/<name>/SKILL.md` (it also scans `.devin/skills/`, `.claude/skills/`, `.github/skills/`, `.windsurf/skills/`, and `.cognition/skills/`). Copy the skills into your repo and commit them:

```bash
git clone --depth 1 https://github.com/Arize-ai/arize-skills.git /tmp/arize-skills
mkdir -p .agents/skills
cp -R /tmp/arize-skills/skills/arize-* .agents/skills/
git add .agents/skills && git commit -m "Add Arize skills for Devin"
```

To install only some skills, copy just those folders (for example `/tmp/arize-skills/skills/arize-trace`).

Copy the folders; don't symlink them. `install.sh` and `npx skills add` link skills to a local checkout, which works for a local agent but leaves broken links when committed, so Devin's cloud sessions can't read them. To update, run the copy again and commit the result.

Invoke a repository skill by mentioning it in a prompt, for example `@skills:arize-trace`, or let Devin choose one automatically.

## Set up the `ax` CLI and credentials

The skills run the [`ax` CLI](https://github.com/Arize-ai/arize-ax-cli) against your Arize account, so Devin's machine needs the CLI and an API key.

**1. Install `ax` in the environment.** Add it to the `initialize` section of your [blueprint](https://docs.devin.ai/onboard-devin/environment/blueprints) (**Settings → Environment → Blueprints**), so it's included in the snapshot every session starts from:

```yaml
initialize: |
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ~/.local/bin/uv tool install arize-ax-cli
```

If you skip this step, Devin installs `ax` itself the first time a skill needs it. That works, but it repeats in every session.

**2. Add your credentials as [Devin Secrets](https://docs.devin.ai/product-guides/secrets).** On the [Secrets page](https://app.devin.ai/secrets), create these raw secrets:

| Secret | Value |
|--------|-------|
| `ARIZE_API_KEY` | An API key from [app.arize.com/admin](https://app.arize.com/admin) → **API Keys** |
| `ARIZE_SPACE` | Your space name or base64 space ID (find it with `ax spaces list -o json`) |
| `ARIZE_DEFAULT_PROJECT` | *(Optional)* The project to use when a prompt doesn't name one |

Use the **Personal** scope for a key tied to your own account. Use **Organization** only for a shared service key, because every member's sessions can use organization secrets. To limit a key to one repository, add it under that repository's blueprint **Secrets** tab instead.

**3. Verify.** Start a session and ask:

> Run `ax --version && ax profiles show` and confirm the Arize CLI can authenticate.

Then try a real workflow:

> Use the arize-trace skill to export and summarize the most recent traces from my project.

## Troubleshooting

- **Skills don't appear.** For a plugin, open its details sheet in Customize and check that the skills are listed; after a change, click **Plugin settings → Reindex plugins**. For repository skills, confirm the files are on the branch Devin is using, then ask Devin to reload its skills.
- **Plugin shows under "Installed but blocked".** An organization or enterprise policy forbids it. Ask the policy owner to add `Arize-ai/arize-skills` to `optionalPlugins` or `requiredPlugins`.
- **`ax: command not found`.** The blueprint step didn't run or `~/.local/bin` isn't on `PATH`. Rebuild the snapshot, or have Devin run `uv tool install arize-ax-cli` in the session.
- **Authentication errors.** Confirm `ARIZE_API_KEY` is visible to the session. A personal secret only works in sessions you start, and a repository secret only works in its own repository.

For how Devin finds and runs skills, see Devin's [Skills guide](https://docs.devin.ai/product-guides/skills) and [Plugins guide](https://docs.devin.ai/product-guides/plugins).
