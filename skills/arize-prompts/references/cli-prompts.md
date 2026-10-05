# ax prompts — CLI notes

Flag names, arguments, types, defaults, and which options are required are authoritative in `--help` for the installed CLI:

- Command list → run `ax prompts --help`
- One command's flags → run `ax prompts <sub> --help`, e.g. `ax prompts create --help`

This file carries only what `--help` does not cover: the provider-enum scope, the variable-format mapping, the Prompt Hub wording map, tags, and the messages JSON shape. Official docs: https://arize.com/docs/api-clients/cli/prompts

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
