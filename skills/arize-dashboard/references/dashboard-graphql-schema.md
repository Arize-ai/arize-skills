# Dashboard programmatic GraphQL — schema reference

Mutations use **graphql-relay** `input` objects. Optional `clientMutationId` if your client expects it.

**Examples and variable JSON:** `https://arize.com/docs/ax/graphql-reference/apis/dashboards-api`

**Request shape and headers:** `https://arize.com/docs/ax/graphql-reference/overview/how-to-use-graphql/forming-calls`

**Queries in this skill:** references/graphql-queries.md

If a field or enum is missing here, **introspect** the tenant endpoint — do not guess.

---

## HTTP endpoint

**Hosted Arize (SaaS):**

`https://app.arize.com/graphql`

- Method: **POST**
- Header: **`x-api-key`** (service API key; same family as `ax`)
- Body: `{"query":"<string>","variables":{...}}`
- Header: **`Content-Type: application/json`**

**Do not** build this URL from **`api_host`**, **`api_scheme`**, or **`single_host`** in `~/.arize/profiles/*.toml`. Profile TOML targets REST, Flight, and CLI surfaces — not programmatic GraphQL. Wrong host is a common agent mistake.

**Not SaaS:** Ask the user for the programmatic GraphQL HTTPS URL (or internal runbook). Do not infer from profile metadata.

**Example (only when `$ARIZE_API_KEY` is already exported):**

```bash
curl -sS 'https://app.arize.com/graphql' \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query":"query Q($id:ID!){ node(id:$id){ ... on Model { name } } }","variables":{"id":"MODEL_ID"}}'
```

---

## Query root (programmatic)

Typical entry points:

- **`node(id: ID!)`** — **Model**, **Dashboard**, widget types
- **`viewer`**, **`account`** — org context (rare for dashboard tasks)

---

## Dashboard reads on Model

| Field | Purpose |
|-------|---------|
| `modelDashboards(search, first, after)` | List dashboards; `dashboardId`, `dashboardName`, `dashboardStatus` on edges |
| `modelSchema` | Features, tags, predictions, actuals for `DimensionInput` |
| `modelPrimaryBaseline` | Baseline id for drift widgets |

---

## Dashboard metadata mutations

| Mutation | Purpose |
|----------|---------|
| `createDashboard` | Empty dashboard (`name`, `spaceId`) → `dashboard.id` |
| `createDashboardFromTemplate` | Template dashboard (`name`, `modelId`, `template`, template-specific fields) |
| `updateDashboardName` | Rename (`dashboardId`, `name`) |
| `updateDashboardStatus` | Active / archived / deleted |
| `copyDashboard` | Duplicate — use only when the user asks |

---

## Widget create mutations

| Mutation | Widget kind |
|----------|-------------|
| `createBarChartWidget` | Distribution / bar |
| `createLineChartWidget` | Performance, data quality, drift (`widgetType`), or monitor (`widgetType: monitorLineChartWidget`, `monitorId`) |
| `createStatisticWidget` | Single statistic (performance or data quality) |
| `createTextWidget` | Markdown / text block |

Drift line charts use **`createLineChartWidget`** with **`widgetType: driftLineChartWidget`** and plot field **`comparisonDatasetModelBaselineId`** (query baseline on Model first).

---

## Widget update / delete

For each widget family there is a matching **`update*Widget`** and **`delete*Widget`** (e.g. `updateBarChartWidget`, `deleteLineChartWidget`). Pass the widget **`id`** from the dashboard inventory query.

Exact input shapes mirror the create mutations — see the dashboards API doc.

---

## Enums and categories (non-exhaustive)

Use introspection to list all values on your tenant.

| Name | Used for |
|------|----------|
| `DashboardTemplates` / template enum in docs | `createDashboardFromTemplate` — e.g. model performance, drift, LLM tracing overview templates (names vary by release) |
| `DashboardStatus` | `dashboardStatus` on listings; filter **active** unless user wants archived |
| `TimeSeriesMetricCategory` | Line / statistic widgets — e.g. evaluation vs model data metrics |
| `PerformanceMetric` | AUC, accuracy, etc. on line/statistic plots |
| `DataQualityMetric` | `percentEmpty`, `count`, etc. |
| `DimensionCategory` | `featureLabel`, `prediction`, `tag`, … |
| `WidgetType` / `widgetType` input | Distinguish `lineChartWidget`, `driftLineChartWidget`, `monitorLineChartWidget` on `createLineChartWidget` |

---

## Core inputs

| Input | Notes |
|-------|-------|
| `DimensionInput` | `id`, `name`, `dataType` from `modelSchema` |
| `BarChartPlotInput` / `LineChartPlotInput` | `modelId`, `position`, `dimension`, `dimensionCategory`, `metric`, `filters`, `modelEnvironmentName`, `positiveClass`, split-by fields |
| `StatisticWidgetFilterItemInput` | Filters on statistic widgets |

---

## Drift baseline

```graphql
query ModelBaseline($modelId: ID!) {
  node(id: $modelId) {
    ... on Model {
      modelPrimaryBaseline { id }
    }
  }
}
```

Use returned **`id`** as **`comparisonDatasetModelBaselineId`** on drift plots.
