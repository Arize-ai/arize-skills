---
name: arize-align-evaluator
description: Aligns an Arize LLM-as-judge evaluator with human ground truth from annotation queues, span annotations, or dataset label columns. Checks label fit and quality, measures annotator agreement, reports record-level disagreements, and stops for approval before any evaluator change. Use when the user mentions align evaluator, calibrate LLM judge, evaluator vs human labels, judge agreement, gold labels, labeling queue ground truth, or inter-annotator agreement.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.38.0), Python 3.9+, and a configured Arize profile.
---

# Arize Align Evaluator Skill

> **`SPACE`** — `--space` flags accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

**Alignment** means measuring how closely an LLM-as-judge evaluator reproduces human judgments, then fixing it where it doesn't. Before the agreement numbers mean anything, you have to answer three questions:

1. **Do the human labels apply to this evaluator?** Do they cover the same unit, the same rubric and the same input the evaluator sees?
2. **Are the labels good enough to align against?** That means enough applicable, decisive and varied records, ideally checked by a second annotator.
3. **Where exactly do the human and the evaluator disagree, and why?**

This skill answers all three in a written **pre-alignment report**, then stops. Nothing about the evaluator changes until the user has read the report and approved a specific change.

For creating evaluators, tasks and runs in general, use **arize-evaluator**. This skill reuses those commands and adds the measurement, the gates and the approval step.

---

## Hard rules

- **Do not change anything before approval.** Phases 1–4 are read-only. Do not create or update evaluators, evaluator versions or tasks, do not trigger runs, and do not touch queues or annotations until the user approves a specific change after reading the report (Phase 5).
- **Never create a new version of a production evaluator automatically.** Iterate on a separate candidate evaluator (Phase 6). Promoting a candidate to the production evaluator requires its own explicit approval.
- **Preserve the human labels as given.** Never relabel, merge or coerce a human label to fit the evaluator's choices. `cannot_judge` and `unclear` are unscorable, not a class to map onto one of the evaluator's labels. If annotators disagree, keep both original votes.
- **Never fabricate results.** If a command fails or a field is missing, report that. Do not estimate agreement, invent labels, or grade records yourself in place of the evaluator.
- **Stored outputs are not a baseline.** Stored eval results carry no version ID. Agreement computed from them is descriptive only until the current version is re-run on the gold set.

---

## Prerequisites

Proceed directly with the task — run the `ax` command you need. Do NOT check versions, env vars, or profiles upfront.

If an `ax` command fails, troubleshoot based on the error:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `Error due to additional fields (not defined in ...)`, an enum validation error, or non-JSON output from a read command → the CLI is too old to parse the API's current response. Run `ax --version`, upgrade (see [references/ax-setup.md](references/ax-setup.md)), and check `which -a ax` in case an older copy shadows the upgraded one on `PATH`. **Stop here; do not work around it.** Without parsed responses, the gates in Phase 3 cannot run.
- `401 Unauthorized` / missing API key → run `ax profiles show` to inspect the current profile. If the profile is missing or the API key is wrong, follow [references/ax-profiles.md](references/ax-profiles.md) to create/update it. If the user doesn't have their key, direct them to https://app.arize.com/admin > API Keys
- Space unknown → see [Space](references/ax-profiles.md#space)
- **Security:** Never read `.env` files or search the filesystem for credentials. Exception: the non-secret `ARIZE_SPACE_ID` line (see [Space](references/ax-profiles.md#space)). Use `ax profiles` for Arize credentials and `ax ai-integrations` for LLM provider keys. Never ask the user to paste secrets into chat.

### The bundled report script

[scripts/align_report.py](scripts/align_report.py) uses only the Python standard library. It has two read-only subcommands:

- `fetch` saves the queue, all of its records (every page) and the evaluator as JSON.
- `report` joins those files and prints the pre-alignment report as Markdown. With `--json-out`, it also writes per-record results.

Find the installed skill's root and run the script by absolute path, so it works from any workspace. Use a scratch directory for its output, not the user's repo.

---

## Choose the ground-truth source

| Where the human labels live | Use |
|---|---|
| An Arize **annotation queue** (also called a labeling queue) | Phases 1–6 below (the default and best-supported path) |
| `annotation.<name>.label` on project spans, applied by the SDK or UI | [references/other-ground-truth.md](references/other-ground-truth.md#span-annotations) |
| A dataset column holding human labels, plus an experiment | [references/other-ground-truth.md](references/other-ground-truth.md#dataset-label-column) |
| No labels yet, or an existing queue came out NOT USABLE | Use **arize-align-queue-builder** to design and create a queue sized and balanced for this evaluator, then come back |

A queue is the preferred source because it is the only one that records who cast each vote, so it can measure annotator agreement when a record has two or more votes. A single annotator is allowed. Span annotations and dataset columns keep only one label per record; the report must say so.

If the user is unsure, list the queues: `ax annotation-queues list --space SPACE --name "KEYWORD"`.

---

## Phase 1: Identify the evaluator and the queue

1. **Find the evaluator.** Run `ax evaluators list --space SPACE --name "KEYWORD"`. There are often several variants, such as a production copy, a provider-comparison copy, or a benchmark copy. Ask which one is being aligned if it is not obvious.
2. **Read its current version:** `ax evaluators get EVALUATOR --space SPACE -o json`. Record these fields:
   - `version.template_config.name`. **The stored output column is named after this, not after the evaluator.** It is `<prefix>.<template_config.name>.label`, where the prefix is `eval` for `SPAN`, `trace_eval` for `TRACE` and `session_eval` for `SESSION`. Two copies of one evaluator usually write to different columns, such as `session_eval.my_eval` and `session_eval.my_eval_anthropic`.
   - `version.template_config.data_granularity`, `classification_choices` and `template` (note its `{variables}`).
   - `version.id`, `version.created_at` and `version.commit_message`.
3. **Read the queue:** `ax annotation-queues get QUEUE --space SPACE -o json`. Record its `annotation_configs` (the rubric labels), its `annotators` and its `instructions`. If the queue has more than one config, ask which one is the ground truth for this evaluator.

## Phase 2: Fetch the records

```bash
python3 SKILL_ROOT/scripts/align_report.py fetch \
  --space SPACE --queue QUEUE --evaluator EVALUATOR --out-dir WORK_DIR
```

Use `--ax PATH` if the right `ax` is not first on `PATH`. To fetch by hand instead, page through `ax annotation-queues list-records QUEUE --space SPACE --limit 100 -o json` using `--cursor` until `pagination.has_more` is false.

Before trusting the join, read [references/queue-records.md](references/queue-records.md). Queue records have three traps that the script handles, and that you must handle yourself if you join by hand:
- Votes can be at span, trace or session level (`annotations`, `trace_annotations`, `session_annotations`). They are keyed by **annotation config name**, and a record can carry labels from other queues' configs.
- Each vote appears twice, once with an `annotator` and once without.
- `evaluations` holds whatever stored results exist for the record's trace and session, from every evaluator.

## Phase 3: Build the pre-alignment report

```bash
python3 SKILL_ROOT/scripts/align_report.py report \
  --dir WORK_DIR --json-out WORK_DIR/report.json > WORK_DIR/report.md
```

Useful flags:
- `--config NAME` picks the annotation config when the queue has several.
- `--eval-column session_eval.X` overrides the derived output column.
- `--not-applicable` and `--unscorable` set the human labels to exclude. The defaults are `not_applicable`, and `cannot_judge` plus `unclear`.
- `--adjudications FILE` takes a JSON file mapping `record_id` to a resolved label, once disputes are adjudicated.

The report sorts every record into one of these buckets: **gold** (applicable, decisive and resolved), **not_applicable**, **unscorable**, **off_rubric** (a human label the evaluator cannot output), **disputed** or **unlabeled**. Only gold records count toward human-vs-evaluator agreement. Every other bucket is reported with its share of the records, never silently dropped.

It then applies the quality gates and gives one verdict:

| Verdict | Meaning | What you may claim |
|---|---|---|
| **USABLE** | Every gate passes | Agreement numbers are evidence, once re-run on the current version (Phase 6) |
| **EXPLORATORY** | At least 5 gold records in 2 or more classes, but some gate fails | Patterns worth investigating. No accuracy figure is evidence of alignment. |
| **NOT USABLE** | Too few gold records, or only one class | Do not propose evaluator changes from this queue. Fix the queue first. |

The gates cover gold count, classes, exclusions, join coverage, stored-output coverage, annotator agreement and open disputes. Their thresholds, why each exists, how κ is computed and how to adjudicate are in [references/gates-and-agreement.md](references/gates-and-agreement.md).

## Phase 4: Check fit, then present the report and STOP

The script checks the structure: label sets, granularity, other configs and coverage. You must also check the meaning, by reading actual records:

1. **Is the unit the same?** Queue records are usually `SPAN` records, while many evaluators score the whole `SESSION`. Confirm that each record's `attributes.session.id` identifies the session the labeler judged, and that the evaluator's input variable (for example `{conversation}`) covers that whole session. A label on one span in a multi-turn session can disagree with a correct session-level verdict.
2. **Does the rubric mean the same thing?** Read the evaluator template next to the queue instructions and label definitions. Watch for one label meaning different things on each side. A common case is `no_output_produced` vs `wrong`, where one side treats "the agent didn't produce an artifact" as a failure and the other treats it as a separate class.
3. **Read the not-applicable records.** If humans marked records `not_applicable` and the evaluator gave a substantive label, the disagreement is about applicability, not grading quality. Check the evaluator's `not_applicable` instruction and the task's admission filter before touching the grading criteria.
4. **Read every discrepancy.** For each row in the report's discrepancy table, open the session (use **arize-trace** to export it, and **arize-link** for a UI link). Decide whether the human or the evaluator is right, or whether the record is ambiguous. Quote the specific evidence.

Then **present the report to the user and stop.** Use the structure in [references/report-template.md](references/report-template.md). It must include:
- the verdict and every failed gate, in plain language
- what the human labels say (distribution and exclusions), separate from what the evaluator says
- the fit findings from steps 1–3
- each discrepancy with its record ID, session ID, both labels and your reading of the evidence
- annotator disagreements and the proposed adjudication; if there was only one annotator, say so
- **either** a proposed template change, quoting the exact current wording, the exact replacement and the records that justify it, **or** a recommendation not to change the evaluator yet, with what to fix in the queue first
- what remains uncertain

End by asking the user to approve, edit or reject the proposal. **Do not continue to Phase 6 in the same turn.**

**Do not propose a template change when:**
- the verdict is NOT USABLE
- the discrepancy is explained by applicability, the admission filter, a unit mismatch or a stale version
- the only evidence is a class the queue has no examples of
- the change would turn `cannot_judge` into an evaluator class

In those cases, recommend fixing the queue, the filter or the mapping instead.

## Phase 5: Get approval

Approval must name the change: "approve the proposed edit to the not_applicable rule," not just "looks good, continue." If the user edits the proposal, restate the final change before acting on it. If the user approves fixing the queue rather than the evaluator, stop this skill there and hand off to **arize-annotation**.

## Phase 6: After approval — baseline, iterate, re-measure

1. **Create a candidate copy, not a new production version.** Copy the evaluator and give it a distinct `template_config.name`, such as `<name>_candidate`, so its results go to their own column and never overwrite production output. See **arize-evaluator** for the create command. Check the subcommand names with `ax evaluators --help`, because CLI releases have renamed them. Use the **current** production template first, unchanged.
2. **Re-run the baseline on the gold sessions only.** Create a non-continuous task for the candidate on the same project. Set `--query-filter` so it selects only the gold sessions, and set `--data-start-time` and `--data-end-time` to cover their timestamps. First trigger a run with a small `--max-spans` and confirm that only the intended sessions were scored. Then run the full set with `--wait`.
3. **Measure the baseline.** Re-run `report` with `--eval-column` set to the candidate's column. This number is the real baseline.
4. **Apply the approved change** as a new version of the **candidate**, then re-run and re-measure. To draft revisions from disagreements, use [references/alignment-meta-prompt.md](references/alignment-meta-prompt.md). The rules there prevent overfitting.
5. **Report before and after on the same gold set.** Give per-class precision and recall, list the records that flipped in each direction, and say whether the gain is larger than the noise for this sample size.
6. **Promoting to production is a separate decision.** Present the candidate's results and the exact diff. Create a new version of the production evaluator only after the user explicitly approves promotion.

**When to stop iterating:** stop when the target threshold is met on a gold set that passes the gates, when agreement plateaus between iterations, when the remaining disagreements are ones reasonable annotators also dispute, or after 3–4 iterations. Further gains are rarely available from template edits alone. For targets by evaluator type, see [references/gates-and-agreement.md](references/gates-and-agreement.md#target-thresholds).

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `limit: Input should be less than or equal to 100` | Use `--limit 100` and page with `--cursor`. |
| Report says the stored output column is missing on every record | The column is named after `template_config.name`, not the evaluator name. Check `ax evaluators get` and pass `--eval-column` if it differs. Or the evaluator has not run on these sessions; see Phase 6. |
| Labels from other queues appear on records | Expected: one span can be in several queues. Pass `--config` and the script ignores the other configs. |
| Second annotator assigned but no overlap | Their `completion_status` is `PENDING`. A single annotator is allowed; say "single annotator" in the report, or ask them to finish if you want agreement measured. |
| A human label isn't in the evaluator's choices | It is bucketed `off_rubric` or `unscorable`. Discuss the rubric mismatch in the report; never coerce the label. |
| Agreement is 0% | Label spellings differ, such as `correct` vs `Correct`, or the wrong column was joined. Check the fit section. |
| Agreement looks high but the queue has one class | Accuracy is meaningless with one class. The gates mark this NOT USABLE or EXPLORATORY. |

---

## Related Skills

- **arize-align-queue-builder**: build a balanced, correctly sized queue for this evaluator when none exists or the current one fails the gates
- **arize-annotation**: create annotation configs and queues, assign annotators, and add records
- **arize-evaluator**: evaluator, task and run mechanics (create, version, trigger, column mapping)
- **arize-trace**: export a session to read the evidence behind a discrepancy
- **arize-link**: deep links to sessions, queues and evaluators for the report
- **arize-prompt-optimization**: improve the application's prompt rather than the judge's
