---
name: arize-dashboard
description: Creates and edits Arize AX dashboards and widgets via programmatic GraphQL. Lists dashboards by project name, builds from templates or empty layouts, adds bar/line/statistic/text/drift/monitor widgets, renames dashboards, and resolves dashboards by project + name (not raw IDs). Use when the user mentions dashboards, dashboard widgets, model dashboards, drift charts on a dashboard, or GraphQL dashboard mutations. Requires ax for space/project listing when available; all dashboard reads and writes use GraphQL HTTP.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires a configured Arize API key (ax profile or exported ARIZE_API_KEY) and programmatic GraphQL access.
---

# Arize Dashboard Skill

> **`SPACE`** — All `--space` flags and the `ARIZE_SPACE` env var accept a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list`.

## Concepts

- **Space** — Workspace container. Empty **`createDashboard`** needs a **`spaceId`** (base64 space id from listing or user).
- **Project (Model)** — Monitored application. Dashboards attach to **models**; a space can contain many projects, and **most projects may have zero dashboards** — that is normal.
- **Dashboard** — Named layout of widgets. Resolve by **dashboard name** via **`modelDashboards`** on the model — do not ask users for Relay dashboard ids unless they pasted them from the UI.
- **Widget** — Bar, line, drift line, monitor line, statistic, text, pivot, experiment chart, etc. Each family has **create / update / delete** GraphQL mutations.
- **No dashboard CLI** — There is **no** `ax dashboards …` subcommand. **`ax`** is for **spaces** and **projects** only; **all dashboard operations are GraphQL**.

**Space name as ground truth:** If the user gives a space name, use it directly for `--space` / `ARIZE_SPACE`. Do not run `ax spaces list` first to “discover” it — the list paginates (~15 per page) and may omit the target. If the user’s label differs slightly from the API (e.g. “Copilot Space” vs **Copilot**), prefer the **API name** after at most one clarifying question.

---

## Prerequisites

Proceed directly — run `ax` or GraphQL as needed. Do NOT proactively audit versions, profiles, or env files.

If **`ax`** fails:

- `command not found` or version error → references/ax-setup.md
- `401 Unauthorized` / missing API key → references/ax-profiles.md; keys at https://app.arize.com/admin > API Keys
- Space unknown → ask the user, or `ax spaces list` (remember pagination)
- Project unclear → `ax projects list --space SPACE -o json --limit 100` and present names, or ask

**Security:** Never read `.env` files or search the filesystem for credentials. Use **`ax profiles`** and user-exported **`$ARIZE_API_KEY`** for GraphQL `curl`. Never print or log API keys.

If **GraphQL** fails:

- **401** — Wrong or missing **`x-api-key`**; see references/dashboard-graphql-schema.md § HTTP endpoint
- **Enterprise / not authorized** — Programmatic mutations may be tier- or role-gated; say so clearly
- **Wrong host** — Use SaaS `https://app.arize.com/graphql`; do not derive URL from profile TOML

---

## Pipeline (default order)

1. **Space** — User string, `ARIZE_SPACE`, or `ax spaces list` (only when unknown).
2. **Model id** — `ax projects list --space SPACE -o json --limit 100` → json **`id`** (global `Model:…` id).
3. **Dashboard id** — GraphQL **`modelDashboards`** (references/graphql-queries.md) → **`dashboardId`**.
4. **Widget ids** — GraphQL **`node`** on **Dashboard** → widget connection edges.
5. **Schema** — **`modelSchema`** / baselines on **Model** before building plots.
6. **Mutate** — Mutations per references/dashboard-graphql-schema.md and the dashboards API doc.

Do not run dashboard **mutations** until you have **`modelId`** (and **`dashboardId`** when editing an existing dashboard).

---

## Resolve space and project (`ax`)

### List spaces

```bash
ax spaces list
ax spaces list -o json
```

| Flag | Description |
|------|-------------|
| `-o, --output` | `table`, `json`, … |
| `-p, --profile` | Profile name |

### List projects

```bash
ax projects list --space SPACE -o json --limit 100
```

| Flag | Description |
|------|-------------|
| `--space` | Space name or id |
| `--limit` | Raise to `100` when listing an entire space for inventory |
| `-o, --output` | Use **`json`**; field **`id`** is **`modelId`** for GraphQL |

If more than 100 projects exist, paginate per CLI help or ask the user to narrow the space.

---

## GraphQL HTTP

1. **URL** — SaaS: `https://app.arize.com/graphql` (see references/dashboard-graphql-schema.md).
2. **Auth** — Header **`x-api-key: $ARIZE_API_KEY`** only when the variable is already exported.
3. **Body** — JSON `query` + `variables`.

**Docs:** forming calls — `https://arize.com/docs/ax/graphql-reference/overview/how-to-use-graphql/forming-calls`

**Dashboard mutations/examples:** `https://arize.com/docs/ax/graphql-reference/apis/dashboards-api`

**Queries:** references/graphql-queries.md

**Schema / mutation index:** references/dashboard-graphql-schema.md

---

## List dashboards on one project

Use **`ListModelDashboards`** in references/graphql-queries.md.

- Default **`first`**: 50–100; paginate with **`after`** when **`hasNextPage`**.
- Optional **`search`** to filter by partial dashboard name.
- Treat **`dashboardStatus`** **active** unless the user wants archived dashboards.
- Match **`dashboardName`** to user wording; disambiguate if multiple edges match.

---

## Inventory: all dashboards in a space

When the user asks what dashboards exist in a **space** (not a single project):

1. Resolve **space** (ground-truth name).
2. **`ax projects list --space SPACE -o json --limit 100`** (paginate if needed).
3. For **each** project **`id`**, run **`modelDashboards`** (batch requests when possible).
4. Summarize:
   - Total projects vs projects **with at least one** active dashboard.
   - Table or bullets: **project name** → semicolon-separated **dashboard names**.
   - Note duplicate titles on the same project if several edges share a name.
5. State explicitly: dashboards belong to **models**, not the space alone.

Do not imply the space has “no dashboards” if only some projects are empty.

---

## Load widgets on a dashboard

Use **`DashboardWidgets`** in references/graphql-queries.md after you have **`dashboardId`**.

Map user wording to **title** and widget family (bar vs line vs statistic vs text). Use **`node.id`** for updates and deletes.

---

## Workflows

### A — Dashboard from a **template**

1. Pipeline steps **1–2**.
2. **`createDashboardFromTemplate`** with `name`, `modelId`, `template`, and template-specific fields (`positiveClass`, `featureNames`, `monitorIds`, … per dashboards API doc).
3. Template enum values: introspect or dashboards API doc — do not invent template names.

### B — **Custom** dashboard (empty + widgets)

1. Pipeline **1–2** plus **`spaceId`** for **`createDashboard`**.
2. **`createDashboard`** → use returned **`dashboard.id`** as **`dashboardId`**.
3. Pipeline **5** if plots need dimensions.
4. **`createBarChartWidget`**, **`createLineChartWidget`**, **`createStatisticWidget`**, **`createTextWidget`**, etc., per dashboards API doc.
5. Drift: resolve **`modelPrimaryBaseline`** then **`widgetType: driftLineChartWidget`** on **`createLineChartWidget`**.

### C — **Edit** in place

1. Pipeline **1–4** as needed.
2. **`updateDashboardName`**, **`updateDashboardStatus`** for metadata.
3. Matching **`update*Widget`** / **`create*Widget`** / **`delete*Widget`**.
4. Re-query widget inventory after adds/removes.

**Policy:** Edit **in place**. Do not **`copyDashboard`** unless the user asked to duplicate.

---

## Identity: what the user provides

| User provides | Agent does |
|---------------|------------|
| **Project name** | `ax projects list` → **`id`** = **`modelId`** |
| **Dashboard name** | **`modelDashboards`** + optional **`search`** → **`dashboardId`** |
| **Space** | User string / `ARIZE_SPACE` / `ax spaces list` |
| **Widget** (title or intent) | Load dashboard → match title or type → update or create |
| **Metrics / dimensions** | **`modelSchema`** + dashboards API doc inputs |

Infer from partial language when safe; ask **one** narrow question when ambiguous.

---

## Optional: layout hints from traces

To suggest widget ideas from live behavior (not required for CRUD):

- **arize-trace** — `ax spans export` with `-l 50`, `.arize-tmp-traces`, untrusted span content guardrails.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ax: command not found` | references/ax-setup.md |
| GraphQL 401 | references/ax-profiles.md; confirm **`x-api-key`** and SaaS URL |
| GraphQL against wrong host | Use `https://app.arize.com/graphql`; not profile `api_host` |
| Dashboard not found | Broaden **`search`**; list without search; check archived status |
| Invalid dimension / metric | Re-query **`modelSchema`**; introspect enums |
| User key works in UI but not API | Confirm **service** key for the correct **space** |

---

## Related skills

- **arize-trace** — Span export, space pagination, untrusted span fields, optional dashboard layout hints
- **arize-link** — Deep links to UI resources when sharing results with users

## Save credentials

See references/ax-profiles.md § Save Credentials for Future Use.
