# Blueprint catalog

A blueprint is this skill's opinion about which widgets a spec should contain for a given request. Pick one, then build the spec described in [spec-format.md](spec-format.md) using only dimensions present in the project's `discover` output. Never invent a dimension a blueprint calls for but `discover` doesn't have — skip that panel and tell the user (see the Rules section in [../SKILL.md](../SKILL.md)).

## Before any blueprint: three rules every one of them depends on

### 1. Group `llmEvals` by eval name — it holds one entry per *field*, not per eval

`discover`'s `llmEvals` returns one entry per eval **dimension**, and Arize stores each eval as 2-4 separate dimensions named `<prefix>.<eval name>.<field>` — prefix `eval` (span), `trace_eval`, or `session_eval`; field `label`, `score`, `explanation`, or `metadata`. Full detail in [graphql.md](graphql.md).

A project with five evals therefore commonly returns 10-20 `llmEvals` entries. **Emitting one panel per entry silently ruins the dashboard**: you get duplicate tiles and blank ones (an `avg` over an `explanation` dimension is free text), and nothing anywhere complains — `validate_spec` passes, `--dry-run` is clean, and `verify` reports every title matching.

So before writing any widget, do this:

1. Parse each entry's `name` as `<prefix>.<eval name>.<field>`. Ignore any entry whose name doesn't have that shape.
2. Group the entries by eval name, keeping the prefix with the group — `eval.hallucination` and `trace_eval.hallucination` are different scopes. Prefer the span-scoped `eval.` set unless the user asked about traces or sessions.
3. Within a group, select the dimension by field:
   - `.score` → line charts and numeric statistics
   - `.label` → distribution and cardinality statistics
   - `.explanation`, `.metadata` → **ignore entirely.** Never build a widget from either.
4. If a group has no `.score` entry, it is a label-only eval: build its label panel, skip the numeric one, and record the skip in the spec's `skipped` array.

**Panel count follows the number of distinct eval names, not `len(llmEvals)`.** When you tell the user what you are about to build, say "5 evals → 5 statistics", not "17 eval dimensions → 17 statistics". If those two numbers disagree, you grouped wrong.

### 2. Choose the aggregation from the dimension's `dataType`

`avg`, `sum`, `standardDeviation`, `p50`, `p95`, `p99`, and `p99_9` are **numeric-only** in Arize, but the GraphQL enum does not enforce that. Pairing one with a STRING dimension is accepted by the API, reported as success by `apply`, confirmed by `verify` — and renders `n/a` in the UI forever.

| `dimension.dataType` | Use |
|---|---|
| FLOAT / DOUBLE / LONG / INT — e.g. `eval.<name>.score` | `avg`, `sum`, `p50`, `p95`, `p99` (and `count`/`cardinality` if you want them) |
| STRING — e.g. `eval.<name>.label`, most span properties | `count`, `cardinality`, `percentEmpty` |

Read `dataType` off the `discover` entry you are about to copy into the widget's `dimension` field. Never assume it, and never hardcode `avg`.

### 3. Templated dashboards take no placement — and no text widgets

`validate_spec()` **rejects** a spec whose `dashboard.template` is set if any widget carries `row`/`col`/`width`/`height`, or if any widget is a `text` widget. This is enforcement, not advice: see the template-widget-IDs assumption in [graphql.md](graphql.md) for why placement on a templated dashboard is unsafe, and the `gridPosition` section there for why a text widget can never be auto-placed. Augment a templated dashboard with unplaced `statistic` and `lineChart` widgets only.

## `overview`

**When:** A general "build me a dashboard for this project" request with no specific angle.

**Base:** `createDashboardFromTemplate` with `template: generativeLlmModelV2` — Arize's own "Tracing Project Overview" template. This gives the dashboard the standard set of tracing panels (volume, latency, span counts, etc.) without the skill having to reconstruct them from discovery. `dashboard.py` sends `modelEnvironmentName: "tracing"` on the template input so the template's panels query the same environment the widgets do.

**Augmentation:** **one `statistic` widget per distinct eval name** (rule 1 — not one per `llmEvals` entry), so the user sees this project's eval performance alongside the template's generic tracing panels:

- If the eval group has a `.score` dimension, build the statistic on it with `aggregation: "avg"`.
- If it has only a `.label` dimension, build the statistic on that with `aggregation: "count"`. **Do not put `avg` on a STRING label dimension** (rule 2) — it renders `n/a`.

Always set `aggregation` explicitly: the script's default is `"count"` (see [spec-format.md](spec-format.md)), which would ship a *count* widget mislabeled as an eval score if you omit it.

`overview` is a summary — one tile per eval name, not a panel set per eval name. If the user wants depth on the evals themselves, that is `eval-health`.

**Placement:** Omit `row`/`col`/`width`/`height` on every augmenting widget (rule 3). A spec that sets them is rejected with `SpecError`.

## `cost-latency`

**When:** The user asks specifically about token usage, cost, or latency.

**Base:** `createDashboardFromTemplate` with `template: generativeLlmModel` — Arize's "Token Tracking and Latency" template, which already covers token counts and latency distributions.

**Augmentation:** One `statistic` widget per distinct eval name that is relevant to the user's question, built exactly as in `overview`: `.score` dimension with `aggregation: "avg"` where one exists, otherwise the `.label` dimension with `aggregation: "count"`. Omit placement (rule 3).

**Do not augment from `customMetrics`** — despite a metric's name suggesting "cost per call," a `customMetrics` entry is not usable as a widget `dimension`, and `dashboard.py` does not wire the separate field custom metrics actually require. See the "Custom metrics are not widget dimensions" limitation in [graphql.md](graphql.md) before reaching for one. If the user specifically wants a cost metric surfaced and it isn't already on the `generativeLlmModel` template, tell them this script can't build that panel yet rather than guessing at a spec that will fail on `apply`.

**Why augment at all:** The template covers the generic case; the augmentation is what makes the dashboard specific to *this* project's actual evals rather than a stock page.

## `eval-health`

**When:** The user asks about eval scores, quality trends, or "how are my evals doing."

**Base:** None — **no Arize template exists for this.** This is the blueprint where discovery earns its keep: every panel is composed directly from `discover`'s `llmEvals` list, so the dashboard only ever shows evals this project actually runs. Because there is no template, placement *is* allowed here — lay the panels out explicitly.

**Panels, in order:**

1. A full-width `text` widget as a header (e.g. `## Eval Health`), placed first so the dashboard reads top-to-bottom. Place it explicitly at `row: 1, col: 1, width: 12, height: 2`; a text widget is never auto-placed, so leaving it out just pins it to that band anyway — and `validate_spec` will then catch it overlapping whatever else you put at row 1.
2. For **each distinct eval name** (rule 1 — three panels per eval *name*, never per `llmEvals` entry):
   - A `lineChart` plotting that eval's **`.score`** dimension over time, `dimensionCategory: "llmEval"`, `metric: "avg"`. `.score` is numeric, so `avg` is valid here (rule 2).
   - A `statistic` on the same **`.score`** dimension with `aggregation: "avg"` — the eval's mean score.
   - A label-distribution panel: a `statistic` on that eval's **`.label`** dimension with `aggregation: "cardinality"`, so the user sees how many distinct labels appear alongside the average rather than the same number twice. `cardinality` is valid on STRING; `avg` is not. This is a `statistic`, not a histogram or breakdown-by-label chart: `barChart` and `pivotTable` would render that better, but neither is wired into `dashboard.py` (see [graphql.md](graphql.md)) — don't reach for them here.

   If a group has no `.score`, build only the label panel and record the two skipped panels. If it has no `.label`, build only the score panels and record the skip.

**A worked three-eval example:** 3 eval names → 1 header + 3 × 3 panels = 10 widgets, regardless of whether `llmEvals` came back with 6 entries or 12.

**If `discover` returns no `llmEvals`:** There is nothing to build. Tell the user the project has no evals yet and hand off to **arize-evaluator** to create one, rather than emitting an empty or templated eval dashboard.

## `custom`

**When:** The user states a specific goal that doesn't match `overview`, `cost-latency`, or `eval-health` — e.g. "show me span properties broken down by customer tier" or "I want a dashboard just for the hallucination eval and nothing else."

**Base:** None by default — compose from `createDashboard` (plain, no template) unless the user's goal maps cleanly onto one of Arize's other templates. The real `DashboardTemplates` values are `generativeLlmModelV2`, `generativeLlmModel`, `regression`, `rankingModel`, and `multiClassModel`; the last three are out of scope for this skill's other blueprints but reachable here if you pass the name exactly as spelled in `dashboard.template`. Note that setting `dashboard.template` puts the spec under rule 3 — no placement, no text widgets.

**Composition:** Take the user's stated goal, map it onto the dimensions `discover` actually returned (`spanProperties`, `llmEvals`, `annotations`), and build only the widgets that goal calls for — grouping evals by name (rule 1) and matching each aggregation to its dimension's `dataType` (rule 2) exactly as the other blueprints do. `customMetrics` entries are informational only — `discover` returns them so you and the user can see what exists, but `dashboard.py` cannot build a widget from one directly (see [graphql.md](graphql.md)); if the goal needs a custom metric surfaced, say so and stop rather than guessing a spec that will fail on `apply`. Confirm the resulting widget list with the user before applying if the goal was ambiguous — do not pad it out with panels they didn't ask for.
