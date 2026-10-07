# Sampling records for an alignment queue

## Why stratify by the evaluator's stored label

A random sample of production mirrors production's label mix. If 90% of sessions are `target_retrieved`, a 10-record random queue holds about 9 of them and maybe no `wrong_target` at all. Agreement on that queue cannot show whether the evaluator recognizes the rare, important failures. Sampling each stored label separately guarantees every label gets records.

The trade-off is that the sample is chosen by the evaluator under test. Two consequences:
- **Report agreement per label.** The overall rate on a stratified queue is not a production-wide accuracy, so don't quote it as one.
- **Records the evaluator got wrong are still caught.** A record sampled as `wrong_target` that humans call `target_retrieved` is a false positive, which is exactly what alignment needs to see. But a failure mode the evaluator never stores under any label, because it marks those sessions `not_applicable`, can hide. That is why each plan includes 2 records with a stored `not_applicable` label. If humans label them as applicable, plan a larger applicability check.

## Scope probes

Two random `not_applicable` records rarely land on the cases that matter. When another evaluator grades the same sessions (usually the version this one replaces), `--na-probe-eval` picks records this evaluator called not applicable that the other graded decisively, spread across the other evaluator's labels. Use it when a label comes up empty because a new scope rule moved those sessions to not applicable. On `copilot-prod`, a v2 trace-diagnosis judge gave no `diagnosis_wrong` or `no_diagnosis` in about 500 sessions, while v1 had graded 136 sessions `diagnosis_wrong` in 30 days. Widening the backfill would have cost about 176 judge calls a day for few records; ten probes test the scope rule directly. The other evaluator only chooses records. Humans label blind, and its labels are never compared with the gold set.

## Sizing

```
per_label = ceil( max(min_per_class, target_gold / k) / (1 - expected_exclusion) )
```

- `k` is the number of decisive labels: the evaluator's choices minus not-applicable.
- `target_gold` (default 10) and `min_per_class` (default 3) match the **arize-align-evaluator** gates.
- `expected_exclusion` (default 0.30) is the share humans will mark not applicable or cannot judge. Use the real rate from an earlier queue when one exists. A previous queue that lost 70% of its records to exclusions should not be planned at 30%.

Example: 3 decisive labels, at the defaults, gives `ceil(max(3, 3.33) / 0.7)` = 5 per label. With 2 not-applicable probes, that is 17 records in total, expected to yield about 10 gold.

## Candidate pool

- **Time spread.** One export returns only the newest spans, so the script splits the window into `--slices` (default 4) and draws `pool / slices` from each slice.
- **One span per unit.** Candidates are deduplicated by session ID (session evaluators), trace ID (trace evaluators) or span ID. Use `--root-filter` so each candidate is the unit's entry span. For a session, that is usually the root span of a turn.
- **Exclusions.** `--exclude-queue` removes any session, trace or span already in those queues, so units are never labeled twice across rounds.

## Picking within a label

1. **Provider disagreements first, capped.** If `--compare-eval` names another copy of the evaluator, units where the copies disagree are taken first, up to `--max-disagreement-share` (default 40%) of the label's quota. These units sit near the decision boundary, so a human label settles something. The cap stops a burst of disagreements from one backfill from crowding out typical cases.
2. **Spread across entry points.** The remaining picks go round-robin across span names (for example `ROUTER-CHAT`, `ROUTER-SEARCH`), so no single product surface dominates.
3. **Seeded.** Pass `--seed` to reproduce or vary a plan.
