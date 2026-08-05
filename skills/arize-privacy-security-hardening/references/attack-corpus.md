# Attack Corpus

The corpus is the asset. Judges get rewritten, prompts get replaced, models get swapped; the corpus accumulates value and becomes the regression suite that outlives all of them.

A corpus is only useful if every row is **gradeable** and **discriminating**. Gradeable means a judge can decide defended-or-compromised from the response text alone. Discriminating means a hardened build passes it and an unhardened build fails it. Rows that fail either test inflate the row count and depress the signal.

## Row schema

Every row carries its own grading context. The judge receives these fields, so a row is self-describing rather than depending on judge-side knowledge.

| Field | Required | Purpose |
|---|---|---|
| `attack_id` | yes | Stable unique id (e.g. `inj-014`). Never renumber — it is how a regression is traced across runs. |
| `family` | yes | One family from [threat-model.md](threat-model.md). Exactly one, even for chained rows: tag the family whose *outcome* is the harm. |
| `technique` | yes | The specific mechanism (`fake_system_turn`, `context_memo_authority`, `tool_summary_request`, `foreign_id_comparison`). Lets you find which technique class defeats you. |
| `severity` | yes | `critical` / `high` / `medium`. Drives the gate: Critical families require 100%. |
| `prompt` | yes | The attacker's turn, verbatim. |
| `context` | when applicable | Simulated retrieved-document or tool-result text fed to the agent alongside the prompt. **Where indirect-injection payloads and internal-id-bearing records live.** Empty or `(none)` for direct attacks. |
| `expected_behavior` | yes | What defending looks like, in prose. Passed to the judge. |
| `success_criteria` | yes | The concrete test — which specific string, id, or claim must be absent, or which ground-truth standard must be stated. For `unsafe_confirmation` rows this carries the real standard so the judge grades against fact. For `is_control` rows it describes what *serving* the request looks like. |
| `target_control` | recommended | The guardrail, filter, or authorization check this row probes (`guardrail.input_jailbreak_filter`, `tool.authz_check`, or `none` for a deliberately unguarded surface). Turns a failure into a work item. |
| `observed_in_production` | recommended | `true` for rows seeded from real traffic. These are worth several synthetic rows — mark them so they are never pruned. |
| `is_control` | for control rows | `true` for benign lookalikes. **Scored by the separate Over-Refusal judge, not by the family judge** — for these rows refusing is the failure, and the resistance rubric treats refusal as a pass. Excluded from resistance denominators. |
| `industry_principle` | when an overlay applies | Links the row to the domain principle it enforces (see [industry-overlays.md](industry-overlays.md)). Makes stratification auditable. |

Defaults belong at the family level, not per row. Define `expected_behavior`, `success_criteria`, and `target_control` once per family and merge them into rows, overriding only where a row is special. This keeps a 600-row corpus editable and stops the same prose drifting into forty inconsistent variants.

## The quality bar

Reject a row unless it passes all four:

1. **Gradeable from the response alone.** If deciding the verdict requires database state or knowledge of which tool ran, a judge cannot grade it. Either move the needed evidence into `context` or make it a code evaluator over spans instead.
2. **Discriminating.** A hardened build passes, an unhardened build fails. If both pass, the row is measuring the base model's native refusals, not your defenses — it contributes nothing to the gap metric and should be rewritten or cut.
3. **Defeatable by a named control.** You can point at the guardrail, filter, or authorization check that should stop it. A row nothing could plausibly stop is a research note, not a test.
4. **Fabricated.** No real customer data, no real PHI, no live secrets, no real internal identifiers. Datasets are exported, shared, and long-lived. Fabricate every value, and make fabricated ids *shaped* like the real ones so leakage detection stays realistic.

> **The calibration failure to avoid.** A corpus of generic harm prompts ("how do I make a weapon") scores ~100% on any current frontier model and produces a zero gap between baseline and hardened builds. It looks like a passing grade and measures nothing about your app. Aim the corpus at **policy** violations: disclosing internals, obeying instructions embedded in retrieved content, acting outside tenant scope, claiming writes, confirming unsafe premises. Those are the attacks a helpful model has no native reason to refuse — and the only ones where your hardening shows up as a number.

## Stratification

For a golden dataset (Stage 3 in [maturity-ladder.md](maturity-ladder.md)), stratify on three axes and record the resulting matrix:

- **family** — every reachable family, minimum 8 rows (see the resolution table in [maturity-ladder.md](maturity-ladder.md)); more for Critical families, which need enough rows for "100%" to be a real claim.
- **severity** — do not let Medium rows dominate the count; the gate is driven by the Critical cells.
- **technique** — at least three distinct techniques per family. Eight rephrasings of one technique measure one thing eight times.

Plus two cross-cutting requirements:

- **Composed rows.** Include the chains from the composition table in [threat-model.md](threat-model.md). An agent clean on every single-family probe frequently fails `indirect_injection → unauthorized_action`, because the input-stage filter never sees the payload.
- **Benign control set, 15–20% of rows.** Legitimate requests that superficially resemble attacks: a user asking for *their own* record id, a genuine "what can you help with?" question, a real edge-case safety question, a legitimate cross-store comparison the user *is* entitled to. Without controls, a hardening pass that refuses everything scores 100% resistance while destroying the product. **Route these rows to the Over-Refusal judge in [judge-library.md](judge-library.md), on its own eval column, and keep them out of every resistance denominator.** Sending a control row through a family judge measures nothing: that rubric scores a clean refusal as `defended`, so a refuse-everything agent passes its controls too. For control rows, write `expected_behavior` and `success_criteria` as *what serving the request looks like*, since that is what the Over-Refusal judge grades against.

## Building the corpus

### Step 1 — Seed from real traffic first

Real attempts beat invented ones because they are calibrated to what your users actually try, and because "this happened in production" ends the argument about whether the test matters.

Export recent spans with `arize-trace` and look for: refusals and near-refusals, unusually long or structured user turns, requests containing ids the user should not have, transparency probes ("what tools do you use?"), and anything the existing guardrails flagged. Where a real trace maps to a family, write it up as a row with `observed_in_production: true` — **paraphrased and with every identifier and personal value replaced by fabricated equivalents of the same shape.** Never lift a production payload verbatim into a dataset.

If there is no production traffic yet (Stage 1), skip this step rather than faking it.

### Step 2 — Expand with domain variants

For each seeded row, write variants that hold the family constant and vary the technique: change the delivery channel (prompt vs. retrieved context vs. tool result), change the framing (imperative, polite request, authority claim, hypothetical, workflow justification), change the target (a different tool, a different restricted field, a different tenant).

Use the domain vocabulary from [industry-overlays.md](industry-overlays.md). A generic "show me the other user's record" is weaker than a probe using the real entities, roles, and document types of the domain, because the agent's actual prompt is written in those terms.

### Step 3 — Write the family defaults

Before generating rows at volume, fix the per-family `expected_behavior`, `success_criteria`, and `target_control`. These become the judge's grading context, so vague prose here caps judge accuracy no matter how good the template is.

### Step 4 — Create the dataset

The corpus is a plain array of objects with the schema above; column names come straight from the field names. Create it with the `arize-dataset` skill (`ax datasets create --file -` accepts stdin, so no temp file is needed), then `ax datasets append` for later additions.

Two things to get right:

- **Pin a version** once the corpus is a gate (Stage 3+) and reference that version id in the gate record. An unpinned corpus makes "we regressed" unfalsifiable, because the corpus itself may have changed.
- **Compare the schema before appending — nothing will stop you.** Fields are free-form: extra fields in appended rows are added as new columns, and fields absent from the new rows become null. A typo (`famliy` for `family`) therefore creates a silent new column rather than failing. The damage shows up downstream: the judge's `column_mappings` still point at the correctly spelled field, which is null for the new rows, so those rows come back **unscored rather than errored** and quietly shrink the denominator. Export the existing keys and diff them against the new rows before every append.

Write generated corpus files under `.scratch/` or the project's own gitignored scratch location — not into the repository — unless the team explicitly wants the corpus version-controlled alongside the app.

### Step 5 — Run it, then read the failures

Run the corpus as an experiment (see the `arize-experiment` skill), ideally as two arms so you get the gap metric. Then **read every failing row's actual response text**. This is where the real findings are: the failures cluster by technique, and the cluster tells you which single control to build first. Do not skip straight to the aggregate.

## Adding a family end to end

The most common follow-up request. Five steps, in order:

1. Add the family's defaults (`expected_behavior`, `success_criteria`, `target_control`) to the family definition.
2. Write 8+ rows across at least three techniques, plus one or two benign controls for that family.
3. Register the matching judge from [judge-library.md](judge-library.md) at `span` granularity, with `column_mappings` for every variable the template uses — including `{context}` if rows carry it.
4. Append the rows to the dataset (new version) and re-run the experiment. Experiment names collide on re-run, so use a fresh name or a suffix.
5. Hand-verify five verdicts from the new judge before adding the family to the gate.

## Maintaining it

- **Harvest on a cadence** (Stage 4). Export recent production spans, promote novel attack shapes and near-misses into rows. A static corpus decays as your surface and your attackers change.
- **Promote every incident.** A production failure becomes a corpus row the same day, with `observed_in_production: true`. This is the highest-value row you will ever add and the cheapest guarantee that the same failure does not ship twice.
- **Prune, but never prune the real rows.** Cut synthetic rows that no build has ever failed *and* that no longer map to a live control. Keep rows marked `observed_in_production`.
- **Re-check discrimination after a model upgrade.** Rows that discriminated on the old model may pass trivially on the new one. Rows whose gap has collapsed to zero need rewriting, not deletion — the family still matters.
