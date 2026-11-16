# Labeling directly on traces

Some users want to label production traces as they browse them, without a queue. This page sets up the label config for that and says what those labels can and can't be used for.

## The config

- **Same label values as the queue config.** Use the evaluator's choices, spelled exactly the same, plus `not_applicable` (if the evaluator lacks it) and `cannot_judge`. These are the values in `config_values.json` when a plan exists. Otherwise take them from the evaluator's `classification_choices` ([Label values](rubric-and-instructions.md#label-values)). With identical values, direct labels and queue labels can be pooled later when aligning.
- **Its own config, with a dated name** such as `<evaluator> direct (YYYY-MM-DD)` (at most 40 characters). Don't reuse the queue's config. If they shared one, span exports would mix hand-picked labels made with evaluator output visible with blind queue labels, and the report couldn't tell them apart.
- **The critique config is optional,** as with queues ([Critique config](rubric-and-instructions.md#critique-config)).

Annotation configs belong to the space. Once created, the config appears in the annotate panel of every span in the project, so labelers can use it from the trace and session views.

```bash
ax annotation-configs create categorical --name "<evaluator> direct (YYYY-MM-DD)" --space SPACE \
  --value LABEL_1 --value LABEL_2 ... --value not_applicable --value cannot_judge \
  --optimization-direction NONE -o json
```

The config has no description field, and labeling without a queue has no instructions box. Write the same versioned instructions as for a queue ([Instructions template](rubric-and-instructions.md#instructions-template)), check each label's definition against the template by hand (the same check as Phase 3), and have the user share the instructions with labelers as a doc or link. A config with no definitions behind it gets labels that apply a different rule from the judge's.

## Where the label goes

- **Span and trace evaluators:** label the span or trace the evaluator graded.
- **Session evaluators:** one label per session, on one agreed place. Use a session-level annotation if the session view offers one. Otherwise use the root span of the session's **last** trace, so the label is given once the whole session has happened. Put the rule in the instructions. Two labels on one session become a disputed record.
- **Label sessions that have ended.** A label made mid-session judges fewer turns than the evaluator grades.

**Check after the first label.** Before anyone labels more, export the labeled span and confirm where the value landed:

```bash
ax spans export PROJECT --space SPACE --span-id SPAN_ID --stdout
```

Look for `annotation.<config name>.label`, or a session-level annotation on the session. If it isn't where the instructions say, fix the instructions before labeling continues.

## What these labels can and can't do

Two things differ from a queue:
- **Labelers aren't blind.** The trace and session views show evaluator results next to the trace.
- **The selection rate is unknown.** People label what they choose to open.

So direct labels are good for:
- error analysis, and finding criterion questions
- dev records, disagreements to read, and few-shot candidates in the alignment phases

They can't give:
- the reported agreement or a `measured` status
- a test batch
- weighted estimates or production rates

Those still need the calibration queue, a uniform random sample labeled blind. Tell the user this before creating the config. The alignment phases read span annotations by a hand join ([Span annotations](other-ground-truth.md#span-annotations)).
