#!/usr/bin/env python3
"""Build populated Arize dashboards from a declarative spec via the programmatic GraphQL API."""

from __future__ import annotations

import json
import os
import sys
import tomllib
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
