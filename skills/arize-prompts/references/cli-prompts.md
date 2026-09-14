# ax prompts — CLI reference

Consult when you need full flag lists or edge cases. Official docs: https://arize.com/docs/api-clients/cli/prompts

---

## `ax prompts list`

List prompts in a space. Run `ax prompts list --help` for the full flag list.

---

## `ax prompts create`

Create a prompt with an initial version. Run `ax prompts create --help` for the full flag list.

Notes beyond `--help`: `--provider` has no `GEMINI` option (unlike `ax ai-integrations`). `F_STRING` (the default `--input-variable-format`, for `{variable}` placeholders) can be used without asking the user; `MUSTACHE` is for `{{variable}}`. `--commit-message` is the same concept as Prompt Hub's **Version description (optional)** on first save, and `--description` the same as Hub's **Description (optional)**. `--model` is optional in the CLI, but the main **SKILL.md** for this skill requires always passing an explicit `--model` when proposing `create` commands.

**Tags:** Prompt Hub lets you set comma-separated **Tags (optional)** on the new-prompt save form. There is no `--tags` (or similar) on `ax prompts create` — add tags in the UI after create, or document them for the user to paste.

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

Add a new immutable version to an existing prompt. Run `ax prompts create-version --help` for the full flag list.

Notes beyond `--help`: `--provider`/`--input-variable-format` use the same enums as `create`. `--commit-message` is the same concept as Hub's **Save New Version** → **Version description (optional)**. Per the main **SKILL.md** in this skill, always pass `--model` explicitly (confirm with the user if unknown) even though the CLI allows omitting it.

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
  {"role": "SYSTEM", "content": "You are a helpful assistant for {company}."},
  {"role": "USER", "content": "Answer the question: {question}"}
]
```
