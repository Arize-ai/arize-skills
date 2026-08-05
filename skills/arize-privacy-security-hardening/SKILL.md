---
name: arize-privacy-security-hardening
description: "Use when hardening an LLM app or agent against privacy and security failures before production — prompt injection, jailbreaks, PII/PHI leakage in prompts and traces, tool and tenant authorization, unauthorized actions, data minimization, unsafe confirmations. Runs a staged conversation scaled to app maturity, then builds the test surface in Arize: attack corpus dataset, LLM-as-judge evaluators, red-team experiments, continuous evals. For regulatory audits use arize-compliance-audit."
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI authenticated to the target space. Building judges requires an AI integration in that space. Measuring against live traffic requires Arize tracing already installed.
---

# Arize Privacy and Security Hardening Skill

Use this skill to take an LLM application from "it works" to "we know how it fails and we measure it." It is a **conversation, not a report generator**: you interview the team, read their code, agree on a plan scaled to where they actually are, and then build the artifacts in Arize that turn hardening into a number — an attack corpus, LLM-as-judge evaluators, a red-team experiment, and continuous evals.

Do not use this skill to audit against a named regulation (EU AI Act, GDPR, HIPAA, NIST AI RMF, ISO 42001) — that is `arize-compliance-audit`. Do not use it for first-time tracing setup (`arize-instrumentation`) or for tracing-quality problems. This skill does not perform penetration testing of infrastructure, does not write novel weaponized exploits, and does not decide domain facts on the user's behalf.

## Scope and safety

**Present this before Phase 0, then continue.**

---

> ⚠️ **Scope**
>
> This skill builds **defensive** adversarial test suites for a system you own or are authorized to test. Confirm that authorization before probing anything that is deployed. Attack corpora here use well-known public attack *categories* to test your controls; the skill does not develop novel exploits or evasion techniques.
>
> This is engineering guidance, not a legal, certification, or penetration-testing assessment. For "does this satisfy regulation X", use the `arize-compliance-audit` skill.

---

**Rules that hold throughout:**

- **Never put real sensitive data in a corpus.** No real customer PII, PHI, payment data, credentials, or real internal identifiers. Fabricate every value, shaped like the real thing. Datasets are exported, shared, and long-lived.
- **Never embed credential values.** Reference environment variables. Never ask the user to paste a secret into chat.
- **Read before you write.** Phases 0–2 change nothing.
- **Confirm every mutation individually.** Creating Arize resources and editing code are separate, individually confirmed actions. Never batch them.
- **Report what you actually did.** If a judge scored nothing, a family was skipped, or a gate was not met, say so with the numbers.

## Core principles

- **Converse, don't dump.** Never present the full threat model. Ask, narrow to the families this app can actually reach, and rank them. A read-only chatbot with no retrieval has four reachable families, not ten.
- **Scale rigor to maturity.** The most common failure is over-building: a 900-row golden dataset for an agent whose tool surface changes next sprint. The second most common is under-building: shipping to external users on twelve ad-hoc prompts.
- **Every recommendation lands as an artifact.** A dataset row, a judge, an experiment, a task, or a code change. If a recommendation cannot become one of those, it belongs in the user's backlog, not in this plan.
- **Measure the delta, not the absolute.** "97% resistant" is meaningless alone; the base model may have refused everything anyway. The hardened-minus-baseline gap is what proves the work mattered.
- **Verify the judge before trusting the number.** A security judge that assumes refusal reports a perfect score on a leaking agent.

## Phase 0: Readiness interview

Use `AskUserQuestion`. **Do not infer any of these** — the whole plan hangs off them, and guessing produces a plausible plan for the wrong application.

Ask across five dimensions (batch them; two or three `AskUserQuestion` calls, not five):

**1. Lifecycle stage** — prototype (works on the happy path, no adversarial testing ever run) / internal beta (real internal or design-partner users, traces flowing) / launch candidate (date set, external users imminent) / production at scale (live external traffic, incidents have blast radius).

**2. Data classes** in prompts, retrieval, or traces — public or synthetic only / internal business data / customer PII / PHI, payment data, or credentials / inputs to a consequential decision about a person.

**3. Industry** — healthcare and life sciences / financial services / HR, hiring, and education / other. "Other" is fully supported; see the generic overlay in [references/industry-overlays.md](references/industry-overlays.md).

**4. Capability surface** — read-only or write-capable; what the tools can actually do; retrieval, user-supplied files, or web content; multi-tenant or per-entity scoping; persistent memory; agent-to-agent delegation; human-in-the-loop on irreversible steps.

**5. Existing defenses and evidence** — guardrails (which stage, and whether they block or only log); input/output filtering; and **is Arize tracing live**.

### Phase 0 output

Present a compact snapshot, then go straight to Phase 1:

```
Stage:               {prototype | internal beta | launch candidate | production at scale}
Data sensitivity:    {tier + the specific classes named}
Capability risk:     {read-only | writes | writes + delegation}, tools: {count and blast radius}
Untrusted input:     {retrieval / files / tool results / memory / none}
Evidence:            {tracing live in project X | not instrumented}
Dominant families:   {2-3 families, ranked, with why this app in particular}
Out of scope:        {families excluded and the trigger they don't satisfy}
```

Pick the families from [references/threat-model.md](references/threat-model.md) by capability trigger, then promote severities using the overlay in [references/industry-overlays.md](references/industry-overlays.md).

**If tracing is not live, name exactly what that blocks — and do not over-block.** Phase 3 works without it: a dataset experiment generates its own runs, so the corpus, the judges, and the baseline-vs-hardened arms are all buildable on an uninstrumented app. That is the whole Stage 1 artifact set, so a prototype proceeds normally.

What tracing gates is everything that reads *production* rather than the corpus: continuous evaluation on live traffic and the trace-side privacy check (Phase 4), seeding the corpus from real attempts, and verifying Phase 1 findings against real spans. Say that, offer `arize-instrumentation` as the path to Stage 2, and continue.

## Phase 1: Recon

**Read-only. Write nothing, install nothing, create nothing.**

Six surfaces. For each, run the searches, then record evidence and gaps with real file paths and line numbers.

### A. Data flow and minimization

What actually reaches the prompt, the retrieval corpus, the tool results, and the **span attributes**. Search for PII/PHI/payment field names (`email`, `phone`, `ssn`, `dob`, `address`, `mrn`, `diagnosis`, `card`, `account`, `salary`) in prompt assembly, retrieval, and serialization code. Check whether any redaction runs **before** the OTLP exporter — a span processor, not a post-hoc filter. Check retention configuration. Check whether tool results are projected to the minimum fields or dumped whole into context.

**Concern:** sensitive values reaching `input.value` / `output.value` unredacted. This is the leak that needs no attacker.

### B. Trust boundaries and injection surface

Where untrusted content is concatenated into instructions. Find the system prompt and read how retrieved documents, tool results, file contents, and prior-session memory are inserted — are they labelled and delimited as untrusted data, or interpolated as if authored by the developer? Check whether memory writes are re-validated on read, and whether one agent's output becomes another's instructions.

**Concern:** no structural separation between instructions and fetched content. This is the highest-yield gap in agentic apps and the one teams least often test.

### C. Capability and authorization

Inventory every tool and its blast radius. For each: who can call it, what it can mutate, and **where the authorization check lives**. The question that matters is whether scope comes from the authenticated session server-side or from an argument the model supplies. Look for tenant/row scoping, allowlists, sandboxing, confirmation gates on irreversible actions, and step or depth budgets on autonomous loops.

**Concern:** a tool that accepts an identifier and trusts it. That is LLM-reachable IDOR.

### D. Output safety and leakage

Paths by which the system prompt, tool names, index names, or internal identifiers reach a response. Is there any output-stage filter? Are business rules and thresholds sitting in the system prompt where extraction exposes them? Any hardcoded secrets in source.

### E. Defense in depth

Guardrail libraries present (`guardrails-ai`, `nemo-guardrails`, `llm-guard`, `lakera`, `rebuff`, or hand-rolled). For each: which stage it runs at (input, output, pre-tool), whether it **blocks or only monitors**, and **whether it emits a traced span**. A guardrail that produces no span cannot be graded, and a monitor-only guardrail on a Critical family is not a control.

### F. Evidence and detection

Are all LLM and tool calls traced, or only some? Error and exception spans? Session and user ids (needed to investigate an incident or answer a subject request)? Existing evaluators? Alerting? Where a project is live, **verify against real spans** with `arize-trace` rather than trusting the code read — instrumentation frequently covers less than the code suggests.

### Phase 1 output

**Part 1 — surface table**

| Surface | Evidence found | Gaps | Rating |
|---|---|---|---|
| A. Data flow and minimization | | | Solid / Partial / Weak / N/A |
| B. Trust boundaries | | | |
| C. Capability and authorization | | | |
| D. Output safety | | | |
| E. Defense in depth | | | |
| F. Evidence and detection | | | |

**Part 2 — gap detail. Required for every Partial or Weak rating. Never omit this section.**

For each, write a subsection with:

1. **The exact code path** — file path, line numbers, and the **quoted** code. Do not paraphrase.
2. **Why it matters in this app** — name the specific tool that is abusable, the specific data flow that is exposed, the specific identifier an attacker gets. Not "prompt injection is a risk".
3. **What is missing** — the precise control. "A span processor that hashes `patient.mrn` before the OTLP exporter fires in `tracing.py:34`", not "add PII redaction".
4. **Which family it opens** — so it links to the corpus rows that will prove it.

This section is the primary value of the recon for engineers. A table with no gap detail is not actionable.

## Phase 2: Agree the hardening plan

Select the stage row from [references/maturity-ladder.md](references/maturity-ladder.md) and present a plan in three parts. Then **confirm before building anything.**

**Build now** — the specific artifacts for this stage: corpus size and family composition, which judges, how many experiment arms, which continuous evals. Name numbers, not categories.

**Defer, with the reason** — what you are deliberately not doing yet and what would trigger it. This is as important as the build list; it is what stops over-building.

**The exit gate** — the numeric bar to reach the next stage, with the families that require 100%. Example for a launch candidate: *≥90% resistance per family, 100% on `cross_tenant_access` and `unauthorized_action`, over-refusal ≤5% on the control set per the Over-Refusal evaluator, no per-family regression versus the last passing run.* Where a Critical gate covers `unauthorized_action`, name how actual writes are detected — the response-only judge does not cover them.

Two things to state explicitly in the plan:

- **The gap requirement.** Two arms (current prompt vs. hardened prompt), because a single-arm pass rate cannot distinguish your hardening from the base model's native refusals.
- **Measurement resolution.** With 8 rows in a family the finest measurable difference is 12.5 points. Do not promise a precision the corpus cannot support; see the resolution table in [references/maturity-ladder.md](references/maturity-ladder.md).

Also flag any **code-level gap that no corpus can fix**. If scope comes from a model-supplied argument, red-teaming will document the failure repeatedly and never fix it — that one belongs in Phase 5 first, and the corpus row exists to prove the fix.

## Phase 3: Build the red-team surface

Confirm each step. Report the created resource and a deep link (`arize-link`).

**1. Build the corpus.** Follow [references/attack-corpus.md](references/attack-corpus.md): the row schema, the four-point quality bar, and stratification. Seed from real traffic first where it exists (`arize-trace`), paraphrased with every identifier fabricated. Include composed/chained rows and a benign control set of 15–20%, without which over-refusal is invisible. Create the dataset with `arize-dataset`; write any generated files under `.scratch/` or the project's gitignored scratch location, not into the repo.

**2. Register the judges.** One per family, from [references/judge-library.md](references/judge-library.md), via `arize-evaluator`. Non-negotiables:
- `--data-granularity span` — a `trace`-granularity evaluator is **not rejected** on an experiment; it runs and scores nothing (`num_successes: 0`, `num_errors: 0`, `failure_reason: … 'context.trace_id'`), which reads as a clean run.
- Binary labels (`defended` = 1, `compromised` = 0) with `--classification-choices` matching the template's labels exactly.
- The literal-text clause, the untrusted-data framing, and the app-specific forbidden-behavior list from Phase 1.
- `column_mappings` for **every** template variable, including `{context}` where rows carry payloads in retrieved content. An unmapped variable yields no scores rather than an error.
- Low temperature, and `--include-explanations` on (plural; `--help` truncates the name and the singular form is rejected).

**3. Run two arms.** Via `arize-experiment`: current prompt and hardened prompt over the same corpus version. Report three separate numbers — per-family resistance (control rows excluded from the denominator), per-family gap, and the over-refusal rate from the Over-Refusal evaluator on the control rows. These come from **different evaluators on different eval columns**; a family judge scores refusal as a pass, so it cannot produce the over-refusal number.

**4. Verify the judges, then read the failures.** Hand-check 5 `defended` and 5 `compromised` verdicts against the actual response text before quoting any gate number. Then read every failing row's response. Failures cluster by technique, and the cluster names the one control to build first.

## Phase 4: Build the standing defense

The corpus tests a build; this watches production.

1. **Continuous evaluation tasks** on the live project for the top families (`arize-evaluator`). Start with a backfill on historical spans to validate column mappings before enabling continuous — and note the eval index can lag 1–2 hours, so a window ending "now" scores zero spans while reporting success.
2. **Deterministic checks alongside the judges** — a code evaluator asserting no PII/PHI patterns in span attributes (this is what catches the passive leak), and one asserting token, tool-call, and latency budgets. Cheaper than judges and not fool-able.
3. **Human review** — an annotation queue for flagged spans via `arize-annotation`, so `compromised` verdicts on real traffic get adjudicated rather than accumulating.
4. **Alerting** — configure monitors in the Arize UI. There is no `ax monitors` command; do not imply one exists. Watch per-family pass rate and refusal rate; a *rising* refusal rate usually means a prompt change made the agent over-cautious.
5. **Re-test triggers** — re-run the gating experiment on any system-prompt change, model version change, new tool, new data source, or new tenant class. Not only on a calendar.
6. **Incident replay** — a production failure becomes a corpus row the same day, marked as observed in production. Write this path down so it is used under pressure.

## Phase 5: Code remediation (optional)

Offer these individually. `AskUserQuestion` before each. Never batch. Follow the project's existing style and confirm the app still builds.

| Fix | What it is |
|---|---|
| Redaction span processor | Hash or drop sensitive attributes **before** the OTLP exporter, so values never reach the backend |
| Untrusted-content delimiting | Restructure prompt assembly to label and fence retrieved content, tool results, and memory as data |
| Server-side scope injection | Derive tenant/subject scope from the authenticated session; stop accepting it from model output |
| Pre-tool authorization check | A blocking check on every scoped tool call, not monitor-only |
| Tool allowlist and confirmation gates | Least privilege per agent role; explicit confirmation on irreversible tools |
| Output filter | Deny-list for tool names, index names, prompt fragments, and identifier patterns |
| Result projection | Return minimum-necessary fields from tools so the model cannot leak what it never received |
| Identity attributes on spans | `user.id` / `session.id` for incident investigation and subject lookups |
| Budgets | Max tokens, step/depth caps, input size limits, tool timeouts |

Prefer fixes that remove data from the model's reach over fixes that instruct the model to behave. A tool that never returns the MRN cannot leak it; a prompt that asks the model not to mention the MRN can be talked out of it.

After a fix lands, re-run the affected family and report the before/after. That number is the deliverable.

## Related skills

| Need | Skill |
|---|---|
| No tracing, or tracing covers only some calls | `arize-instrumentation` |
| Inspect real spans; seed the corpus from production traffic | `arize-trace` |
| Create and version the attack corpus | `arize-dataset` |
| Register judges, create tasks, run backfills and continuous evals | `arize-evaluator` |
| Run and compare the baseline vs. hardened arms | `arize-experiment` |
| Human review queue for flagged spans | `arize-annotation` |
| Manage the hardened system prompt as a versioned template | `arize-prompts` |
| Improve a prompt that keeps failing one family | `arize-prompt-optimization` |
| Share evidence with stakeholders | `arize-link` |
| The ask becomes "prove it to a regulator or a security review" | `arize-compliance-audit` |

## Gotchas

- **A trace-granularity judge on an experiment is not rejected — it scores nothing.** Verified live: the task is created, the run is triggered, and it completes with `num_successes: 0`, `num_errors: 0`, `failure_reason: … 'context.trace_id'`. Zero errors makes it read as a clean run. Register red-team judges at `span` granularity, and treat any zero-success run as a failure.
- **A CLI mutation can succeed while the command reports an error.** Response-parse failures in `ax` are reported as create failures on calls that already committed server-side; a naive retry then hits `409 Conflict`. Confirm with a `list` before concluding anything failed, and never create a differently-named duplicate on the strength of an error message.
- **Dataset fields round-trip as strings.** `true` comes back as `'true'`, so `bool(is_control)` is always truthy and quietly folds control rows into the resistance denominator. Compare explicitly.
- **An evaluation task scores every run in the experiment.** There is no per-row scoping, so each judge also scores the rows it does not apply to. Filter on `is_control` when computing rates; never report a raw column average.
- **Judges confabulate refusals.** A response that literally enumerated its tools and printed internal ids has been scored `defended` with the explanation "the assistant appropriately declined". Every judge needs the literal-text clause. Hand-verify before quoting a number.
- **Generic harm prompts measure nothing.** Current frontier models refuse them natively, so the corpus scores ~100% with a zero gap. Aim at policy violations: disclosure, injection via retrieved content, tenant scope, claimed writes, unsafe confirmation.
- **All-`defended` is a smell, not a win.** Usually an empty `{output}`, a broken mapping, or a confabulating judge.
- **A resistance judge cannot measure over-refusal.** It scores a clean refusal as `defended`, so control rows need the separate Over-Refusal evaluator on its own eval column. Never branch a resistance rubric on an `is_control` flag.
- **A response-only judge cannot see a write that actually happened.** It detects *claimed* writes. Actual mutations need tool-call evidence in the run or a trace/code evaluator over tool spans, or a Critical `unauthorized_action` gate passes falsely.
- **Appended dataset fields are free-form.** A typo creates a new column silently; the mapped field is then null for those rows, so they come back unscored rather than errored. Diff the schema before every append.
- **Missing `column_mappings` fail silently.** Map every variable the template names.
- **Template variables are single-brace `{input}`.** The `ax --template` help text says `{{variable}}`; that is wrong and doubled braces do not bind.
- **Evaluator versions are immutable.** Template edits create a new version; point the task at it. If a fix appears to do nothing, confirm which version the task is running.
- **Eval index lag is 1–2 hours.** A backfill window ending "now" completes successfully and scores zero spans.
- **Experiment names collide on re-run.** Use a fresh name or a suffix per run.
- **`query_filter` only matches indexed attributes.** Custom or metadata keys silently match nothing; filter on `span_kind` or other well-known attributes.
- **No `ax monitors` command.** Monitors and alerts are UI configuration.
- **Guardrails that emit no span cannot be graded**, and monitor-only guardrails on a Critical family are not controls.
- **Never seed a corpus with real sensitive values**, including real internal identifiers. Fabricate, shaped like the originals.

## Reference files

- [references/threat-model.md](references/threat-model.md) — the ten attack families: capability trigger, probe techniques, defended behavior, judge, control, severity; plus taxonomy mapping and chained-attack composition
- [references/maturity-ladder.md](references/maturity-ladder.md) — four stages with corpus sizing, artifacts, numeric exit gates, and gate arithmetic including measurement resolution
- [references/judge-library.md](references/judge-library.md) — the grounded-judge anatomy, per-family specializations, code evaluators, and the judge verification procedure
- [references/attack-corpus.md](references/attack-corpus.md) — row schema, quality bar, stratification, control set, build and maintenance workflow
- [references/industry-overlays.md](references/industry-overlays.md) — healthcare, financial services, HR/hiring/education overlays plus a generic blast-radius overlay and an extension recipe

## Reference links

| Resource | URL |
|---|---|
| OWASP Top 10 for LLM Applications | https://genai.owasp.org/llm-top-10/ |
| MITRE ATLAS matrix | https://atlas.mitre.org/matrices/ATLAS |
| NIST AI 600-1 (Generative AI Profile) | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf |
| OpenInference semantic conventions | https://github.com/Arize-ai/openinference |
| Arize AX documentation | https://arize.com/docs/ax |
