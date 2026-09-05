# Maturity Ladder

This file answers the question the whole engagement turns on: **how much rigor is warranted right now?** A prototype does not need a 900-row golden dataset, and a launch candidate is not served by twelve ad-hoc prompts in a notebook.

Pick the stage from Phase 0, propose that stage's artifacts, and state the **exit gate** the team must clear to move up. Over-building at Stage 1 is the most common failure: teams spend two weeks on a corpus for an agent whose tool surface changes next sprint.

| Stage | Recognize it by | Corpus | Artifacts | Exit gate |
|---|---|---|---|---|
| 1. Prototype | Works on the happy path; no adversarial testing ever run | 20–40 rows, top 3 families | 1 dataset, 2–3 judges, 1 experiment | Every family probed at least once; no Critical family fails |
| 2. Internal beta | Real users (internal or design partners); traces flowing | 80–200 rows, all reachable families | Versioned dataset, judge per family, baseline vs. hardened arms, first online eval | ≥80% per family; Critical families 100%; gap proven vs. baseline |
| 3. Launch candidate | Date set; external users imminent | 300–800 rows, stratified | Golden dataset (pinned version), full judge suite, gating experiment, online evals + review queue | ≥90% per family; Critical 100%; no regression vs. last run |
| 4. Production at scale | Live external traffic; incidents have a blast radius | Golden set + rows harvested from real traffic | All of Stage 3 plus drift watch, re-red-team cadence, incident replay path | Gates hold continuously; corpus refreshed on schedule |

---

## Stage 1 — Prototype

**Recognize it.** The app works for the demo. Nobody has tried to break it. There may be no tracing yet. Prompts and tool definitions are still changing weekly.

**What you are buying.** Cheap, fast evidence about whether the agent has a *category* of problem. You are not measuring a rate, you are discovering unknowns.

**Corpus.** 20–40 rows across the **top three families only** (from [threat-model.md](threat-model.md), ranked by severity for this app). Roughly 8–12 rows per family. Hand-written is fine and often better than generated at this size.

**Artifacts to create.**
1. One dataset (unversioned is fine — it will churn).
2. Two or three judges, one per family, using the grounded pattern in [judge-library.md](judge-library.md).
3. One experiment against the current prompt.
4. Read the failures yourself. At this size, human review of every failing row is both feasible and the highest-value step.

**What to skip.** Baseline-vs-hardened arms (there is no hardened arm yet), continuous online evals (traffic is not real), annotation queues, drift monitoring, stratification.

**Prerequisite.** If tracing is not live, do that first via `arize-instrumentation`. Without spans there is no evidence trail, judges have nothing to attach to, and the experiment cannot be inspected when a judge looks wrong.

**Exit gate to Stage 2.** Every family in scope has been probed at least once, every failure has been read by a human, and no Critical-severity family fails. Do not chase a percentage here — with 10 rows per family the measurement resolution is 10 points.

---

## Stage 2 — Internal beta

**Recognize it.** Internal users or design partners are using it. Traces are flowing to Arize. The prompt is stabilizing. Someone has asked "is this safe to show a customer?"

**What you are buying.** A defensible per-family rate, plus proof that your defenses are the reason the agent passes — not the base model's built-in refusals.

**Corpus.** 80–200 rows across **all reachable families**. Minimum 8 rows per family (see the resolution table below), more for Critical families. Seed from real traffic first: export production spans via `arize-trace`, find the adversarial or near-miss requests users actually sent, and mark those rows `observed_in_production: true`. Real rows are worth several synthetic ones because they are calibrated to what your users actually try. Then expand with domain variants.

**Artifacts to create.**
1. Versioned dataset (start pinning versions now — this corpus becomes the golden set).
2. One judge per family.
3. **Two experiment arms**: current/baseline prompt and a hardened prompt. The hardened-minus-baseline **gap** is the headline number. Without it you cannot distinguish "our hardening works" from "the model would have refused anyway".
4. First continuous evaluation task on the live project for the top one or two families.

**What to skip.** Full stratification, drift monitoring, formal re-test cadence.

**Exit gate to Stage 3.** ≥80% resistance per family, 100% on Critical families, and a demonstrated positive gap between the hardened and baseline arms. If the gap is near zero, either the corpus is testing the base model's native refusals instead of your policy (rewrite the rows — see the calibration warning in [threat-model.md](threat-model.md)) or the hardening is not doing anything.

---

## Stage 3 — Launch candidate

**Recognize it.** There is a launch date. External users are imminent. Failures will be visible to customers and possibly to regulators.

**What you are buying.** A release gate. The corpus stops being a discovery tool and becomes a contract: this build does not ship unless it clears these numbers.

**Corpus — the golden dataset.** 300–800 rows, **stratified** on three axes:
- **family** × **severity** × **industry principle** (from [industry-overlays.md](industry-overlays.md))
- Include composed/chained rows (see the composition table in [threat-model.md](threat-model.md)) — they are where single-family-clean agents actually fail.
- Include a **benign control set**, roughly 15–20% of rows: legitimate requests that superficially resemble attacks (a user asking about their *own* record, a genuine transparency question, a real edge-case safety question). Without controls you cannot detect over-refusal, and a hardening pass that takes resistance to 100% by refusing everything is a product regression, not a win. Score them with the dedicated **Over-Refusal** evaluator in [judge-library.md](judge-library.md) and keep them out of the resistance denominators — a family judge scores refusal as a pass, so it cannot detect over-refusal by construction.
- Pin a dataset version and reference that version id in the gate. An unpinned corpus makes "we regressed" unfalsifiable.

**Artifacts to create.**
1. Golden dataset, version pinned.
2. Full judge suite: one per family, plus the trace-side privacy check and a code evaluator for `resource_abuse` budgets.
3. Gating experiment run on every release candidate, compared against the last passing run.
4. Continuous evaluation tasks for the top families on live traffic.
5. Annotation queue for human review of flagged production spans (`arize-annotation`).

**Exit gate to production.** ≥90% resistance per family (control rows excluded from the denominator); **100% on Critical families**; over-refusal within tolerance (name a number, e.g. ≤5%) as measured by the **Over-Refusal** evaluator on the control set, reported as its own figure rather than folded into resistance; no per-family regression versus the previous passing run.

Two gate honesty requirements:

- **A Critical `unauthorized_action` gate needs write evidence.** The response-only judge detects *claimed* writes but cannot see whether a mutation actually happened. Meet this gate with tool-call evidence in the run or a trace/code evaluator over tool spans, and record which — see the scope limit in [judge-library.md](judge-library.md).
- **Record the judge verification.** Note that the sample hand-check was done, per judge version. An unverified judge makes every number above unfalsifiable.

Write the gate down with the dataset version, judge versions, and the run ids, and record which families were excluded from scope and why.

---

## Stage 4 — Production at scale

**Recognize it.** Live external traffic. Incidents have a blast radius. Prompts, models, and tools change under change control.

**What you are buying.** Continuous assurance rather than a point-in-time result, and the ability to answer "when did this start?" after an incident.

**Additions to Stage 3.**
1. **Harvest loop.** On a schedule, export recent production spans (`arize-trace`), find near-misses and novel attack shapes, and append them to the golden dataset as new rows. An attack corpus that never changes decays — attackers adapt and your app's surface changes.
2. **Drift watch.** Track refusal rate and per-family pass rate over time. A *rising* refusal rate is as much a signal as a falling one: it usually means a prompt change made the agent over-cautious.
3. **Re-red-team triggers.** Re-run the gating experiment on any system-prompt change, model version change, new tool, new data source, or new tenant class — not only on a calendar.
4. **Incident replay path.** When something goes wrong in production, the trace becomes a corpus row and a regression test. Document that path so it is used under pressure.
5. **Evidence export.** When the ask shifts from "are we hardened?" to "prove it to an auditor or a customer's security review", hand off to `arize-compliance-audit`, which maps this evidence onto framework requirements.

**Gate.** The Stage 3 gates hold continuously, and the corpus has been refreshed within the cadence you committed to.

---

## Gate arithmetic

**Resistance rate per family** = defended rows ÷ total rows in that family. Report **per family**, never as a single aggregate — an aggregate of 92% hides a Critical family at 60%, and the aggregate is dominated by whichever family happens to have the most rows.

**Measurement resolution.** With `n` rows in a family, the finest difference you can observe is `1/n`. Do not quote a precision the corpus cannot support:

| Rows in family | Resolution | Honest claim |
|---|---|---|
| 5 | 20 points | "no failures observed" — not a rate |
| 8 | 12.5 points | "≥87.5%" at best |
| 20 | 5 points | "90% ± one row" |
| 50 | 2 points | a rate you can trend over time |

This is why Stage 1's gate is "no Critical failures" rather than a percentage, and why a Critical family needs more rows than a Medium one.

**The gap metric.** `resistance(hardened) − resistance(baseline)`, per family. This is the number that proves your work mattered, and it is the single most persuasive artifact for a stakeholder review. A near-zero gap on a family means the corpus is measuring the base model rather than your defenses.

**Judge trust.** Before trusting any gate number, hand-verify a sample of judge verdicts — at least 5 defended and 5 compromised rows. A judge that confabulates refusals produces a confidently wrong gate; see the verification procedure in [judge-library.md](judge-library.md). Do this once per judge version, and again whenever a number looks surprisingly good.
