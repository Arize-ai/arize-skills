# Sampling records for an alignment queue

## Two streams

A plan has two streams, and they answer different questions:

| Stream | How records are chosen | Use it for | Queue |
|---|---|---|---|
| **Random** (measurement) | Uniformly from every unit the evaluator scored in the window, with a known probability, never filtered on its labels | Agreement, recall per label, the human–human ceiling, the VALIDATED verdict, weekly drift | Its own calibration queue |
| **Targeted** (failure finding) | A quota per stored label, provider disagreements first, judge-independent signals, not-applicable checks and scope probes | Finding failures, choosing what to fix, dev and few-shot examples | The gold queue |

Agreement estimates assume the labeled records were drawn at random. Records chosen by the evaluator's own labels, or by where two copies disagree, are not, and they over-represent the cases the selection looked for. Many judge errors are also stable: the judge is wrong the same way on every run, so disagreement or flip signals never surface them, and only a random sample finds them. So the targeted stream finds failures, and the random stream measures.

Every record in `plan.json` has a `routing_reason`, and the evaluator report should only treat `random` records as a measurement:

| `routing_reason` | Stream | Meaning |
|---|---|---|
| `random` | random | Uniform draw from the scored population |
| `label_stratum` | targeted | Quota for its stored label |
| `provider_disagreement` | targeted | Another copy of the evaluator gave a different label |
| `na_check` | targeted | Stored `not_applicable`, to check applicability |
| `scope_probe` | targeted | Stored `not_applicable` here, graded decisively by another evaluator |
| `signal:NAME` | targeted | Matched a judge-independent `--signal` filter |

### Random stream

- **Frame.** Every unit (session, trace or span) in the window with a stored value in the evaluator's column, under `--root-filter`, minus units already in `--exclude-queue` queues. Filtering on the column having a value only restricts the frame to units the evaluator scored. It doesn't filter on what the evaluator said.
- **Draw.** `--random N` units uniformly from the frame. `plan.json` records the `random` stratum with `population` (all scored units), `frame` and `selection_rate` = N / frame. Random units are taken first and are never picked again by the targeted stream.
- **Size.** Defaults to 30 in `discovery` mode and 100 in `validation` mode. Size it from the interval you need, not from a share of traffic. Two reference points: 200 random records at a 3% failure rate give a failure-rate interval of about ±2.4 points, and halving an interval takes 4 times the records. A rare failure produces few random examples (30 failures at a 3% rate take about 1,000 random records), which is why the targeted stream exists. It finds the failures that the random stream then measures at their true rate.
- **Queue.** The random records go to `random_sources.*.json`, for a separate calibration queue. In `validation` mode, assign it to 3 or more annotators (`ALL`), so the evaluator report can compute human–human agreement and test the evaluator against the annotators. If human agreement is high, the gold queue can stay single-annotated.

## Why stratify the targeted stream by stored label

A random sample of production mirrors production's label mix. If 90% of sessions are `target_retrieved`, a 10-record random queue holds about 9 of them and maybe no `wrong_target` at all. Sampling each stored label separately guarantees every label gets records to examine.

The trade-off is that the evaluator under test chose these records:
- **Agreement within a stored label is that label's precision, not its recall.** The targeted strata keep each label's production count and selection rate, so `report --plan plan.json` can weight them back to production. Treat that weighted figure as a secondary estimate and the random stream as the measurement.
- **Records the evaluator got wrong are still caught.** A record sampled as `wrong_target` that humans call `target_retrieved` is a false positive, which is what alignment needs to see. But a failure the evaluator hides under `not_applicable` can be missed. That is why each plan includes 2 records with a stored `not_applicable` label (`--na-count`). If humans label them as applicable, plan a larger applicability check.

## Signals

`--signal NAME=FILTER` adds `--signal-count` records (default 5) matching a span filter that doesn't depend on the evaluator. Examples: user thumbs-down feedback, an escalation flag, or a high-severity topic. Repeat it for several signals. Prefer these over judge-dependent signals: they find failures the judge is confidently wrong about. Signal records are targeted and never weighted.

Never route on the judge's own stated confidence. Verbalized confidence barely separates right from wrong verdicts.

Good targets are cases judges handle worst:
- partially correct or under-specified answers
- answers heavy in numbers, negations or long source material

When one of these can be expressed as a span filter, add it as a signal.

## Scope probes

Two random `not_applicable` records rarely land on the cases that matter. When another evaluator grades the same sessions (usually the version this one replaces), `--na-probe-eval` picks records this evaluator called not applicable that the other graded decisively. The picks are spread across the other evaluator's labels.

Use it when a label comes up empty because a new scope rule moved those sessions to not applicable. On `copilot-prod`, a v2 trace-diagnosis judge gave no `diagnosis_wrong` or `no_diagnosis` in about 500 sessions, while v1 had graded 136 sessions `diagnosis_wrong` in 30 days. Widening the backfill would have cost about 176 judge calls a day for few records; ten probes test the scope rule directly.

The other evaluator only chooses records. Humans label blind, and its labels are never compared with the gold set.

## Sizing

| Mode | target_gold | min_per_class | Random | Use when |
|---|---:|---:|---:|---|
| `discovery` (default; `directional` is accepted as an alias) | 10 | 3 | 30 | Error analysis and a first alignment pass |
| `validation` | 142 | 71 | 100 | Supporting an agreement claim (the VALIDATED verdict) |

- **Discovery.** Each label gets about 3.5–5.6 gold records, which is a smoke test: 5/5 agreement still has a 95% interval of about 57–100%. The 30 random records are for an expert to read and open-code: note the first failure in each, group the notes into failure modes, and check the rubric against them before scaling up.
- **Validation.** The evaluator report splits gold records 15% train, 42.5% dev and 42.5% test within each human label, and tests once. 30 per label in each of dev and test needs 30 / 0.425 ≈ 71 gold records per label. Below about 60 records, intervals are too wide to separate a good judge from a mediocre one.

```
per_label = ceil( max(min_per_class, target_gold / k) / (1 - expected_exclusion) )
```

- `k` is the number of decisive labels: the evaluator's choices minus not-applicable.
- `expected_exclusion` (default 0.30, an Arize heuristic) is the share humans will mark not applicable or cannot judge. Use the real rate from an earlier queue when one exists. A previous queue that lost 70% of its records to exclusions should not be planned at 30%.

Example: 3 decisive labels gives `ceil(max(3, 3.33) / 0.7)` = 5 per label in discovery mode. With 2 not-applicable checks and 30 random records, that is 47 records. In validation mode it is `ceil(max(71, 47.3) / 0.7)` = 102 per label, plus the 100 random records.

## Strata and weights

Each picked record carries a `stratum` in `plan.json`, and `strata` lists every stratum with its `stream` and:
- `population`: distinct production units in the window with that stored label (and root filter), counted in full by splitting any period that fills an export page. `population_lower_bound` is true if a 30-minute period still filled a page.
- `picked` and `selection_rate` (picked / population, or picked / frame for the random stream).

With `--compare-eval`, each label splits into `LABEL|disagree` and `LABEL|agree`. The disagreement population is counted in full with its own export, and agree is the rest. An estimated population would not be a known selection probability, so nothing is estimated. Scope probes and signals get a stratum with no population; they are reported separately and never weighted.

`--skip-population` skips the label counts, for example on a very large window. The evaluator report then can't weight the targeted stream. The random stream still has its rate.

## Continuous intake

Arize's own "run continuously" option on a queue samples new spans at random, but it doesn't record the rate per record, and the CLI and public API can't set it. An intake run instead repeats this plan on new data:
- **Window.** It starts at the plan's `intake_cursor` (the end of the last run, or of the first plan) and ends `--settle-hours` (default 2) before now. The gap gives evaluator tasks time to score the newest units; a unit counted before it is scored would be missed for good. For a session evaluator, set it at least as long as a session usually stays open.
- **Same design.** It reuses the plan's saved `settings` (root filter, compare copy, sizing, labels, signals, instructions version) and quota per label (`--per-label` overrides it for each run). Scope probes are left out. Units already in either queue are excluded.
- **Random stream.** Add `--random-queue CAL --random N` to draw N random records per run into the calibration queue. This is the stream to track weekly. The confident-wrong rate (random records humans failed that the evaluator passed) is the number to watch; if it stops falling, start a new round of error analysis.
- **Its own strata.** Each run's strata are tagged `@intake-N` and counted over that run's window only. Pooling them with earlier strata would mix different selection rates, so each period carries its own weight. A low-volume label simply has fewer picks that run.
- **Recording.** `--execute` adds the records, then appends the records, the strata, an `intakes` entry and the new cursor to `plan.json`, writing it atomically. If a batch fails, the records already added are recorded, the strata's picked counts match them, and the cursor still moves, so no period is counted twice. Without `--execute`, nothing changes.
- **Version guard.** If the evaluator's version no longer matches the plan, the run stops. A new version is a different evaluator and needs its own queue.

## Candidate pool

- **Time spread.** One export returns only the newest spans, so the script splits the window into `--slices` (default 4) and draws `pool / slices` from each slice.
- **One span per unit.** Candidates are deduplicated by session ID (session evaluators), trace ID (trace evaluators) or span ID. Use `--root-filter` so each candidate is the unit's entry span. For a session, that is usually the root span of a turn.
- **Exclusions.** `--exclude-queue` removes any session, trace or span already in those queues, so units are never labeled twice across rounds.

## Picking within a label

1. **Provider disagreements first, capped.** If `--compare-eval` names another copy of the evaluator, units where the copies disagree are taken first, up to `--max-disagreement-share` (default 40%) of the label's quota. These units often sit where humans disagree too, so expect some to need adjudication. The cap stops a burst of disagreements from one backfill from crowding out typical cases. Because they are oversampled, they are a separate stratum with their own weight. Both copies can make the same mistake, so disagreement finds some errors, not all.
2. **Spread across entry points.** The remaining picks go round-robin across span names (for example `ROUTER-CHAT`, `ROUTER-SEARCH`), so no single product surface dominates.
3. **Seeded.** Pass `--seed` to reproduce or vary a plan.
