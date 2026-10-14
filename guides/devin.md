# Installing Arize Skills for Devin

[Devin](https://devin.ai) loads skills in the [Agent Skills](https://agentskills.io/specification) format, the same `SKILL.md` format this repo ships, and it can install a Claude Code plugin directly, which this repo is. So Arize skills work in Devin unchanged.

Setup depends on where Devin runs:

- **[Devin app](#devin-app)** (app.devin.ai): sessions run on Devin's cloud machine, so the `ax` CLI goes in Devin's environment settings and you create an Arize profile in each session.
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

### 3. Create your Arize profile in each session

`ax` authenticates only through a profile, and every Devin session starts from a fresh snapshot with no profile. Create one at the start of each session that uses the skills, in a terminal you open yourself, so the API key never passes through Devin:

1. In the session, open the **IDE** tab and open a new terminal in VS Code ([session tools](https://docs.devin.ai/work-with-devin/devin-session-tools)). Don't type into one of Devin's shell terminals: Devin runs its commands there and logs their output.
2. Run `ax profiles create` and enter an API key from [app.arize.com/admin](https://app.arize.com/admin) → **API Keys** when the wizard prompts for it.
3. Tell Devin the profile is ready.

Don't store the key as a Devin Secret. Devin binds secrets into the commands it runs, so the agent can read them. Don't create the profile in the blueprint either: anything a build writes is saved into the snapshot that every session in your organization starts from.

Name your Arize space and project in your prompts. If you don't name a space, the skills use `ax spaces list` and ask you to pick one when there are several.

### 4. Verify

After creating the profile, ask:

> Run `ax profiles show` and `ax spaces list` to confirm the Arize CLI can authenticate. Then use the arize-trace skill to export and summarize the most recent traces from project `my-project` in space `my-workspace`.

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

Create an `ax` profile once with the interactive wizard. Run it in your own terminal, not through Devin: the wizard prompts for your API key, so the key never appears in a command, your shell history, or Devin's context. The profile is stored locally and used by every session:

```bash
ax profiles create
```

If the wizard reports `Detected ARIZE_API_KEY` and asks to create the config from environment variables, answer **No**, or `unset ARIZE_API_KEY` and start again. Otherwise the profile reads the key from your environment on every run, where Devin can read it too.

Name your Arize space and project in your prompts. If you don't name a space, the skills check `ax spaces list` and ask you to pick one when there are several.

See [Authentication](../README.md#authentication) in the README for more profile options, including on-prem deployments.

### 4. Verify

Run `ax --version && ax profiles show` in your terminal, then start `devin` in your project and ask:

> Use the arize-trace skill to export and summarize the most recent traces from project `my-project` in space `my-workspace`.

## Troubleshooting

- **Skills don't appear in the Devin app.** Open the plugin's details sheet in Customize and check that the skills are listed. After a change, click **Plugin settings → Reindex plugins** and start a new session.
- **Skills don't appear in the CLI.** Run `devin plugins list`. If the plugin is missing, check that you're signed in (`devin auth login`). If it's stale, run `devin plugins update arize-skills`.
- **Plugin shows as blocked.** An organization or enterprise policy forbids it. Ask the policy owner to add `Arize-ai/arize-skills` to `optionalPlugins` or `requiredPlugins`.
- **`ax: command not found`.** In the Devin app, the blueprint step didn't run or `~/.local/bin` isn't on `PATH`; rebuild the snapshot. In the CLI, run `uv tool update-shell` and open a new terminal.
- **`No active profile configured`.** `ax` has no profile, and setting `ARIZE_API_KEY` doesn't create one. In the Devin app, a profile lasts only for the session it was created in, so create it again in each new session ([step 3](#3-create-your-arize-profile-in-each-session)). In the CLI, run `ax profiles create` in your own terminal.
- **Authentication errors with a profile.** Run `ax profiles show` to see which profile is active. To replace a wrong key, create a new profile with the wizard (`ax profiles create NAME`); it becomes the active one.

For how Devin finds and runs skills, see Devin's [Skills guide](https://docs.devin.ai/product-guides/skills) and [Plugins guide](https://docs.devin.ai/product-guides/plugins).
