"""Pytest fixtures for skill sandbox tests."""

import os

import pytest

from src.sandbox import create_sandbox


def _require_env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        pytest.skip(f"{name} not set")
    return val


@pytest.fixture(scope="session")
def arize_env():
    """Ensure all required env vars are present."""
    return {
        "ANTHROPIC_API_KEY": _require_env("ANTHROPIC_API_KEY"),
        "ARIZE_API_KEY": _require_env("ARIZE_API_KEY"),
        "ARIZE_SPACE_ID": _require_env("ARIZE_SPACE_ID"),
    }


@pytest.fixture
def sandbox_workspace(tmp_path, arize_env):
    """Create a sandbox workspace with the langchain-py app."""
    return create_sandbox(tmp_path, app_name="langchain-py")
