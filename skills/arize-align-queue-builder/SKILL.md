---
name: arize-align-queue-builder
description: Builds an Arize annotation queue designed to produce enough meaningful human labels to align a specific LLM-as-judge evaluator. Derives the label config from the evaluator, samples balanced records across its labels, sizes the queue for expected exclusions, writes annotator instructions, and stops for approval before creating anything. Use when the user needs a labeling queue, gold set, or human labels for evaluator alignment, or when an existing queue had too few usable labels.
metadata:
  author: arize
  version: "1.1"
compatibility: Requires the ax CLI (≥ 0.38.0), Python 3.9+, and a configured Arize profile.
---

# Arize Align Queue Builder Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

This skill builds an annotation queue whose labels can be used to align one evaluator. A queue built by picking recent spans usually fails in four ways:
- Most records turn out to be off-topic, so humans mark them not applicable.
- Nearly every label is the same, so the evaluator's other labels are never tested.
- The rubric doesn't match the evaluator's labels.
- The same session is labeled twice.

This skill designs the queue to avoid all four. The output is a queue that **arize-align-evaluator** can measure. This skill does not measure agreement or change evaluators.

For plain queue mechanics (create, update, assign, delete), use **arize-annotation**.

---

## Hard rules

- **Do not create anything before approval.** Phases 1–3 are read-only. Do not create the annotation config, the queue or its records until the user approves the plan in Phase 4.
- **Never label records yourself.** Never present model output or stored evaluator labels as human labels.
- **Keep labeling blind.** Stored evaluator labels are used to *choose* records. The instructions must tell annotators not to look at evaluator output, and the plan must never be shared with them.
- **One record per unit.** For a session evaluator, each session appears once, and sessions already in the user's other queues for this evaluator are excluded.

---

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `Error due to additional fields`, an enum validation error, or non-JSON output → the CLI is older than the API. Upgrade, and check `which -a ax` for an older copy earlier on `PATH`.
- `401 Unauthorized` / missing API key → run `ax profiles show`, then follow [references/ax-profiles.md](references/ax-profiles.md)
- Space unknown → see [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Never ask the user to paste secrets into chat.

[scripts/plan_queue.py](scripts/plan_queue.py) uses only the Python standard library and is read-only. Run it by absolute path from the installed skill root, writing to a scratch directory.

---

## Phase 1: Understand the evaluator

1. **Find the evaluator** with `ax evaluators list --space SPACE --name "KEYWORD"`, and confirm with the user which variant is being aligned. Then read it with `ax evaluators get EVALUATOR --space SPACE -o json`. Record:
   - `template_config.name`. The stored output column is `<prefix>.<name>.label`, where the prefix is `eval`, `trace_eval` or `session_eval` depending on granularity.
   - `data_granularity`, which sets the unit each record must represent.
   - `classification_choices`.
   - The `template`, especially how it defines each label and when to use `not_applicable`.
2. **Find the task that runs it** with `ax tasks list --space SPACE`, then `ax tasks get TASK -o json`. The task must list **this exact evaluator** by ID; check every page of the list. Record the `project_id` and the `query_filters`. That filter is the evaluator's admission rule; the queue should sample from the population that rule admits.

   **If no task runs this evaluator** (a new evaluator, or a new version built to replace another), it has no stored labels to plan from. Hand off to **arize-align-history-backfill** in its new-evaluator mode. It agrees an admission rule with the user, scores sessions with the evaluator itself, and checks the task against that rule. Then plan on the evaluator's own column. Don't treat a predecessor's task or labels as this evaluator's. If the user wants a quick proxy plan from a predecessor's stored labels (`--eval-name`), say that labels the predecessor can't output will come up empty, and that its scope rules differ.
3. **Check for other copies.** A provider copy (for example a `*_anthropic` evaluator on the same task population) is useful. Records where two copies disagree are often the most informative to label.
4. **Find the existing queues for this evaluator** with `ax annotation-queues list --space SPACE --name "KEYWORD"`. Their records will be excluded. If one exists, ask whether this is a **new queue** or a **top-up** of the existing one (see Phase 6).

## Phase 2: Design the label config and instructions

Follow [references/rubric-and-instructions.md](references/rubric-and-instructions.md). In short:
- **Label values** are the evaluator's choices, spelled exactly the same, plus `not_applicable` (if the evaluator lacks it) and `cannot_judge`. The script writes these to `config_values.json`. Don't add labels the evaluator cannot output. They become off-rubric records that can't be compared.
- **Reuse an existing config** if one already has exactly these values, so labels stay comparable across rounds. Otherwise propose a new one with a dated name.
- **Instructions** define every label in the template's own terms. They say which unit to judge (the whole session for session evaluators) and when `cannot_judge` is allowed, and they tell annotators not to look at evaluator output. For session evaluators, they also tell annotators to put the label on the **session**, not on the individual span.

## Phase 3: Plan the records

```bash
python3 SKILL_ROOT/scripts/plan_queue.py \
  --space SPACE --project PROJECT --evaluator EVALUATOR \
  --root-filter "ROOT_SPAN_FILTER" \
  --compare-eval OTHER_COPY_TEMPLATE_NAME \
  --exclude-queue EXISTING_QUEUE [EXISTING_QUEUE ...] \
  --out-dir WORK_DIR
```

- `--root-filter` makes each candidate a single entry-point span, for example `attributes.is_copilot_root_span = 'true'`, or `parent_id` being null. Ask the user, or derive it from the task's filters. Without it, child spans of one session compete with each other as candidates.
- `--compare-eval` is the `template_config.name` of another copy of the evaluator. Disagreements between the copies are picked first, up to 40% of each label's quota.
- `--na-probe-eval` is the template name of another evaluator that grades the same sessions, for example the version this one replaces. It adds `--na-probe-count` records (default 5) that this evaluator called not applicable but the other graded decisively. Use it when a label comes up empty because the new scope rule moved those sessions to not applicable. If humans label the probes decisively, the scope rule is too strict. The other evaluator only chooses records; labelers stay blind to it.
- `--expected-exclusion` is the share of records you expect humans to mark not applicable or cannot judge. The default is 0.30. If an earlier queue for this evaluator exists, use its actual excluded rate from the **arize-align-evaluator** report.
- `--mode` sets the size. `directional` (default) aims for about 10 gold records, enough to start aligning. `validation` aims for 30 per label and 50 in all, enough for the evaluator's VALIDATED verdict. Ask the user which they need; validation queues are several times larger.

How it picks (details and reasoning in [references/sampling.md](references/sampling.md)):
1. For each evaluator label, it exports candidates whose stored label is that label, drawn evenly across the time window.
2. It deduplicates to one span per unit and drops units already in excluded queues.
3. It sizes each decisive label's quota so the queue should clear the gates after exclusions (5 per label at the defaults; formula in [Sizing](references/sampling.md#sizing)), and adds 2 records with a stored `not_applicable` label to test applicability.
4. Within each label, it spreads picks across entry points (span names), and puts provider disagreements first.
5. It counts each stratum's production units and records every record's stratum and selection rate, so the evaluator report can weight results back to production ([Strata and weights](references/sampling.md#strata-and-weights)).

The research behind each choice, and which choices are Arize heuristics, is in [references/research.md](references/research.md).

It writes `plan.md`, `plan.json`, `config_values.json` and the record sources. Arize accepts at most 7 days per record source and at most 2 sources per call, so the script splits the records into `record_sources.create.json` (for `create`) and `record_sources.add_N.json` (for `add-records`). `record_sources.json` holds all of them. Periods where the evaluator's column has no values are skipped and listed in `plan.md`. The script retries rate limits itself; run one evaluator at a time rather than several in parallel.

If a label is short of candidates, widen `--days` first. If the continuous task hasn't been running long enough to have them, use **arize-align-history-backfill** (copy mode) to score older sessions with a candidate copy of the evaluator, then re-plan with `--eval-name` and `--start-time`/`--end-time` pointing at the backfilled column. Low-volume topics are cheap to backfill further back. A label the evaluator almost never gives (none in hundreds of sessions) usually won't come from more backfill; use `--na-probe-eval` instead. Otherwise accept the shortfall and say so. Don't fill the gap with records from other labels.

## Phase 4: Present the plan and STOP

Show the user:
- the evaluator, version, unit and admission filter the plan is based on
- the per-label table from `plan.md`, including any shortfall, and the expected number of gold records
- the proposed annotation config values (or the existing config to reuse), and the full instructions text
- annotators and assignment. A single annotator is fine. With two or more, use `ALL` if they want agreement measured.
- the queue name, for example `<evaluator> alignment gold (YYYY-MM-DD)`, and the config name from `plan.md` (Arize caps it at 40 characters)
- when the records came from a backfill, the column **arize-align-evaluator** will compare against: the backfill copy's `*_backfill` column, not the live one, because the live task never scored these sessions
- the sizing mode and the expected gold per label; at the default size, say that the queue can start an alignment but not validate one
- the caveats: records are stratified by the evaluator's own labels, so agreement within a label is its precision; recall and production rates need `report --plan plan.json`; labelers must stay blind to the labels

Then ask the user to approve or adjust. **Do not create anything in the same turn.**

## Phase 5: After approval, create the queue

1. **Resolve the annotators.** Each `--annotator-email` must belong to a user with access to the space, and people often have a different address per account. Check with `ax users list --email NAME -o json`, use the address listed there, and confirm it with the user. An unknown address fails with `Annotator email not found or does not have access`.
2. **Create the config**, unless you are reusing one. With `-o json`, the response includes its `id`:

   ```bash
   ax annotation-configs create categorical --name "CONFIG_NAME" --space SPACE \
     --value LABEL_1 --value LABEL_2 ... --optimization-direction NONE -o json
   ```
3. **Create the queue with its first record sources, then add the rest:**

   ```bash
   ax annotation-queues create --name "QUEUE_NAME" --space SPACE \
     --annotation-config-id CONFIG_ID \
     --annotator-email A@example.com [--annotator-email B@example.com] \
     --assignment-method ALL \
     --instructions "$(cat WORK_DIR/instructions.txt)" \
     --record-sources WORK_DIR/record_sources.create.json
   ax annotation-queues add-records QUEUE_ID --space SPACE --record-sources WORK_DIR/record_sources.add_1.json
   # ...one add-records per remaining record_sources.add_N.json
   ```

   Instructions are limited to 5000 characters. Create queues one at a time; if a call fails part way, check what exists (`ax annotation-configs get`, `ax annotation-queues get`) before retrying, so nothing is created twice.
4. **Verify.** Run `ax annotation-queues list-records QUEUE --space SPACE --limit 100 -o json`. Confirm the record count matches the plan, every planned span ID is present, and no session appears twice. If any are missing, report which ones. Re-run `add-records` with the plan's source file that holds them, or explain why they were dropped.

## Phase 6: Check partway, then top up

After annotators have labeled about a third of the records, run the **arize-align-evaluator** report on the queue. Check the bucket counts against the plan:
- **Excluded rate well above expected:** the admission population is wider than the evaluator's scope. Raise `--expected-exclusion`, or tighten `--root-filter`, before topping up.
Top up only on counts: a label short of gold records, or exclusions above plan. Never top up because agreement so far looks low or high; that biases the result.

- **A label is short of gold records:** run the script again with `--labels THAT_LABEL --per-label N --exclude-queue THIS_QUEUE`, and add each new `record_sources.create.json` / `record_sources.add_N.json` file with `ax annotation-queues add-records QUEUE --space SPACE --record-sources FILE`. That still requires the user's approval.
- **Annotators disagree:** clarify the label definitions in the instructions with `ax annotation-queues update --instructions` before more labeling.

When labeling is complete, hand off to **arize-align-evaluator**. Name the column it should compare against (the `*_backfill` column when the records came from a backfill), and pass it `plan.json` (`report --plan`) for production-weighted estimates. For a topped-up queue, merge the strata of every plan run into one `plan.json` first.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `No spans found` for a label | The evaluator has not stored that label in the window. Widen `--days`, check the column name (`<prefix>.<template_config.name>.label`), or backfill older sessions with **arize-align-history-backfill**. |
| Export with the task's full filter returns nothing | Session task filters can combine conditions on different spans of a session. Use the root-span condition alone as `--root-filter`; the stored-label filter already restricts candidates to admitted units. |
| Candidates cluster on a few days | A backfill scored those days. The script draws evenly across `--slices` time windows; raise `--slices` or narrow `--days`. |
| Planned records missing after create | Check `record_sources.json` covers their time window and project. Re-add the missing span IDs with `add-records`. |
| Script stops with "No part of the window has values for the eval column" | A wrong `--eval-name` or `--na-probe-eval`, a window the evaluator never scored, or a new column still indexing (20+ minutes after a run). Periods with no values are skipped, not fatal. |
| `time range ... must not exceed 7 days` or `List should have at most 2 items` | A hand-built record source. Use the script's split files: `record_sources.create.json` for `create`, then `add-records` with each `record_sources.add_N.json`. |
| `Annotator email not found or does not have access` | The address isn't a user in this space. Look it up with `ax users list --email NAME`. |
| Labels land on spans instead of the session | The level is chosen when annotating. Restate it in the instructions; **arize-align-evaluator** reads span, trace and session labels either way. |

---

## Related Skills

- **arize-align-evaluator**: measure the finished queue against the evaluator, and run the alignment loop
- **arize-align-history-backfill**: score sessions the evaluator never labeled, either pre-task history (copy mode) or everything, for an evaluator with no task (new-evaluator mode)
- **arize-annotation**: annotation config and queue CRUD, assigning records
- **arize-evaluator**: find the evaluator's task, filters and granularity
- **arize-trace**: export a session to check what annotators will see
