# Annotation queue records as ground truth

This is how `ax annotation-queues list-records -o json` shapes a record, and how to join it to an evaluator safely. [scripts/align_report.py](../scripts/align_report.py) implements these rules. Read this file if you join records by hand or need to explain a join result.

## Record shape

```json
{
  "id": "QW5ub3RhdGlvblF1ZXVlUmVjb3Jk...",
  "annotation_queue_id": "QW5ub3RhdGlvblF1ZXVl...",
  "source_type": "SPANS",
  "granularity": "SPAN",
  "data": {
    "context.span_id": "c0c6b35a49a9e40f",
    "context.trace_id": "1cb988f76c9dba6a9f6124eb041ac917",
    "attributes.session.id": "58937",
    "start_time": "1789992961987",
    "attributes.input.value": "...",
    "...": "every span column, many null"
  },
  "annotations": [
    { "name": "my-config", "score": 1, "label": "target_retrieved" },
    { "name": "my-config", "score": 1, "label": "target_retrieved",
      "annotator": { "id": "VXNlcj...", "email": "reviewer@example.com" } },
    { "name": "other-queue-config", "label": "no_filter_produced",
      "annotator": { "email": "reviewer@example.com" } }
  ],
  "trace_annotations": [],
  "session_annotations": [],
  "evaluations": [
    { "name": "session_eval.my_eval", "score": 1, "label": "target_retrieved", "explanation": "..." },
    { "name": "session_eval.some_other_eval", "label": "...", "explanation": "..." }
  ],
  "assigned_users": [
    { "user": { "email": "reviewer@example.com" }, "completion_status": "COMPLETED" },
    { "user": { "email": "second@example.com" }, "completion_status": "PENDING" }
  ]
}
```

`list-records` defaults to 15 records per page and allows at most 100. Page with `--cursor` until `pagination.has_more` is `false`.

## Join rules

1. **Read all three label lists, filtered by config name.** Depending on the annotation config, votes land in `annotations` (span level), `trace_annotations`, or `session_annotations`. Session-level configs put every vote in `session_annotations` and leave `annotations` empty. Reading only `annotations` makes such a queue look unlabeled. Keep only entries whose `name` matches the queue's ground-truth annotation config (from `ax annotation-queues get`). The same span is often in several queues, so it carries their labels too. If one annotator has different labels for the config at two levels, treat the record as unresolved.
2. **Count votes only from entries that have an `annotator`.** Each queue vote appears twice: once with the annotator, and once without, which is the span's latest value for that config. Counting both doubles every vote. A record with only unattributed entries was labeled outside the queue, through the SDK or a span-level UI edit. Treat it as one vote of unknown origin and say so in the report.
3. **Coverage comes from `assigned_users[].completion_status`.** An annotator who is assigned but `PENDING` has not voted. Report each annotator's completed and pending counts, so "no disagreements" is never mistaken for "annotators agree."
4. **Join to the evaluator through its output column.** Find the entry in `evaluations` whose `name` equals `<prefix>.<template_config.name>`. The prefix is `eval` for span evaluators, `trace_eval` for trace evaluators and `session_eval` for session evaluators. The evaluator's display name does not appear here.
5. **Make sure each record is one evaluator unit.** For a session evaluator, every record needs `attributes.session.id`, and no two records may share a session; otherwise one session is double-counted. For a trace evaluator, use `context.trace_id` the same way.
6. **Stored outputs carry no version.** Compare each record's `start_time` (epoch milliseconds) with the evaluator's `version.created_at`. Records older than the current version may have been scored by an earlier version, unless a backfill re-ran them. Either way, a fresh run is the only real baseline.

## Unit mismatch: span records, session evaluators

Queues built from spans present one span per record, often the root span of one turn, while session evaluators judge the whole conversation. Before treating the label as ground truth for the session:

- Confirm the queue instructions told labelers to judge the **full session**, not the visible span.
- Confirm the evaluator's input variable (for example `{conversation}`) is mapped to the whole session, and that the session fits within the 100K-character aggregation cap. See "Data Granularity" in the **arize-evaluator** skill.
- Spot-check a few records: export the session with **arize-trace** and confirm it is what the labeler would have seen.

If any of these fail, the label and the evaluator are not judging the same thing. Report it as a fit problem, not as evaluator error.

## Blind labeling vs audit

Queue instructions often tell labelers not to look at the production eval output. That rule is for labeling. During the alignment audit you do read the stored outputs. Just never write an evaluator's output back as a human label, and never change a human label after seeing the evaluator's verdict. Corrections go through adjudication (see [gates-and-agreement.md](gates-and-agreement.md#adjudication)), and every original vote is kept.
