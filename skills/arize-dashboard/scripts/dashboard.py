#!/usr/bin/env python3
"""Build populated Arize dashboards from a declarative spec via the programmatic GraphQL API."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

SAAS_API_HOST = "api.arize.com"
SAAS_APP_HOST = "app.arize.com"


class DashboardError(Exception):
    pass


class ConfigError(DashboardError):
    pass


class GraphQLError(DashboardError):
    pass


class LayoutError(DashboardError):
    pass


def active_profile_name(home, profile=None, environ=None):
    environ = os.environ if environ is None else environ
    if profile:
        return profile
    if environ.get("ARIZE_PROFILE"):
        return environ["ARIZE_PROFILE"]
    marker = Path(home) / ".active_profile"
    if marker.exists():
        name = marker.read_text().strip()
        if name:
            return name
    return "default"


def _profile_name_is_explicit(home, profile, environ):
    """Check if the profile name came from an explicit source (not terminal default)."""
    if profile:
        return True
    if environ.get("ARIZE_PROFILE"):
        return True
    marker = Path(home) / ".active_profile"
    if marker.exists():
        name = marker.read_text().strip()
        if name:
            return True
    return False


def load_profile(home, profile=None, environ=None):
    environ = os.environ if environ is None else environ
    home = Path(home)
    name = active_profile_name(home, profile, environ)
    is_explicit = _profile_name_is_explicit(home, profile, environ)
    path = home / "profiles" / f"{name}.toml"
    if not path.exists():
        # If the name came from an explicit source, don't fall back to config.toml
        if is_explicit:
            raise ConfigError(
                f"Profile '{name}' not found at {path}. Run 'ax profiles list' to see available profiles."
            )
        # Only fall back to config.toml for terminal defaults
        path = home / "config.toml"
    if not path.exists():
        raise ConfigError(
            f"No Arize profile named '{name}' under {home}. Run 'ax profiles list' to see available profiles."
        )
    data = tomllib.loads(path.read_text())
    routing = data.get("routing", {})
    api_host = routing.get("api_host", "")
    app_host = environ.get("ARIZE_APP_HOST") or routing.get("app_host")
    if not app_host:
        if api_host == SAAS_API_HOST:
            app_host = SAAS_APP_HOST
        else:
            raise ConfigError(
                f"Profile '{name}' has no routing.app_host and api_host is '{api_host}', "
                "so the app URL cannot be inferred. Set app_host in the profile or pass --app-host."
            )
    api_key = environ.get("ARIZE_API_KEY") or data.get("auth", {}).get("api_key")
    if not api_key:
        raise ConfigError(f"Profile '{name}' has no auth.api_key and ARIZE_API_KEY is unset.")
    return {
        "name": name,
        "api_key": api_key,
        "app_host": app_host,
        "app_scheme": environ.get("ARIZE_APP_SCHEME") or routing.get("app_scheme", "https"),
    }


def graphql_endpoint(cfg):
    return f"{cfg['app_scheme']}://{cfg['app_host']}/graphql"


class Client:
    def __init__(self, endpoint, api_key, http=None):
        self.endpoint = endpoint
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=60.0)

    def execute(self, query, variables=None, context="GraphQL request"):
        response = self._http.post(
            self.endpoint,
            json={"query": query, "variables": variables or {}},
            headers={"authorization": f"Bearer {self._api_key}"},
        )
        if response.status_code != 200:
            raise GraphQLError(f"{context} returned HTTP {response.status_code}; check credentials and endpoint.")
        body = response.json()
        if body.get("errors"):
            joined = "; ".join(e.get("message", "unknown error") for e in body["errors"])
            raise GraphQLError(f"{context} failed: {joined}")
        return body.get("data", {})


GRID_COLUMNS = 12


def to_grid_position(row, col, width, height):
    """Convert natural 1-indexed placement to Arize's [rowStart, colStart, rowEnd, colEnd].

    Arize reads gridPosition as [rowStart, colStart, rowEnd, colEnd] on a
    12-column grid, NOT [x, y, w, h]. Passing [x, y, w, h] renders widgets as
    tall narrow columns and makes data widgets disappear.
    """
    return [row, col, row + height, col + width]


def _placed(widget):
    return all(widget.get(k) is not None for k in ("row", "col", "width", "height"))


def validate_layout(widgets):
    boxes = []
    for widget in widgets:
        if not _placed(widget):
            continue  # left to the backend's next-available-slot placement
        title = widget.get("title", "<untitled>")
        row, col = widget["row"], widget["col"]
        width, height = widget["width"], widget["height"]
        if width <= 0 or height <= 0:
            raise LayoutError(f"Widget '{title}' must have positive width and height; got {width}x{height}.")
        if row < 1 or col < 1:
            raise LayoutError(f"Widget '{title}' row and col are 1-indexed; got row={row}, col={col}.")
        if col + width > GRID_COLUMNS + 1:
            raise LayoutError(
                f"Widget '{title}' exceeds the {GRID_COLUMNS}-column grid: col={col} + width={width} > {GRID_COLUMNS + 1}."
            )
        boxes.append((title, row, col, row + height, col + width))
    for i, (title_a, r1, c1, r2, c2) in enumerate(boxes):
        for title_b, r3, c3, r4, c4 in boxes[i + 1:]:
            if r1 < r4 and r3 < r2 and c1 < c4 and c3 < c2:
                raise LayoutError(f"Widgets '{title_a}' and '{title_b}' overlap on the grid.")


DISCOVER_QUERY = """
query Discover($projectId: ID!, $start: DateTime, $end: DateTime) {
  node(id: $projectId) {
    ... on Model {
      id
      name
      tracingSchema(startTime: $start, endTime: $end) {
        spanProperties(first: 200) { edges { node { dimension { id name dataType category } } } }
        llmEvals(first: 100)       { edges { node { dimension { id name dataType category } } } }
        annotations(first: 100)    { edges { node { dimension { id name dataType category } } } }
      }
      customMetrics(first: 50) { edges { node { id name } } }
    }
  }
}
"""


def _dimensions(connection):
    if not connection:
        return []
    out = []
    for edge in connection.get("edges") or []:
        dim = ((edge or {}).get("node") or {}).get("dimension")
        if dim:
            out.append({k: dim.get(k) for k in ("id", "name", "dataType", "category")})
    return out


def discover(client, project_id, days=30, now=None):
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    data = client.execute(
        DISCOVER_QUERY,
        {"projectId": project_id, "start": start.isoformat(), "end": end.isoformat()},
        context="Project discovery",
    )
    node = data.get("node")
    if not node:
        raise DashboardError(
            f"ID '{project_id}' is not a project, or is not visible with this API key. "
            "Project IDs are base64 — copy it from the Arize URL."
        )
    schema = node.get("tracingSchema") or {}
    metrics = node.get("customMetrics") or {}
    return {
        "project": {"id": node.get("id"), "name": node.get("name")},
        "spanProperties": _dimensions(schema.get("spanProperties")),
        "llmEvals": _dimensions(schema.get("llmEvals")),
        "annotations": _dimensions(schema.get("annotations")),
        "customMetrics": [
            {"id": e["node"]["id"], "name": e["node"]["name"]}
            for e in (metrics.get("edges") or [])
            if e and e.get("node")
        ],
    }


WIDGET_TYPES = ("text", "statistic", "lineChart")

CREATE_TEXT_WIDGET = """
mutation CreateTextWidget($input: CreateTextWidgetMutationInput!) {
  createTextWidget(input: $input) { textWidget { id title } }
}
"""

CREATE_STATISTIC_WIDGET = """
mutation CreateStatisticWidget($input: CreateStatisticWidgetMutationInput!) {
  createStatisticWidget(input: $input) { statisticWidget { id title } }
}
"""

CREATE_LINE_CHART_WIDGET = """
mutation CreateLineChartWidget($input: CreateLineChartWidgetMutationInput!) {
  createLineChartWidget(input: $input) { lineChartWidget { id title } }
}
"""


class SpecError(DashboardError):
    pass


def validate_spec(spec):
    meta = spec.get("dashboard") or {}
    for field in ("name", "projectId", "spaceId"):
        if not meta.get(field):
            raise SpecError(f"spec.dashboard.{field} is required.")
    widgets = spec.get("widgets") or []
    for widget in widgets:
        title = widget.get("title", "<untitled>")
        kind = widget.get("type")
        if kind not in WIDGET_TYPES:
            raise SpecError(f"Widget '{title}' has unsupported type '{kind}'. Supported: {', '.join(WIDGET_TYPES)}.")
        if not widget.get("title"):
            raise SpecError("Every widget needs a title.")
        if kind == "text" and not widget.get("content"):
            raise SpecError(f"Text widget '{title}' requires content.")
        if kind in ("statistic", "lineChart"):
            if not widget.get("dimension"):
                raise SpecError(f"Widget '{title}' requires a dimension from discovery output.")
            if not widget.get("dimensionCategory"):
                raise SpecError(f"Widget '{title}' requires a dimensionCategory.")
    validate_layout(widgets)


def _grid(widget):
    if not _placed(widget):
        return None
    return to_grid_position(widget["row"], widget["col"], widget["width"], widget["height"])


def widget_mutation(widget, dashboard_id, project_id):
    kind = widget["type"]
    grid = _grid(widget)
    payload = {"dashboardId": dashboard_id, "title": widget["title"], "creationStatus": "published"}
    if kind == "text":
        # createTextWidget requires gridPosition; fall back to a full-width band.
        payload["content"] = widget["content"]
        payload["gridPosition"] = grid or to_grid_position(1, 1, GRID_COLUMNS, 2)
        return CREATE_TEXT_WIDGET, {"input": payload}

    payload["modelId"] = project_id
    payload["modelEnvironmentName"] = widget.get("modelEnvironmentName", "tracing")
    payload["dimension"] = widget["dimension"]
    payload["dimensionCategory"] = widget["dimensionCategory"]
    payload["timeSeriesMetricType"] = widget.get("timeSeriesMetricType", "modelDataMetric")
    if grid:
        payload["gridPosition"] = grid

    if kind == "statistic":
        payload["aggregation"] = widget.get("aggregation", "count")
        return CREATE_STATISTIC_WIDGET, {"input": payload}
    elif kind == "lineChart":
        plot = {
            "modelId": project_id,
            "modelVersionIds": [],
            "modelEnvironmentName": payload["modelEnvironmentName"],
            "dimension": widget["dimension"],
            "dimensionCategory": widget["dimensionCategory"],
            "metric": widget.get("metric", "count"),
            "title": widget["title"],
            "position": 0,
            "filters": [],
        }
        line = {k: payload[k] for k in ("dashboardId", "title", "creationStatus", "timeSeriesMetricType")}
        if grid:
            line["gridPosition"] = grid
        line["plots"] = [plot]
        return CREATE_LINE_CHART_WIDGET, {"input": line}
    else:
        raise SpecError(f"Widget '{widget.get('title', '<untitled>')}' has unsupported type '{kind}'. Supported: {', '.join(WIDGET_TYPES)}.")


CREATE_DASHBOARD = """
mutation CreateDashboard($input: CreateDashboardMutationInput!) {
  createDashboard(input: $input) { dashboard { id name } }
}
"""

CREATE_DASHBOARD_FROM_TEMPLATE = """
mutation CreateDashboardFromTemplate($input: CreateDashboardFromTemplateMutationInput!) {
  createDashboardFromTemplate(input: $input) { dashboard { id name } }
}
"""

VERIFY_QUERY = """
query VerifyDashboard($id: ID!) {
  node(id: $id) {
    ... on Dashboard {
      id
      name
      statisticWidgets(first: 100) { edges { node { title } } }
      textWidgets(first: 100)      { edges { node { title } } }
      lineChartWidgets(first: 100) { edges { node { title } } }
    }
  }
}
"""


def dashboard_url(cfg, org_id, space_id, dashboard_id):
    # NOTE: This URL path is unverified against a live Arize app and flagged as a follow-up.
    return (
        f"{cfg['app_scheme']}://{cfg['app_host']}"
        f"/organizations/{org_id}/spaces/{space_id}/dashboards/{dashboard_id}"
    )


def apply(client, spec, dry_run=False):
    validate_spec(spec)
    meta = spec["dashboard"]
    widgets = spec.get("widgets") or []
    if dry_run:
        return {
            "dashboardId": None,
            "created": [w["title"] for w in widgets],
            "skipped": spec.get("skipped", []),
            "dryRun": True,
        }
    if meta.get("template"):
        query, variables = CREATE_DASHBOARD_FROM_TEMPLATE, {
            "input": {"name": meta["name"], "modelId": meta["projectId"], "template": meta["template"]}
        }
        key = "createDashboardFromTemplate"
    else:
        query, variables = CREATE_DASHBOARD, {
            "input": {"name": meta["name"], "spaceId": meta["spaceId"]}
        }
        key = "createDashboard"
    data = client.execute(query, variables, context="Dashboard creation")
    dashboard_id = data[key]["dashboard"]["id"]

    created = []
    for widget in widgets:
        wq, wv = widget_mutation(widget, dashboard_id, meta["projectId"])
        client.execute(wq, wv, context=f"Creating widget '{widget['title']}'")
        created.append(widget["title"])
    return {
        "dashboardId": dashboard_id,
        "created": created,
        "skipped": spec.get("skipped", []),
        "dryRun": False,
    }


def verify(client, dashboard_id):
    data = client.execute(VERIFY_QUERY, {"id": dashboard_id}, context="Dashboard verification")
    node = data.get("node")
    if not node:
        raise DashboardError(f"Dashboard '{dashboard_id}' not found.")
    titles = []
    for field in ("statisticWidgets", "textWidgets", "lineChartWidgets"):
        for edge in (node.get(field) or {}).get("edges") or []:
            titles.append(edge["node"]["title"])
    return {"id": node["id"], "name": node.get("name"), "widgetTitles": titles}
