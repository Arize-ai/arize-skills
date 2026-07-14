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

The app cannot send traces without an Arize **API key** and **space**. Prefer
the simplest path that already works for the user. Do **not** require the `ax`
CLI to finish onboarding.

In order:

1. If `ARIZE_API_KEY` and `ARIZE_SPACE` (or `ARIZE_SPACE_ID`) are already set in
   the environment (or the user will set them), use those. Generated code must
   read env vars only — never embed literal secrets.
2. If they want a persistent CLI profile and `ax` is installed, use
   `ax profiles show` / `ax profiles create` / `ax auth login` (do not run
   `ax auth login` yourself — it opens a browser).
3. If `ax` is missing and env vars are enough for the app, continue. Only
   suggest installing `ax` if the user wants CLI profile setup or CLI-based
   verification later.

Never read `.env` files for secrets, and never print raw credential values.

## Step 4 — Verify a trace landed

"Done" for first-trace onboarding means: instrumentation is in place, the app
ran at least one LLM call, spans flushed, and the user has a clear way to see
the trace in Arize. Prefer the lightest verification path — do **not** install
`ax`, write custom SpanProcessor capture scripts, or wait on time-range export
lag unless needed.

Verification ladder (stop at the first that succeeds):

1. **Run the app** and trigger at least one real LLM call. For CLI/scripts,
   ensure flush before exit (`force_flush()` then `shutdown()`), or spans never
   leave the process.
2. **Prefer a known `trace_id`:** if the app logs one, or you can add a single
   temporary log line for the root span's trace ID, use that for a
   deterministic check. Do not invent scratchpad exporters or custom OTel
   processors to "capture" IDs.
3. **Arize UI is a valid verify:** tell the user the project name and where to
   look (recent root CHAIN / agent spans with tools). UI confirm is enough to
   call onboarding successful when `ax` is not installed.
4. **Optional CLI verify** (only if `ax` is already installed, or the user
   explicitly wants it): use the `arize-trace` skill with
   `ax spans export PROJECT --trace-id TRACE_ID`. Never use time-range queries
   (`--days`, `--start-time`) to verify a trace from seconds ago — that index
   lags **6–12 hours** and will false-negative. If you only have a time window,
   say so and point the user at the UI instead of looping on empty exports.

If verification is blocked, end with a concrete status: app instrumentation
status, whether flush succeeded, latest local `trace_id` if any, and whether
the blocker is credentials, project name, network/collector, or missing CLI —
not another unverified install attempt.

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
  network/collector issue. Do **not** treat "ax not installed" or empty
  time-range exports (6–12h lag) as proof spans failed. The Verification
  section of `skills/arize-instrumentation/SKILL.md` has the full triage
  checklist.

## Path 1 fallback — skills only, no agent

When there is no coding agent to paste this prompt into — CI pipelines, Docker
builds, headless SSH sessions — use the plain one-liner:

```bash
npx skills add Arize-ai/arize-skills --skill "*" --yes
```

This installs the skills but does **not** instrument the app or send a trace
(editing app code needs an agent). A human or agent still has to complete Steps
2–4 later to get a trace flowing.
