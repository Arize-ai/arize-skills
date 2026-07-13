# Agent Install Playbook

This file is the playbook a coding agent follows when a user pastes the Arize
hero prompt:

> Install the Arize skills from https://github.com/Arize-ai/arize-skills and use
> them to add Arize tracing to this application following best practices.

Goal: **one prompt → skills installed → app instrumented → a trace visible in
Arize AX**, with the fewest possible interruptions. Run the whole flow in a
single agent session. Only two things require the user: their Arize credentials,
and a confirmation of the code changes before you apply them.

This document is written to be read by an AI agent, not rendered in a browser.
URLs are literal text; there are no clickable links.

## Step 1 — Install the skills (non-interactive)

Run the install with defaults so the user is never sent through the wizard:

```bash
npx skills add Arize-ai/arize-skills --skill "*" --yes
```

What the flags do, and why these defaults are safe here:

- `--skill "*"` — install all Arize skills. These are first-party Arize skills,
  so there is no reason to make the user hand-pick a subset up front.
- `--yes` — accept the defaults and skip the confirmation prompts, including the
  security summary. Acceptable because every skill is first-party Arize content.
- Agent is **auto-detected** (Cursor, Claude Code, Codex, Copilot, Windsurf, …)
  and skills are symlinked into the **current project** — no scope question.

The CLI still prints its own installation / security / completion screens. That
is expected; you do not need to act on them. When it finishes, the skills are
available in this project — most relevant here is `arize-instrumentation`.

If `npx` is unavailable, fall back to the git-clone installer documented in
README.md ("Option 2: git clone"). Do not block on this — pick whichever install
path works in the current environment and continue.

## Step 2 — Instrument the app

Invoke the **`arize-instrumentation`** skill and follow its two-phase flow. Do
not re-derive instrumentation from scratch — the skill encodes the correct
package names, import order, project-name resource attribute, and per-language
setup. See `skills/arize-instrumentation/SKILL.md`.

In brief, the skill will:

1. **Phase 0 / 1 (read-only analysis):** detect language, package manager, LLM
   providers, frameworks, and any existing OTel setup. It scopes the target
   service (asking you only if a monorepo or entrypoint is genuinely ambiguous),
   then returns a short summary of what it proposes to change.
2. **User confirmation:** the user confirms the Phase 1 summary before any code
   is written. This is the one instrumentation checkpoint we keep by design — do
   not skip it.
3. **Phase 2 (implementation):** install the instrumentation packages, create a
   centralized instrumentation module initialized before any LLM client, and
   reference credentials via environment variables only. Never embed literal
   secret values in generated code.

## Step 3 — Credentials (the one input that can't be eliminated)

The app cannot send traces without an Arize **API key** and **space**. Let the
`arize-instrumentation` skill drive this — it checks for an existing `ax` profile
before asking the user to create one. In short:

- Check for an existing profile: `ax profiles show` (and `ax profiles validate`).
- If none exists, ask the user to run `ax profiles create` (interactive wizard),
  or `ax auth login` for browser-based OAuth (do not run `ax auth login`
  yourself — it opens a browser).
- If `ax` is not installed, see the Prerequisites section of README.md.

Never read `.env` files for secrets, and never print raw credential values.

## Step 4 — Verify a trace landed

Instrumentation is only "done" when a span actually reaches Arize:

1. Run the app (or trigger one real request) so it makes at least one LLM call.
2. Use the **`arize-trace`** skill to confirm the trace arrived, with the
   expected `openinference.span.kind`, `input.value` / `output.value`, and
   parent-child structure.
3. For CLI / short-lived scripts, make sure spans are flushed before exit
   (`force_flush()` then `shutdown()`), or they will never leave the process.

## Edge cases — don't strand the user

The hero prompt promises "one paste → traces." When it can't go cleanly, say so
plainly and give the user the next action:

- **Can't instrument** (unsupported language/framework, unclear monorepo scope,
  no obvious entrypoint): state exactly what's blocking, ask the one question
  that unblocks you, and point to https://arize.com/docs/ax/integrations for the
  manual path. Do not guess and silently instrument the wrong service.
- **Partial success** (skills installed but instrumentation failed midway):
  report what succeeded, what's left, and the exact next step — never leave the
  user with no traces and no next action.
- **Verification fails** (code applied but no spans arrive): distinguish the
  cause instead of retrying blindly — wrong/expired credentials, missing project
  name resource attribute (HTTP 500), exporter not flushed, no traffic yet, or a
  network/collector issue. The Verification section of
  `skills/arize-instrumentation/SKILL.md` has the full triage checklist.

## Path 1 fallback — skills only, no agent

When there is no coding agent to paste this prompt into — CI pipelines, Docker
builds, headless SSH sessions — use the plain one-liner:

```bash
npx skills add Arize-ai/arize-skills --skill "*" --yes
```

This installs the skills but does **not** instrument the app or send a trace
(editing app code needs an agent). A human or agent still has to complete Steps
2–4 later to get a trace flowing.
