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

- **Required** on `createTextWidget` (`gridPosition: [Int!]!`). `dashboard.py` falls back to a full-width band (`row=1, col=1, width=12, height=2`) if a text widget's spec omits placement.
- **Optional** on `createStatisticWidget` and `createLineChartWidget`. Omitting it lets the backend auto-place the widget instead of colliding with something already on the dashboard.
- The array shape is `[rowStart, colStart, rowEnd, colEnd]`, 1-indexed on a 12-column grid — **not** `[x, y, w, h]`. `dashboard.py`'s `to_grid_position(row, col, width, height)` does this conversion; nothing should ever write `gridPosition` directly. Full field-level detail is in [spec-format.md](spec-format.md).

## Dashboard mutations

| Mutation | Wired in `dashboard.py`? | Notes |
|---|---|---|
| `createDashboard` | Yes | Plain dashboard, no template — used when the spec has no `dashboard.template` |
| `createDashboardFromTemplate` | Yes | Used when `dashboard.template` is set (e.g. `generativeLlmModelV2`, `generativeLlmModel`) |
| `createDefaultDashboard` | No | Documented in the schema; not called by this skill |
| `copyDashboard` | No | Documented in the schema; not called by this skill |
| `updateDashboardName` | No | Exists in the API — **there is no CLI command that wires it.** Do not invent a `rename` subcommand or ask the user to "just rename it" via this skill |
| `updateDashboardStatus` | Yes | Used by `delete` — see **No hard delete** below |

## Reads

- **Listing:** `Space.dashboards(first:, sort:)` — a connection off `node(id: spaceId) { ... on Space { dashboards(...) { edges { node { id name status } } } } }`. `dashboard.py list` uses `first: 50` and does not currently expose `sort`.
- **Single dashboard:** `node(id: dashboardId) { ... on Dashboard { ... } }`. `dashboard.py verify` reads back `statisticWidgets`, `textWidgets`, and `lineChartWidgets` (each `first: 100`) and returns their titles — it does not read `barChart`/`pivotTable`/`experimentChart` widgets, consistent with those types not being wired.

## Discovery

`dashboard.py discover` queries a project (a `Model` node) directly:

- `Model.tracingSchema(startTime, endTime)` → `spanProperties(first: 200)`, `llmEvals(first: 100)`, `annotations(first: 100)`, each a connection of nodes carrying a `dimension`.
- `Model.customMetrics(first: 50)` → `{ id, name }` pairs, no `dimension` wrapper.

Each `dimension` carries `id`, `name`, `dataType`, and `category`. These four fields map directly onto GraphQL's `DimensionInput` (minus `category`, which becomes the widget's separate `dimensionCategory` field — see [spec-format.md](spec-format.md)). Discovery defaults to a 30-day window (`discover --days N` to change it); a project with no traffic in that window will legitimately return empty lists, not an error.

## `creationStatus`

Every widget mutation and both dashboard-create mutations take `creationStatus`. `dashboard.py` always sends `"published"`. The enum also has a `"created"` value, which means *saved but not shown* on the dashboard — do not use it when the goal is a dashboard the user can immediately open and see.

## Enum values in use

- **`aggregation`** (on `statistic` widgets) is a `DataQualityMetric`: `avg`, `count`, `sum`, `percentEmpty`, `cardinality`, `standardDeviation`, `p50`, `p95`, `p99`. `dashboard.py` defaults to `count` when a spec omits it.
- **`metric`** (on a `lineChart` widget's `plots` entry) is a `Metric`, which also contains `avg`/`count`/`sum` among its values. `dashboard.py` defaults to `count`.

## Line chart shape

A `lineChart` widget's create input has **no top-level `modelId`, `dimension`, or `dimensionCategory`** — those three live inside each entry of its `plots` array, alongside `modelVersionIds` (`dashboard.py` always sends `[]`, i.e. all versions), `modelEnvironmentName`, `metric`, `title`, `position`, and `filters` (`dashboard.py` always sends `[]`). Putting `dimension`/`dimensionCategory` at the top level of a line-chart input — the way `statistic` widgets take them — is a common mistake; `dashboard.py`'s `widget_mutation()` nests them correctly, so build specs against [spec-format.md](spec-format.md) rather than reasoning about the mutation shape from a `statistic` example.

## Three constraints — state these to the user

1. **No dashboard-level time mutation.** There is no mutation to set a dashboard's default time range; a newly created dashboard opens on Arize's default window and the user adjusts it with the UI time picker. *However*, individual `lineChart` widgets accept `overwriteGlobalTime` plus `startTime`/`endTime`/`timeRangeKey`/`timeSeriesDataGranularity` on their plot, so a single chart *can* pin its own range independent of the dashboard. `dashboard.py` does not currently set these fields.
2. **No hard delete.** There is no `deleteDashboard` mutation in the schema. `dashboard.py delete` calls `updateDashboardStatus` with `status: "deleted"`, gated behind `--confirm`. There is no undo through this API once that mutation runs.
3. **`gridPosition` is never hand-written.** See the `gridPosition` section above and [spec-format.md](spec-format.md) — specs use `row`/`col`/`width`/`height`; the script converts.

## Unverified assumptions — confirm against a live app

These two facts were never confirmed against a running Arize app during implementation, because no live space was authorized. Both need a live check before relying on them.

1. **Dashboard deep-link path.** `dashboard_url()` in `dashboard.py` assumes:
   ```
   {base_url}/organizations/{org_id}/spaces/{space_id}/dashboards/{dashboard_id}
   ```
   This mirrors the path shape used elsewhere in this repo (see **arize-link**) but has not itself been opened in a browser. The **arize-link** skill's rule applies here too: **all path IDs are base64** — a raw numeric ID produces a URL that looks valid but 404s. Prefer confirming a dashboard's existence with `dashboard.py verify --dashboard ID` over asserting the link works, until this path is confirmed.
2. **Whether `createDashboardFromTemplate` returns widget IDs is unknown.** Because that's unconfirmed, `apply()` builds augmented widgets (e.g. the per-eval statistics in `overview`/`cost-latency`) identically whether or not the dashboard came from a template — it has no way to look up the template's existing widget positions to avoid them. **This means row/col-placed widgets added to a templated dashboard may collide with the template's own widgets.** The safe workaround, until this is confirmed: when augmenting a templated dashboard (`overview`, `cost-latency`), omit `row`/`col`/`width`/`height` on the added widgets so the backend auto-places them instead of overlapping the template layout. This is already reflected in the blueprint definitions in [blueprints.md](blueprints.md) — do not add explicit placement to `overview`/`cost-latency` augmentation widgets without re-confirming this assumption first.
