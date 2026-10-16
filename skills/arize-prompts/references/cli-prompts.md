# ax prompts — gotchas and messages shape

For flags, arguments, and defaults, run `ax prompts --help` and `ax prompts <sub> --help`. Official docs: https://arize.com/docs/api-clients/cli/prompts

---

## Gotchas

- **`--model`:** the CLI accepts `create` / `create-version` without it, but the Hub then shows no default model. Always pass an explicit `--model`.
- **Tags:** set tags in the Hub UI after `create`; suggest tag values in prose for the user to add.
- **`update`** changes prompt metadata (description) only. Message text, model, and provider change through `create-version`.
- **`set-version-labels`** replaces all existing labels on the version with the `--label` list passed. Use `remove-version-label` to drop a single label.
- **Name vs ID:** pass `--space` whenever `NAME_OR_ID` is a prompt name.

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
