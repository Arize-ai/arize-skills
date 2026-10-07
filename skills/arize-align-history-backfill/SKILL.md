---
name: arize-align-history-backfill
description: Scores Arize sessions an evaluator never labeled so an alignment queue can sample labels the stored data lacks. Copy mode backfills history before a production evaluator's task started, using a verbatim copy calibrated against production. New-evaluator mode scores an evaluator with no task, checked against an admission rule agreed with the user. Use when arize-align-queue-builder reports a label shortfall or no stored labels, or the user wants older sessions in a gold set.
metadata:
  author: arize
  version: "1.1"
compatibility: Requires the ax CLI (≥ 0.38.0), Python 3.9+, a configured Arize profile, and the evaluator's AI integration.
---

# Arize Align History Backfill Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

**arize-align-queue-builder** picks queue records by the label an evaluator already stored on them. It can't see sessions the evaluator never scored. That happens in two ways:
- **History.** The evaluator runs in production, but its continuous task started after the sessions you need. For example, the last 30 days have too few `metric_wrong` sessions.
- **New evaluator.** The evaluator has no task at all, because it is new or is a new version built to replace another. Nothing it would label is stored anywhere.

This skill scores those sessions so the planner can sample from them.

The scoring runs as an evaluation **task on the project**, not as an experiment. Arize builds each session's input the same way a production evaluator sees it, and the task applies the admission filter itself. A dataset and experiment would need a hand-built transcript and a rebuilt filter, and neither would match production exactly.

The backfilled labels are used **only to choose records**. Humans label those records blind, so the backfilled labels never become ground truth. That protects the labels, not the metrics: agreement measured on records chosen this way needs each record's selection rate, which **arize-align-queue-builder** records in its plan.

The research behind each step, and which steps are Arize heuristics, is in [references/research.md](references/research.md).

---

## Hard rules

- **Never modify a production evaluator, its task, or its output column.** In copy mode, all scoring goes through a candidate copy with its own `template_config.name`, for example `<name>_backfill`.
- **Never backfill with an evaluator that a live task runs.** Its output column belongs to that task, so backfilled labels would mix into production's, admitted by a different filter and covering a period production never scored. This includes a new-evaluator-mode task left over after the user later attaches the evaluator to a live task. Re-check Phase 0 before every historical run. If a live task now runs the evaluator, stop using the old task (offer to delete it), switch to copy mode, and tell the user which sessions were already written to the live column.
- **Only compare an evaluator with an exact copy of itself.** `calibrate` compares a candidate with the evaluator it was copied from, and the script refuses when their templates or label choices differ. A predecessor, an earlier version or a sibling evaluator was built to behave differently. It is not a reference for labels, and its admission is not one either unless the user says it should be.
- **Get approval before each step that writes or costs money.** Phase 2's plan covers creating the task (and the candidate copy, in copy mode) and the check run. The full window needs a second approval, after the admission check and the test run pass.
- **Do not backfill if the admission check fails.** If the task admits different sessions than intended, the backfilled population is wrong.
- **Never use `--override-evaluations`** on any run here. Never trigger a production task.

---

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `Error due to additional fields`, an enum validation error, or non-JSON output → the CLI is older than the API. Upgrade, and check `which -a ax` for an older copy earlier on `PATH`.
- `401 Unauthorized` / missing API key → run `ax profiles show`, then follow [references/ax-profiles.md](references/ax-profiles.md)
- Space unknown → see [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Never ask the user to paste secrets into chat.

[scripts/backfill.py](scripts/backfill.py) uses only the Python standard library. Run it by absolute path from the installed skill root; global flags such as `--ax PATH` go before the subcommand. Only `copy-evaluator --execute` writes to Arize. Its read commands export many spans and retry rate limits themselves; run them one at a time, not in parallel.

---

## Phase 0: Pick the mode

Run `ax tasks list --space SPACE` and look for a task whose `evaluators` include **this exact evaluator** (by ID). Check every page; `--limit` caps at 100, so follow `pagination.next_cursor`.

| Situation | Mode | Reference for the admission check |
|---|---|---|
| A continuous task runs this evaluator | **Copy mode** | The production task. The candidate is a verbatim copy (`copy-evaluator`) and `calibrate` compares the two. |
| A continuous task runs this evaluator but has **not scored anything yet** (just created) | **Copy mode, calibrate later** | The production task. Copy the evaluator and set the candidate task's `--query-filter` to the live task's filter **verbatim**, then confirm the two strings are identical (`ax tasks get` both). That check stands in for calibration until the live task has a fully scored day; then run `calibrate` and report it with the queue. |
| No task runs this evaluator (new evaluator, new version, rewrite) | **New-evaluator mode** | An **admission rule agreed with the user** (below). `check-admission` compares the task's scored sessions with that rule. No other evaluator is involved. |

A task for a *related* evaluator (the version this one replaces, or a provider copy with a different template) does not make this copy mode. In new-evaluator mode the evaluator itself is the candidate. It already writes its own column, so no copy is needed.

### New-evaluator mode: agree the admission rule

Ask the user which sessions the evaluator should see once it is deployed. Use the answer in this order:
1. **Their planned deployment filter**, if they have one (a spec, a router, a task they plan to create). Use it as is.
2. **Otherwise, one of two defaults:**
   - **Every root session.** Use `{"filters": [{"id": "A", "filter": "ROOT_SPAN_FILTER"}], "expression": "A"}`. The evaluator's own `not_applicable` decides scope. This is the most faithful choice, but it costs one judge call per session, most of them `not_applicable`. It suits high-volume topics.
   - **Root sessions with the evaluator's evidence anywhere in the session.** Clause A is the root filter. Clause B matches the tool span names and output block types the template treats as evidence. The expression is `A AND B`, read across the session's spans. It suits low-volume topics.

   A predecessor's filter is a reasonable starting point for clause B **only if the user agrees** it should be. Check every evidence name the template cites against real spans (`ax spans export ... --filter "name = 'TOOL'"`). Template names that never occur add nothing, and very common reads (for example, a generic column lookup) admit unrelated sessions.

Save the rule as `admission.json`. Every later step reads it from that file.

---

## Phase 1: Estimate (read-only)

1. **Copy mode only: find the coverage start.** Confirm with `ax tasks get TASK -o json` that it is the continuous task for this evaluator, and note its `created_at`. The backfill window ends where the task's coverage begins. Use the earliest date the evaluator's column has values; any earlier backfill shows up there too. In new-evaluator mode, any window works, recent ones included, because the evaluator's column is empty everywhere.
2. **Estimate the admitted sessions:**

   ```bash
   # copy mode
   python3 SKILL_ROOT/scripts/backfill.py estimate --space SPACE --project PROJECT --task PROD_TASK \
     --start-time START --end-time END --root-filter "ROOT_SPAN_FILTER" --broad A
   # new-evaluator mode
   python3 SKILL_ROOT/scripts/backfill.py estimate --space SPACE --project PROJECT \
     --admission admission.json --evaluator EVALUATOR \
     --start-time START --end-time END --root-filter "ROOT_SPAN_FILTER" --broad A
   ```

   It exports the spans matching each clause and evaluates the expression per session: a session is admitted if its spans satisfy the clauses. `--broad A` marks the root-span clause as one that matches nearly everything, so it is re-checked against the narrower clauses instead of exported in full. It prints:
   - the number of admitted sessions, a lower bound if an export was truncated
   - how many of them are already scored
   - the single-string `--query-filter` to use for the task

   For a tighter count, raise `--pool` or `--slices`.
   **This count is a model, not the platform's rule.** It can be wrong in either direction. On `copilot-prod`, one day had 11 sessions admitted by the per-session reading while production scored 47. Another week estimated about 1,140 root sessions while a one-day run admitted 47. Quote the cost as a range, and size it again from the check run's real count.
3. **Size the window.** Each admitted session costs one judge call at the evaluator's model. Choose the smallest window likely to fill the shortfall. If 5 `metric_wrong` records are needed and recent data shows about 1 in 5 admitted sessions gets that label, aim for at least 25–50 admitted sessions, not the whole history. In new-evaluator mode there is no label history to size from. Start with about a week for low-volume topics and 2–3 days for every-root-session rules, and extend after the test run shows the label mix.

## Phase 2: Present the plan and STOP

Show the user:
- the mode, and why: the production task that runs this exact evaluator, or the fact that none exists
- in new-evaluator mode, the admission rule from `admission.json` and where it came from
- the shortfall this backfill is meant to fill, quoted from the queue builder's plan (or "no stored labels" in new-evaluator mode)
- the window, the estimated number of admitted sessions, and the judge calls that implies
- copy mode: the candidate evaluator name and output column, from the dry run `backfill.py copy-evaluator --space SPACE --source PROD_EVALUATOR --name PROD_EVALUATOR-backfill --template-name TEMPLATE_backfill`. Report any setting the dry run says the CLI can't copy.
- the task (non-continuous, same project, the single-string filter) and the **check window**: about one day, costing about that day's admitted sessions. In copy mode, production must already have scored it.
- copy mode: a **repeat copy** (a second identical candidate, e.g. `TEMPLATE_backfill_repeat`, with its own task) run on the check window only, to measure the run-to-run noise floor. It doubles the check day's cost, and nothing else.
- if the window reaches more than 14 days back: Arize's online-evals docs say evals apply to spans up to 14 days old. The test slice in Phase 5 shows whether older spans accept results.
- what becomes visible: a new task in the space, a new evaluator in copy mode, and the evaluator's output column on the project's sessions

Ask for approval to create the task (and the candidate copy, in copy mode) and to run the check. **Do not create anything in the same turn.**

## Phase 3: Create the task

1. **Copy mode only:** create the candidate with `backfill.py copy-evaluator ... --execute`. This copies the production version verbatim: template, choices, model, integration, granularity, explanations and function calling. It then reads the result back, reports any field that differs, and writes `TEMPLATE_NAME.manifest.json` with the exact model, parameters and output mode. Keep the manifest with the queue plan. If it warns that the model name looks like an alias, check that it still points at the snapshot production used; if production's snapshot is gone, treat the copy as a new evaluator (new-evaluator mode). Create the repeat copy the same way, with `--name ...-backfill-repeat --template-name TEMPLATE_backfill_repeat`.
2. **Create the task:**

   ```bash
   ax tasks create-evaluation --name "EVALUATOR backfill (DATE)" --task-type TEMPLATE_EVALUATION \
     --project PROJECT --space SPACE --no-continuous \
     --query-filter "SINGLE_STRING_FILTER_FROM_ESTIMATE" \
     --evaluators '[{"evaluator_id": "EVALUATOR_OR_CANDIDATE_ID"}]'
   ```

   In copy mode, copy `column_mappings` from the production task's evaluator entry if it has any. Session evaluators that use `{conversation}` usually have none.

   **A single string is read one span at a time.** The rule's `A AND B` is read across a session's spans. When clause B matches child spans (tool spans), the single string admits only sessions whose *root* span also shows the evidence. That usually means the root output contains `"name": "TOOL"` or `"type": "BLOCK"`. So add those output-`CONTAINS` forms to clause B for every tool name. A clause made only of `name IN (...)` on tool spans can never match a root span; it admits nothing.

## Phase 4: Check admission on one day

```bash
ax tasks trigger-run TASK --data-start-time CHECK_START --data-end-time CHECK_END --wait --timeout 1800
```

`trigger-run` returns `No data found between ...` when the window has no admitted sessions. Pick a weekday with traffic for that topic.

After the first run, results reach the spans before the filter index sees the new column. That can take 20 minutes or more. If the command below says no part of the window has values for the column, wait and re-run it; that does not mean nothing was scored. Periods with no values inside the window are treated as empty, not as errors.

**Copy mode: `calibrate`.** Pick a window whose production runs have completed: `ax tasks list-runs PROD_TASK` shows each run's `data_end_time`.

```bash
python3 SKILL_ROOT/scripts/backfill.py calibrate --space SPACE --project PROJECT \
  --start-time CHECK_START --end-time CHECK_END --root-filter "ROOT_SPAN_FILTER" \
  --prod-evaluator PROD_EVALUATOR --cand-evaluator CANDIDATE --repeat-evaluator REPEAT_CANDIDATE
```

It first confirms the candidate is a copy of the production evaluator, meaning the same template, label choices and granularity, and exits otherwise. Then it compares which sessions each scored and how their labels agree. **Admission must match**: by default, at most 5% of sessions scored by only one side.

Label agreement is reported separately, as a count and as Cohen's κ, with the label mix on each side:
- **Noise floor.** With `--repeat-evaluator`, it compares the candidate with the repeat copy on the same sessions. Run-to-run noise differs a lot by task and model, so this measures it instead of assuming it. If production agreement sits more than `--noise-margin` (default 5 points) below the floor, the gap is more than noise: check settings that didn't copy, the model version and the output mode before backfilling. Without a repeat copy, the report says the gap can't be attributed to noise.
- **Different turn counts.** For templates that report `LAST_TURN_CHECK`, disagreements where the two sides saw different turn counts are counted separately: one side scored the session before it ended. Agreement is also shown without them.
- A gap that remains is acceptable, because backfilled labels only choose records, but give the numbers when presenting the queue plan. After the check, delete the repeat copy's task (`ax tasks delete`) once the user confirms.

**New-evaluator mode: `check-admission`.**

```bash
python3 SKILL_ROOT/scripts/backfill.py check-admission --space SPACE --project PROJECT \
  --start-time CHECK_START --end-time CHECK_END --root-filter "ROOT_SPAN_FILTER" \
  --admission admission.json --broad A --cand-evaluator EVALUATOR --write-units intended.json
```

It reads the rule across each session's spans, then compares the sessions it admits with the sessions the task actually scored. The same 5% tolerance applies. Labels are not compared, because there is nothing to compare them with. `--write-units` saves the sessions the rule admits, plus ready-made task filters that admit exactly those sessions, for the fix below. `estimate --write-units` writes the same file without a test run.

### If the admission check fails

- **The task missed sessions the rule admits:** the single string is narrower than the rule. Usually the evidence is on child spans only. First add the root-output `CONTAINS` forms (Phase 3) and re-check. If sessions are still missed, use **session-ID admission**:
  - Run `estimate --write-units units.json` over the window. Its `query_filters` list holds `ROOT_SPAN_FILTER AND attributes.session.id IN (...)` strings of up to 100 sessions each.
  - For each string, set it with `ax tasks update TASK --query-filter` and trigger a run over the window.
  - Re-run `check-admission` on the test slice to confirm the task applies it.
  - Copy mode has one more option: create the candidate task in the Arize UI with the production task's filter clauses and expression.
- **The task scored sessions the rule does not admit:** the single string is broader. Narrow it, or switch to session-ID admission.
- **Copy mode, production scored sessions the candidate did not:** also check the window against the production runs' `data_start_time` and `data_end_time`. Sessions that started before the window and continued into it are re-scored by a continuous task but skipped by a one-off run. When every missed session is `not_applicable`, that boundary effect is harmless.
- Report the counts and stop. Do not backfill on a failed check unless the user accepts a subset, as below.

**Accepting a subset.** The candidate's sessions may be a subset of the reference's (almost none scored only by the candidate). The user may then accept the narrower population. Backfilled labels only choose records, so a subset is acceptable when it covers the labels the queue is short of. Before running, give the user the subset size, which labels it under-covers, and what the missed sessions were labeled where known. Record that acceptance and those numbers in the queue plan. When reporting results, never present the backfilled population as production's.

**Copy mode: label disagreements are findings.** When the same template and model disagree on a shared session, read the explanations:
- *Different turn counts*: production scored the session before it finished. Its stored labels for multi-turn sessions may be stale, which also affects **arize-align-evaluator** comparisons.
- *Same turns, opposite readings*: the template is ambiguous on that case. Pass those sessions to the queue builder as priority records, and mention the ambiguity in the alignment report.

## Phase 5: Test one historical slice

Before the full window, run one small slice of the window, such as a single day. In new-evaluator mode, the check day can serve as this slice if it falls inside the window.

```bash
ax tasks trigger-run TASK --data-start-time DAY_START --data-end-time DAY_END --max-spans 200 --wait
ax tasks get-run RUN_ID
python3 SKILL_ROOT/scripts/backfill.py verify --space SPACE --project PROJECT \
  --start-time DAY_START --end-time DAY_END --root-filter "ROOT_SPAN_FILTER" --cand-evaluator CANDIDATE
```

- `num_successes` > 0, and `verify` shows labels: the data is scorable. Compare the count with the estimate for that day, and use the label mix to resize the window.
- The run completes with 0 successes while the estimate shows admitted sessions: the evaluation index may not cover that period. Report this and stop. The backfill can't reach that history.
- `num_errors` > 0: check `ax tasks get-run RUN_ID` and the integration (**arize-ai-provider-integration**).

Present the admission check and test results, plus the remaining cost, and **ask for approval of the full window.**

## Phase 6: Run the full window, then hand back

1. Run the full window in pieces of about a week, so each run stays under the `--max-spans` limit (default 10,000) and the wait timeout. Use `trigger-run ... --wait --timeout 3600`, then run `verify` on the whole window.
2. Hand back to **arize-align-queue-builder**, pointing its planner at the backfilled column and window:

   ```bash
   python3 QUEUE_BUILDER_ROOT/scripts/plan_queue.py ... \
     --eval-name TEMPLATE --start-time WINDOW_START --end-time WINDOW_END \
     --exclude-queue EXISTING_QUEUES
   ```

   In copy mode, `TEMPLATE` is the candidate's `*_backfill` name; add `--labels SHORT_LABEL --per-label N` to fill only the shortfall. In new-evaluator mode, it is the evaluator's own template name, and the planner samples every label. Backfill only sessions that have ended: leave out the most recent hours of a window that runs up to now, so no session is scored mid-conversation.
3. **Clean up.** The task is non-continuous, so it does not run again on its own. Keep the evaluator, its column, and in copy mode the candidate copy, because the queue's records were selected from them. Delete them (`ax tasks delete`, `ax evaluators delete`) only if the user asks, after confirming. Deletion can't be undone.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `calibrate` exits with "is not a copy of" | The two evaluators differ in template, label choices or granularity. If no task runs this evaluator, use new-evaluator mode and `check-admission`. If production changed after the copy, make a fresh copy. |
| `estimate` admits 0 sessions | One clause matches nothing in the window. Check each clause's count; the old data may predate the attributes the filter uses. |
| The task scores far fewer sessions than the rule admits | The single string reads one span at a time, but the rule reads across a session's spans (Phase 3). Add root-output `CONTAINS` forms, or use session-ID admission. |
| Production scores many more units than `estimate` predicts | The platform's admission is broader than the per-unit reading; the extra units are often `not_applicable`. `calibrate` measures the real ratio. Quote the cost as a range. |
| `trigger-run`: `No data found between ...` | No admitted sessions in that window. Pick a weekday with traffic for the topic. |
| "No part of the window has values for the eval column" 20+ minutes after a run | Results reach spans before the filter index. Confirm by exporting root spans for the window and looking for the template name in `evaluations`; then wait and re-run. |
| `copy-evaluator` notes structured output cannot be set | The CLI has no flag for it. Proceed if calibration's label agreement is acceptable; mention it in the plan. |
| Run stuck `PENDING` / `RUNNING` | `ax tasks get-run RUN_ID`; `ax tasks cancel-run RUN_ID` if it has to stop. |
| Planner sees no backfilled labels | Pass `--eval-name` with the template name that was scored, and the backfill window. The default 30-day window may not include it. |

---

## Related Skills

- **arize-align-queue-builder**: plans the queue and reports which labels are short
- **arize-align-evaluator**: measures the finished queue against the evaluator
- **arize-evaluator**: task, trigger-run and column-mapping mechanics
- **arize-ai-provider-integration**: fix judge-model credential errors
