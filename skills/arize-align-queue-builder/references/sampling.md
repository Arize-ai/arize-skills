# Sampling records for an alignment queue

## Why stratify by the evaluator's stored label

A random sample of production mirrors production's label mix. If 90% of sessions are `target_retrieved`, a 10-record random queue holds about 9 of them and maybe no `wrong_target` at all. Agreement on that queue cannot show whether the evaluator recognizes the rare, important failures. Sampling each stored label separately guarantees every label gets records.

The trade-off is that the sample is chosen by the evaluator under test. Two consequences:
- **Agreement within a stored label is that label's precision, not its recall.** The overall rate on a stratified queue is not a production-wide accuracy either. To get recall (TPR/TNR) and a production rate, the plan records each stratum's production unit count and selection rate in `plan.json`; pass it to the evaluator report with `--plan plan.json` and it weights each stratum back to production.
- **Records the evaluator got wrong are still caught.** A record sampled as `wrong_target` that humans call `target_retrieved` is a false positive, which is exactly what alignment needs to see. But a failure mode the evaluator never stores under any label, because it marks those sessions `not_applicable`, can hide. That is why each plan includes 2 records with a stored `not_applicable` label. If humans label them as applicable, plan a larger applicability check.

## Scope probes

Two random `not_applicable` records rarely land on the cases that matter. When another evaluator grades the same sessions (usually the version this one replaces), `--na-probe-eval` picks records this evaluator called not applicable that the other graded decisively, spread across the other evaluator's labels. Use it when a label comes up empty because a new scope rule moved those sessions to not applicable. On `copilot-prod`, a v2 trace-diagnosis judge gave no `diagnosis_wrong` or `no_diagnosis` in about 500 sessions, while v1 had graded 136 sessions `diagnosis_wrong` in 30 days. Widening the backfill would have cost about 176 judge calls a day for few records; ten probes test the scope rule directly. The other evaluator only chooses records. Humans label blind, and its labels are never compared with the gold set.

## Sizing

Two modes, matching the evaluator's two passing verdicts:

| Mode | target_gold | min_per_class | Use when |
|---|---:|---:|---|
| `directional` (default) | 10 | 3 | Starting an alignment: enough to see gross misalignment and propose changes |
| `validation` | 50 | 30 | Supporting an agreement claim (the VALIDATED verdict) |

At the default size, each label ends up with about 3.5–5.6 gold records. That is a smoke test: 5/5 agreement still has a 95% interval of about 57–100%. The plan prints the expected gold per label so this is visible before anyone labels.

```
per_label = ceil( max(min_per_class, target_gold / k) / (1 - expected_exclusion) )
```

- `k` is the number of decisive labels: the evaluator's choices minus not-applicable.
- `target_gold` (default 10) and `min_per_class` (default 3) match the **arize-align-evaluator** gates.
- `expected_exclusion` (default 0.30, an Arize heuristic) is the share humans will mark not applicable or cannot judge. Use the real rate from an earlier queue when one exists. A previous queue that lost 70% of its records to exclusions should not be planned at 30%.

Example: 3 decisive labels, at the defaults, gives `ceil(max(3, 3.33) / 0.7)` = 5 per label. With 2 not-applicable probes, that is 17 records in total, expected to yield about 10 gold. In `validation` mode the same evaluator gives `ceil(max(30, 16.7) / 0.7)` = 43 per label.

## Strata and weights

Each picked record carries a `stratum` in `plan.json`, and `strata` lists every stratum with:
- `population`: distinct production units in the window with that stored label (and root filter), counted in full by splitting any period that fills an export page. `population_lower_bound` is true if a 30-minute period still filled a page.
- `picked` and `selection_rate` (picked / population).

With `--compare-eval`, each label splits into `LABEL|disagree` and `LABEL|agree`. Their populations are estimated from the candidate pool's disagreement share (`population_estimated`), because counting disagreements in full would need an export per pair of labels. Scope probes and their records get a `probe:` stratum with no population; they are reported separately and never weighted into production estimates.

`--skip-population` skips the counts, for example on a very large window. The evaluator report then can't give production-weighted estimates.

## Continuous intake

Arize's own "run continuously" option on a queue samples new spans at random, and the CLI and public API can't set it. An intake run instead repeats this plan on new data:
- **Window.** It starts at the plan's `intake_cursor` (the end of the last run, or of the first plan) and ends `--settle-hours` (default 2) before now. The gap gives evaluator tasks time to score the newest units; a unit counted before it is scored would be missed for good. For a session evaluator, set it at least as long as a session usually stays open.
- **Same design.** It reuses the plan's saved `settings` (root filter, compare copy, sizing, labels) and quota per label (`--per-label` overrides it for each run). Scope probes are left out. Units already in the queue are excluded.
- **Its own strata.** Each run's strata are tagged `@intake-N` and counted over that run's window only. Pooling them with earlier strata would mix different selection rates, so each period carries its own weight in `report --plan`. A low-volume label simply has fewer picks that run.
- **Recording.** `--execute` adds the records, then appends the records, the strata, an `intakes` entry and the new cursor to `plan.json`, writing it atomically. If a batch fails, the records already added are recorded, the strata's picked counts match them, and the cursor still moves, so no period is counted twice. Without `--execute`, nothing changes.
- **Version guard.** If the evaluator's version no longer matches the plan, the run stops. A new version is a different evaluator and needs its own queue.


## Candidate pool

- **Time spread.** One export returns only the newest spans, so the script splits the window into `--slices` (default 4) and draws `pool / slices` from each slice.
- **One span per unit.** Candidates are deduplicated by session ID (session evaluators), trace ID (trace evaluators) or span ID. Use `--root-filter` so each candidate is the unit's entry span. For a session, that is usually the root span of a turn.
- **Exclusions.** `--exclude-queue` removes any session, trace or span already in those queues, so units are never labeled twice across rounds.

## Picking within a label

1. **Provider disagreements first, capped.** If `--compare-eval` names another copy of the evaluator, units where the copies disagree are taken first, up to `--max-disagreement-share` (default 40%) of the label's quota. These units sit near the decision boundary, so a human label settles something. The cap stops a burst of disagreements from one backfill from crowding out typical cases. Because they are oversampled, they are a separate stratum with their own weight; pooling them with the rest would pull agreement down. Both copies can make the same mistake, so disagreement finds some errors, not all.
2. **Spread across entry points.** The remaining picks go round-robin across span names (for example `ROUTER-CHAT`, `ROUTER-SEARCH`), so no single product surface dominates.
3. **Seeded.** Pass `--seed` to reproduce or vary a plan.
