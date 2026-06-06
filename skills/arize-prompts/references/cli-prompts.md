# ax prompts — CLI reference

Consult when you need full flag lists or edge cases. Official docs: https://arize.com/docs/api-clients/cli/prompts

---

## `ax prompts list`

List prompts in a space.

```bash
ax prompts list [--space SPACE] [--name FILTER] [--limit N] [--cursor CURSOR] [--output FILE]
```

| Option | Description |
|--------|-------------|
| `--space` | Space name or ID |
| `--name` | Case-insensitive substring filter on prompt name |
| `--limit` | Max results (default 15) |
| `--cursor` | Pagination cursor |

---

## `ax prompts create`

Create a prompt with an initial version.

```bash
ax prompts create \
  --name NAME \
  --space SPACE \
  --provider PROVIDER \
  --input-variable-format FORMAT \
  --messages JSON_OR_PATH \
  [--commit-message MSG] \
  [--description DESC] \
  [--model MODEL]
```

| Option | Description |
|--------|-------------|
| `--name` | Unique prompt name within the space |
| `--space` | Space name or ID |
| `--provider` | **Required.** `openAI`, `anthropic`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `gemini`, `custom` |
| `--input-variable-format` | `f_string` (default for `{variable}` placeholders — use without asking the user), `mustache` for `{{variable}}`, or `none` |
| `--messages` | Path to JSON file or inline JSON array of message objects |
| `--commit-message` | Initial version message (default: `Initial version`). Same concept as Hub **Version description (optional)** on first save. |
| `--description` | Optional prompt-level description (Hub **Description (optional)** on the prompt) |
| `--model` | Default model for this version. CLI may allow omission; the main **SKILL.md** for this skill requires always passing an explicit `--model` when proposing `create` commands. |

**Tags:** Prompt Hub lets you set comma-separated **Tags (optional)** on the new-prompt save form. There is no `--tags` (or similar) on `ax prompts create` in current CLI help — add tags in the UI after create, or document them for the user to paste.

---

## `ax prompts get`

Get a prompt by name or ID. Without `--version-id` or `--label`, returns the latest version.

```bash
ax prompts get NAME_OR_ID [--space SPACE] [--version-id ID] [--label LABEL]
```

---

## `ax prompts update`

Update prompt description only (not messages or model).

```bash
ax prompts update NAME_OR_ID [--space SPACE] --description DESC
```

---

## `ax prompts delete`

Delete a prompt and **all** versions. Irreversible.

```bash
ax prompts delete NAME_OR_ID [--space SPACE] [--force]
```

---

## `ax prompts list-versions`

```bash
ax prompts list-versions NAME_OR_ID [--space SPACE] [--limit N] [--cursor CURSOR]
```

---

## `ax prompts create-version`

Add a new immutable version to an existing prompt.

```bash
ax prompts create-version NAME_OR_ID \
  --provider PROVIDER \
  --input-variable-format FORMAT \
  --messages JSON_OR_PATH \
  [--space SPACE] \
  [--commit-message MSG] \
  [--model MODEL]
```

| Option | Description |
|--------|-------------|
| `--provider` | **Required.** Same enum as `create`: `openAI`, `anthropic`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `gemini`, `custom` |
| `--input-variable-format` | Same as `create` (default `f_string` for `{variable}`) |
| `--messages` | Updated messages JSON for this version |
| `--commit-message` | Same concept as Hub **Save New Version** → **Version description (optional)** (CLI default: `New version`) |
| `--model` | Default model for this version — **always pass explicitly** per the main **SKILL.md** in this skill (confirm if unknown). |
| `--space` | Required when `NAME_OR_ID` is a prompt name |

---

## `ax prompts get-version-by-label`

Resolve which version a label points to.

```bash
ax prompts get-version-by-label NAME_OR_ID --label LABEL [--space SPACE]
```

---

## `ax prompts set-version-labels`

Set labels on a **version ID**. Replaces **all** existing labels on that version with the provided list.

```bash
ax prompts set-version-labels VERSION_ID --label L1 [--label L2 ...]
```

---

## `ax prompts remove-version-label`

Remove one label from a version (does not delete the version).

```bash
ax prompts remove-version-label VERSION_ID --label LABEL
```

---

## Messages JSON shape

Must be a non-empty JSON array. Each object needs `role`; optional fields include `content`, `tool_call_id`, `tool_calls`.

Example:

```json
[
  {"role": "system", "content": "You are a helpful assistant for {company}."},
  {"role": "user", "content": "Answer the question: {question}"}
]
```
