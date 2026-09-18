"""Behavioral tests for the bundled Arize dashboard helper; no live services."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arize-dashboard" / "scripts" / "dashboard.py"
_spec = importlib.util.spec_from_file_location("arize_dashboard", SCRIPT)
dashboard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dashboard)


def write_profile(home, name, *, api_key="secret-key", api_host="api.arize.com", app_host="app.arize.com"):
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    body = f'[profile]\nname = "{name}"\n\n[auth]\napi_key = "{api_key}"\n\n[routing]\napi_host = "{api_host}"\napi_scheme = "https"\n'
    if app_host:
        body += f'app_host = "{app_host}"\napp_scheme = "https"\n'
    (home / "profiles" / f"{name}.toml").write_text(body)


def test_active_profile_read_from_marker_file(tmp_path):
    write_profile(tmp_path, "phaseb")
    (tmp_path / ".active_profile").write_text("phaseb")
    assert dashboard.active_profile_name(tmp_path, environ={}) == "phaseb"


def test_explicit_profile_beats_marker(tmp_path):
    (tmp_path / ".active_profile").write_text("phaseb")
    assert dashboard.active_profile_name(tmp_path, profile="staging", environ={}) == "staging"


def test_env_profile_beats_marker(tmp_path):
    (tmp_path / ".active_profile").write_text("phaseb")
    assert dashboard.active_profile_name(tmp_path, environ={"ARIZE_PROFILE": "demo"}) == "demo"


def test_onprem_app_host_is_preserved(tmp_path):
    write_profile(tmp_path, "jobkorea", api_host="arize-app.iqhub.co", app_host="arize-app.iqhub.co")
    cfg = dashboard.load_profile(tmp_path, profile="jobkorea", environ={})
    assert dashboard.graphql_endpoint(cfg) == "https://arize-app.iqhub.co/graphql"


def test_missing_app_host_on_unknown_api_host_is_an_error(tmp_path):
    write_profile(tmp_path, "onprem", api_host="arize-app.iqhub.co", app_host=None)
    with pytest.raises(dashboard.ConfigError, match="app_host"):
        dashboard.load_profile(tmp_path, profile="onprem", environ={})


def test_missing_app_host_defaults_only_for_saas(tmp_path):
    write_profile(tmp_path, "saas", api_host="api.arize.com", app_host=None)
    cfg = dashboard.load_profile(tmp_path, profile="saas", environ={})
    assert cfg["app_host"] == "app.arize.com"


def test_env_overrides_profile_key(tmp_path):
    write_profile(tmp_path, "saas", api_key="from-file")
    cfg = dashboard.load_profile(tmp_path, profile="saas", environ={"ARIZE_API_KEY": "from-env"})
    assert cfg["api_key"] == "from-env"


def test_execute_raises_on_graphql_errors_without_leaking_key():
    def handler(request):
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(200, json={"errors": [{"message": "Dashboard not found"}]})

    client = dashboard.Client("https://app.arize.com/graphql", "secret-key",
                              http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(dashboard.GraphQLError) as excinfo:
        client.execute("query { viewer { id } }")
    assert "Dashboard not found" in str(excinfo.value)
    assert "secret-key" not in str(excinfo.value)


def test_execute_raises_on_http_error():
    handler = lambda request: httpx.Response(403, text="forbidden")
    client = dashboard.Client("https://app.arize.com/graphql", "secret-key",
                              http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(dashboard.GraphQLError, match="403"):
        client.execute("query { viewer { id } }")


def test_execute_returns_data():
    handler = lambda request: httpx.Response(200, json={"data": {"viewer": {"id": "abc"}}})
    client = dashboard.Client("https://app.arize.com/graphql", "secret-key",
                              http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.execute("query { viewer { id } }") == {"viewer": {"id": "abc"}}


def test_terminal_default_falls_back_to_config_toml(tmp_path):
    """Terminal default (no marker, no env, no arg) can fall back to config.toml."""
    (tmp_path / "config.toml").write_text('[profile]\nname = "default"\n\n[auth]\napi_key = "config-key"\n\n[routing]\napi_host = "api.arize.com"\napp_scheme = "https"\n')
    cfg = dashboard.load_profile(tmp_path, profile=None, environ={})
    assert cfg["api_key"] == "config-key"


def test_explicit_profile_missing_does_not_silently_load_config_toml(tmp_path):
    """Regression test: explicit --profile must not fall back to config.toml.

    This test guards against deletion of the _profile_name_is_explicit gate.
    A populated config.toml with distinguishable credentials exists, but
    profiles/staging.toml does not. The explicit profile request must error,
    not silently load the config.toml's credentials.
    """
    (tmp_path / "config.toml").write_text('[profile]\nname = "default"\n\n[auth]\napi_key = "config-toml-key"\n\n[routing]\napi_host = "api.arize.com"\napp_scheme = "https"\n')
    with pytest.raises(dashboard.ConfigError) as excinfo:
        dashboard.load_profile(tmp_path, profile="staging", environ={})
    # The key assertion: an error was raised. We do not check for config-toml-key
    # in the loaded config because the file should never be read.
    assert "staging" in str(excinfo.value)


def test_marker_file_missing_profile_does_not_silently_load_config_toml(tmp_path):
    """Regression test: .active_profile marker must not fall back to config.toml.

    A populated config.toml exists but the profile it points to does not.
    Must raise ConfigError, not silently load config.toml.
    """
    (tmp_path / "config.toml").write_text('[profile]\nname = "default"\n\n[auth]\napi_key = "config-toml-key"\n\n[routing]\napi_host = "api.arize.com"\napp_scheme = "https"\n')
    (tmp_path / ".active_profile").write_text("nonexistent")
    with pytest.raises(dashboard.ConfigError) as excinfo:
        dashboard.load_profile(tmp_path, profile=None, environ={})
    assert "nonexistent" in str(excinfo.value)


def test_env_var_missing_profile_does_not_silently_load_config_toml(tmp_path):
    """Regression test: ARIZE_PROFILE env var must not fall back to config.toml.

    A populated config.toml exists but the profile it points to does not.
    Must raise ConfigError, not silently load config.toml.
    """
    (tmp_path / "config.toml").write_text('[profile]\nname = "default"\n\n[auth]\napi_key = "config-toml-key"\n\n[routing]\napi_host = "api.arize.com"\napp_scheme = "https"\n')
    with pytest.raises(dashboard.ConfigError) as excinfo:
        dashboard.load_profile(tmp_path, profile=None, environ={"ARIZE_PROFILE": "staging"})
    assert "staging" in str(excinfo.value)


def test_full_width_header_matches_known_good_grid_position():
    # A full-width header occupying the first 2 rows.
    assert dashboard.to_grid_position(row=1, col=1, width=12, height=2) == [1, 1, 3, 13]


def test_three_wide_stat_matches_known_good_grid_position():
    # A 3-wide stat in the next 4 rows at the left.
    assert dashboard.to_grid_position(row=3, col=1, width=3, height=4) == [3, 1, 7, 4]


def test_grid_position_is_not_xywh():
    # The natural-but-wrong guess is [x, y, w, h]; assert we never emit it.
    assert dashboard.to_grid_position(row=1, col=1, width=12, height=2) != [0, 0, 12, 2]


def test_width_overflowing_grid_is_rejected():
    with pytest.raises(dashboard.LayoutError, match="exceeds"):
        dashboard.validate_layout([{"title": "wide", "row": 1, "col": 6, "width": 8, "height": 2}])


def test_full_width_widget_is_allowed():
    dashboard.validate_layout([{"title": "header", "row": 1, "col": 1, "width": 12, "height": 2}])


def test_overlapping_widgets_are_rejected():
    widgets = [
        {"title": "a", "row": 1, "col": 1, "width": 6, "height": 4},
        {"title": "b", "row": 2, "col": 3, "width": 6, "height": 4},
    ]
    with pytest.raises(dashboard.LayoutError, match="overlap"):
        dashboard.validate_layout(widgets)


def test_adjacent_widgets_do_not_count_as_overlapping():
    widgets = [
        {"title": "a", "row": 1, "col": 1, "width": 6, "height": 4},
        {"title": "b", "row": 1, "col": 7, "width": 6, "height": 4},
    ]
    dashboard.validate_layout(widgets)


def test_non_positive_dimensions_are_rejected():
    with pytest.raises(dashboard.LayoutError, match="positive"):
        dashboard.validate_layout([{"title": "bad", "row": 1, "col": 1, "width": 0, "height": 2}])


def test_widgets_without_coordinates_are_left_to_auto_placement():
    dashboard.validate_layout([{"title": "auto"}])


def _schema_payload():
    def entry(dim_id, name, data_type, category):
        return {"node": {"dimension": {"id": dim_id, "name": name, "dataType": data_type, "category": category}}}

    return {
        "node": {
            "id": "proj-1",
            "name": "support-agent",
            "tracingSchema": {
                "spanProperties": {"edges": [entry("sp__status_code", "status_code", "STRING", "spanProperty")]},
                "llmEvals": {"edges": [entry("ev__hallucination", "hallucination", "STRING", "llmEval")]},
                "annotations": {"edges": []},
            },
            "customMetrics": {"edges": [{"node": {"id": "cm-1", "name": "cost_per_call"}}]},
        }
    }


def _client_returning(payload, captured=None):
    def handler(request):
        if captured is not None:
            captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": payload})

    return dashboard.Client("https://app.arize.com/graphql", "secret-key",
                            http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_discover_flattens_the_three_buckets():
    result = dashboard.discover(_client_returning(_schema_payload()), "proj-1")
    assert result["project"]["name"] == "support-agent"
    assert result["llmEvals"] == [
        {"id": "ev__hallucination", "name": "hallucination", "dataType": "STRING", "category": "llmEval"}
    ]
    assert result["spanProperties"][0]["name"] == "status_code"
    assert result["annotations"] == []
    assert result["customMetrics"] == [{"id": "cm-1", "name": "cost_per_call"}]


def test_discover_sends_a_time_window():
    captured = []
    dashboard.discover(_client_returning(_schema_payload(), captured), "proj-1", days=7)
    variables = captured[0]["variables"]
    assert variables["projectId"] == "proj-1"
    assert variables["start"] < variables["end"]


def test_discover_tolerates_missing_buckets():
    payload = {"node": {"id": "p", "name": "quiet", "tracingSchema": None, "customMetrics": None}}
    result = dashboard.discover(_client_returning(payload), "p")
    assert result["llmEvals"] == []
    assert result["customMetrics"] == []


def test_discover_rejects_an_unknown_project():
    with pytest.raises(dashboard.DashboardError, match="not a project"):
        dashboard.discover(_client_returning({"node": None}), "missing")


def _valid_spec():
    return {
        "dashboard": {"name": "Eval Health", "projectId": "proj-1", "spaceId": "space-1"},
        "widgets": [
            {"type": "text", "title": "Header", "content": "## Evals",
             "row": 1, "col": 1, "width": 12, "height": 2},
            {"type": "statistic", "title": "Hallucination", "aggregation": "avg",
             "dimension": {"id": "ev__h", "name": "hallucination", "dataType": "STRING"},
             "dimensionCategory": "llmEval", "row": 3, "col": 1, "width": 3, "height": 4},
        ],
    }


def test_valid_spec_passes():
    dashboard.validate_spec(_valid_spec())


def test_spec_requires_a_dashboard_name():
    spec = _valid_spec()
    del spec["dashboard"]["name"]
    with pytest.raises(dashboard.SpecError, match="name"):
        dashboard.validate_spec(spec)


def test_spec_rejects_unknown_widget_type():
    spec = _valid_spec()
    spec["widgets"][0]["type"] = "pieChart"
    with pytest.raises(dashboard.SpecError, match="pieChart"):
        dashboard.validate_spec(spec)


def test_spec_rejects_text_widget_without_content():
    spec = _valid_spec()
    del spec["widgets"][0]["content"]
    with pytest.raises(dashboard.SpecError, match="content"):
        dashboard.validate_spec(spec)


def test_spec_surfaces_layout_errors():
    spec = _valid_spec()
    spec["widgets"][1]["col"] = 11
    spec["widgets"][1]["width"] = 6
    with pytest.raises(dashboard.LayoutError):
        dashboard.validate_spec(spec)


def test_text_widget_mutation_publishes_and_converts_grid():
    widget = _valid_spec()["widgets"][0]
    query, variables = dashboard.widget_mutation(widget, "dash-1", "proj-1")
    assert "createTextWidget" in query
    assert variables["input"]["gridPosition"] == [1, 1, 3, 13]
    assert variables["input"]["creationStatus"] == "published"
    assert variables["input"]["dashboardId"] == "dash-1"


def test_statistic_widget_mutation_carries_dimension_and_project():
    widget = _valid_spec()["widgets"][1]
    query, variables = dashboard.widget_mutation(widget, "dash-1", "proj-1")
    payload = variables["input"]
    assert "createStatisticWidget" in query
    assert payload["modelId"] == "proj-1"
    assert payload["dimensionCategory"] == "llmEval"
    assert payload["dimension"]["name"] == "hallucination"
    assert payload["timeSeriesMetricType"] == "modelDataMetric"
    assert payload["creationStatus"] == "published"


def test_unplaced_widget_omits_grid_position():
    query, variables = dashboard.widget_mutation(
        {"type": "statistic", "title": "auto", "aggregation": "count",
         "dimension": {"id": "d", "name": "n", "dataType": "STRING"}, "dimensionCategory": "spanProperty"},
        "dash-1", "proj-1")
    assert "gridPosition" not in variables["input"]


def test_line_chart_widget_mutation_nests_plot_fields():
    widget = {
        "type": "lineChart", "title": "Accuracy Over Time", "metric": "count",
        "dimension": {"id": "d", "name": "timestamp", "dataType": "TIMESTAMP"},
        "dimensionCategory": "spanProperty",
        "row": 1, "col": 1, "width": 6, "height": 4,
    }
    query, variables = dashboard.widget_mutation(widget, "dash-1", "proj-1")
    assert "createLineChartWidget" in query
    payload = variables["input"]
    assert len(payload["plots"]) == 1
    plot = payload["plots"][0]
    assert plot["modelId"] == "proj-1"
    assert plot["dimension"]["name"] == "timestamp"
    assert plot["dimensionCategory"] == "spanProperty"
    assert plot["metric"] == "count"
    # Critical: these must NOT be at top level
    assert "modelId" not in payload
    assert "dimension" not in payload
    assert "dimensionCategory" not in payload
    assert payload["creationStatus"] == "published"


def test_unplaced_line_chart_omits_grid_position():
    widget = {
        "type": "lineChart", "title": "auto", "metric": "count",
        "dimension": {"id": "d", "name": "n", "dataType": "TIMESTAMP"},
        "dimensionCategory": "spanProperty",
    }
    query, variables = dashboard.widget_mutation(widget, "dash-1", "proj-1")
    assert "gridPosition" not in variables["input"]


def test_widget_mutation_rejects_unsupported_type():
    widget = {
        "type": "barChart", "title": "Chart", "metric": "count",
        "dimension": {"id": "d", "name": "n", "dataType": "STRING"},
        "dimensionCategory": "spanProperty",
    }
    with pytest.raises(dashboard.SpecError, match="barChart"):
        dashboard.widget_mutation(widget, "dash-1", "proj-1")
