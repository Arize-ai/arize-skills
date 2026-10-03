# GraphQL API surface

`dashboard.py` talks to Arize's programmatic GraphQL API at `{app_scheme}://{app_host}/graphql`, authenticated with `Bearer {api_key}` from the active `ax` profile. This document records the verified API surface the script relies on, what's wired into the CLI vs. documented-only, and two assumptions that were never confirmed against a live Arize app.

## Widget types

Arize supports six widget types with full CRUD. **This skill's script wires three of them end to end** — `text`, `statistic`, `lineChart`. The other three exist in the API but have no blueprint or spec support here:

| Widget type | Wired in `dashboard.py`? | Mutation |
|---|---|---|
| `text` | Yes | `createTextWidget` |
| `statistic` | Yes | `createStatisticWidget` |
| `lineChart` | Yes | `createLineChartWidget` |
| `barChart` | No — documented only | `createBarChartWidget` |
| `pivotTable` | No — documented only | `createPivotTableWidget` |
| `experimentChart` | No — documented only | `createExperimentChartWidget` |

`widget_mutation()` in `dashboard.py` raises `SpecError` for any `type` other than `text`, `statistic`, or `lineChart` — including `barChart`/`pivotTable`/`experimentChart`, even though Arize itself supports them. Extending the script to cover them is future work, not something to fake by hand-crafting the mutation in a spec.

### `gridPosition`

- **Required** on `createTextWidget` (`gridPosition: [Int!]!`). A text widget is therefore **never auto-placed**: if its spec omits placement, `dashboard.py` falls back to a full-width band (`row=1, col=1, width=12, height=2` → `[1, 1, 3, 13]`). `validate_spec()` writes that fallback onto the widget *before* `validate_layout()` runs, so the band takes part in overlap detection and shows up in `--dry-run` output — two unplaced text widgets, or an unplaced text widget plus anything else at row 1, is a `LayoutError`, not a silent stack.
- **Optional** on `createStatisticWidget` and `createLineChartWidget`. Omitting it lets the backend auto-place the widget instead of colliding with something already on the dashboard.
- The array shape is `[rowStart, colStart, rowEnd, colEnd]`, 1-indexed on a 12-column grid — **not** `[x, y, w, h]`. `dashboard.py`'s `to_grid_position(row, col, width, height)` does this conversion; nothing should ever write `gridPosition` directly. Full field-level detail is in [spec-format.md](spec-format.md).

## Dashboard mutations

| Mutation | Wired in `dashboard.py`? | Notes |
|---|---|---|
| `createDashboard` | Yes | Plain dashboard, no template — used when the spec has no `dashboard.template` |
| `createDashboardFromTemplate` | Yes | Used when `dashboard.template` is set (e.g. `generativeLlmModelV2`, `generativeLlmModel`). `dashboard.py` sends `modelEnvironmentName: "tracing"` explicitly — see below |
| `createDefaultDashboard` | No | Documented in the schema; not called by this skill |
| `copyDashboard` | No | Documented in the schema; not called by this skill |
| `updateDashboardName` | No | Exists in the API — **there is no CLI command that wires it.** Do not invent a `rename` subcommand or ask the user to "just rename it" via this skill |
| `updateDashboardStatus` | Yes | Used by `delete` — see **No hard delete** below |

### `createDashboardFromTemplate` must be told the environment

`dashboard.py` sends `modelEnvironmentName: "tracing"` on the template input. Omitting it is not neutral: server-side, an omitted value falls through to `production` unless a recent LLM-template default applies, and on-prem deployments predating that default would then build every template panel against `production` — which has no tracing data, so the whole templated half of the dashboard renders empty while the augmented statistics render fine. Sending it explicitly is accepted on current builds too, so it is strictly safer. Template names are `DashboardTemplates` values: `generativeLlmModelV2`, `generativeLlmModel`, `regression`, `rankingModel`, `multiClassModel`.

## Reads

- **Listing:** `Space.dashboards(first:, sort:)` — a connection off `node(id: spaceId) { ... on Space { dashboards(...) { edges { node { id name status } } } } }`. `dashboard.py list` uses `first: 50` and does not currently expose `sort`.
- **Single dashboard:** `node(id: dashboardId) { ... on Dashboard { ... } }`. `dashboard.py verify` reads back `statisticWidgets`, `textWidgets`, and `lineChartWidgets` (each `first: 100`) and returns their titles — it does not read `barChart`/`pivotTable`/`experimentChart` widgets, consistent with those types not being wired.
- **`apply` verifies itself.** After creating the widgets, `apply` runs that same read and diffs the returned titles against the spec's titles. Spec titles that did not come back land in `missingTitles`, `verified` goes `false`, the CLI prints the list on stderr and exits non-zero. Extra titles are *not* an error — a templated dashboard legitimately carries the template's own widgets as well.

## Discovery

`dashboard.py discover` queries a project (a `Model` node) directly:

- `Model.tracingSchema(startTime, endTime)` → `spanProperties(first: 200)`, `llmEvals(first: 100)`, `annotations(first: 100)`, each a connection of nodes carrying a `dimension`.
- `Model.customMetrics(first: 50)` → `{ id, name }` pairs, no `dimension` wrapper — informational only; see **Known limitation: custom metrics are not widget dimensions** below before treating one as buildable.

Each `dimension` carries `id`, `name`, `dataType`, and `category`. These four fields map directly onto GraphQL's `DimensionInput` (minus `category`, which becomes the widget's separate `dimensionCategory` field — see [spec-format.md](spec-format.md)). Discovery defaults to a 30-day window (`discover --days N` to change it); a project with no traffic in that window will legitimately return empty lists, not an error.

### Eval dimensions are one per *field*, not one per eval

`llmEvals` returns **one entry per eval dimension**, and Arize stores each eval as 2-4 separate dimensions. The web app's `parseEvalDimensionName` parses every eval dimension name as `<prefix>.<eval name>.<field>`:

| Part | Values |
|---|---|
| prefix | `eval` (span-scoped), `trace_eval` (trace-scoped), `session_eval` (session-scoped) |
| eval name | the evaluator's name, e.g. `hallucination`, `correctness` |
| field | `label`, `score`, `explanation`, `metadata` |

A project with one `hallucination` eval can return four entries — `eval.hallucination.label`, `eval.hallucination.score`, `eval.hallucination.explanation`, `eval.hallucination.metadata`. A project with five evals commonly returns 10-20 entries.

**Consequence for building a dashboard:** never emit one panel per `llmEvals` entry. Group the list by parsed eval name first, then pick the dimension by field:

| Field | `dataType` | Build from it | Never |
|---|---|---|---|
| `.score` | numeric (FLOAT/DOUBLE/LONG) | line charts, `avg`/`p95` statistics | — |
| `.label` | STRING | `count`/`cardinality`/`percentEmpty` statistics | `avg` and the other numeric-only functions |
| `.explanation` | STRING | nothing — it is free text | any widget |
| `.metadata` | STRING | nothing | any widget |

The number of panels a blueprint produces is driven by the number of distinct eval **names**, not by `len(llmEvals)`. The panel-by-panel recipe is in [blueprints.md](blueprints.md).

## `creationStatus`

Every **widget** mutation takes `creationStatus`; `dashboard.py` always sends `"published"`. The enum also has a `"created"` value, which means *saved but not shown* on the dashboard — do not use it when the goal is a dashboard the user can immediately open and see.

**Neither dashboard-create mutation takes `creationStatus`.** `CreateDashboardMutationInput` is `{name, spaceId, clientMutationId}`, and `CreateDashboardFromTemplateMutationInput` has no `creationStatus` field either. `dashboard.py` is right not to send one — do not "fix" it to match this section's old wording, or every `apply` will fail on an unknown input field.

## Enum values in use

- **`aggregation`** (on `statistic` widgets) is a `DataQualityMetric`. The full enum is `avg`, `count`, `sum`, `percentEmpty`, `cardinality`, `standardDeviation`, `p50`, `p95`, `p99`, `p99_9`, `newValues`, `missingValues`, `averageStringListLength`. `dashboard.py` defaults to `count` when a spec omits it — `count` is valid on every `dataType`, which is why it is the default, but it is rarely the number the user asked for.
- **`metric`** (on a `lineChart` widget's `plots` entry) is a `Metric`, which also contains `avg`/`count`/`sum` among its values. `dashboard.py` defaults to `count`.

### The aggregation rule: choose it from the dimension's `dataType`

`avg`, `sum`, `standardDeviation`, `p50`, `p95`, `p99`, and `p99_9` are **numeric-only** — the Arize web app lists them in `NumericOnlyDataQualityMetricFunctions` and hides them for categorical dimensions. **The GraphQL enum does not enforce this.** A mutation pairing `avg` with a STRING dimension is accepted, `apply` reports success, `verify` reports a matching title, and the widget renders `n/a` forever.

| `dimension.dataType` | Valid `aggregation` / `metric` |
|---|---|
| FLOAT, DOUBLE, LONG, INT — e.g. `eval.<name>.score` | `avg`, `sum`, `standardDeviation`, `p50`, `p95`, `p99`, `p99_9`, plus `count`, `percentEmpty`, `cardinality` |
| STRING — e.g. `eval.<name>.label`, most span properties | `count`, `cardinality`, `percentEmpty`, `newValues`, `missingValues` |

Read `dataType` off the very `discover` entry you are about to put in the widget's `dimension` field. Never assume it, and never hardcode `avg`.

## Line chart shape

A `lineChart` widget's create input has **no top-level `modelId`, `dimension`, or `dimensionCategory`** — those three live inside each entry of its `plots` array, alongside `modelVersionIds` (`dashboard.py` always sends `[]`, i.e. all versions), `modelEnvironmentName`, `metric`, `title`, `position`, and `filters` (`dashboard.py` always sends `[]`). Putting `dimension`/`dimensionCategory` at the top level of a line-chart input — the way `statistic` widgets take them — is a common mistake; `dashboard.py`'s `widget_mutation()` nests them correctly, so build specs against [spec-format.md](spec-format.md) rather than reasoning about the mutation shape from a `statistic` example.

## Three constraints — state these to the user

1. **No dashboard-level time mutation.** There is no mutation to set a dashboard's default time range; a newly created dashboard opens on Arize's default window and the user adjusts it with the UI time picker. *However*, individual `lineChart` widgets accept `overwriteGlobalTime` plus `startTime`/`endTime`/`timeRangeKey`/`timeSeriesDataGranularity` on their plot, so a single chart *can* pin its own range independent of the dashboard. `dashboard.py` does not currently set these fields.
2. **No hard delete.** There is no `deleteDashboard` mutation in the schema. `dashboard.py delete` calls `updateDashboardStatus` with `status: "deleted"`, gated behind `--confirm`. There is no undo through this API once that mutation runs.
3. **`gridPosition` is never hand-written.** See the `gridPosition` section above and [spec-format.md](spec-format.md) — specs use `row`/`col`/`width`/`height`; the script converts.

## Known limitation: custom metrics are not widget dimensions

This is confirmed against Arize's schema, not a guess — unlike the two items below.

A custom metric does **not** attach to a widget through `dimension`/`dimensionCategory` the way a span property, eval, or annotation does. `CreateStatisticWidgetMutationInput` has a **separate** `customMetric: CustomMetricInput` field for this, and `CustomMetricInput` requires `id`, `name`, **`metric`** (the metric expression string, e.g. `'AVG(predictionScore)'`), and **`requiresPositiveClass`** — none of which `discover` fetches (`Model.customMetrics` returns only `{id, name}`, per the Discovery section above) and none of which `widget_mutation()` wires up.

**Practical consequence:** treat `discover`'s `customMetrics` list as informational — something to show the user ("this project also has a `cost_per_call` custom metric") — never as a source for a widget's `dimension` field. Putting a `customMetrics` entry's `id`/`name` into a `dimension` object passes `validate_spec` (which only checks the fields are truthy) and `--dry-run`, then fails with a `GraphQLError` on the real `apply`, because the resulting mutation references a dimension that doesn't exist. Wiring `customMetric` support into `dashboard.py` is a follow-up, not something to work around by hand today.

## Unverified assumptions — confirm against a live app

These two facts were never confirmed against a running Arize app during implementation, because no live space was authorized. Both need a live check before relying on them.

1. **Dashboard deep-link path.** `dashboard_url()` in `dashboard.py` assumes:
   ```
   {base_url}/organizations/{org_id}/spaces/{space_id}/dashboards/{dashboard_id}
   ```
   It is reachable from the CLI: `apply --org ORG_ID` and `verify --org ORG_ID --space SPACE_ID` print it as the result's `url`. Without `--org` the result carries `"url": null` and a hint instead — the script never guesses an organization id. This mirrors the path shape used elsewhere in this repo (see **arize-link**) but has not itself been opened in a browser. The **arize-link** skill's rule applies here too: **all path IDs are base64** — a raw numeric ID produces a URL that looks valid but 404s. Prefer confirming a dashboard's existence with `dashboard.py verify --dashboard ID` over asserting the link works, until this path is confirmed.
2. **Whether `createDashboardFromTemplate` returns widget IDs is unknown.** Because that's unconfirmed, `apply()` builds augmented widgets (e.g. the per-eval statistics in `overview`/`cost-latency`) identically whether or not the dashboard came from a template — it has no way to look up the template's existing widget positions to avoid them. **This means row/col-placed widgets added to a templated dashboard may collide with the template's own widgets.** This is **enforced in code, not left to prose**: `validate_spec()` raises `SpecError` when `dashboard.template` is set and any widget carries `row`/`col`/`width`/`height` (even one of the four), and it raises `SpecError` for any `text` widget on a templated dashboard, because a text widget cannot be auto-placed at all (see the `gridPosition` section) and its fallback band would land on top of the template's top row. So when augmenting a templated dashboard (`overview`, `cost-latency`): statistics and line charts only, with no placement fields, and the backend puts them in free slots. Relaxing this is a one-line change to `_reject_unsafe_placement_on_template()` once someone confirms against a live app what `createDashboardFromTemplate` reports back.
