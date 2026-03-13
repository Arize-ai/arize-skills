"""
Shared fixtures for all skill tests.

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
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

# Ensure tests dir is on path so harness is importable when running from project root
_tests_dir = pathlib.Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from harness.report import TestReport
from harness.runner import SkillTestRunner

SKILLS_DIR = pathlib.Path(__file__).parent.parent / "skills"


def load_skill_prompt(skill_name: str) -> str:
    """Load the SKILL.md content to use as the system prompt."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    return skill_path.read_text(encoding="utf-8")


# ---- Session-scoped fixtures ----


@pytest.fixture(scope="session")
def arize_api_key():
    key = os.environ.get("ARIZE_API_KEY")
    if not key:
        pytest.skip("ARIZE_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def arize_space_id():
    sid = os.environ.get("ARIZE_SPACE_ID")
    if not sid:
        pytest.skip("ARIZE_SPACE_ID not set")
    return sid


@pytest.fixture(scope="session")
def test_project_name():
    return os.environ.get("TEST_PROJECT_NAME", "skill-tests")


@pytest.fixture(scope="session")
def test_model():
    return os.environ.get("TEST_MODEL", None)


@pytest.fixture(scope="session")
def test_report():
    report = TestReport(
        report_dir=os.environ.get("SKILL_TESTS_REPORT_DIR", "test-results")
    )
    yield report
    path = report.save()
    print(f"\nTest report saved to: {path}")


# ---- Function-scoped fixtures ----


@pytest.fixture
def workspace(tmp_path):
    """Provide a clean temp workspace directory for each test."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws)


@pytest.fixture
def arize_env(arize_api_key, arize_space_id, test_project_name):
    """Environment dict for Claude Code sessions."""
    return {
        "ARIZE_API_KEY": arize_api_key,
        "ARIZE_SPACE_ID": arize_space_id,
        "ARIZE_DEFAULT_PROJECT": test_project_name,
        "PATH": os.environ.get("PATH", "")
        + ":"
        + os.path.expanduser("~/.local/bin"),
    }


def make_runner(
    skill_name: str,
    workspace: str,
    arize_env: dict,
    model: str | None = None,
    max_turns: int = 50,
    max_budget_usd: float = 1.0,
) -> SkillTestRunner:
    """Factory for creating a SkillTestRunner with standard config."""
    return SkillTestRunner(
        skill_name=skill_name,
        system_prompt=load_skill_prompt(skill_name),
        cwd=workspace,
        env=arize_env,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
    )
