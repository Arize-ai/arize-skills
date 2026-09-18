---
name: arize-dashboard
description: "Builds populated Arize dashboards for a project — discovers the project's span properties, evals, and annotations, then creates widgets backed by that data. Use when the user mentions create dashboard, build a dashboard, dashboard for my project, LLM observability dashboard, eval dashboard, token/cost dashboard, add a widget, or list/delete dashboards. For links to existing Arize resources use arize-link; for why a dashboard shows zero or n/a use arize-instrumentation-health."
metadata:
  author: arize
  version: "1.0"
---

# Arize Dashboard Skill

Builds Arize dashboards that are populated with widgets backed by a project's real tracing data — not blank templates. The skill runs a bundled script, `scripts/dashboard.py`, over the Arize programmatic GraphQL API; it discovers what a project actually has (span properties, evals, annotations, custom metrics), then composes a dashboard spec from that discovery output.

## How this skill fits

| Skill | Use it for |
|-------|------------|
| **This skill (`arize-dashboard`)** | Creating a new dashboard populated from a project's real data; listing dashboards in a space; soft-deleting a dashboard |
| **arize-link** | A deep link to an *existing* Arize resource (project, trace, dataset, …) |
| **arize-instrumentation-health** | Auditing whether a project's traces are healthy *before* building a dashboard on them — run this first if the user reports evals or metrics showing blank/zero |
| **arize-evaluator** | Creating the LLM-as-judge or code evaluators that produce the `llmEvals` this skill discovers — run this first if the project has no evals yet and the user wants an eval dashboard |

## What this skill does

- Discovers a project's span properties, evals, annotations, and custom metrics via `dashboard.py discover`.
- Creates a new dashboard, either from an Arize template (`overview`, `cost-latency`) or fully composed (`eval-health`, `custom`), then adds widgets built from that discovery output.
- Supports three widget types end to end: `text`, `statistic`, `lineChart`.
- Lists dashboards in a space and reads back a dashboard's widget titles (`verify`).
- Soft-deletes a dashboard.

## What this skill does not do

- **Does not edit an existing dashboard's widgets or layout.** There is no update-widget command; to change a dashboard, build a new spec and `apply` it, or add widgets by hand in the UI.
- **Does not rename a dashboard.** The Arize API has an `updateDashboardName` mutation (see [references/graphql.md](references/graphql.md)), but no CLI command wires it — do not invent a `rename` subcommand.
- **Does not manage monitors or alerts.**
- **Does not target non-LLM model dashboards.** Arize also has `regression`/`rankingModel`/`multiClassModel` templates; no blueprint here uses them. The `custom` blueprint could reach one if you pass its template name explicitly, but that is not this skill's job — treat a request for a non-LLM model dashboard as out of scope and say so.
- **Does not hard-delete.** See the limitation below.

## Two limitations to tell the user up front

Before building anything, make sure the user knows these two things — they are API constraints, not bugs in this skill:

1. **No dashboard-level time range.** The API has no mutation to set a dashboard's default time window, so a newly created dashboard opens on Arize's default window; the user adjusts it with the UI time picker. The one exception: an individual `lineChart` widget *can* pin its own range via `overwriteGlobalTime` plus `startTime`/`endTime`/`timeRangeKey`/`timeSeriesDataGranularity` (see [references/graphql.md](references/graphql.md)) — `dashboard.py` does not currently set these, so a chart falls back to the dashboard's window unless you extend the spec.
2. **No hard delete.** There is no `deleteDashboard` mutation. `dashboard.py delete` sets the dashboard's status to `deleted` via `updateDashboardStatus`. This is gated behind `--confirm` and **there is no undo through this API.**

## Workflow

1. **Resolve the project and space IDs.** `dashboard.py` takes raw base64 IDs, not names — look them up first:
   ```bash
   ax projects list --space SPACE -o json   # get the project's "id"
   ax spaces list -o json                   # get the space's "id"
   ```
2. **Discover what the project actually has:**
   ```bash
   python3 skills/arize-dashboard/scripts/dashboard.py discover --project PROJECT_ID
   ```
   This returns `spanProperties`, `llmEvals`, and `annotations`, each already shaped for reuse as a widget `dimension` — and `customMetrics`, which is informational only: `{id, name}` pairs you can show the user, but **not** something a `statistic`/`lineChart` widget's `dimension` field can be built from (see the custom-metrics limitation in [references/graphql.md](references/graphql.md)). Default lookback is 30 days; pass `--days N` to widen or narrow it.

   **`llmEvals` holds one entry per eval *field*, not per eval.** Arize stores each eval as 2-4 dimensions — `eval.<name>.label`, `eval.<name>.score`, `eval.<name>.explanation`, `eval.<name>.metadata` (plus `trace_eval.`/`session_eval.` variants). Group the list by eval name before deciding how many panels to build, use `.score` for numeric widgets and `.label` for categorical ones, and never build anything from `.explanation`/`.metadata`. See [references/blueprints.md](references/blueprints.md).
3. **Pick a blueprint** from the table below and read its full definition in [references/blueprints.md](references/blueprints.md).
4. **Write a spec** following [references/spec-format.md](references/spec-format.md), using only dimensions that `discover` actually returned.
5. **Dry-run it:**
   ```bash
   python3 skills/arize-dashboard/scripts/dashboard.py apply --spec spec.json --dry-run
   ```
   This validates the spec and prints each widget's resolved `gridPosition` without creating anything — check it before spending a real API call.
6. **Apply it:**
   ```bash
   python3 skills/arize-dashboard/scripts/dashboard.py apply --spec spec.json
   ```
   `apply` re-reads the dashboard after creating the widgets and diffs the titles against the spec. If `verified` is `false` or `missingTitles` is non-empty, some widget was accepted by the API but did not land: **do not report that run as a success** — tell the user exactly which panels are missing.
7. **Report the result to the user**, including anything you skipped (see Rules below), anything in `missingTitles`, and the two limitations above if they weren't already mentioned. A direct link needs the deep-link path — see the "Unverified assumptions" note in [references/graphql.md](references/graphql.md) before promising a working URL. `apply --org ORG_ID` and `verify --org ORG_ID --space SPACE_ID` will print that link as the result's `url`, but it is still unconfirmed against a live app; prefer the **arize-link** skill's project link, or `dashboard.py verify --dashboard DASHBOARD_ID` to confirm the dashboard exists, until that path is confirmed.

`--profile` and `--home` are accepted both before and after the subcommand on every command, e.g. `dashboard.py --profile prod discover --project X` and `dashboard.py discover --project X --profile prod` are equivalent. Credentials and the API/app endpoint resolve from the active `ax` profile: `~/.arize/.active_profile` names the profile, then `~/.arize/profiles/<name>.toml` supplies `auth.api_key` and `routing.app_host`/`api_host`. Do not ask the user for an API key — resolve it through the profile, same as every other skill in this repo.

## Blueprint selection

| Blueprint | When to use it | Built from |
|-----------|-----------------|------------|
| `overview` | General "give me a dashboard for this project" request, no specific angle stated | Arize template `generativeLlmModelV2` ("Tracing Project Overview"), augmented with one statistic per discovered eval **name** |
| `cost-latency` | User asks about token usage, cost, or latency | Arize template `generativeLlmModel` ("Token Tracking and Latency"), augmented |
| `eval-health` | User asks about eval scores, eval health, or quality over time | Fully composed — no Arize template covers this. Per discovered eval **name**: a `.score` line chart, a `.score` summary statistic, and a `.label` distribution panel, behind a full-width text header |
| `custom` | User states a specific goal that doesn't match the above | Composed from the stated goal plus whatever `discover` returned |

Full panel-by-panel definitions, including why each blueprint is shaped the way it is, are in [references/blueprints.md](references/blueprints.md). Read the three rules at the top of that file before building any of them — panel counts follow distinct eval **names** (not the length of `llmEvals`), aggregations follow the dimension's `dataType`, and templated dashboards accept no placement.

## Rules

- **Never invent a dimension.** Every `dimension` on a `statistic` or `lineChart` widget must come verbatim (`id`, `name`, `dataType`) from that project's `discover` output. If a blueprint calls for a panel — e.g. a "cost per call" statistic — and `discover` returned no matching dimension or custom metric, **skip that panel** and tell the user what you skipped and why, rather than guessing at a dimension ID. Record skipped panels in the spec's optional top-level `skipped` array (see [references/spec-format.md](references/spec-format.md)) so `apply`'s output surfaces them.
- **Match the aggregation to the dimension's `dataType`.** `avg`/`sum`/`p50`/`p95`/`p99` are numeric-only — valid on an eval's `.score` (FLOAT/DOUBLE/LONG), never on a STRING dimension such as an eval's `.label`. STRING dimensions take `count`/`cardinality`/`percentEmpty`. The GraphQL API does **not** reject the wrong pairing: the widget is created, `verify` finds its title, and it renders `n/a` forever. Read `dataType` off the `discover` entry you are copying; see [references/spec-format.md](references/spec-format.md).
- **Never hand-write `gridPosition`.** The spec format uses `row`/`col`/`width`/`height` (1-indexed on a 12-column grid); `dashboard.py` converts these to Arize's `[rowStart, colStart, rowEnd, colEnd]` array internally. If you omit all four on a `statistic` or `lineChart`, the widget is left unplaced and the backend auto-places it — do this for widgets added to a templated dashboard (`overview`, `cost-latency`); see the placement-collision note in [references/graphql.md](references/graphql.md). **`text` is the exception: it is never auto-placed.** Its API mutation requires a `gridPosition`, so omitting placement pins it to the full-width band at row 1 — exactly the collision the rule above exists to prevent. Place every text widget explicitly, and don't put one on a templated dashboard at all.
- **Templated dashboards are placement-free — and `dashboard.py` enforces it.** If `dashboard.template` is set, `validate_spec` raises `SpecError` for any widget carrying `row`/`col`/`width`/`height` and for any `text` widget. Augment `overview`/`cost-latency` with unplaced `statistic`/`lineChart` widgets only.
- **Confirm before `delete`.** `dashboard.py delete` requires `--confirm` and there is no undo; make sure the user explicitly asked for this dashboard to be removed before running it.

## CLI reference

Every command also accepts the common flags `[--profile P] [--home DIR] [--app-host HOST]`, before or after the subcommand.

```
dashboard.py discover --project PROJECT_ID [--days N]
dashboard.py apply    --spec SPEC.json [--dry-run] [--org ORG_ID]
dashboard.py verify   --dashboard DASHBOARD_ID [--org ORG_ID --space SPACE_ID]
dashboard.py list     --space SPACE_ID
dashboard.py delete   --dashboard DASHBOARD_ID --confirm
```

- `--app-host HOST` overrides the app endpoint for an on-prem deployment whose profile has no `routing.app_host`; it beats both `ARIZE_APP_HOST` and the profile.
- `--org ORG_ID` prints the dashboard deep link as the result's `url`. Without it the result carries `"url": null` and a hint — the script never guesses an organization id. `verify` needs `--space` alongside `--org` because the link path contains both.

All commands print JSON to stdout (or, for `delete`, a one-line confirmation) and exit non-zero with a plain error message on stderr on failure — no tracebacks are surfaced. `apply` also exits non-zero when its post-apply read-back finds a widget missing.

| Symptom | Fix |
|---------|-----|
| `Profile '...' not found` | Run `ax profiles list`, then pass `--profile NAME` or set the active profile |
| `ID '...' is not a project, or is not visible with this API key` | The `--project` value must be the project's base64 `id` from `ax projects list -o json`, not its name |
| `ID '...' is not a space, or is not visible with this API key` | Same, for `--space` — use `ax spaces list -o json` |
| `Refusing to delete without --confirm` | Re-run with `--confirm` only after the user has explicitly confirmed |
| `SpecError` on `apply` | The spec is missing a required field, uses an unsupported widget `type`, or a widget is missing `dimension`/`dimensionCategory` — see [references/spec-format.md](references/spec-format.md) |
| `LayoutError` on `apply` | Two placed widgets overlap, or a widget's `row`/`col` is out of the 12-column grid — see [references/spec-format.md](references/spec-format.md). An unplaced `text` widget counts as placed at row 1, full width |
| `SpecError` mentioning a templated dashboard | The spec sets `dashboard.template` and a widget has placement fields or is a `text` widget — drop the placement, or drop the template |
| `Cannot read spec file` / `is not valid JSON` | The `--spec` path is wrong or the file isn't a JSON object — the message names the path and, for JSON, the line and column |
| `These widgets are not on the dashboard after apply` | The dashboard was created but a widget didn't land; report the named panels to the user as missing rather than claiming success |

## References

- [references/blueprints.md](references/blueprints.md) — the four blueprints, panel by panel, and why each is shaped the way it is
- [references/spec-format.md](references/spec-format.md) — the full spec JSON contract, field by field, with a worked example
- [references/graphql.md](references/graphql.md) — the underlying GraphQL API surface, what's wired vs. documented-only, and two unverified assumptions to confirm against a live app before relying on them
