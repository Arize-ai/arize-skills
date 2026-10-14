# Installing Arize Skills for Devin

[Devin](https://devin.ai) loads skills in the [Agent Skills](https://agentskills.io/specification) format, the same `SKILL.md` format this repo ships, and it can install a Claude Code plugin directly, which this repo is. So Arize skills work in Devin unchanged.

This guide covers Devin's local agents: [Devin Desktop](https://docs.devin.ai/desktop/getting-started) (with the Devin Local agent) and the [Devin CLI](https://docs.devin.ai/cli/index). Both run on your machine and share the same plugins.

## 1. Install the skills

Sign in with `devin auth login`, then:

```bash
devin plugins install Arize-ai/arize-skills          # your personal plugins: Devin Desktop and the CLI
devin plugins install Arize-ai/arize-skills --local  # or: this machine only
devin plugins info arize-skills                      # list the skills it provides
```

Plugin skills are namespaced: invoke one as `/arize-skills:arize-trace`, or describe the task and Devin picks the right skill. Update with `devin plugins update arize-skills` and remove with `devin plugins remove arize-skills`.

## 2. Set up `ax`

The skills use the `ax` CLI. Install it and create a profile on your machine as described in the README's [Prerequisites](../README.md#prerequisites), the same as for any other agent.

## Troubleshooting

- **Skills don't appear.** Run `devin plugins list`. If the plugin is missing, check that you're signed in (`devin auth login`). If it's stale, run `devin plugins update arize-skills`.
- **Skills don't appear in Devin Desktop.** Check that the conversation uses the Devin Local agent (agent selector, bottom right).
- **Plugin shows as blocked.** An organization or enterprise policy forbids it. Ask the policy owner to add `Arize-ai/arize-skills` to `optionalPlugins` or `requiredPlugins`.

For how Devin finds and runs skills, see Devin's [Skills](https://docs.devin.ai/cli/extensibility/skills/overview) and [Plugins](https://docs.devin.ai/cli/extensibility/plugins/overview) docs.
