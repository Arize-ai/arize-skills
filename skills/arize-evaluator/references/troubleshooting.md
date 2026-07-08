# Diagnosing Cancelled Evaluator Runs

Step-by-step checklist for when a task run reports status `cancelled`. Referenced from `SKILL.md`.


When a task run is cancelled (status `cancelled`), follow this checklist in order:

**1. Check integration credentials**
```bash
ax ai-integrations list --space SPACE -o json
```
Verify the integration ID used by the evaluator exists and has valid credentials. If the integration was deleted or the API key expired, the run cancels within ~1 second.

**2. Verify the model name**
```bash
ax evaluators get EVALUATOR_NAME --space SPACE -o json
```
Check the `model_name` field. A typo or deprecated model causes the LLM call to fail and the run to cancel after ~3 minutes.

**3. Export a sample span/run and compare paths to column_mappings**

For project tasks:
```bash
ax spans export PROJECT --space SPACE -l 1 --days 7 --stdout | python3 -m json.tool
```

For experiment tasks:
```bash
ax experiments export EXPERIMENT_NAME --dataset DATASET_NAME --space SPACE --stdout | python3 -c "import sys,json; runs=json.load(sys.stdin); print(json.dumps(runs[0], indent=2)) if runs else print('No runs')"
```

Compare the exported JSON paths against the task's `column_mappings`. For each template variable, confirm the mapped path actually exists. Common mismatches:
- Mapping `output` to `attributes.output.value` on an experiment run (should be just `output`)
- Mapping `input` to `attributes.input.value` on a CHAIN span when the actual path is `attributes.llm.input_messages`
- Mapping `context` to a path that doesn't exist on the span kind being filtered

**4. Check that `data_start_time` is not epoch**

If `trigger-run` used a start time of `0`, `1970-01-01`, or an empty string, the time window is invalid. Always derive from real span timestamps:
```bash
ax spans export PROJECT --space SPACE -l 5 --days 30 --stdout | python3 -c "
import sys, json
spans = json.load(sys.stdin)
for s in spans:
    print(s.get('start_time', 'N/A'), s.get('end_time', 'N/A'))
"
```

**5. Verify span kind matches evaluator scope**

If the evaluator was created with `--data-granularity trace` but the task's `query_filter` is `span_kind = 'LLM'`, the run may find no qualifying data and cancel. Ensure the granularity and filter are consistent.

**6. Check that all template variables resolve**

Every `{variable}` in the evaluator template must have a corresponding `column_mappings` entry that resolves to a non-null value. Test resolution against a real span:
```bash
ax spans export PROJECT --space SPACE -l 3 --days 7 --stdout | python3 -c "
import sys, json
spans = json.load(sys.stdin)
# Replace these paths with your actual column_mappings values
mappings = {'input': 'attributes.input.value', 'output': 'attributes.output.value'}
for i, span in enumerate(spans):
    print(f'--- Span {i} ---')
    for var, path in mappings.items():
        parts = path.split('.')
        val = span
        for p in parts:
            val = val.get(p) if isinstance(val, dict) else None
        status = 'FOUND' if val else 'MISSING'
        print(f'  {var} ({path}): {status} — {str(val)[:80] if val else \"null\"}')
"
```
If any variable shows MISSING on all spans, fix the column mapping or adjust `query_filter` to target a different span kind.
