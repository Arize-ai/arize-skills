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
| `dashboard.template` | No | An Arize dashboard template name — one of `generativeLlmModelV2`, `generativeLlmModel`, `regression`, `rankingModel`, `multiClassModel` (see [blueprints.md](blueprints.md)). When set, `apply` calls `createDashboardFromTemplate` instead of `createDashboard`, sending `modelEnvironmentName: "tracing"`, and **`validate_spec` then rejects any widget with placement fields and any `text` widget** — see [Templated dashboards](#templated-dashboards-no-placement-no-text-widgets) below |
| `widgets` | Yes (may be empty) | Array of widget objects, defined below. Created in array order |
| `skipped` | No | Not validated — a free-form array for recording panels you deliberately left out (e.g. `"Cost per call — no matching custom metric in discover output"`), so `apply`'s JSON result echoes it back for your report to the user |

## The aggregation rule — read this before choosing `aggregation` or `metric`

**Match the function to the dimension's `dataType`:**

| `dimension.dataType` | Valid `aggregation` (statistic) / `metric` (lineChart) |
|---|---|
| FLOAT, DOUBLE, LONG, INT — e.g. an eval's `.score` dimension | `avg`, `sum`, `p50`, `p95`, `p99`, `p99_9`, `standardDeviation`, plus `count`, `cardinality`, `percentEmpty` |
| STRING — e.g. an eval's `.label` dimension, most span properties | `count`, `cardinality`, `percentEmpty`, `newValues`, `missingValues` |

`avg` and the other numeric-only functions are **not rejected** when paired with a STRING dimension: the GraphQL enum accepts the mutation, `apply` reports success, `verify` reports the title present, and the widget renders `n/a` in the UI forever. Nothing in this script can catch it for you. Read `dataType` off the `discover` entry you are copying into `dimension` and choose accordingly — see [graphql.md](graphql.md) for the full enum and the reason.

Note also that `discover`'s `llmEvals` holds one entry per eval *field* (`eval.<name>.label`, `eval.<name>.score`, `eval.<name>.explanation`, `eval.<name>.metadata`), not one per eval. Build numeric widgets on `.score`, categorical widgets on `.label`, and nothing at all on `.explanation`/`.metadata`. See [blueprints.md](blueprints.md).

## Widgets

Every widget needs `type` and `title`. `type` must be one of `text`, `statistic`, `lineChart` (see [graphql.md](graphql.md) for why the other three Arize widget types aren't accepted here — an unsupported `type` raises `SpecError`).

### `text`

```json
{ "type": "text", "title": "Header", "content": "## Evals", "row": 1, "col": 1, "width": 12, "height": 2 }
```

`content` is required (Markdown). **Placement is required by the underlying API for this widget type, so a text widget is never auto-placed.** If you omit `row`/`col`/`width`/`height` (or set only some of them), `dashboard.py` falls back to a full-width band at the top — `row=1, col=1, width=12, height=2`. That fallback is written onto the widget by `validate_spec` *before* layout validation, so the band is checked for overlaps like any other box and `--dry-run` prints its real `gridPosition` rather than `<auto>`. Two unplaced text widgets, or an unplaced text widget plus any other widget at row 1, is a `LayoutError`. Place text widgets explicitly.

### `statistic`

```json
{
  "type": "statistic",
  "title": "Hallucination — average score",
  "aggregation": "avg",
  "dimension": { "id": "ev__hallucination_score", "name": "eval.hallucination.score", "dataType": "DOUBLE" },
  "dimensionCategory": "llmEval",
  "row": 3, "col": 1, "width": 3, "height": 4
}
```

`dimension` and `dimensionCategory` are required and must come verbatim from `discover` output (`dimension` is `{id, name, dataType}`; `dimensionCategory` is `discover`'s `category` field for that entry — e.g. `"llmEval"`, `"spanProperty"`, `"annotation"`). Note `avg` here sits on a numeric `DOUBLE` dimension — the eval's `.score`, not its STRING `.label`; the aggregation rule above says why that matters. `aggregation` defaults to `"count"` if omitted; see [graphql.md](graphql.md) for the full `DataQualityMetric` enum. Placement (`row`/`col`/`width`/`height`) is optional — omit all four to let the backend auto-place the widget.

### `lineChart`

```json
{
  "type": "lineChart",
  "title": "Correctness Over Time",
  "metric": "avg",
  "dimension": { "id": "ev__correctness_score", "name": "eval.correctness.score", "dataType": "DOUBLE" },
  "dimensionCategory": "llmEval",
  "row": 1, "col": 1, "width": 6, "height": 4
}
```

(Time is always the chart's x-axis — a `lineChart` widget doesn't need a separate time dimension; `dimension`/`dimensionCategory`/`metric` say *what* is plotted over time, here the `correctness` eval's average score.)

Same `dimension`/`dimensionCategory` contract as `statistic`. `metric` defaults to `"count"` if omitted, and obeys the same numeric-vs-STRING rule as `aggregation`; see [graphql.md](graphql.md) for the `Metric` enum. Unlike `statistic`, this shape stays flat in the spec — `dashboard.py` nests `dimension`/`dimensionCategory`/`metric` into the mutation's `plots` array for you; you never write `plots` by hand. Placement is optional, same as `statistic`.

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

**Provide all four fields together, or omit all four together.** A `statistic` or `lineChart` with all four omitted is left unplaced and the Arize backend auto-places it on the dashboard — this is the mechanism used for widgets added to a templated dashboard (see the placement-collision note in [graphql.md](graphql.md)). A widget with only some of the four set is treated as unplaced by `_placed()` (which requires all four), so partial placement silently becomes auto-placement — don't rely on that; either place a widget fully or not at all. (`text` is the exception to all of this: it is never auto-placed — see its section above.)

### Templated dashboards: no placement, no text widgets

When `dashboard.template` is set, `validate_spec` raises `SpecError` if:

- any widget carries `row`, `col`, `width`, or `height` — even one of the four. This script cannot see where the template's own widgets sit (see the unverified template-widget-IDs assumption in [graphql.md](graphql.md)), so explicit placement here can silently overlap them. Omit all four and the backend places the widget in a free slot.
- any widget has `type: "text"` — a text widget requires a `gridPosition` and so cannot be auto-placed at all; its fallback band would be pinned on top of the template's top row.

Augment a templated dashboard with unplaced `statistic` and `lineChart` widgets only. If you need a header or explicit layout, build the dashboard without a template.

**`gridPosition` — the array Arize's mutations actually take, `[rowStart, colStart, rowEnd, colEnd]` — is never written by hand in a spec.** `dashboard.py`'s `to_grid_position(row, col, width, height)` derives it from `row`/`col`/`width`/`height` at apply time. Writing `gridPosition` directly in a spec has no effect — `validate_spec`/`widget_mutation` only look at `row`/`col`/`width`/`height`.

## Worked example

A minimal `eval-health` spec with a header and one eval's three panels, using dimensions exactly as `discover` would return them. Note that the one `hallucination` eval contributes two different dimensions: the numeric `.score` carries the `avg` widgets, the STRING `.label` carries the `cardinality` widget, and its `.explanation`/`.metadata` dimensions are deliberately unused.

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
      "dimension": { "id": "ev__hallucination_score", "name": "eval.hallucination.score", "dataType": "DOUBLE" },
      "dimensionCategory": "llmEval",
      "row": 3, "col": 1, "width": 8, "height": 4
    },
    {
      "type": "statistic",
      "title": "Hallucination — average score",
      "aggregation": "avg",
      "dimension": { "id": "ev__hallucination_score", "name": "eval.hallucination.score", "dataType": "DOUBLE" },
      "dimensionCategory": "llmEval",
      "row": 3, "col": 9, "width": 2, "height": 4
    },
    {
      "type": "statistic",
      "title": "Hallucination — distinct labels",
      "aggregation": "cardinality",
      "dimension": { "id": "ev__hallucination_label", "name": "eval.hallucination.label", "dataType": "STRING" },
      "dimensionCategory": "llmEval",
      "row": 3, "col": 11, "width": 2, "height": 4
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

which prints each widget's resolved `gridPosition` (or `<auto>` for an unplaced `statistic`/`lineChart` — a `text` widget always shows a real position) and the list of widget titles that would be created.

## What `apply` returns

`apply` prints a JSON object:

| Key | Meaning |
|---|---|
| `dashboardId` | The created dashboard's base64 id (`null` on `--dry-run`) |
| `created` | Widget titles this run submitted, in order |
| `skipped` | Your `skipped` array, echoed back for the report you give the user |
| `verified` | `true` only if a read-back of the dashboard found every title in `created` |
| `missingTitles` | Titles that did not come back from that read-back — widgets that were accepted but did not land |
| `dashboardWidgetTitles` | Every title the dashboard has, including a template's own widgets |
| `verification` | Which of the three outcomes happened: `verified` (every title landed), `missingWidgets` (one didn't), or `notCompleted` (the read-back itself failed — including a network error — so the dashboard exists but nothing is known about its widgets) |
| `verifyError` | Present only if the read-back itself failed; the dashboard still exists, the check didn't run |
| `url` | The deep link, but only when `apply --org ORG_ID` was passed. Otherwise `null` |
| `urlHint` | Present when `url` is `null` — the script never guesses an organization id |

If `missingTitles` is non-empty or `verifyError` is set, `apply` exits **non-zero** and repeats the problem on stderr. The dashboard id is still printed, so the user can go look at what did land.
