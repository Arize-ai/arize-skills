# Blueprint catalog

A blueprint is this skill's opinion about which widgets a spec should contain for a given request. Pick one, then build the spec described in [spec-format.md](spec-format.md) using only dimensions present in the project's `discover` output. Never invent a dimension a blueprint calls for but `discover` doesn't have — skip that panel and tell the user (see the Rules section in [../SKILL.md](../SKILL.md)).

## `overview`

**When:** A general "build me a dashboard for this project" request with no specific angle.

**Base:** `createDashboardFromTemplate` with `template: generativeLlmModelV2` — Arize's own "Tracing Project Overview" template. This gives the dashboard the standard set of tracing panels (volume, latency, span counts, etc.) without the skill having to reconstruct them from discovery.

**Augmentation:** Add one `statistic` widget per eval in `discover`'s `llmEvals`, setting `aggregation: "avg"` explicitly (the script's `aggregation` default is `"count"` — see [spec-format.md](spec-format.md) — which would silently ship a *count* widget mislabeled as an eval score if you omit it) so the user sees eval performance alongside the template's tracing panels.

**Placement:** Because a template-created dashboard's own widget layout isn't fully known to this skill (see the template-widget-IDs note in [graphql.md](graphql.md)), omit `row`/`col`/`width`/`height` on the augmenting statistics so the backend auto-places them instead of risking a collision with the template's widgets.

## `cost-latency`

**When:** The user asks specifically about token usage, cost, or latency.

**Base:** `createDashboardFromTemplate` with `template: generativeLlmModel` — Arize's "Token Tracking and Latency" template, which already covers token counts and latency distributions.

**Augmentation:** Add a `statistic` widget (`aggregation: "avg"`, explicit — see the `overview` note above on why the default is wrong here) per relevant discovered eval from `llmEvals`, again with no `row`/`col`/`width`/`height` so it auto-places. **Do not augment from `customMetrics`** — despite a metric's name suggesting "cost per call," a `customMetrics` entry is not usable as a widget `dimension`, and `dashboard.py` does not wire the separate field custom metrics actually require. See the "Custom metrics are not widget dimensions" limitation in [graphql.md](graphql.md) before reaching for one. If the user specifically wants a cost metric surfaced and it isn't already on the `generativeLlmModel` template, tell them this script can't build that panel yet rather than guessing at a spec that will fail on `apply`.

**Why augment at all:** The template covers the generic case; the augmentation is what makes the dashboard specific to *this* project's actual evals rather than a stock page.

## `eval-health`

**When:** The user asks about eval scores, quality trends, or "how are my evals doing."

**Base:** None — **no Arize template exists for this.** This is the blueprint where discovery earns its keep: every panel is composed directly from `discover`'s `llmEvals` list, so the dashboard only ever shows evals this project actually runs.

**Panels, in order:**
1. A full-width `text` widget as a header (e.g. `## Eval Health`), placed first so the dashboard reads top-to-bottom.
2. For **each** discovered eval:
   - A `lineChart` widget plotting that eval's score over time (`dimensionCategory: "llmEval"`, `metric` appropriate to the eval's `dataType` — `avg` for a numeric/continuous score).
   - A `statistic` widget summarizing that eval (e.g. `aggregation: "avg"` for a mean score, or `"count"` for a categorical eval).
   - A label-distribution panel — a third `statistic` widget, e.g. `aggregation: "cardinality"` for how many distinct labels appear, so the user sees the shape of the results alongside the average, not just a single number twice. This is a `statistic`, not a histogram or breakdown-by-label chart: `barChart` and `pivotTable` would render that better, but neither is wired into `dashboard.py` (see [graphql.md](graphql.md)) — don't reach for them here.

**If `discover` returns no `llmEvals`:** There is nothing to build. Tell the user the project has no evals yet and hand off to **arize-evaluator** to create one, rather than emitting an empty or templated eval dashboard.

## `custom`

**When:** The user states a specific goal that doesn't match `overview`, `cost-latency`, or `eval-health` — e.g. "show me span properties broken down by customer tier" or "I want a dashboard just for the hallucination eval and nothing else."

**Base:** None by default — compose from `createDashboard` (plain, unNamed-template dashboard) unless the user's goal maps cleanly onto one of Arize's other templates (e.g. `regression`, `ranking`, `multiclass` — out of scope for this skill's other blueprints, but reachable here if you pass that template name explicitly in `dashboard.template`).

**Composition:** Take the user's stated goal, map it onto the dimensions `discover` actually returned (`spanProperties`, `llmEvals`, `annotations`), and build only the widgets that goal calls for. `customMetrics` entries are informational only — `discover` returns them so you and the user can see what exists, but `dashboard.py` cannot build a widget from one directly (see [graphql.md](graphql.md)); if the goal needs a custom metric surfaced, say so and stop rather than guessing a spec that will fail on `apply`. Confirm the resulting widget list with the user before applying if the goal was ambiguous — do not pad it out with panels they didn't ask for.
