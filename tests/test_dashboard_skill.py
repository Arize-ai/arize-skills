"""Behavioral tests for the bundled Arize dashboard helper; no live services."""

import importlib.util
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
