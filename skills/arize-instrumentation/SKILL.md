---
name: arize-instrumentation
description: Adds Arize AX tracing to an LLM application for the first time. Follows a two-phase agent-assisted flow to analyze the codebase then implement instrumentation after user confirmation. Use when the user wants to instrument their app, add tracing from scratch, set up LLM observability, integrate OpenTelemetry or openinference, or get started with Arize tracing.
metadata:
  author: arize
  version: "1.0"
compatibility: Python and TypeScript/JavaScript apps use openinference-instrumentation packages for auto-instrumentation. Go apps use arize-otel-go for setup plus per-provider instrumentors openinference-instrumentation-openai-go and openinference-instrumentation-anthropic-sdk-go, or manual spans via openinference-semantic-conventions. Java apps use the OpenTelemetry SDK with manual OpenInference spans. See https://arize.com/docs/PROMPT.md for setup details.
---

# Arize Instrumentation Skill

Use this skill when the user wants to **add Arize AX tracing** to their application. Follow the **two-phase, agent-assisted flow** from Agent-Assisted Tracing Setup (https://arize.com/docs/ax/alyx/tracing-assistant) and Arize AX Tracing — Agent Setup Prompt (https://arize.com/docs/PROMPT.md).

## Quick start (for the user)

If the user asks you to "set up tracing" or "instrument my app with Arize", you can start with:

> Follow the instructions from https://arize.com/docs/PROMPT.md and ask me questions as needed.

Then execute the two phases below.

## Core principles

- **Prefer inspection over mutation** — understand the codebase before changing it.
- **Do not change business logic** — tracing is purely additive.
- **Use auto-instrumentation where available** — add manual spans only for custom logic not covered by integrations.
- **Follow existing code style** and project conventions.
- **Keep output concise and production-focused** — do not generate extra documentation or summary files.
- **NEVER embed literal credential values in generated code** — always reference environment variables (e.g., `os.environ["ARIZE_API_KEY"]`, `process.env.ARIZE_API_KEY`). This includes API keys, space IDs, and any other secrets. The user sets these in their own environment; the agent must never output raw secret values.
- **NEVER ask the user to paste secrets into the coding agent chat** — including `ARIZE_API_KEY`, provider API keys, tokens, or other credentials. Instruct them to set env vars in their app `.env` or their own shell. See references/credentials-and-config.md and references/ax-profiles.md.
- **Ask before creating persistent local state.** Do not create or update `ax` profiles, edit shell startup files (`.zshrc`/`.bashrc`), persist environment variables, or write memory/note files without explicit user consent. Prefer non-persistent verification (env vars set for the run, temp `--output-dir` exports); offer to persist only after the user approves (see references/ax-profiles.md § Save Credentials for Future Use).

## Phase 0: Environment preflight

Before changing code:

1. **Confirm scope before touching anything.** Identify the exact target — service, entrypoint, framework, and tracing type. If it is ambiguous, do read-only inspection only and **ask the minimal scope question before installing packages or editing code** (see *When you must ask the user first*). Do not assume the whole repo, and do not pick a service or framework for the user.
2. Identify the local runtime surface you will need for verification:
   - package manager and app start command
   - whether the app is long-running, server-based, or a short-lived CLI/script
   - whether `ax` will be needed for post-change verification
3. Do NOT proactively check `ax` installation or version. If `ax` is needed for verification later, just run it when the time comes. If it fails, see references/ax-profiles.md.
4. Never silently replace a user-provided space ID, project name, or project ID. If the CLI, collector, and user input disagree, surface that mismatch as a concrete blocker.

### When you must ask the user first

If monorepo scope, service entrypoint, or target app is still unclear after quick inspection — or you would otherwise open with a bare list of questions — use this opening pattern:

1. Acknowledge the skill, e.g.: **I found the arize-instrumentation skill in this repo** (you may add `skills/arize-instrumentation/SKILL.md` if helpful).
2. Then a clear pause line, e.g.: **A few clarifying questions before I invoke it:**
3. Ask **minimal** numbered or short bullet questions — only what blocks Phase 1 or Phase 2.

Cases that require a scope question before acting: a **monorepo** with several packages; **multiple deployable services** (e.g. an API and a worker); or **multiple LLM frameworks/entrypoints** in one codebase (e.g. a LangChain service alongside a raw-OpenAI script). Name the candidates you found and ask which to instrument.

## Phase 1: Analysis (read-only)

**Do not write any code or create any files during this phase.**

### Steps

1. **Check dependency manifests** to detect stack:
   - Python: `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile`
   - TypeScript/JavaScript: `package.json`
   - Java: `pom.xml`, `build.gradle`, `build.gradle.kts`
   - Go: `go.mod`

2. **Scan import statements** in source files to confirm what is actually used.

3. **Check for existing tracing/OTel** — look for `TracerProvider`, `register()`, `opentelemetry` imports, `ARIZE_*`, `OTEL_*`, `OTLP_*` env vars, or other observability config (Datadog, Honeycomb, etc.).

4. **Identify scope** — for monorepos or multi-service projects, ask which service(s) to instrument.

### What to identify

| Item | Examples |
|------|----------|
| Language | Python, TypeScript/JavaScript, Java, Go |
| Package manager | pip/poetry/uv, npm/pnpm/yarn, maven/gradle, go modules |
| LLM providers | OpenAI, Anthropic, LiteLLM, Bedrock, etc. |
| Frameworks | LangChain, LangGraph, LlamaIndex, Vercel AI SDK, Mastra, etc. |
| Existing tracing | Any OTel or vendor setup |
| Tool/function use | LLM tool use, function calling, or custom tools the app executes (e.g. in an agent loop) |

**Key rule:** When a framework is detected alongside an LLM provider, inspect the framework-specific tracing docs first and prefer the framework-native integration path when it already captures the model and tool spans you need. Add separate provider instrumentation only when the framework docs require it or when the framework-native integration leaves obvious gaps. If the app runs tools and the framework integration does not emit tool spans, add manual TOOL spans so each invocation appears with input/output; see references/manual-spans.md.

### Phase 1 output

Return a concise summary:

- Detected language, package manager, providers, frameworks
- Proposed integration list (from the routing table in the docs)
- Any existing OTel/tracing that needs consideration
- If monorepo: which service(s) you propose to instrument
- **If the app uses LLM tool use / function calling:** note that you will add manual CHAIN + TOOL spans so each tool call appears in the trace with input/output (avoids sparse traces).

If the user explicitly asked you to instrument the app now, and the target service is already clear, present the Phase 1 summary briefly and continue directly to Phase 2. If scope is ambiguous, or the user asked for analysis first, stop and wait for confirmation.

## Integration routing and docs

Use the Agent Setup Prompt routing table at https://arize.com/docs/PROMPT.md to map detected signals to integration docs and fetch the matched pages for exact installation steps and code snippets. Use https://arize.com/docs/llms.txt as a fallback for doc discovery.

See references/integration-routing.md for the full list of supported integrations by language and platform.

## Credentials and configuration

Instrumentation needs three values the user sets — **Arize API key**, **Space** (name or base64 ID), and **project name** — plus the **collector endpoint** (defaults to US `otlp.arize.com`). Key rules:

- **Follow config precedence and never silently override what the app is configured with** (project name, space, IDs, endpoint). If sources disagree, surface the mismatch instead of rewriting config.
- **Emit and verify with the same credential context** — a trace exported to one space but verified with an `ax` profile pointing elsewhere looks missing; report that as a credential-context blocker.
- **Read only the target app's own config for credentials** — never scan sibling repos, unrelated `.env` files, or shell startup files. If credentials are missing, ask the user to set them; never accept a pasted key in chat.

See references/credentials-and-config.md for precedence, export/verify context matching, safe env parsing, and the missing-credentials onboarding response. See references/ax-profiles.md for getting an API key and profile setup.

## Phase 2: Implementation

Proceed **only after the user confirms** the Phase 1 analysis — and, when scope was ambiguous, only after the specific service/framework is confirmed.

### Steps

1. **Fetch integration docs** — Read the matched doc URLs and follow their installation and instrumentation steps.
2. **Install packages** using the detected package manager **before** writing code:
   - Python: `pip install arize-otel` plus `openinference-instrumentation-{name}` (hyphens in package name; underscores in import, e.g. `openinference.instrumentation.llama_index`).
   - TypeScript/JavaScript: `@opentelemetry/sdk-trace-node` plus the relevant `@arizeai/openinference-*` package.
   - Java: OpenTelemetry SDK plus `openinference-instrumentation-*` in pom.xml or build.gradle.
   - Go: Use arize-otel-go (https://github.com/Arize-ai/arize-otel-go) for tracer setup, plus a per-provider instrumentor when one exists. Install:
     ```
     go get github.com/Arize-ai/arize-otel-go
     go get github.com/Arize-ai/openinference/go/openinference-semantic-conventions
     go get github.com/Arize-ai/openinference/go/openinference-instrumentation
     # Plus exactly one of these, matched to the detected client:
     go get github.com/Arize-ai/openinference/go/openinference-instrumentation-openai-go        # official openai/openai-go SDK
     go get github.com/Arize-ai/openinference/go/openinference-instrumentation-anthropic-sdk-go # anthropics/anthropic-sdk-go v1.43+
     ```
     **Wire the exporter** with one call: `arizeotel.Register(ctx, arizeotel.Options{ProjectName: "my-app"})` — defaults to `otlp.arize.com` (US), use `arizeotel.EndpointArizeEurope` for EU. It reads `ARIZE_SPACE_ID` / `ARIZE_API_KEY` / `ARIZE_PROJECT_NAME` / `ARIZE_COLLECTOR_ENDPOINT` from env when the matching `Options` fields are unset. **Wire the OpenAI instrumentor** by passing `option.WithMiddleware(openaiotel.Middleware(otel.Tracer("my-app")))` to `openai.NewClient(...)` (alongside `option.WithAPIKey(...)`). **Wire the Anthropic instrumentor** by passing `option.WithMiddleware(anthropicotel.Middleware(otel.Tracer("my-app")))` to `anthropic.NewClient(...)`. Both instrumentors expose `WithTraceConfig(instrumentation.TraceConfig{...})` for in-code overrides of the `OPENINFERENCE_HIDE_*` env-driven masking config. Module floor is Go 1.25 (the openinference Go modules require it; `arize-otel-go` itself is Go 1.23+).
3. **Credentials** — the app needs an **Arize API key** and **Space**. See **Credentials and configuration** above and references/credentials-and-config.md for precedence, safe handling, and the missing-credentials onboarding response. Inspect only the target app's own config to learn what it exports; never scan unrelated projects, and never surface secret values.
   - Run `ax profiles show` to check for an existing profile. Run `ax profiles validate` to verify an existing profile's credentials are still valid.
   - If no profile exists, guide the user to run `ax profiles create` which provides an **interactive wizard** that walks through API key and space setup. See CLI profiles docs at https://arize.com/docs/api-clients/cli/profiles for details.
   - **OAuth alternative (v0.18.0+):** Users can authenticate via browser-based OAuth PKCE instead of API keys by running `ax auth login`. Inform users of this option if they prefer not to manage API keys — do **not** run `ax auth login` yourself as it opens a browser.
   - If the user needs to find their API key manually, direct them to **https://app.arize.com** and to navigate to the settings page (do not use organization-specific URLs with placeholder IDs — they won't resolve for new users).
   - If credentials are not set, instruct the user to set them as environment variables in their app `.env` or their own shell — never ask them to paste key values into chat, and never embed raw values in generated code. All generated instrumentation code must reference `os.environ["ARIZE_API_KEY"]` / `os.environ["ARIZE_SPACE_ID"]` (Python), `process.env.ARIZE_API_KEY` / `process.env.ARIZE_SPACE_ID` (TypeScript/JavaScript), or `os.Getenv("ARIZE_API_KEY")` / `os.Getenv("ARIZE_SPACE_ID")` (Go — `arize-otel-go` reads `ARIZE_SPACE_ID`, not `ARIZE_SPACE`). With the recommended `arizeotel.Register(ctx, arizeotel.Options{...})` flow, generated Go code does not need to call `os.Getenv` at all — `Register` reads both env vars when the matching `Options` fields are unset.
   - See references/ax-profiles.md for full profile setup and troubleshooting.
4. **Centralized instrumentation** — Create a single module (e.g. `instrumentation.py`, `instrumentation.ts`, `instrumentation.go`) and initialize tracing **before** any LLM client is created.
5. **Existing OTel** — If there is already a TracerProvider, add Arize as an **additional** exporter (e.g. BatchSpanProcessor with Arize OTLP). Do not replace existing setup unless the user asks.

### Implementation rules

- Use **auto-instrumentation first**; manual spans only when needed.
- Prefer the repo's native integration surface before adding generic OpenTelemetry plumbing. If the framework ships an exporter or observability package, use that first unless there is a documented gap.
- **Fail gracefully** if env vars are missing (warn, do not crash).
- **Import order:** register tracer → attach instrumentors → then create LLM clients.
- **Project name attribute (required):** Arize rejects spans with HTTP 500 if the project name is missing — `service.name` alone is not accepted. Set it as a **resource attribute** on the TracerProvider (recommended — one place, applies to all spans):
  - **Python:** `register(project_name="my-app")` handles it automatically (sets `"openinference.project.name"` on the resource). For routing spans to different projects, use `set_routing_context(space_id=..., project_name=...)` from `arize.otel`.
  - **TypeScript:** Arize accepts both `"model_id"` (shown in the official TS quickstart) and `"openinference.project.name"` via `SEMRESATTRS_PROJECT_NAME` from `@arizeai/openinference-semantic-conventions` (shown in the manual instrumentation docs) — both work.
  - **Go:** `arizeotel.Register(ctx, arizeotel.Options{ProjectName: "my-app"})` handles this automatically (sets `openinference.project.name` and `service.name` on the resource). If you're wiring `sdktrace.NewTracerProvider` directly (multi-exporter, on-prem collector), pass `attribute.String("openinference.project.name", "my-app")` to `resource.New(...)` manually.
- **CLI/script apps — flush before exit:** `provider.shutdown()` (TS) / `provider.force_flush()` then `provider.shutdown()` (Python) / `tp.Shutdown(ctx)` (Go) must be called before the process exits, otherwise async OTLP exports are dropped and no traces appear.
- **When the app has tool/function execution:** add manual CHAIN + TOOL spans; see references/manual-spans.md so the trace tree shows each tool call and its result — otherwise traces will look sparse (only LLM API spans, no tool input/output).

## Verification

Treat instrumentation as complete only when all of the following are true:

1. The app still builds or typechecks after the tracing change.
2. The app starts successfully with the new tracing configuration.
3. You trigger at least one real request or run that should produce spans.
4. You either verify the resulting trace in Arize, or you provide a precise blocker that distinguishes app-side success from Arize-side failure.

Final status is **confirmed**, **confirmed with warnings**, or a **classified blocker** — never a bare "done" when warnings or blockers remain.

Follow references/verification.md for the deterministic trace lookup, failure classification, and post-arrival smoke check. Keep the main flow tight:

1. Run the application and trigger at least one real request or LLM call.
2. Use the `arize-trace` skill to confirm traces arrived, using the same credential context the app exported with.
3. If no traces arrive, classify the blocker using references/verification.md instead of continuing with unrelated probes.
4. If traces arrive, run the smoke check in references/verification.md. If warnings remain, report **confirmed with warnings** and give the next fix step.
5. For broader or repeated quality concerns, hand off to `arize-instrumentation-health` when that skill is available.

## Progress and status reporting

Instrumentation spans several slow steps. Keep the user oriented:

- Emit a short milestone at each checkpoint: **dependency install → tracing wiring → app run → trace export → verification**.
- Summarize recovered errors in plain language and mark them **resolved** — do not present a recovered dependency/CLI error as if it were a blocker.
- Don't make raw command output the primary status; quote only the decisive line when it matters.
- End with a concise summary that separates **completed work** from any **remaining verification blockers**.

## Next steps after verification

Trace confirmation is the start of the observability workflow, not the end. After a confirmed trace, briefly offer the next relevant step based on the user's goal — keep it short and optional, not a pitch:

- Inspect or debug traces → **`arize-trace`**
- Curate examples into a dataset → **`arize-dataset`**
- Add LLM-as-judge or code evaluators → **`arize-evaluator`**
- Compare models or prompts on a test set → **`arize-experiment`**
- Improve a prompt → **`arize-prompt-optimization`**

If the trace has obvious quality issues, point to trace inspection/debugging (**`arize-trace`**) first, before suggesting downstream workflows.

## Emitting `session.id` for multi-turn session tracking

For session-level evaluations in Arize (e.g. the `{conversation}` template variable in `arize-evaluator`), spans must carry `attributes.session.id`. This section covers how to emit it correctly.

**Pattern (Python / OpenTelemetry):**

```python
from typing import Optional
import uuid

def chat(question: str, session_id: str, chat_history: Optional[list] = None) -> str:
    with tracer.start_as_current_span("chat") as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("input.value", question)
        span.set_attribute("session.id", session_id)
        answer = your_llm_call(question)  # replace with the actual LLM call
        span.set_attribute("output.value", answer)
        return answer
```

Generate `session_id` once per conversation and pass it in from the caller:

```python
session_id = str(uuid.uuid4())  # generate once per conversation, not per turn

for user_message in conversation:
    reply = chat(user_message, session_id=session_id)
```

Rules:
- **Same `session_id` for every turn in one conversation.** Each call produces its own span, but all spans share the same `session_id` so Arize groups them.
- **New `session_id` when a fresh conversation starts.** Generate a new UUID at the start of each session, not at each turn.
- **Pass `session_id` in from the caller** — the caller (request handler, notebook cell, app frontend) owns the session boundary.

**Auto-instrumentation note:** If using OpenInference auto-instrumentation (e.g. for LiteLLM or OpenAI), you do not control span creation directly. Wrap the LLM call in a manually-created CHAIN span and set `session.id` there — the auto-instrumented LLM spans will nest under it as children.

**Flushing spans (Jupyter notebooks and short-lived scripts):**

The OTLP batch exporter holds spans in memory and ships them on a timer or when the buffer fills. In a Jupyter notebook or short-lived script the process may end before the buffer flushes — spans emit correctly locally but never reach Arize.

Call `force_flush()` after finishing a conversation you want to inspect:

```python
tracer_provider.force_flush()   # ships buffered spans immediately
```

Call `shutdown()` only when done tracing entirely — it closes the exporter and cannot be reversed without re-initializing:

```python
tracer_provider.force_flush()
tracer_provider.shutdown()
```

**Checklist before debugging missing session data in Arize:**
1. Is `session.id` set on the CHAIN span? If using auto-instrumentation, wrap the LLM call in a manual CHAIN span and set it there.
2. Is the same `session_id` passed to every turn in the conversation?
3. Was `force_flush()` called after the conversation ended?
4. Did you wait ~30 seconds for ingestion before checking the Arize UI?


## Reference links

| Resource | URL |
|----------|-----|
| Agent-Assisted Tracing Setup | https://arize.com/docs/ax/alyx/tracing-assistant |
| Agent Setup Prompt (full routing + phases) | https://arize.com/docs/PROMPT.md |
| Arize AX Docs | https://arize.com/docs/ax |
| Full integration list | https://arize.com/docs/ax/integrations |
| Doc index (llms.txt) | https://arize.com/docs/llms.txt |

## IDE Integration (MCP)

If the user asks about IDE-based instrumentation guidance or MCP setup, see references/tracing-assistant-mcp.md.

## Save Credentials for Future Use

See references/ax-profiles.md § Save Credentials for Future Use.
