# Installing Arize Skills for Devin

[Devin](https://devin.ai) loads skills in the [Agent Skills](https://agentskills.io/specification) format, the same `SKILL.md` format this repo ships, and it can install a Claude Code plugin directly, which this repo is. So Arize skills work in Devin unchanged.

Arize skills use the `ax` CLI. Set it up as described in the README's [Prerequisites](../README.md#prerequisites). The only Devin-specific difference is in the Devin app, covered below.

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

### 2. Set up `ax`

Devin app sessions run on a fresh cloud machine, so nothing you set up on your own machine carries over:

- **Install:** add `ax` to the `initialize` section of your [blueprint](https://docs.devin.ai/onboard-devin/environment/blueprints) (**Settings → Environment → Blueprints**), so every session starts with it:

  ```yaml
  initialize: |
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ~/.local/bin/uv tool install arize-ax-cli
  ```

- **Authenticate:** an `ax` profile lasts only for the session it was created in. At the start of a session, open a terminal in the session's **IDE** tab and run `ax profiles create` there, not in Devin's shell.

## Devin CLI

### 1. Install the skills

Sign in with `devin auth login`, then:

```bash
devin plugins install Arize-ai/arize-skills          # personal scope: also available in the Devin app
devin plugins install Arize-ai/arize-skills --local  # or: this machine only
devin plugins info arize-skills                      # list the skills it provides
```

Plugin skills are namespaced: invoke one as `/arize-skills:arize-trace`, or describe the task and Devin picks the right skill. Update with `devin plugins update arize-skills` and remove with `devin plugins remove arize-skills`.

### 2. Set up `ax`

Install and authenticate `ax` on your machine as described in the README's [Prerequisites](../README.md#prerequisites), the same as for any other agent.

## Troubleshooting

- **Skills don't appear in the Devin app.** Open the plugin's details sheet in Customize and check that the skills are listed. After a change, click **Plugin settings → Reindex plugins** and start a new session.
- **Skills don't appear in the CLI.** Run `devin plugins list`. If the plugin is missing, check that you're signed in (`devin auth login`). If it's stale, run `devin plugins update arize-skills`.
- **Plugin shows as blocked.** An organization or enterprise policy forbids it. Ask the policy owner to add `Arize-ai/arize-skills` to `optionalPlugins` or `requiredPlugins`.
- **`ax: command not found` in the Devin app.** The blueprint step didn't run or `~/.local/bin` isn't on `PATH`; rebuild the snapshot.
- **`No active profile configured` in the Devin app.** Profiles don't carry over between sessions; run `ax profiles create` again in the new session.

For how Devin finds and runs skills, see Devin's [Skills guide](https://docs.devin.ai/product-guides/skills) and [Plugins guide](https://docs.devin.ai/product-guides/plugins).
