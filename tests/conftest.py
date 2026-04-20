"""
Shared fixtures for skill tests.

Key environment variables (set in CI or locally):
  ARIZE_API_KEY       - Arize API key
  ARIZE_SPACE_ID      - Arize space ID
  TEST_PROJECT_NAME   - Arize project name for trace-related tests
  TEST_MODEL          - Claude model override (default: None = use SDK default)
  SKILL_TESTS_REPORT_DIR - Where to save JSON reports (default: test-results)
"""

import os
import pathlib
import sys

import pytest
from dotenv import load_dotenv

# Load .env from the repository root (parent of tests/)
load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=True)

# Remove CLAUDECODE so the SDK can spawn Claude Code subprocesses even when
# tests are run from inside a Claude Code session (nested sessions are blocked
# by the presence of this env var).
os.environ.pop("CLAUDECODE", None)

# Ensure tests dir is on path so harness is importable when running from project root
_tests_dir = pathlib.Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))


@pytest.fixture(scope="session")
def test_model():
    return os.environ.get("TEST_MODEL", None)
