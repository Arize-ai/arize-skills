---
name: arize-align-evaluator
description: Aligns an Arize LLM-as-judge evaluator with human ground truth from annotation queues, span annotations, or dataset label columns. Reports the judge's status (provisional or measured) with blockers, test-split agreement and recall per label, compares queue and judge label definitions, and stops for approval before any evaluator change. Use for align evaluator, calibrate LLM judge, evaluator vs human labels, judge agreement, gold labels, or inter-annotator agreement.
metadata:
  author: arize
  version: "2.0"
compatibility: Requires the ax CLI (≥ 0.38.0), Python 3.9+, and a configured Arize profile.
---

# Arize Align Evaluator Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

**Alignment** means measuring how closely an LLM-as-judge reproduces human judgments, then fixing it where it doesn't, without fitting the fix to the records you looked at. This skill follows the eval alignment SOP's steps in order:

1. settle the criterion
2. check the gold set and its status
3. split it
4. measure
5. revise without overfitting
6. keep the judge's structure
7. correct production rates
8. test once per frozen version

Every rule cites a source in [references/sources.md](references/sources.md), or says it's an Arize heuristic.

**There are no verdict tiers.** The report gives the judge's **status**:

- **measured** when every status condition holds
- **provisional** otherwise, with each blocker and its source

It also gives heuristic **warnings** with their basis, and the numbers with intervals, test split first.

For creating evaluators, tasks and runs in general, use **arize-evaluator**. For building the queues this skill measures, use **arize-align-queue-builder**.

---

## Hard rules

| Rule | Source |
|---|---|
| **Tune and report on different sessions.** A judge version's reported agreement comes from sessions never used to write or choose its prompt. | Dwork; SIREN; SOP rule 1 |
| **A judge version is (rubric, prompt, model, admission filter).** Change any one and re-measure. | Angelopoulos; Lee; SOP rule 2 |
| **Grade whole sessions, and reject stale results.** A result scored before its session ended graded fewer turns than exist. | SOP rule 3 |
| **Never quote percent agreement alone.** Report π next to it, plus recall on the failing labels. | Thakur; SOP rule 4 |
| **Corrected production rates come only from random-stream labels.** | Angelopoulos; Chen; SOP rule 5 |
| **Change nothing before approval.** Phases 0–4 are read-only: no evaluators, versions, tasks, runs, queues or annotations. | — |
| **Edit the evaluator in place, after approval.** An approved change is a new version of the evaluator itself; Arize keeps the version history, so the template can be rolled back. Save the current version first, read the new one back, and record the switch time. Never change an evaluator without the user naming the change. | Skill practice; [references/changing-evaluators.md](references/changing-evaluators.md) |
| **Sessions read to write a rule never count as test.** List them with `--read-sessions`. | Dwork; SIREN; SOP rule 1 |
| **Preserve human labels as given.** Never relabel, merge or coerce a label. `cannot_judge` is unscorable, never an evaluator class. Keep every annotator's original vote. | — |
| **Never fabricate results.** If a command fails or a field is missing, say so. Never grade records yourself in place of the judge. | — |

---

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `Error due to additional fields (not defined in ...)`, an enum validation error, or non-JSON output from a read command → the CLI is too old to parse the API's current response. Run `ax --version`, upgrade (see [references/ax-setup.md](references/ax-setup.md)), and check `which -a ax` in case an older copy shadows the upgraded one on `PATH`. **Stop here; do not work around it.**
- `401 Unauthorized` / missing API key → run `ax profiles show` to inspect the current profile. If the profile is missing or the API key is wrong, follow [references/ax-profiles.md](references/ax-profiles.md) to create/update it. If the user doesn't have their key, direct them to https://app.arize.com/admin > API Keys
- Space unknown → see [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Use `ax profiles` for Arize credentials and `ax ai-integrations` for LLM provider keys. Never ask the user to paste secrets into chat.

[scripts/align_report.py](scripts/align_report.py) uses only the Python standard library. Its subcommands are all read-only:

| Subcommand | Does |
|---|---|
| `fetch` | Saves the queue, every page of its records, and the evaluator |
| `report` | Prints the alignment report |
| `compare` | Before/after numbers, plus the ship gate |
| `lint` | Flags revisions that patch specific records |

Run it by absolute path from the installed skill root, and write to a scratch directory.

---

## Phase 0: Inputs

1. **The evaluator.** Run `ax evaluators list --space SPACE --name "KEYWORD"`, and ask which variant if several exist. Then `ax evaluators get EVALUATOR --space SPACE -o json`. Record:
   - `template_config.name`. The output column is `<prefix>.<name>.label`, where the prefix is `eval`, `trace_eval` or `session_eval` by granularity.
   - `data_granularity`, `classification_choices` and `template`
   - `version.id`, `created_at` and `commit_message`
2. **Its task and admission filter.** Run `ax tasks list` and `ax tasks get`. The filter is part of the judge version.
3. **The ground truth.** The best source is the two queues from **arize-align-queue-builder**, plus their `plan.json`:
   - the **calibration** queue measures
   - the **gold** queue fills train and dev, and finds disagreements

   For span annotations or dataset label columns, see [references/other-ground-truth.md](references/other-ground-truth.md). If no usable queue exists, build one with **arize-align-queue-builder**.
4. **Which labels are failing**, for example `wrong` or `no_answer_produced`. Ask the user if it isn't obvious; they're passed as `--fail-label`.

## Phase 1: Settle the criterion (SOP step 1)

Read the template's definition of each label, and its scope rule, next to the queue's instructions. The report does a first pass (the label-definition diff), but read them yourself too.

- **If the two sides define a label differently, it's a criterion question.** The human and the judge are applying different rules, and agreement can't be read until it's settled. Frame it for the user: quote both definitions, give the options, and recommend one. A decision closes this report; it stays provisional. Then:
  - bump the rubric version, and write the template change as a new evaluator version (Phase 5, steps 1–2)
  - measure the new version on a **new queue pair** labeled under the new instructions, never by re-reviewing or relabeling the old queues. Their labels stay the record under the old rubric, and the sessions read become dev.
- **Draft both sides of the new rule:** the template wording and the matching queue instructions, so humans and the judge apply the same rule. Building the new queues is a queue change, so hand the instructions to **arize-align-queue-builder**, with the switch time as the window start and the old queues to exclude. This skill doesn't build them.
- **Keep applicability rules (when a session is in scope) apart from grading rules.** A scope disagreement needs a scope rule.
- **A criterion change and a judge change are different tracks.** See [references/revision.md](references/revision.md#two-kinds-of-change-sop-step-1).

Sources: Shankar et al. (criteria drift, p.2 L13–15); SOP addendum G.

## Phase 2: The gold set and its status (SOP step 2)

```bash
python3 SKILL_ROOT/scripts/align_report.py fetch --space SPACE --queue QUEUE --evaluator EVALUATOR \
  --out-dir WORK_DIR [--count-turns "ROOT_SPAN_FILTER" --project PROJECT]
python3 SKILL_ROOT/scripts/align_report.py report --dir WORK_DIR --plan PLAN_JSON \
  --rubric-version "RUBRIC_VERSION" --admission-filter "FILTER" --fail-label LABEL [--fail-label LABEL] \
  --json-out WORK_DIR/report.json > WORK_DIR/report.md
```

- **Use `--count-turns`** whenever the template reports `LAST_TURN_CHECK`. Without it, staleness is "not checked", and that's a blocker.
- **Read [references/queue-records.md](references/queue-records.md) before joining by hand.** Session records count only session-level labels, each vote appears twice, and `evaluations` holds every evaluator's results.

The status is **measured** only when all of these hold. Otherwise it's **provisional**.

| Condition | Source |
|---|---|
| 30+ scored gold records per label in each of dev and test, for 2+ labels | Husain & Shankar |
| No stale results | SOP rule 3 |
| Every gold record carries a result from the current version | SOP rule 2 |
| One record per session | SOP addendum F |
| No open criterion question | SOP step 1; addendum G |

**Warnings** never change the status. They cover fewer than 10 gold records, a label with fewer than 3, over 30% excluded, coverage below 90%, a single annotator, open disputes, and span records for a session judge. Each prints its basis, and most are Arize heuristics. Details are in [references/measurement.md](references/measurement.md).

**While provisional:**
- Report every number with its interval, and don't claim a target.
- Fix criterion, scope and queue problems first, then make at most one batch of template fixes.
- Don't tune prompt by prompt.

Most judges are provisional at discovery scale; that's expected.

## Phase 3: Split (SOP step 3)

- **Split by session, within each human label, stable across runs:** 15% train, 42.5% dev, 42.5% test. This follows Husain's 10–20 / 40–45 / 40–45.
- **Train and dev come from the gold queue,** because a rare failure can't fill 30 per split from a random sample. **Measurement comes from the calibration queue** (SOP addendum A).
- **Test is a batch labeled after freezing, by default** (`--test-from`). A same-batch test split is marked directional (Kochelka; SPEAR).

## Phase 4: Measure (SOP step 4)

The report prints, test split first:

- agreement, π and recall per label, failing labels first
- balanced accuracy, precision, leniency on the failing labels, and the confusion matrix
- AC1 and PABAK next to π when one label holds ≥ 80% (SOP addendum C)
- applicability and grade on separate lines
- the human ceiling with one rater held out, or "single annotator; no human ceiling measured" (Mukherjee; SOP addendum E)
- production estimates (Phase 7)

Meanings and sources are in [references/measurement.md](references/measurement.md).

**Then review:**

1. **Read every disagreement.** Open the session with **arize-trace**, and add it to the `--read-sessions` file. Decide whether the human is right, the judge is right, or it's ambiguous, and quote the evidence. Group the disagreements into patterns. See [references/disagreement-review.md](references/disagreement-review.md).
2. **Read the not-applicable records.** If humans said out of scope and the judge graded, the question is applicability. Check the scope rule and the task's admission filter. Spot-check a few sessions the filter excluded, too.
3. **When the session supports the judge,** adjudicate the human label; don't edit the template.
4. **Note when the judge grades its own model's output.** It's a cheap precaution, not a rule: no source here establishes self-preference.

**Present the report and STOP.** Use [references/report-template.md](references/report-template.md). Propose exactly one of these:

- **A criterion decision** for the user
- **A queue or label fix:** re-score stale sessions, top up a label, or adjudicate. Queue changes, including a new queue pair and top-ups, go to **arize-align-queue-builder**.
- **One batch of template edits,** quoting the exact current wording, the exact replacement and the records behind each. Only when no criterion question is open.

Ask the user to approve, edit or reject. **Do not continue in the same turn.**

**Don't propose template edits when:**

- a criterion question is open
- the disagreement comes from applicability, the admission filter, the unit, a stale result or an older version
- the session supports the judge
- the only evidence is a label the queue has no examples of
- the change would turn `cannot_judge` into a judge label
- a provisional judge has already had its one batch

## Phase 5: Revise without overfitting (SOP step 5, after approval)

Approval must name the change. Then, editing the evaluator in place:

1. **Baseline first.** Save the current version's JSON (for rollback) and its report as `baseline.json`.
2. **Write the new version** from the current version's full config, changing only what was approved. Read it back, compare every field, and report any difference. Record the version's `created_at` as the **switch time** in the changelog.
3. **Re-score the gold sessions** with a one-off, non-continuous task, filtered to those session IDs. Then re-run the report with `--rescored-at RUN_START`. Re-run it unchanged once more to see the noise floor. After a criterion change, this only shows the rule took effect; the old labels follow the old rubric, so agreement comes from the new queue.
4. **Treat what you read as dev.** Every session read while writing the rule goes in `--read-sessions`, so it never counts as test. Check each edit with `lint`, run the reproduce check, and look at dev once per batch.
5. **Freeze, then test on a later batch:** label it after the switch, score it once with `--test-from`, and score one other judge model on it, using a temporary copy with the other model that you delete after scoring.
6. Run the ship gate:

   ```bash
   python3 SKILL_ROOT/scripts/align_report.py compare baseline.json final.json --gate \
     --fail-label LABEL --second-judge second.json --ledger looks.json [--candidates N --fresh fresh.json]
   ```

   It passes only when all of these hold:

   - test π doesn't fall
   - the dev → test gap is ≤ 0.10 (an Arize heuristic)
   - failing-label recall doesn't drop
   - a second judge model was scored
   - when several candidates were tried, the winner was re-scored on fresh sessions

Every step, the meta-prompt for drafting revisions, and the stopping rules are in [references/revision.md](references/revision.md). Read [references/changing-evaluators.md](references/changing-evaluators.md) before writing any version.

**State the costs of an in-place edit before making it:** the production task scores live traffic with the new version from the switch time on, and stored results carry no version ID, so the column mixes versions. Rolling back restores the template, not the scores written since. Record the switch time; it's the only way to tell the versions' results apart.

**A temporary candidate copy** is the alternative when the user wants old and new scored side by side on the same records before live traffic changes. Delete it after the ship gate.

Record each change in the changelog as a criterion change or a judge change, with the switch time.

## Phase 6: Keep the judge's structure (SOP step 6)

- **Keep the judge's categories.** Test any change of scale (binary, coarse, continuous) on dev first. No source shows binary beats the alternatives for LLM judges.
- **Keep one criterion per judge.** The support for this is qualitative.
- **Chain of thought is optional.** Its measured gains were small.

## Phase 7: Production rates (SOP step 8)

With `--plan`, the calibration queue's report gives each label's production rate:

- **judge-only,** which is biased
- **corrected with PPI++** from random-stream labels
- **human-only**

Use the narrower interval. PPI assumes the labeled records match production's label mix. A stratified sample without its weights biases it, and then Rogan–Gladen or fixed weights apply (Lee §8). Re-collect labels after any judge version change. See [references/production-rates.md](references/production-rates.md).

## Phase 8: Cadence (SOP step 9)

1. **Weekly:** error analysis on new sessions, and dev revisions in batches.
2. **When a new version is frozen:** label a test batch, score it once, and run the ship gate.
3. **Revise only one or two judges at a time,** so their test batches fit the labeling budget (an Arize heuristic).
4. **Keep the calibration queue topped up** through intake; it's the drift check.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `limit: Input should be less than or equal to 100` | Use `--limit 100` and page with `--cursor`. |
| The output column is missing on every record | The column is named after `template_config.name`. Check `ax evaluators get` and pass `--eval-column`. Or the judge hasn't run on these sessions. |
| "No stale results: not checked" | Re-run `fetch` with `--count-turns ROOT_FILTER --project PROJECT`. |
| A criterion question is flagged but the definitions agree | The diff is a text heuristic. Read both. If they really agree, pass `--definitions-agree` and say so in the report. |
| Labels from other queues appear on records | Expected: a session can be in several queues. Pass `--config`. |
| Span-level labels are ignored on session records | Expected. They were made from one turn. Label sessions in a session queue (**arize-align-queue-builder**). |
| Agreement looks high but π is near 0 | One label dominates. Read AC1, balanced accuracy and failing-label recall. |
| Agreement is 0% | Label spellings differ, or the wrong column was joined. Check the fit section. |
| `Turn data mode requires a Turn Definition` when creating a version | See [references/changing-evaluators.md](references/changing-evaluators.md#turn-data-templates). |

---

## Related Skills

- **arize-align-queue-builder**: build the calibration and gold queues this skill measures
- **arize-align-history-backfill**: score sessions the evaluator never scored, for a new evaluator or a short history
- **arize-annotation**: plain queue mechanics, such as assigning a second annotator
- **arize-evaluator**: evaluator, task and run mechanics
- **arize-trace**: export a session to read the evidence behind a disagreement
- **arize-link**: deep links to sessions, queues and evaluators
