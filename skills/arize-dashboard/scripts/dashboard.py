#!/usr/bin/env python3
"""Build populated Arize dashboards from a declarative spec via the programmatic GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from collections import Counter
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


def load_profile(home, profile=None, environ=None, app_host=None):
    """Resolve credentials and the app endpoint.

    app_host precedence: the --app-host flag, then ARIZE_APP_HOST, then the
    profile's routing.app_host, then the SaaS default (only when api_host is
    the SaaS host).
    """
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
    app_host = app_host or environ.get("ARIZE_APP_HOST") or routing.get("app_host")
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
        _, _, row_end, col_end = to_grid_position(row, col, width, height)
        boxes.append((title, row, col, row_end, col_end))
    for i, (title_a, r1, c1, r2, c2) in enumerate(boxes):
        for title_b, r3, c3, r4, c4 in boxes[i + 1:]:
            if r1 < r4 and r3 < r2 and c1 < c4 and c3 < c2:
                raise LayoutError(f"Widgets '{title_a}' and '{title_b}' overlap on the grid.")


TEXT_FALLBACK = {"row": 1, "col": 1, "width": GRID_COLUMNS, "height": 2}

PLACEMENT_FIELDS = ("row", "col", "width", "height")


def has_placement(widget):
    """True if the widget carries any explicit placement field."""
    return any(widget.get(k) is not None for k in PLACEMENT_FIELDS)


def resolve_text_placement(widgets):
    """Materialize the text-widget placement fallback *before* layout validation.

    createTextWidget requires gridPosition, so an unplaced text widget is never
    auto-placed by the backend: widget_mutation pins it to the full-width band
    at row 1. Writing that fallback onto the widget here means the box takes
    part in overlap detection and shows up in --dry-run output, instead of
    silently landing on top of whatever else already claims row 1.
    """
    for widget in widgets:
        if widget.get("type") == "text" and not _placed(widget):
            widget.update(TEXT_FALLBACK)


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


def _reject_unsafe_placement_on_template(widget, title, kind, template):
    """Refuse the two ways a widget can silently overlap a template's own widgets.

    Whether createDashboardFromTemplate reports the positions of the widgets it
    creates is an unverified assumption (see references/graphql.md), so this
    script cannot route around the template layout. Until that is confirmed
    against a live app, the only safe augmentation is a statistic or lineChart
    with no placement at all, which the backend places in the next free slot.
    """
    if kind == "text":
        raise SpecError(
            f"Widget '{title}' is a text widget on a dashboard created from template "
            f"'{template}'. createTextWidget requires a gridPosition, so the backend cannot "
            "auto-place it and it would be pinned over the template's own top-row widgets. "
            "Add text widgets only to a dashboard built without a template."
        )
    if has_placement(widget):
        raise SpecError(
            f"Widget '{title}' sets explicit placement (row/col/width/height) on a dashboard "
            f"created from template '{template}'. This script cannot see where the template's "
            "own widgets sit, so explicit placement here can silently overlap them. Omit "
            "row/col/width/height on every widget added to a templated dashboard and the "
            "backend auto-places them in free slots."
        )


def validate_spec(spec):
    meta = spec.get("dashboard") or {}
    for field in ("name", "projectId", "spaceId"):
        if not meta.get(field):
            raise SpecError(f"spec.dashboard.{field} is required.")
    widgets = spec.get("widgets") or []
    template = meta.get("template")
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
        if template:
            _reject_unsafe_placement_on_template(widget, title, kind, template)
    resolve_text_placement(widgets)
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
        # createTextWidget requires gridPosition. validate_spec() normally writes
        # this fallback onto the widget first (resolve_text_placement) so it is
        # visible to the layout check; this keeps direct callers safe too.
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


def load_spec(path):
    """Read and parse a spec file, turning I/O and JSON failures into SpecError.

    main() only catches DashboardError, so a bare read/parse here would print a
    traceback for the most common first mistake: a mistyped --spec path.
    """
    spec_path = Path(path).expanduser()
    try:
        raw = spec_path.read_text()
    except OSError as error:
        raise SpecError(f"Cannot read spec file '{spec_path}': {error.strerror}.") from error
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SpecError(
            f"Spec file '{spec_path}' is not valid JSON: {error.msg} "
            f"(line {error.lineno}, column {error.colno})."
        ) from error
    if not isinstance(parsed, dict):
        raise SpecError(f"Spec file '{spec_path}' must contain a JSON object with 'dashboard' and 'widgets'.")
    return parsed


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


def _title_diff(expected, actual):
    """Spec titles that did not come back from the dashboard read (multiset-aware)."""
    remaining = Counter(actual)
    missing = []
    for title in expected:
        if remaining.get(title, 0) > 0:
            remaining[title] -= 1
        else:
            missing.append(title)
    return missing


def _verification(client, dashboard_id, expected_titles):
    """Read the dashboard back and report which spec titles did not land.

    Three outcomes, reported in `verification`: "verified" (every spec title is
    on the dashboard), "missingWidgets" (a mutation was accepted but produced
    nothing), "notCompleted" (the read-back itself failed, so nothing is known
    either way).

    Extra titles are expected and not an error: a templated dashboard carries
    the template's own widgets too.

    This is the one call in the script that happens AFTER a write, so it also
    catches httpx.HTTPError — transport failures (ConnectError, ReadTimeout)
    are not DashboardError and would otherwise escape apply() with the new
    dashboard's id still unprinted. There is no deleteDashboard mutation in
    this API, so a dashboard whose id the user never saw is an orphan they
    cannot find or remove. A failed read-back degrades to "created but
    unverified"; it never costs the handle.
    """
    try:
        seen = verify(client, dashboard_id)
    except (DashboardError, httpx.HTTPError) as error:
        return {
            "verified": False,
            "verification": "notCompleted",
            "verifyError": f"{type(error).__name__}: {error}" if isinstance(error, httpx.HTTPError) else str(error),
            "missingTitles": None,
        }
    missing = _title_diff(expected_titles, seen["widgetTitles"])
    return {
        "verified": not missing,
        "verification": "missingWidgets" if missing else "verified",
        "missingTitles": missing,
        "dashboardWidgetTitles": seen["widgetTitles"],
    }


LINK_HINT = (
    "Pass --org ORG_ID (the organization's base64 id) to print a deep link, or hand the "
    "dashboard id to the arize-link skill. This script never guesses an organization id."
)


def _link(cfg, org_id, space_id, dashboard_id):
    if cfg and org_id and space_id:
        return {"url": dashboard_url(cfg, org_id, space_id, dashboard_id)}
    return {"url": None, "urlHint": LINK_HINT}


def apply(client, spec, dry_run=False, cfg=None, org_id=None):
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
        # modelEnvironmentName must be sent explicitly: older server builds fall
        # through to "production" when it is omitted, which would leave every
        # template panel querying an environment that has no tracing data.
        query, variables = CREATE_DASHBOARD_FROM_TEMPLATE, {
            "input": {
                "name": meta["name"],
                "modelId": meta["projectId"],
                "template": meta["template"],
                "modelEnvironmentName": meta.get("modelEnvironmentName", "tracing"),
            }
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
    result = {
        "dashboardId": dashboard_id,
        "created": created,
        "skipped": spec.get("skipped", []),
        "dryRun": False,
    }
    result.update(_verification(client, dashboard_id, created))
    result.update(_link(cfg, org_id, meta.get("spaceId"), dashboard_id))
    return result


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


LIST_QUERY = """
query ListDashboards($id: ID!, $first: Int!) {
  node(id: $id) {
    ... on Space {
      dashboards(first: $first) { edges { node { id name status } } }
    }
  }
}
"""

UPDATE_STATUS = """
mutation UpdateDashboardStatus($input: UpdateDashboardStatusMutationInput!) {
  updateDashboardStatus(input: $input) { dashboard { id status } }
}
"""


def list_dashboards(client, space_id, first=50):
    data = client.execute(LIST_QUERY, {"id": space_id, "first": first}, context="Listing dashboards")
    node = data.get("node")
    if not node:
        raise DashboardError(f"ID '{space_id}' is not a space, or is not visible with this API key.")
    return [e["node"] for e in (node.get("dashboards") or {}).get("edges") or []]


def delete_dashboard(client, dashboard_id):
    # There is no deleteDashboard mutation; removal is a status change.
    return client.execute(
        UPDATE_STATUS,
        {"input": {"dashboardId": dashboard_id, "status": "deleted"}},
        context="Deleting dashboard",
    )


def _client_for(args):
    cfg = load_profile(Path(args.home).expanduser(), profile=args.profile, app_host=args.app_host)
    return cfg, Client(graphql_endpoint(cfg), cfg["api_key"])


def main(argv=None):
    # --home/--profile live on a parent parser so they are accepted both before
    # and after the subcommand ("dashboard.py discover --profile x" works).
    # SUPPRESS keeps the subparser's copy from clobbering a value given before
    # the subcommand; defaults are applied after parsing instead.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", default=argparse.SUPPRESS, help="Arize config directory")
    common.add_argument("--profile", default=argparse.SUPPRESS,
                        help="ax profile name (default: the active profile)")
    common.add_argument("--app-host", default=argparse.SUPPRESS,
                        help="Override the app host (e.g. arize-app.example.com) for on-prem "
                             "deployments whose profile has no routing.app_host")

    parser = argparse.ArgumentParser(
        description="Build Arize dashboards from a declarative spec.", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", parents=[common],
                                help="List a project's span properties, evals, and annotations")
    p_discover.add_argument("--project", required=True)
    p_discover.add_argument("--days", type=int, default=30)

    p_apply = sub.add_parser("apply", parents=[common], help="Create a dashboard from a spec file")
    p_apply.add_argument("--spec", required=True)
    p_apply.add_argument("--dry-run", action="store_true")
    p_apply.add_argument("--org", help="Organization base64 id; when given, print the dashboard deep link")

    p_verify = sub.add_parser("verify", parents=[common], help="Read back a dashboard's widgets")
    p_verify.add_argument("--dashboard", required=True)
    p_verify.add_argument("--org", help="Organization base64 id; with --space, print the dashboard deep link")
    p_verify.add_argument("--space", help="Space base64 id; needed alongside --org to build a link")

    p_list = sub.add_parser("list", parents=[common], help="List dashboards in a space")
    p_list.add_argument("--space", required=True)

    p_delete = sub.add_parser("delete", parents=[common], help="Soft-delete a dashboard")
    p_delete.add_argument("--dashboard", required=True)
    p_delete.add_argument("--confirm", action="store_true")

    args = parser.parse_args(argv)
    args.home = getattr(args, "home", "~/.arize")
    args.profile = getattr(args, "profile", None)
    args.app_host = getattr(args, "app_host", None)
    try:
        if args.command == "delete" and not args.confirm:
            print("Refusing to delete without --confirm. This sets the dashboard's "
                  "status to 'deleted' and there is no undo via this API.", file=sys.stderr)
            return 2
        if args.command == "apply":
            spec = load_spec(args.spec)
            if args.dry_run:
                validate_spec(spec)
                for widget in spec.get("widgets") or []:
                    grid = _grid(widget)
                    print(f"{widget['title']}: gridPosition={grid or '<auto>'}")
                print(json.dumps(apply(None, spec, dry_run=True), indent=2))
                return 0

        cfg, client = _client_for(args)

        if args.command == "discover":
            print(json.dumps(discover(client, args.project, days=args.days), indent=2))
        elif args.command == "apply":
            result = apply(client, spec, cfg=cfg, org_id=args.org)
            print(json.dumps(result, indent=2))
            if result.get("verifyError"):
                print("Could not verify the dashboard after creating it: "
                      f"{result['verifyError']}", file=sys.stderr)
                return 1
            if result.get("missingTitles"):
                print("These widgets are not on the dashboard after apply: "
                      + ", ".join(result["missingTitles"])
                      + ". The dashboard was created but is incomplete.", file=sys.stderr)
                return 1
        elif args.command == "verify":
            if args.org and not args.space:
                raise DashboardError(
                    "--org needs --space to build a dashboard link; the path is "
                    "/organizations/<org>/spaces/<space>/dashboards/<id>. Pass --space SPACE_ID, "
                    "or drop --org and use the arize-link skill."
                )
            result = verify(client, args.dashboard)
            result.update(_link(cfg, args.org, args.space, args.dashboard))
            print(json.dumps(result, indent=2))
        elif args.command == "list":
            print(json.dumps(list_dashboards(client, args.space), indent=2))
        elif args.command == "delete":
            delete_dashboard(client, args.dashboard)
            print(f"Dashboard {args.dashboard} marked deleted.")
        return 0
    except DashboardError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
