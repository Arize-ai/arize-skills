# ax prompts — CLI notes

Semantics and sequencing rules for `ax prompts`: which identifier each command takes, what `update` can change, what a new version requires, and how labels resolve. [SKILL.md](../SKILL.md) holds the step-by-step workflows; this file is the reference an agent checks before composing a call.

For flag names, types, defaults and which options are required, run `ax prompts --help` for the command list and `ax prompts <sub> --help` for one command — those are current for the installed CLI. Official docs: https://arize.com/docs/api-clients/cli/prompts

---

## Which identifier each command takes

Ten subcommands split into two groups, and passing the wrong kind of identifier is the most common failure.

**Prompt-scoped** — take a prompt `name_or_id` and accept `--space`: `get`, `update`, `delete`, `create-version`, `list-versions`, `get-version-by-label`. (`list` and `create` take `--space` directly.)

**Version-scoped** — take a **version ID** as their positional argument and have no `--space` flag at all: `set-version-labels`, `remove-version-label`. A prompt name or prompt ID fails here. Get the version ID from `ax prompts list-versions <prompt> --space SPACE -o json`, or from the version block of `ax prompts get`.

Pass `--space` whenever the identifier is a **name**. An ID resolves without it.

## `update` changes the description and nothing else

`ax prompts update` exposes exactly one content flag, `--description`. It cannot rename a prompt, and it cannot touch messages, model, provider, or invocation parameters — those live on versions, which are immutable once created.

So route an edit by what is changing:

- Description → `ax prompts update <prompt> --space SPACE --description "..."`.
- Messages, model, provider, or any version parameter → `ax prompts create-version` (below). The old version stays addressable by its ID.
- A different name → create a separate prompt with `ax prompts create` and delete the old one if it is no longer wanted. Labels do not carry over.

## A new version is a full re-specification, not a patch

`create-version` requires `--provider`, `--input-variable-format`, and `--messages` on every call, the same three that `create` requires. It does not inherit them from the current version, so a call passing only the field being changed is rejected for the missing required options.

To change one field, read the current version first and carry the others forward:

```bash
ax prompts get PROMPT_NAME --space SPACE -o json > current.json
# reuse provider, input-variable-format and messages from current.json,
# changing only what this version is meant to change
ax prompts create-version PROMPT_NAME \
  --space SPACE \
  --provider OPEN_AI \
  --input-variable-format F_STRING \
  --messages ./messages.json \
  --model gpt-4o \
  --commit-message "Switch judge model to gpt-4o"
```

`--commit-message` defaults to `New version`, which makes version history unreadable — always set it to what changed.

## Resolving a version on `get`

`ax prompts get` returns the **latest** version when neither `--version-id` nor `--label` is passed. Pass `--label production` to read what a label currently points at, or `--version-id` for one exact version. Use `get-version-by-label` when only the version identity is needed rather than the whole prompt.

## Labels move between versions, and setting them replaces

A label is a pointer to one version, so promoting is a label operation rather than a new version.

`set-version-labels` **replaces every label on that version** with the list passed, so repeating `--label` is how multiple labels are set in one call. To add a label while keeping the existing ones, read the version's current labels first and pass the full intended set. To drop a single label and leave the rest, use `remove-version-label`, which takes one `--label`.

---

## The prompts provider enum is narrower than `ax ai-integrations`

`ax prompts create` and `ax prompts create-version` accept `OPEN_AI`, `AZURE_OPEN_AI`, `AWS_BEDROCK`, `VERTEX_AI`, `ANTHROPIC`, `CUSTOM`.

`ax ai-integrations create` accepts those six plus `NVIDIA_NIM`, `GEMINI`, `LITELLM`, `FIREWORKS`, and `TOGETHER_AI`. So a space can hold a Gemini (or LiteLLM, Fireworks, Together, NVIDIA NIM) integration that has no matching `ax prompts --provider` value. When the model the user names is served by one of those, confirm which `--provider` value to store on the prompt version before running `create` or `create-version`.

---

## Choosing `--input-variable-format`

`--input-variable-format` is required on both `create` and `create-version`. Pick the value from the literal placeholder syntax in the message strings:

| Placeholder written in the message text | Value to pass |
|-----------------------------------------|---------------|
| `{name}` — single braces                | `F_STRING`    |
| `{{name}}` — double braces              | `MUSTACHE`    |
| braces meant literally, no substitution | `NONE`        |

Default to `F_STRING`; the main **SKILL.md** for this skill makes single braces the house convention and says not to ask the user about the format.

---

## Prompt Hub UI wording → CLI flag

| Prompt Hub UI field | CLI flag |
|---------------------|----------|
| **Version description (optional)** on the first save | `--commit-message` on `create` |
| **Version description (optional)** on **Save New Version** | `--commit-message` on `create-version` |
| **Description (optional)** on the prompt | `--description` on `create` or `update` |
| **Tags (optional)** on the save form | no CLI equivalent — see below |

---

## Tags are set in the Hub UI

Prompt Hub takes comma-separated **Tags (optional)** on its save form. `ax prompts create` and `ax prompts update` expose no tag flag, so add tags in the Hub UI after the prompt exists, or list the suggested tags in prose for the user to apply.

---

## Messages JSON shape

Must be a non-empty JSON array. Each object needs `role`; optional fields include `content`, `tool_call_id`, `tool_calls`.

Example:

```json
[
  {"role": "SYSTEM", "content": "You are a helpful assistant for {company}."},
  {"role": "USER", "content": "Answer the question: {question}"}
]
```
