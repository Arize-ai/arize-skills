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
    # The bug this guards is `return [row, col, width, height]`, which for these
    # arguments emits [1, 1, 12, 2]. Asserting against [0, 0, 12, 2] would pass
    # even with that bug in place, so assert against what the bug really emits.
    assert dashboard.to_grid_position(row=1, col=1, width=12, height=2) != [1, 1, 12, 2]
    assert dashboard.to_grid_position(row=3, col=1, width=3, height=4) != [3, 1, 3, 4]


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
                # Arize stores one dimension per eval FIELD, not one per eval:
                # eval|trace_eval|session_eval.<name>.(label|score|explanation|metadata).
                "llmEvals": {"edges": [
                    entry("ev__h_label", "eval.hallucination.label", "STRING", "llmEval"),
                    entry("ev__h_score", "eval.hallucination.score", "DOUBLE", "llmEval"),
                    entry("ev__h_expl", "eval.hallucination.explanation", "STRING", "llmEval"),
                ]},
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


def test_discover_returns_one_entry_per_eval_field_not_per_eval():
    """One eval yields 2-4 llmEvals entries; panel counts key off distinct names."""
    result = dashboard.discover(_client_returning(_schema_payload()), "proj-1")
    assert len(result["llmEvals"]) == 3
    names = {e["name"].split(".")[1] for e in result["llmEvals"]}
    assert names == {"hallucination"}


def test_discover_flattens_the_three_buckets():
    result = dashboard.discover(_client_returning(_schema_payload()), "proj-1")
    assert result["project"]["name"] == "support-agent"
    assert result["llmEvals"] == [
        {"id": "ev__h_label", "name": "eval.hallucination.label", "dataType": "STRING", "category": "llmEval"},
        {"id": "ev__h_score", "name": "eval.hallucination.score", "dataType": "DOUBLE", "category": "llmEval"},
        {"id": "ev__h_expl", "name": "eval.hallucination.explanation", "dataType": "STRING", "category": "llmEval"},
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
            # avg is numeric-only, so the average tile must sit on the eval's
            # .score dimension; the STRING .label dimension would render n/a.
            {"type": "statistic", "title": "Hallucination", "aggregation": "avg",
             "dimension": {"id": "ev__h_score", "name": "eval.hallucination.score", "dataType": "DOUBLE"},
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
    assert payload["dimension"]["name"] == "eval.hallucination.score"
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


def test_dashboard_url_uses_profile_host():
    cfg = {"app_host": "arize-app.iqhub.co", "app_scheme": "https"}
    url = dashboard.dashboard_url(cfg, "org-1", "space-1", "dash-1")
    assert url == "https://arize-app.iqhub.co/organizations/org-1/spaces/space-1/dashboards/dash-1"


def _verify_payload(statistic_titles, text_titles, line_titles=(), name="Eval Health"):
    edges = lambda titles: {"edges": [{"node": {"title": t}} for t in titles]}
    return {"node": {"id": "dash-1", "name": name,
                     "statisticWidgets": edges(statistic_titles),
                     "textWidgets": edges(text_titles),
                     "lineChartWidgets": edges(line_titles)}}


def _scripted_client(responses, captured):
    queue = list(responses)

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": queue.pop(0)})

    return dashboard.Client("https://app.arize.com/graphql", "k",
                            http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_apply_creates_dashboard_then_widgets_in_order():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload(["Hallucination"], ["Header"]),
    ], captured)
    result = dashboard.apply(client, _valid_spec())
    assert result["dashboardId"] == "dash-1"
    assert result["created"] == ["Header", "Hallucination"]
    assert "createDashboard" in captured[0]["query"]
    assert "createTextWidget" in captured[1]["query"]


def test_apply_dry_run_writes_nothing():
    captured = []
    client = _scripted_client([], captured)
    result = dashboard.apply(client, _valid_spec(), dry_run=True)
    assert result["dryRun"] is True
    assert captured == []
    assert result["created"] == ["Header", "Hallucination"]


def test_apply_validates_before_any_write():
    captured = []
    client = _scripted_client([], captured)
    spec = _valid_spec()
    spec["widgets"][0]["type"] = "pieChart"
    with pytest.raises(dashboard.SpecError):
        dashboard.apply(client, spec)
    assert captured == []


def test_verify_returns_widget_titles():
    payload = {"node": {"id": "dash-1", "name": "Eval Health",
                        "statisticWidgets": {"edges": [{"node": {"title": "Hallucination"}}]},
                        "textWidgets": {"edges": [{"node": {"title": "Header"}}]},
                        "lineChartWidgets": {"edges": []}}}
    captured = []
    client = _scripted_client([payload], captured)
    result = dashboard.verify(client, "dash-1")
    assert sorted(result["widgetTitles"]) == ["Hallucination", "Header"]


def test_list_dashboards_returns_names_and_ids():
    payload = {"node": {"dashboards": {"edges": [
        {"node": {"id": "d1", "name": "Overview", "status": "active"}},
        {"node": {"id": "d2", "name": "Evals", "status": "active"}},
    ]}}}
    captured = []
    result = dashboard.list_dashboards(_scripted_client([payload], captured), "space-1")
    assert [d["name"] for d in result] == ["Overview", "Evals"]


def test_delete_uses_status_mutation_not_a_delete_mutation():
    captured = []
    client = _scripted_client([{"updateDashboardStatus": {"dashboard": {"id": "d1", "status": "deleted"}}}], captured)
    dashboard.delete_dashboard(client, "d1")
    sent = captured[0]
    assert "updateDashboardStatus" in sent["query"]
    assert sent["variables"]["input"]["status"] == "deleted"


def test_cli_delete_requires_confirm(capsys, tmp_path):
    code = dashboard.main(["delete", "--dashboard", "d1", "--home", str(tmp_path)])
    assert code != 0
    assert "--confirm" in capsys.readouterr().err


def test_cli_reports_errors_without_a_traceback(capsys, tmp_path):
    code = dashboard.main(["discover", "--project", "p", "--profile", "nope", "--home", str(tmp_path)])
    assert code != 0
    err = capsys.readouterr().err
    assert "Traceback" not in err


def test_apply_dry_run_accepts_none_client():
    """Regression test: apply(None, spec, dry_run=True) must not fail.

    This verifies that the CLI's dry-run path works without credentials,
    since it never touches the client object on that path.
    """
    result = dashboard.apply(None, _valid_spec(), dry_run=True)
    assert result["dryRun"] is True
    assert result["dashboardId"] is None


# --- Text-widget placement is resolved before validation -------------------


def _text_and_stat_spec():
    """A header with no placement plus a statistic that explicitly claims row 1."""
    return {
        "dashboard": {"name": "D", "projectId": "proj-1", "spaceId": "space-1"},
        "widgets": [
            {"type": "text", "title": "Header", "content": "## Evals"},
            {"type": "statistic", "title": "Stat", "aggregation": "count",
             "dimension": {"id": "d", "name": "n", "dataType": "STRING"},
             "dimensionCategory": "llmEval", "row": 1, "col": 1, "width": 3, "height": 4},
        ],
    }


def test_unplaced_text_widget_is_resolved_to_its_real_grid_position():
    """The fallback must be visible to the validator and to --dry-run, not implicit."""
    spec = {"dashboard": {"name": "D", "projectId": "p", "spaceId": "s"},
            "widgets": [{"type": "text", "title": "Header", "content": "## Evals"}]}
    dashboard.validate_spec(spec)
    widget = spec["widgets"][0]
    assert dashboard._grid(widget) == [1, 1, 3, 13]
    assert dashboard.widget_mutation(widget, "dash-1", "p")[1]["input"]["gridPosition"] == [1, 1, 3, 13]


def test_unplaced_text_widget_overlapping_a_placed_widget_is_rejected():
    with pytest.raises(dashboard.LayoutError, match="overlap"):
        dashboard.validate_spec(_text_and_stat_spec())


def test_two_unplaced_text_widgets_are_rejected_instead_of_stacking():
    spec = {"dashboard": {"name": "D", "projectId": "p", "spaceId": "s"},
            "widgets": [{"type": "text", "title": "A", "content": "a"},
                        {"type": "text", "title": "B", "content": "b"}]}
    with pytest.raises(dashboard.LayoutError, match="overlap"):
        dashboard.validate_spec(spec)


def test_cli_dry_run_prints_the_resolved_text_grid_position(tmp_path, capsys):
    spec = {"dashboard": {"name": "D", "projectId": "p", "spaceId": "s"},
            "widgets": [{"type": "text", "title": "Header", "content": "## Evals"}]}
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec))
    code = dashboard.main(["apply", "--spec", str(spec_file), "--dry-run", "--home", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Header: gridPosition=[1, 1, 3, 13]" in out
    assert "<auto>" not in out


# --- Templated dashboards refuse placement --------------------------------


def _templated_spec():
    return {
        "dashboard": {"name": "Overview", "projectId": "proj-1", "spaceId": "space-1",
                      "template": "generativeLlmModelV2"},
        "widgets": [
            {"type": "statistic", "title": "Hallucination", "aggregation": "avg",
             "dimension": {"id": "ev__h_score", "name": "eval.hallucination.score", "dataType": "DOUBLE"},
             "dimensionCategory": "llmEval"},
        ],
    }


def test_templated_spec_accepts_unplaced_widgets():
    dashboard.validate_spec(_templated_spec())


def test_templated_spec_rejects_explicit_placement():
    spec = _templated_spec()
    spec["widgets"][0].update({"row": 1, "col": 1, "width": 3, "height": 4})
    with pytest.raises(dashboard.SpecError, match="templated dashboard|explicit placement"):
        dashboard.validate_spec(spec)


def test_templated_spec_rejects_partial_placement():
    """Partial placement is silently dropped by _placed(), so it must not slip through."""
    spec = _templated_spec()
    spec["widgets"][0]["row"] = 1
    with pytest.raises(dashboard.SpecError, match="explicit placement"):
        dashboard.validate_spec(spec)


def test_templated_spec_rejects_text_widgets():
    """A text widget cannot be auto-placed, so on a template it always overlaps."""
    spec = _templated_spec()
    spec["widgets"].append({"type": "text", "title": "Header", "content": "## Evals"})
    with pytest.raises(dashboard.SpecError, match="text widget"):
        dashboard.validate_spec(spec)


def test_apply_from_template_pins_the_tracing_environment():
    captured = []
    client = _scripted_client([
        {"createDashboardFromTemplate": {"dashboard": {"id": "dash-9", "name": "Overview"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w1", "title": "Hallucination"}}},
        _verify_payload(["Hallucination"], [], name="Overview"),
    ], captured)
    result = dashboard.apply(client, _templated_spec())
    assert result["dashboardId"] == "dash-9"
    assert result["created"] == ["Hallucination"]
    template_input = captured[0]["variables"]["input"]
    assert "createDashboardFromTemplate" in captured[0]["query"]
    assert template_input["template"] == "generativeLlmModelV2"
    assert template_input["modelId"] == "proj-1"
    # Omitting this makes every template panel query the production environment.
    assert template_input["modelEnvironmentName"] == "tracing"
    assert captured[1]["variables"]["input"]["dashboardId"] == "dash-9"


# --- apply verifies what it created ---------------------------------------


def test_apply_verifies_titles_and_reports_success():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload(["Hallucination"], ["Header"]),
    ], captured)
    result = dashboard.apply(client, _valid_spec())
    assert result["verified"] is True
    assert result["missingTitles"] == []
    assert "VerifyDashboard" in captured[-1]["query"]


def test_apply_reports_a_widget_that_did_not_land():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload([], ["Header"]),
    ], captured)
    result = dashboard.apply(client, _valid_spec())
    assert result["verified"] is False
    assert result["missingTitles"] == ["Hallucination"]


def test_apply_tolerates_extra_template_widgets_in_the_readback():
    captured = []
    client = _scripted_client([
        {"createDashboardFromTemplate": {"dashboard": {"id": "dash-9", "name": "Overview"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w1", "title": "Hallucination"}}},
        _verify_payload(["Hallucination", "Template Latency", "Template Volume"], [], name="Overview"),
    ], captured)
    result = dashboard.apply(client, _templated_spec())
    assert result["verified"] is True


def test_apply_surfaces_a_failed_readback_without_raising():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        {"node": None},
    ], captured)
    result = dashboard.apply(client, _valid_spec())
    # The dashboard id must survive: it is the only handle the user has.
    assert result["dashboardId"] == "dash-1"
    assert result["verified"] is False
    assert "not found" in result["verifyError"]


def test_cli_apply_exits_non_zero_when_a_widget_is_missing(tmp_path, capsys, monkeypatch):
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_valid_spec()))
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload([], ["Header"]),
    ], captured)
    cfg = {"app_host": "app.arize.com", "app_scheme": "https", "api_key": "k", "name": "t"}
    monkeypatch.setattr(dashboard, "_client_for", lambda args: (cfg, client))
    code = dashboard.main(["apply", "--spec", str(spec_file), "--home", str(tmp_path)])
    captured_io = capsys.readouterr()
    assert code != 0
    assert "Hallucination" in captured_io.err
    # The dashboard id is still printed so the user can go look at it.
    assert "dash-1" in captured_io.out


# --- deep links -----------------------------------------------------------


def test_apply_omits_a_link_without_an_org_and_never_invents_one():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload(["Hallucination"], ["Header"]),
    ], captured)
    result = dashboard.apply(client, _valid_spec())
    assert result["url"] is None
    assert "arize-link" in result["urlHint"]


def test_apply_emits_a_deep_link_when_given_an_org():
    captured = []
    client = _scripted_client([
        {"createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}},
        {"createTextWidget": {"textWidget": {"id": "w1", "title": "Header"}}},
        {"createStatisticWidget": {"statisticWidget": {"id": "w2", "title": "Hallucination"}}},
        _verify_payload(["Hallucination"], ["Header"]),
    ], captured)
    cfg = {"app_host": "arize-app.iqhub.co", "app_scheme": "https"}
    result = dashboard.apply(client, _valid_spec(), cfg=cfg, org_id="org-1")
    assert result["url"] == (
        "https://arize-app.iqhub.co/organizations/org-1/spaces/space-1/dashboards/dash-1"
    )


def test_cli_verify_org_without_space_is_a_plain_error(tmp_path, capsys, monkeypatch):
    cfg = {"app_host": "app.arize.com", "app_scheme": "https"}
    client = _scripted_client([], [])
    monkeypatch.setattr(dashboard, "_client_for", lambda args: (cfg, client))
    code = dashboard.main(["verify", "--dashboard", "d1", "--org", "org-1", "--home", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0
    assert "--space" in err
    assert "Traceback" not in err


def test_cli_verify_emits_a_link_with_org_and_space(tmp_path, capsys, monkeypatch):
    cfg = {"app_host": "app.arize.com", "app_scheme": "https"}
    client = _scripted_client([_verify_payload(["Hallucination"], ["Header"])], [])
    monkeypatch.setattr(dashboard, "_client_for", lambda args: (cfg, client))
    code = dashboard.main(["verify", "--dashboard", "dash-1", "--org", "org-1",
                           "--space", "space-1", "--home", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["url"] == "https://app.arize.com/organizations/org-1/spaces/space-1/dashboards/dash-1"


# --- spec-file errors are plain messages, not tracebacks ------------------


def test_cli_missing_spec_file_reports_the_path_without_a_traceback(tmp_path, capsys):
    missing = tmp_path / "typo.json"
    code = dashboard.main(["apply", "--spec", str(missing), "--home", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0
    assert "Traceback" not in err
    assert str(missing) in err


def test_cli_malformed_spec_json_reports_the_line_without_a_traceback(tmp_path, capsys):
    bad = tmp_path / "spec.json"
    bad.write_text('{"dashboard": {"name": "D",}}')
    code = dashboard.main(["apply", "--spec", str(bad), "--home", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0
    assert "Traceback" not in err
    assert "not valid JSON" in err


def test_load_spec_rejects_a_non_object_document(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text("[]")
    with pytest.raises(dashboard.SpecError, match="JSON object"):
        dashboard.load_spec(path)


# --- --app-host --------------------------------------------------------


def test_app_host_flag_supplies_a_missing_on_prem_app_host(tmp_path):
    write_profile(tmp_path, "onprem", api_host="arize-api.iqhub.co", app_host=None)
    cfg = dashboard.load_profile(tmp_path, profile="onprem", environ={},
                                 app_host="arize-app.iqhub.co")
    assert dashboard.graphql_endpoint(cfg) == "https://arize-app.iqhub.co/graphql"


def test_app_host_flag_beats_the_profile_and_the_env(tmp_path):
    write_profile(tmp_path, "saas", app_host="app.arize.com")
    cfg = dashboard.load_profile(tmp_path, profile="saas",
                                 environ={"ARIZE_APP_HOST": "from-env.example.com"},
                                 app_host="from-flag.example.com")
    assert cfg["app_host"] == "from-flag.example.com"


def test_cli_accepts_app_host_before_and_after_the_subcommand(tmp_path, capsys):
    write_profile(tmp_path, "onprem", api_host="arize-api.iqhub.co", app_host=None)
    (tmp_path / ".active_profile").write_text("onprem")
    seen = {}

    def fake_client_for(args):
        seen["app_host"] = args.app_host
        raise dashboard.ConfigError("stop here")

    import unittest.mock
    with unittest.mock.patch.object(dashboard, "_client_for", fake_client_for):
        dashboard.main(["--app-host", "a.example.com", "list", "--space", "s", "--home", str(tmp_path)])
        assert seen["app_host"] == "a.example.com"
        dashboard.main(["list", "--space", "s", "--app-host", "b.example.com", "--home", str(tmp_path)])
        assert seen["app_host"] == "b.example.com"
    capsys.readouterr()


def test_apply_survives_a_transport_failure_on_the_read_back():
    """The read-back is the only call that happens AFTER a write.

    A transport error there must not escape: there is no deleteDashboard in
    this API, so a dashboard whose id the user never saw is an orphan they
    cannot find or remove. Created-but-unverified is an acceptable outcome;
    a lost handle is not.
    """
    def handler(request):
        body = json.loads(request.content)
        if "VerifyDashboard" in body["query"]:
            raise httpx.ConnectError("network down")
        if "createDashboard" in body["query"]:
            return httpx.Response(200, json={"data": {
                "createDashboard": {"dashboard": {"id": "dash-1", "name": "Eval Health"}}}})
        return httpx.Response(200, json={"data": {"createTextWidget": {"textWidget": {"id": "w", "title": "t"}}}})

    client = dashboard.Client("https://app.arize.com/graphql", "k",
                              http=httpx.Client(transport=httpx.MockTransport(handler)))
    result = dashboard.apply(client, _valid_spec())
    assert result["dashboardId"] == "dash-1"
    assert result["verification"] == "notCompleted"
    assert result["verified"] is False
    assert "network down" in result["verifyError"]
    assert result["url"] is None and "arize-link" in result["urlHint"]
