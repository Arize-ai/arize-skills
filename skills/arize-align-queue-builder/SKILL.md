---
name: arize-align-queue-builder
description: Builds Arize annotation queues that yield enough human labels to align one LLM-as-judge evaluator, with a random calibration queue that measures it and a targeted queue that covers every label it gives. Derives the label config from the evaluator, sizes for exclusions, writes blind annotator instructions, and stops for approval before creating anything. Use when the user needs human labels for evaluator alignment, a queue had too few usable labels, or a queue should keep taking in new records.
metadata:
  author: arize
  version: "1.2"
compatibility: Requires the ax CLI (≥ 0.38.0), Python 3.9+, and a configured Arize profile.
---

# Arize Align Queue Builder Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

This skill builds the annotation queues whose labels are used to align one evaluator. A queue built by picking recent spans usually fails in five ways:
- Most records turn out to be off-topic, so humans mark them not applicable.
- Nearly every label is the same, so the evaluator's other labels are never tested.
- The rubric doesn't match the evaluator's labels.
- The same session is labeled twice.
- Records picked using the evaluator's own labels are then used to measure it, which biases the result.

So the skill builds two streams ([Two streams](references/sampling.md#two-streams)):
- **Random (calibration queue):** a uniform sample with a known rate, never filtered on the evaluator's labels. Agreement and the human ceiling come from it; **arize-align-evaluator** reports them with the evaluator's status.
- **Targeted (gold queue):** a quota per stored label, so every label, rare ones included, has human labels for checking its precision and for dev and few-shot examples. Optional extras look for errors directly: provider disagreements, judge-independent signals and scope probes.

The output is queues that **arize-align-evaluator** can measure. This skill does not measure agreement or change evaluators.

For plain queue mechanics (create, update, assign, delete), use **arize-annotation**.

---

## Hard rules

- **Do not create anything before approval.** Phases 1–3 are read-only. Do not create the annotation configs, the queues or their records until the user approves the plan in Phase 4. For continuous intake, the user approves the intake settings and schedule once (Phase 7); scheduled runs then add records without asking each time.
- **Never label records yourself.** Never present model output or stored evaluator labels as human labels.
- **Measure only on the random stream.** Targeted records were chosen by the evaluator's labels or other signals. Never quote their agreement as the evaluator's accuracy.
- **Keep labeling blind.** Stored evaluator labels are used to *choose* records. Set each queue's Annotator Columns so evaluator output is hidden, and check it ([Keeping labelers blind](references/rubric-and-instructions.md#keeping-labelers-blind)). Never share the plan with annotators.
- **No queue while a label is flagged.** The definition check (Phase 3) compares the draft instructions with the template. While it flags a label, don't create the queues: fix the instructions or the template first, or read both definitions with the user and confirm they state the same rule. Annotators and the judge applying different rules was the main reason a past alignment couldn't be read.
- **One record per unit.** For a session evaluator, each session appears once across both queues, and sessions already in the user's other queues for this evaluator are excluded. The one exception is a re-grade queue the user asked for after a definition change.

---

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `Error due to additional fields`, an enum validation error, or non-JSON output → the CLI is older than the API. Upgrade, and check `which -a ax` for an older copy earlier on `PATH`.
- `401 Unauthorized` / missing API key → run `ax profiles show`, then follow [references/ax-profiles.md](references/ax-profiles.md)
- Space unknown → see [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Never ask the user to paste secrets into chat.

[scripts/plan_queue.py](scripts/plan_queue.py) uses only the Python standard library and is read-only, except `--intake --execute` (Phase 7). Run it by absolute path from the installed skill root, writing to a scratch directory.

---

## Phase 1: Understand the evaluator

1. **Find the evaluator** with `ax evaluators list --space SPACE --name "KEYWORD"`, and confirm with the user which variant is being aligned. Then read it with `ax evaluators get EVALUATOR --space SPACE -o json`. Record:
   - `template_config.name`. The stored output column is `<prefix>.<name>.label`, where the prefix is `eval`, `trace_eval` or `session_eval` depending on granularity.
   - `data_granularity`, which sets the unit each record must represent.
   - `classification_choices`.
   - The `template`, especially how it defines each label and when to use `not_applicable`.
2. **Find the task that runs it** with `ax tasks list --space SPACE`, then `ax tasks get TASK -o json`. The task must list **this exact evaluator** by ID; check every page of the list. Record the `project_id` and the `query_filters`. That filter is the evaluator's admission rule; the queues should sample from the population that rule admits.

   **If no task runs this evaluator** (a new evaluator, or a new version built to replace another), it has no stored labels to plan from. Hand off to **arize-align-history-backfill** in its new-evaluator mode. It agrees an admission rule with the user, scores sessions with the evaluator itself, and checks the task against that rule. Then plan on the evaluator's own column. Don't treat a predecessor's task or labels as this evaluator's. If the user wants a quick proxy plan from a predecessor's stored labels (`--eval-name`), say that labels the predecessor can't output will come up empty, and that its scope rules differ.
3. **Check for other copies.** A provider copy (for example a `*_anthropic` evaluator on the same task population) is useful. Records where two copies disagree are often the most informative to label.
4. **Find the existing queues for this evaluator** with `ax annotation-queues list --space SPACE --name "KEYWORD"`. Their records will be excluded. If they exist, ask whether this is a **new round** or a **top-up** (see Phase 6).
5. **Ask whether anyone has done error analysis** on this evaluator's traffic: a domain expert reading 30 or more real traces and noting how they fail. If not, start in `discovery` mode. Its 30 random records are for that expert to open-code before the rubric is trusted. Rubric definitions often change once people see real outputs, so settle them before a validation round.
6. **Ask for judge-independent signals.** User thumbs-down or feedback annotations, escalations, or high-severity topics that can be written as a span filter become `--signal` strata. They find failures the evaluator is confidently wrong about.

## Phase 2: Design the label configs and instructions

Follow [references/rubric-and-instructions.md](references/rubric-and-instructions.md). In short:
- **Label values** are the evaluator's choices, spelled exactly the same, plus `not_applicable` (if the evaluator lacks it) and `cannot_judge`. The script writes these to `config_values.json`. Don't add labels the evaluator cannot output. They become off-rubric records that can't be compared.
- **A critique config:** an optional free-text config attached next to the label config. Labeling time is the main cost, so a critique is asked for only on close calls and `cannot_judge`. Fuller critiques for few-shot examples are written during adjudication, on the records that need them.
- **Reuse existing configs** if they already have exactly these values, so labels stay comparable across rounds. Otherwise propose new ones with dated names.
- **Instructions** define every label in the template's own terms. They say which unit to judge (the whole session for session evaluators), when `cannot_judge` is allowed, when a critique is wanted (optional, but asked for on close calls and `cannot_judge`), and to work in sittings of about 100 records. They tell annotators not to look at evaluator output. For session evaluators, they also say to put the label on the **session**, not on an individual span. They start with a version line. Save the draft to a file and pass it to the script as `--instructions-file`; its first line becomes the instructions version.

## Phase 3: Plan the records

```bash
python3 SKILL_ROOT/scripts/plan_queue.py \
  --space SPACE --project PROJECT --evaluator EVALUATOR \
  --root-filter "ROOT_SPAN_FILTER" \
  --mode discovery|validation \
  --compare-eval OTHER_COPY_TEMPLATE_NAME \
  --signal NAME="SPAN_FILTER" \
  --instructions-file WORK_DIR/instructions.txt \
  --exclude-queue EXISTING_QUEUE [EXISTING_QUEUE ...] \
  --out-dir WORK_DIR
```

- `--mode` sets the size ([Sizing](references/sampling.md#sizing)). Ask the user which they need; validation is several times larger.
  - `discovery` (default): about 10 gold targeted records and 30 random ones. Enough for error analysis and a first alignment pass, not to validate.
  - `validation`: 30 gold per label in each of dev and test (102 per label at the default exclusion rate) and 100 random records.
- `--random N` overrides the random stream's size; `--random 0` turns it off, and then nothing in the plan can measure agreement. Size it from the interval needed, not a share of traffic.
- `--root-filter` makes each candidate a single entry-point span, for example `attributes.is_copilot_root_span = 'true'`, or `parent_id` being null. Ask the user, or derive it from the task's filters. Without it, child spans of one session compete with each other as candidates.
- `--compare-eval` is the `template_config.name` of another copy of the evaluator. Disagreements between the copies are picked first, up to 40% of each label's quota, and counted in full as their own stratum.
- `--signal NAME=FILTER` (repeatable) adds `--signal-count` records (default 5) matching a judge-independent span filter.
- `--na-probe-eval` is the template name of another evaluator that grades the same sessions, for example the version this one replaces. It adds `--na-probe-count` records (default 5) that this evaluator called not applicable but the other graded decisively. Use it when a label comes up empty because the new scope rule moved those sessions to not applicable. If humans label the probes decisively, the scope rule is too strict. The other evaluator only chooses records; labelers stay blind to it.
- `--max-turns N` (session evaluators, default 40) skips sessions with more than N turns, counted as spans matching `--root-filter`. Long sessions take far longer to label (roughly 1 minute plus 15 seconds a turn), and a few 100+ turn sessions can cost more than the rest of the queue. Both streams, their strata and the production counts then cover only sessions up to the cap, so the evaluator is unchecked on longer ones; say so when quoting results. `--max-turns 0` turns it off.
- `--instructions-file` runs the **definition check**: each label's definition in the draft instructions next to the template's, flagging labels whose wording differs or that name a tool or field on only one side. It's the same check **arize-align-evaluator** runs after labeling, so a mismatch is caught before anyone labels. It also notes a version line that differs from `--instructions-version` and instructions over 5000 characters.
- **Stale results are skipped.** When a session evaluator's template reports `LAST_TURN_CHECK`, sessions whose stored result graded fewer turns than the session has are left out of both streams and the production counts, the same way as the turn cap. They were scored mid-session, so the label being checked isn't the session's. `plan.md` lists them. `--keep-stale` keeps them; the check needs `--root-filter` to count turns.
- `--expected-exclusion` is the share of records you expect humans to mark not applicable or cannot judge. The default is 0.30. If an earlier queue for this evaluator exists, use its actual excluded rate from the **arize-align-evaluator** report.

It draws the random stream first, then the signals, the label strata (provider disagreements first, spread across entry points) and the not-applicable checks. Each record gets its stratum, `routing_reason`, stream, period and instructions version. How and why it picks each are in [references/sampling.md](references/sampling.md).

It writes `plan.md`, `plan.json`, `config_values.json` and the record sources. Targeted records go to `record_sources.*` (the gold queue), and random records go to `random_sources.*` (the calibration queue). Arize accepts at most 7 days per record source and at most 2 sources per call, so each set is split into a `*.create.json` (for `create`) and `*.add_N.json` files (for `add-records`). Periods where the evaluator's column has no values are skipped and listed in `plan.md`. The script retries rate limits itself; run one evaluator at a time rather than several in parallel.

If a label is short of candidates, widen `--days` first. If the continuous task hasn't been running long enough to have them, use **arize-align-history-backfill** (copy mode) to score older sessions with a candidate copy of the evaluator, then re-plan with `--eval-name` and `--start-time`/`--end-time` pointing at the backfilled column. Low-volume topics are cheap to backfill further back. A label the evaluator almost never gives (none in hundreds of sessions) usually won't come from more backfill; use `--na-probe-eval` instead. Otherwise accept the shortfall and say so. Don't fill the gap with records from other labels.

## Phase 4: Present the plan and STOP

Show the user:
- the evaluator, version, unit and admission filter the plan is based on, and the turn cap with how many scored sessions it left out
- the random stream: its size, the frame it was drawn from, and its rate
- the targeted table from `plan.md`, including any shortfall, and the expected number of gold records
- the proposed label and critique configs (or existing ones to reuse), and the full instructions text with its version line
- the **definition check** from `plan.md`: every flagged label with both definitions. Resolve each flag before approval (hard rules)
- how many sessions were left out as stale
- annotators and assignment for each queue:
  - In `validation` mode the calibration queue needs 3 or more annotators with `ALL`, for human–human agreement. If their agreement is high, the gold queue can be single-annotated.
  - In `discovery` mode one domain expert labels the random records.
- the queue names, for example `<evaluator> calibration (YYYY-MM-DD)` and `<evaluator> gold (YYYY-MM-DD)`, and the config names from `plan.md` (Arize caps them at 40 characters)
- when the records came from a backfill, the column **arize-align-evaluator** will compare against: the backfill copy's `*_backfill` column, not the live one, because the live task never scored these sessions
- the sizing mode and the expected gold per label; in discovery mode, say that the queues can start an alignment but not validate one, and that a discovery round normally ends in a criterion decision and template edits, not an agreement number
- the caveats:
  - Agreement comes from the calibration queue. Targeted records cover every label, and agreement within a stored label is only that label's precision. Without disagreements or signals, they barely test errors hidden inside a common label.
  - Labelers must stay blind; the Annotator Columns step is manual.

Then ask the user to approve or adjust. **Do not create anything in the same turn.**

## Phase 5: After approval, create the queues

1. **Resolve the annotators.** Each `--annotator-email` must belong to a user with access to the space, and people often have a different address per account. Check with `ax users list --email NAME -o json`, use the address listed there, and confirm it with the user. An unknown address fails with `Annotator email not found or does not have access`.
2. **Create the configs**, unless you are reusing them. With `-o json`, each response includes its `id`:

   ```bash
   ax annotation-configs create categorical --name "CONFIG_NAME" --space SPACE \
     --value LABEL_1 --value LABEL_2 ... --optimization-direction NONE -o json
   ax annotation-configs create freeform --name "CRITIQUE_CONFIG_NAME" --space SPACE -o json
   ```
3. **Create each queue with its first record sources, then add the rest.** The calibration queue takes `random_sources.*`, and the gold queue takes `record_sources.*`:

   ```bash
   ax annotation-queues create --name "CALIBRATION_QUEUE_NAME" --space SPACE \
     --annotation-config-id CONFIG_ID --annotation-config-id CRITIQUE_CONFIG_ID \
     --annotator-email A@example.com --annotator-email B@example.com --annotator-email C@example.com \
     --assignment-method ALL \
     --instructions "$(cat WORK_DIR/instructions.txt)" \
     --record-sources WORK_DIR/random_sources.create.json
   ax annotation-queues add-records CALIBRATION_QUEUE_ID --space SPACE --record-sources WORK_DIR/random_sources.add_1.json
   # ...then the same for the gold queue with record_sources.create.json and each record_sources.add_N.json
   ```

   For session evaluators, the source files hold `SESSION` records, so each record is the whole session the evaluator graded and labels land on the session. `ax` help lists only `SPAN` and `EXAMPLE`, but `ax` 0.38+ accepts `SESSION`. A span record opens on one turn, and annotators then judge that turn instead of the session.

   Instructions are limited to 5000 characters. Create queues one at a time; if a call fails part way, check what exists (`ax annotation-configs get`, `ax annotation-queues get`) before retrying, so nothing is created twice.
4. **Hide evaluator output.** ax can't set a queue's Annotator Columns, so ask the user to set them in the Arize UI and check one record as an annotator: [Keeping labelers blind](references/rubric-and-instructions.md#keeping-labelers-blind).
5. **Verify.** Run `ax annotation-queues list-records QUEUE --space SPACE --limit 100 -o json` for each queue. Confirm the record counts match the plan, every planned session ID (span ID for span evaluators) is present, and no session appears twice. If any are missing, report which ones. Re-run `add-records` with the plan's source file that holds them, or explain why they were dropped.

## Phase 6: Check partway, then top up

After annotators have labeled about a third of the records, run the **arize-align-evaluator** report on each queue. Check the bucket counts against the plan:
- **Excluded rate well above expected:** the admission population is wider than the evaluator's scope. Raise `--expected-exclusion`, or tighten `--root-filter`, before topping up.
- **Annotators disagree** in the calibration queue: the label definitions need to change. See [When a definition changes](#when-a-definition-changes).

### When a definition changes

A definition changes when annotators disagree on it, or when **arize-align-evaluator** settles a criterion question and hands over new wording. **Build a new queue pair; never edit the instructions of a queue that has labels.**

- **The old queues stay as they are.** Their labels are the record under the old instructions version, and their instructions aren't changed; a queue whose instructions no longer match its labels misreports what annotators saw.
- **Tell the user a re-grade would be a good next step,** and leave it to them: EvalGen suggests reassessing outputs after updating criteria (Shankar et al. §8.1). Never re-grade yourself. If they want one, build a re-grade queue of the old sessions under the new instructions, from the plan's `random_sources.*` and `record_sources.*` files, rather than editing the old queue. Re-graded labels serve dev and few-shot examples; the new queue pair stays the measurement.
- **The new pair** is a normal run of Phases 1–5. Write the instructions with the new version line, pass them as `--instructions-file` so the definition check runs against the new template, set `--start-time` to the evaluator's switch time when the template changed too, and pass `--exclude-queue` with the old queues so the new pair holds none of their sessions.
- **Only a queue with no labels yet** may have its wording fixed in place, with `ax annotation-queues update QUEUE --space SPACE --instructions TEXT`.

Top up only on counts: a label short of gold records, or exclusions above plan. Never top up because agreement so far looks low or high; that biases the result.

- **A label is short of gold records:** run the script again with `--labels THAT_LABEL --per-label N --random 0 --exclude-queue GOLD_QUEUE CALIBRATION_QUEUE`, and add each new `record_sources.create.json` / `record_sources.add_N.json` file with `ax annotation-queues add-records QUEUE --space SPACE --record-sources FILE`. That still requires the user's approval.
- **The random stream is too small** for the interval needed: re-plan with `--random N` and the same exclusions, and add `random_sources.*` to the calibration queue.

When labeling is complete, hand off to **arize-align-evaluator**:
- Report on the **calibration queue** for agreement, recall per label, human–human agreement and the status.
- Report on the **gold queue** for disagreements to fix and for dev and few-shot examples.
- Name the column to compare against (the `*_backfill` column when the records came from a backfill), and pass `plan.json` (`report --plan`).
- For a topped-up round, merge the strata and records of every plan run into one `plan.json` first. Intake runs (Phase 7) record theirs in `plan.json` themselves.

## Phase 7 (optional): Continuous intake

Use this when the user wants the queues to keep sampling new production units, for example to watch an evaluator for drift. Don't use Arize's "run continuously" queue option for this. It doesn't record a selection rate per record, it can't be set from the CLI, and a random sample alone starves the rare labels that the targeted stream covers. Instead, rerun the plan on each new period:

```bash
python3 SKILL_ROOT/scripts/plan_queue.py --space SPACE \
  --intake WORK_DIR/plan.json --queue GOLD_QUEUE --per-label N \
  --random-queue CALIBRATION_QUEUE --random M [--settle-hours H]
```

1. **Dry run first.** Without `--execute`, it writes `WORK_DIR/intake-N/plan.md` and changes nothing. It samples only units that started since the plan's last run and are in neither queue, with the plan's saved settings and strata. It leaves out the newest `--settle-hours` (default 2) so evaluators have scored them. For session evaluators, use at least the time a session usually stays open.
2. **Get approval for the intake settings,** not for each record. Show the dry run, then agree on:
   - records per label per run (`--per-label`) and random records per run (`--random`)
   - the schedule; daily or weekly fits most evaluators
   - when to stop (a total count or a date)

   Size the runs so the annotators can keep up with the incoming records.
3. **Schedule the run with `--execute`.** Each run adds its records with `add-records`, then appends them, its strata (tagged `@intake-N`) and the new cursor to `plan.json`. Use a cron job or CI job on a machine with an `ax` profile for the space, and keep `plan.json` there; it is the intake's state. Never run two intakes on the same plan at once.
4. **Track the random stream weekly.** Report on the calibration queue. The confident-wrong rate (random records humans failed that the evaluator passed) should fall as the evaluator improves; if it doesn't, start a new round of error analysis.
5. **Watch for stops.** A run stops if the evaluator's version changed: plan new queues for the new version. If `add-records` fails partway, the run records what was added, moves on, and says so at the end of `intake-N/plan.md`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `No spans found` for a label | The evaluator has not stored that label in the window. Widen `--days`, check the column name (`<prefix>.<template_config.name>.label`), or backfill older sessions with **arize-align-history-backfill**. |
| Export with the task's full filter returns nothing | Session task filters can combine conditions on different spans of a session. Use the root-span condition alone as `--root-filter`; the stored-label filter already restricts candidates to admitted units. |
| Candidates cluster on a few days | A backfill scored those days. The script draws evenly across `--slices` time windows; raise `--slices` or narrow `--days`. |
| Planned records missing after create | Check `record_sources.json` covers their time window and project. Re-add the missing session or span IDs with `add-records`. |
| Script stops with "No part of the window has values for the eval column" | A wrong `--eval-name` or `--na-probe-eval`, a window the evaluator never scored, or a new column still indexing (20+ minutes after a run). Periods with no values are skipped, not fatal. |
| `time range ... must not exceed 7 days` or `List should have at most 2 items` | A hand-built record source. Use the script's split files: `record_sources.create.json` for `create`, then `add-records` with each `record_sources.add_N.json`. |
| `Annotator email not found or does not have access` | The address isn't a user in this space. Look it up with `ax users list --email NAME`. |
| Intake says "Nothing to take in" | The plan already covers up to the settle cutoff. Run later, or lower `--settle-hours`. |
| Intake stops on "plan a new queue" | The evaluator has a new version. Plan new queues for it; don't mix versions in one queue. |
| Annotators can see evaluator labels or scores | Edit the queue's Annotator Columns in the Arize UI to leave out the eval columns; ax can't set them. Labels made while evals were visible aren't blind. |
| `--random` draws fewer than asked | The window has fewer scored units than requested. Widen `--days`, or accept a wider interval and say so. |
| Labels land on spans instead of the session | The queue holds span records. Rebuild it from a current plan, which writes `SESSION` records for session evaluators. Labels made on a span record judged one turn, not the session. |
| `record_type` `SESSION` is rejected | The `ax` install or its arize SDK predates session records (SDK 8.56 works). Upgrade, and check `which -a ax`. |

---

## Related Skills

- **arize-align-evaluator**: measure the finished queue against the evaluator, and run the alignment loop
- **arize-align-history-backfill**: score sessions the evaluator never labeled, either pre-task history (copy mode) or everything, for an evaluator with no task (new-evaluator mode)
- **arize-annotation**: annotation config and queue CRUD, assigning records
- **arize-evaluator**: find the evaluator's task, filters and granularity
- **arize-trace**: export a session to check what annotators will see
