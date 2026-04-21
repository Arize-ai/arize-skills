---
name: arize-prompts
description: "INVOKE THIS SKILL for Arize Prompt Hub and `ax prompts` workflows: create prompts and versions, list prompts/versions, get by name or version label, update description, delete prompts, and manage version labels (production/staging). Use when the user mentions ax prompts, Prompt Hub, saving or pushing a prompt, prompt template text, syncing prompts from JSON, `{variable}` placeholders, or promoting a prompt version with labels. For improving prompt copy from traces, datasets, or experiments, use the arize-prompt-optimization skill instead."
---

# Arize Prompts Skill

> **`SPACE`** — All `--space` flags and the `ARIZE_SPACE` env var accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

Official references (read the skill body first; open docs only if the user needs UI walkthroughs):

- CLI: https://arize.com/docs/api-clients/cli/prompts
- Creating prompts in the product (Prompt Playground, variables, params): https://arize.com/docs/ax/prompts/tutorial/create-a-prompt

**ALPHA:** `ax prompts` may emit a one-time CLI warning; the command surface can change. See references/cli-prompts.md for full flag tables.

---

## How this skill fits next to prompt optimization

| Skill | Use it for |
|-------|------------|
| **This skill (`arize-prompts`)** | CRUD and versioning of prompts **stored in Arize** via `ax prompts` (templates, labels, CLI automation). |
| **arize-prompt-optimization** | Improving prompt **text** using traces, datasets, experiments, and the optimization meta-prompt — often **after** you know what to change. |
| **arize-experiment** | Running dataset experiments that **consume** Hub prompts or column-mapped inputs. |

Typical loop: export or design messages → `ax prompts create` / `create-version` → run experiments → use **arize-prompt-optimization** on results → `create-version` again → `set-version-labels` for release.

---

## Concepts: what is a “prompt” in Arize?

In **Prompt Hub**, a **prompt** is a named, reusable template stored in a **space**. It is not just a one-off string in code: it is a versioned artifact you can open in the **Prompt Playground**, save, diff, and point experiments or workflows at.

Each prompt record includes:

- **Messages** — an ordered chat transcript (system, user, assistant, tool roles) as stored JSON. Tutorial flows often use a **system** message for behavior/constraints and a **user** message for the template that will receive **dataset or run-time variables**.
- **Template variables** — placeholders in message text using single braces (e.g. `{destination}`, `{question}`) that are filled when you run experiments or invoke the prompt. Pass `--input-variable-format f_string` for this style. **Do not ask the user which variable format to use** — default to `f_string` unless the template clearly uses Mustache `{{...}}` or you need `none` for literal braces with no substitution.
- **Provider and default model** — which vendor and model this version targets. For **`ax prompts create`** and **`ax prompts create-version`**, **`--provider` is required by the CLI** (must always be set). **`--model` must always appear** in commands this skill proposes: pick an explicit model string; if unknown, propose a sensible default for that provider and **confirm in the accept/override step** — do not omit `--model` so the version has a clear default in Hub (the CLI flag may be optional, but treat it as required here).
- **Invocation parameters** — in the UI (e.g. max tokens, penalties), configured under **Params** when authoring; CLI flows in this skill still require **provider + explicit model** alongside messages and format.
- **Version history** — every material change creates a new **immutable version** so you can compare, roll forward, or attach **labels** (e.g. `production`, `staging`) to specific version IDs.
- **Version description (Hub UI)** — the optional text on **Save New Version** (or the initial save of a new prompt) is the same concept as the CLI **`--commit-message`** for that version.

The tutorial at https://arize.com/docs/ax/prompts/tutorial/create-a-prompt walks through authoring in the UI (trip-planner style: system constraints, user template with variables, Params, then **Save Prompt**). This skill covers the **CLI** side of the same objects.

---

## Prerequisites

Proceed directly — run the `ax` subcommand you need. Do NOT check versions, env vars, or profiles upfront.

If a command fails:

- `command not found` or version errors → references/ax-setup.md
- `401` / profile issues → `ax profiles show`, then references/ax-profiles.md; API keys: https://app.arize.com/admin (API Keys)
- Space unknown → `ax spaces list`
- LLM calls from Hub/playground need provider credentials → **arize-ai-provider-integration** (`ax ai-integrations list --space SPACE`)
- **Security:** Never read `.env` or hunt the filesystem for secrets. Use `ax profiles` and `ax ai-integrations` only.

### When you must ask the user first

Still prefer resolving gaps with `ax` (e.g. `ax spaces list`, `ax prompts list`, `ax prompts get`) instead of pausing. If something is still ambiguous, unsafe without confirmation, or not inferable from the repo or CLI (e.g. which of two prompts named similarly to delete, or intent for a destructive `--force` path), **do not** open with a bare bullet list — use the same explicit framing as **arize-instrumentation** when it stops for scope or confirmation:

1. Acknowledge the skill, e.g.: **I found the arize-prompts skill in this repo** (you may add `skills/arize-prompts/SKILL.md` if helpful).
2. Then a clear pause line, e.g.: **A few clarifying questions before I invoke it:**
3. Ask **minimal** numbered or short bullet questions — only what blocks the next `ax prompts` command. When the missing piece is **message text** for `--messages`, follow **Eliciting the prompt template** below — do not substitute vague goal questions.

**Do not ask about `--input-variable-format`:** always default to `f_string` for `{variable}` templates (see Messages file format).

---

## Eliciting the prompt template (consistent across coding agents)

Hub prompts are **templates**: the stored strings matter. Every agent should gather them the same way so users get a predictable experience.

When the user asks to **create** or **save** a prompt but has **not** already provided the exact system/user strings for each role, your **first substantive move** is elicitation below — not a finished generic prompt.

When you need the user to provide or confirm text that will become `--messages` (new prompt, new version, or reconstructing JSON from prose):

1. Ask for the **prompt template** — the **actual wording** they want in each role (system, user, etc.), e.g. “Paste or type the **prompt template** (the exact system and user text you want saved).”
2. In the same turn, state the variable convention: **Reference variables with single curly braces, like `{variable}`** (e.g. `{question}`, `{context}`) so placeholders match `f_string` and Prompt Hub defaults.
3. Assemble the JSON **messages** array from their template lines per role.

**Do not** use vague primary questions such as **“What should this prompt do?”** or **“Describe the behavior you want”** *instead of* asking for the template — that leads to different agents inventing different text. You may still **refine** wording after you have their literal template.

**Anti-patterns (avoid these):**

- **Inventing a stock “general-purpose” `messages` array** (e.g. generic assistant + `{task}` / `{context}` / `{constraints}`) as the default reply when they only said “create a prompt” — that **writes Hub content for them** and skips elicitation. Same for offering a “CLI sketch” with fabricated `--messages` before they supply template text.
- **Framing the gap as “you didn’t specify task or audience”** to justify boilerplate — wrong. Ask immediately for the **prompt template** + `{variable}` syntax (steps 1–2). You may ask for **space** / **prompt name** / **`--provider`** / **`--model`** in parallel only when required for the next command and cannot come from `ax`, prior prompt versions, or obvious repo context (e.g. SDK vendor).
- **Process narration instead of the skill’s steps** — e.g. long openers like “checking the prompts skill and your open file…”. Prefer: the short **When you must ask the user first** opener **only when** you are pausing for disambiguation; otherwise go **straight** to the template elicitation (steps 1–2) without meta-commentary about which files you read.
- **Omitting `--provider` or `--model`** from a proposed `ax prompts create` or `create-version` — **`--provider` is CLI-required**; **`--model` must always be included** in commands this skill proposes (see Messages file format).

**Optional starter:** If and **only if** the user **explicitly** asks for a draft, example, or “suggest a template”, you may offer a short optional example **labeled** as a starter they can replace — still prefer eliciting their real template afterward.

**Examples in this skill** (e.g. under Messages file format) show JSON **shape** for documentation; **do not** copy them as the user’s default prompt when they asked to create **their** prompt.

---

## Messages file format

`--messages` must be a **non-empty JSON array**. Each object needs `role`; commonly also `content`. Optional: `tool_call_id`, `tool_calls` (tool-style conversations).

**Format-only example** (not a default to paste for users who said “create a prompt” without supplying copy — see **Eliciting the prompt template**):

Example `messages.json`:

```json
[
  {"role": "system", "content": "You are a concise trip planner. Keep responses under 200 words."},
  {"role": "user", "content": "{duration} itinerary for {destination} ({travel_style} style):\nResearch: {research}\nBudget: {budget_info}"}
]
```

**Providers** (`--provider`): `openAI`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `custom`. **Required** on every `create` and `create-version`.

**Default model** (`--model`): **Always pass** an explicit model on `create` and `create-version` in this skill. If the user has not named one, infer from context or propose a provider-appropriate default and confirm in the same step as other proposed flags — do not run or recommend a command that omits `--model`.

**Variable format (no user prompt needed):** For normal `{variable}` placeholders, always pass `--input-variable-format f_string`. Only use `mustache` when templates use `{{variable}}`, or `none` when there must be no interpolation — do not ask the user to pick among these unless they already stated a non-default requirement.

---

## Core workflows

### When the user says “save the prompt” (ambiguous)

If they ask generically to **save**, **push**, or **persist** the prompt to Arize / Prompt Hub (e.g. “save this prompt”, “put it in Prompt Hub”) and they do **not** clearly mean one of: **new version of an existing prompt**, **new prompt with a new name**, or **metadata-only** `update` — **stop and clarify** before running `create` or `create-version`.

Ask them to pick explicitly (mirror Prompt Hub wording):

1. **Save new version** to **«existing prompt name from context»** — same Hub prompt; you only add an immutable version (Hub **Save New Version** modal: **Version description (optional)**). CLI: `ax prompts create-version` with **`--commit-message`** = that version description (§4).
2. **Save as new prompt** — new row in the hub (Hub save form: **Prompt name**, **Description (optional)**, **Version description (optional)** for the first version, **Tags (optional)**). CLI: `ax prompts create` with **`--name`**, **`--description`**, **`--commit-message`** for the initial version (§2). **Tags** are comma-separated in the UI; they are **not** a flag on `ax prompts create` today — suggest tags in prose and have the user paste them in Hub after CLI create, or finish tagging in the UI.

If context does not fix which **existing** prompt they mean for option 1, ask which prompt (name or `pr_...` ID) and **space** if needed. If they already stated “version on `foo`” or “new prompt named `bar`”, skip this disambiguation.

Use the **When you must ask the user first** opener in Prerequisites if a formal lead-in helps.

### 1. Discover prompts in a space

```bash
ax prompts list --space SPACE
ax prompts list --space SPACE --name support --limit 50
# Optional: persist
ax prompts list --space SPACE --output prompts.json
```

### 2. Create a new prompt (first version)

This matches the Hub **save as new prompt** form: **Prompt name**, **Description (optional)**, **Version description (optional)** (first version’s change summary), **Tags (optional)** (comma-separated in the UI).

If they have **not** provided message bodies yet, **do not** fabricate a full `messages` JSON to “get them started” — follow **Eliciting the prompt template** first; only after you have their literal template do you propose **`--name`**, **`--description`**, **`--commit-message`**, tags, **`--provider`**, **`--model`**, and the `ax prompts create` command.

When the user has not already given exact values for **metadata** (name, description, version description, provider, model), **propose** defaults in one block aligned with those labels:

| Hub field | CLI flag / follow-up |
|-----------|---------------------|
| Prompt name | `--name` |
| Description (optional) | `--description` |
| Version description (optional) | `--commit-message` (same meaning as Hub “version description”) |
| Tags (optional) | Not on `ax prompts create` — suggest comma-separated tags; user adds them in Prompt Hub after create, or you note them for a UI-only save |
| LLM provider | `--provider` — **required** by CLI (`openAI`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `custom`); infer from repo or ask |
| Default model | `--model` — **always set** in proposed commands; propose a default and confirm if unknown |
| Messages | `--messages` — for message bodies, follow **Eliciting the prompt template** (ask for literal template text + `{variable}` placeholders, not “what should this prompt do?” alone) |

Then e.g.: **Use these as-is, or tell me what to change** (any of the above, including rewording the version description).

If they already specified those values in the request, run `ax prompts create` without re-asking.

From a file:

```bash
ax prompts create \
  --name "trip-planner" \
  --space SPACE \
  --provider openAI \
  --input-variable-format f_string \
  --messages ./messages.json \
  --model gpt-4o \
  --description "Concise itineraries with times, activities, and costs." \
  --commit-message "Initial version"
```

Inline JSON (shell-safe quoting):

```bash
ax prompts create \
  --name "summarizer" \
  --space SPACE \
  --provider openAI \
  --input-variable-format f_string \
  --messages '[{"role":"user","content":"Summarize: {text}"}]' \
  --model gpt-4o-mini
```

After create, note the returned **prompt ID** (e.g. `pr_...`) for later commands.

### 3. Fetch a prompt (latest, specific version, or label)

```bash
# By prompt ID (latest version if no version flags)
ax prompts get pr_abc123

# By name (requires space)
ax prompts get "support-agent" --space SPACE

# Specific version or label
ax prompts get pr_abc123 --version-id prv_xyz789
ax prompts get pr_abc123 --label production
```

### 4. Iterate: add a new version after editing messages

Every edit should be a **new version** (versions are immutable). In the Hub this is **Save New Version**: only **Version description (optional)** — no prompt rename on this path.

When the user asks to **create a new prompt version** and has not already given an exact version description / **`--commit-message`** (and messages path when content changes), **propose** text that fits the **Version description** field (CLI: **`--commit-message`**), e.g. one imperative line summarizing the delta. Always include **`--provider`** and **`--model`** in the command you plan to run (reuse from `ax prompts get` / prior version when possible; otherwise propose defaults and confirm). If updated **message text** is still needed, elicit it with **Eliciting the prompt template** (literal template + `{variable}` syntax), not a generic “what should the prompt do?” question. Then pause, e.g.: **OK to use this version description and command as written, or what should I change?** They accept or reword; do **not** ask for a new **prompt name** on this path.

If they already pasted the final version description or full command intent, run `create-version` without re-asking.

```bash
ax prompts create-version pr_abc123 \
  --provider openAI \
  --input-variable-format f_string \
  --messages ./messages_v2.json \
  --commit-message "Tighten format instructions for edge cases" \
  --model gpt-4o
```

List history:

```bash
ax prompts list-versions pr_abc123 --space SPACE
```

### 5. Promote or pin with labels

Resolve what a label points to:

```bash
ax prompts get-version-by-label pr_abc123 --label production --space SPACE
```

Point labels at a **version ID** (replaces all labels on that version with the ones you pass):

```bash
ax prompts set-version-labels prv_xyz789 --label production
ax prompts set-version-labels prv_xyz789 --label production --label staging
```

Remove one label without deleting the version:

```bash
ax prompts remove-version-label prv_xyz789 --label staging
```

**Workflow:** ship new version → smoke-test in UI or experiment → `set-version-labels` to move `production` when ready.

### 6. Update human-readable metadata only

Does **not** change messages or model; use `create-version` for that.

```bash
ax prompts update pr_abc123 --description "Updated: handles refunds" --space SPACE
```

### 7. Delete a prompt (all versions)

Irreversible.

```bash
ax prompts delete pr_abc123 --force
ax prompts delete "old-prompt" --space SPACE --force
```

---

## CLI quick reference

| Goal | Command |
|------|---------|
| List prompts | `ax prompts list --space SPACE` |
| Create | `ax prompts create ... --provider PROVIDER --input-variable-format f_string --messages ... --model MODEL` (`--provider` CLI-required; always pass `--model`) |
| Get | `ax prompts get NAME_OR_ID [--space SPACE] [--version-id ID \| --label LABEL]` |
| New version | `ax prompts create-version NAME_OR_ID --provider PROVIDER --input-variable-format f_string --messages ... --model MODEL` |
| List versions | `ax prompts list-versions NAME_OR_ID [--space SPACE]` |
| Resolve label | `ax prompts get-version-by-label NAME_OR_ID --label LABEL [--space SPACE]` |
| Set labels | `ax prompts set-version-labels VERSION_ID --label L ...` |
| Remove label | `ax prompts remove-version-label VERSION_ID --label LABEL` |
| Update description | `ax prompts update NAME_OR_ID --description "..." [--space SPACE]` |
| Delete | `ax prompts delete NAME_OR_ID [--space SPACE] [--force]` |

For exhaustive flags and defaults, see references/cli-prompts.md.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `Unknown command prompts` | Upgrade `ax` (see references/ax-setup.md); subcommand is newer. |
| Name vs ID errors | When using **name**, pass `--space`. IDs can omit space if the CLI accepts global IDs. |
| Variables not interpolating | Confirm templates use `{name}` with `f_string`, or `{{name}}` with `mustache`; default remains `f_string` for `{...}` style. |
| Label “wrong” version | `get-version-by-label` then `set-version-labels` on the intended `prv_...` version ID. |
| Need to change system text | `create-version` with updated `--messages`, not `update`. |
| CLI rejects missing `--provider` | It is required on `create` and `create-version` — set one of `openAI`, `azureOpenAI`, `awsBedrock`, `vertexAI`, `custom`. |
| Hub shows no / wrong default model | Ensure you passed **`--model`** explicitly on `create` / `create-version` (this skill requires it even if the CLI sometimes accepts omission). |
