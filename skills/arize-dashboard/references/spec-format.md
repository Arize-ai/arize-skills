# Spec format

`dashboard.py apply --spec spec.json` reads a single JSON file with two top-level keys: `dashboard` and `widgets`. This is the full contract `validate_spec()` enforces, plus the fields it accepts but doesn't validate.

## Top level

```json
{
  "dashboard": { "name": "...", "projectId": "...", "spaceId": "..." },
  "widgets": [ ... ],
  "skipped": [ ... ]
}
```

| Field | Required | Notes |
|---|---|---|
| `dashboard.name` | Yes | Dashboard title |
| `dashboard.projectId` | Yes | The project's base64 `id`, from `discover`'s `project.id` or `ax projects list -o json` |
| `dashboard.spaceId` | Yes | The space's base64 `id`, from `ax spaces list -o json`. Used by `createDashboard`; ignored by `createDashboardFromTemplate` (a template dashboard is created directly under the project) |
| `dashboard.template` | No | An Arize dashboard template name, e.g. `generativeLlmModelV2` or `generativeLlmModel` (see [blueprints.md](blueprints.md)). When set, `apply` calls `createDashboardFromTemplate` instead of `createDashboard` |
| `widgets` | Yes (may be empty) | Array of widget objects, defined below. Created in array order |
| `skipped` | No | Not validated — a free-form array for recording panels you deliberately left out (e.g. `"Cost per call — no matching custom metric in discover output"`), so `apply`'s JSON result echoes it back for your report to the user |

## Widgets

Every widget needs `type` and `title`. `type` must be one of `text`, `statistic`, `lineChart` (see [graphql.md](graphql.md) for why the other three Arize widget types aren't accepted here — an unsupported `type` raises `SpecError`).

### `text`

```json
{ "type": "text", "title": "Header", "content": "## Evals", "row": 1, "col": 1, "width": 12, "height": 2 }
```

`content` is required (Markdown). Placement is required by the underlying API for this widget type; if you omit `row`/`col`/`width`/`height`, `dashboard.py` falls back to a full-width band (`row=1, col=1, width=12, height=2`) rather than leaving it unplaced.

### `statistic`

```json
{
  "type": "statistic",
  "title": "Hallucination",
  "aggregation": "avg",
  "dimension": { "id": "ev__hallucination", "name": "hallucination", "dataType": "STRING" },
  "dimensionCategory": "llmEval",
  "row": 3, "col": 1, "width": 3, "height": 4
}
```

`dimension` and `dimensionCategory` are required and must come verbatim from `discover` output (`dimension` is `{id, name, dataType}`; `dimensionCategory` is `discover`'s `category` field for that entry — e.g. `"llmEval"`, `"spanProperty"`, `"annotation"`). `aggregation` defaults to `"count"` if omitted; see [graphql.md](graphql.md) for the full `DataQualityMetric` enum. Placement (`row`/`col`/`width`/`height`) is optional — omit all four to let the backend auto-place the widget.

### `lineChart`

```json
{
  "type": "lineChart",
  "title": "Correctness Over Time",
  "metric": "avg",
  "dimension": { "id": "ev__correctness", "name": "correctness", "dataType": "STRING" },
  "dimensionCategory": "llmEval",
  "row": 1, "col": 1, "width": 6, "height": 4
}
```

(Time is always the chart's x-axis — a `lineChart` widget doesn't need a separate time dimension; `dimension`/`dimensionCategory`/`metric` say *what* is plotted over time, here the `correctness` eval's average score.)

Same `dimension`/`dimensionCategory` contract as `statistic`. `metric` defaults to `"count"` if omitted; see [graphql.md](graphql.md) for the `Metric` enum. Unlike `statistic`, this shape stays flat in the spec — `dashboard.py` nests `dimension`/`dimensionCategory`/`metric` into the mutation's `plots` array for you; you never write `plots` by hand. Placement is optional, same as `statistic`.

### Optional fields on `statistic`/`lineChart`

| Field | Default |
|---|---|
| `modelEnvironmentName` | `"tracing"` |
| `timeSeriesMetricType` | `"modelDataMetric"` |

## Placement: `row`/`col`/`width`/`height`

These four fields are **1-indexed on a 12-column grid** — `row=1, col=1` is the top-left cell, and `col + width` must not exceed 13 (i.e. the widget must fit within columns 1–12). `dashboard.py`'s `validate_layout()` rejects a spec where:

- `width` or `height` is not positive,
- `row` or `col` is less than 1,
- `col + width` exceeds 13, or
- two placed widgets' boxes overlap.

**Provide all four fields together, or omit all four together.** A widget with all four omitted is left unplaced and the Arize backend auto-places it on the dashboard — this is the mechanism used for widgets added to a templated dashboard (see the placement-collision note in [graphql.md](graphql.md)). A widget with only some of the four set is treated as unplaced by `_placed()` (which requires all four), so partial placement silently becomes auto-placement — don't rely on that; either place a widget fully or not at all.

**`gridPosition` — the array Arize's mutations actually take, `[rowStart, colStart, rowEnd, colEnd]` — is never written by hand in a spec.** `dashboard.py`'s `to_grid_position(row, col, width, height)` derives it from `row`/`col`/`width`/`height` at apply time. Writing `gridPosition` directly in a spec has no effect — `validate_spec`/`widget_mutation` only look at `row`/`col`/`width`/`height`.

## Worked example

A minimal `eval-health` spec with a header and one eval's panels, using dimensions exactly as `discover` would return them:

```json
{
  "dashboard": {
    "name": "Eval Health — support-agent",
    "projectId": "proj-1",
    "spaceId": "space-1"
  },
  "widgets": [
    {
      "type": "text",
      "title": "Header",
      "content": "## Eval Health — support-agent",
      "row": 1, "col": 1, "width": 12, "height": 2
    },
    {
      "type": "lineChart",
      "title": "Hallucination — score over time",
      "metric": "avg",
      "dimension": { "id": "ev__hallucination", "name": "hallucination", "dataType": "STRING" },
      "dimensionCategory": "llmEval",
      "row": 3, "col": 1, "width": 8, "height": 4
    },
    {
      "type": "statistic",
      "title": "Hallucination — average score",
      "aggregation": "avg",
      "dimension": { "id": "ev__hallucination", "name": "hallucination", "dataType": "STRING" },
      "dimensionCategory": "llmEval",
      "row": 3, "col": 9, "width": 4, "height": 4
    }
  ],
  "skipped": [
    "Cost per call — no matching custom metric in discover output for this project"
  ]
}
```

Validate the layout and grid conversion before spending a real API call:

```bash
python3 skills/arize-dashboard/scripts/dashboard.py apply --spec spec.json --dry-run
```

which prints each widget's resolved `gridPosition` (or `<auto>` for unplaced widgets) and the list of widget titles that would be created.
