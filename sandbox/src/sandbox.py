"""Workspace setup: clone Rosetta Stone app, install arize-instrumentation skill.

Security notes:
- Credentials are passed via the SDK env dict, NOT written to .env files in the workspace.
  This prevents the agent from reading secrets via Bash/Read tools.
- The workspace is a temp directory destroyed after each run.
- Business logic originals are saved to _originals/ for tamper detection.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

from .config import (
    ARIZE_SKILLS_REPO,
    ROSETTA_STONE_REPO,
    SUPPORTED_APPS,
)

# Files the agent should never need to read — used for post-run audit
_SENSITIVE_PATTERNS = {".env", ".env.local", "credentials", "secret", "token"}


def create_sandbox(tmp_dir: Path, app_name: str = "langchain-py") -> Path:
    """Create a sandbox workspace with an uninstrumented app and the arize-instrumentation skill.

    Returns the workspace path ready for the agent.
    """
    if app_name not in SUPPORTED_APPS:
        raise ValueError(f"Unsupported app: {app_name}. Choose from: {list(SUPPORTED_APPS)}")

    app_config = SUPPORTED_APPS[app_name]
    workspace = tmp_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _clone_uninstrumented_app(workspace, app_config["source_path"])
    _save_originals(workspace)
    _install_skill(workspace)

    return workspace


def _clone_uninstrumented_app(workspace: Path, source_path: str) -> None:
    """Sparse-checkout the uninstrumented app from Rosetta Stone."""
    repo_dir = workspace / "_rosetta_stone"

    # Validate source_path to prevent path traversal
    normalized = os.path.normpath(source_path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise ValueError(f"Invalid source path: {source_path}")

    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--sparse", "--depth=1",
         ROSETTA_STONE_REPO, str(repo_dir)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "sparse-checkout", "set", source_path],
        cwd=repo_dir, check=True, capture_output=True, text=True,
    )

    # Copy the app files into the workspace root
    source = repo_dir / source_path
    if not source.exists():
        raise FileNotFoundError(f"Source path not found after clone: {source}")

    for item in source.iterdir():
        dest = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    # Clean up the clone
    shutil.rmtree(repo_dir)


def _save_originals(workspace: Path) -> None:
    """Save copies of business logic files for tamper detection.

    These are stored read-only so the agent can't modify them.
    """
    originals_dir = workspace / "_originals"
    originals_dir.mkdir(parents=True, exist_ok=True)

    for py_file in workspace.rglob("*.py"):
        if py_file.is_relative_to(originals_dir):
            continue
        rel = py_file.relative_to(workspace)
        dest = originals_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(py_file, dest)
        # Make read-only so the agent can't tamper
        dest.chmod(stat.S_IRUSR | stat.S_IRGRP)


def _install_skill(workspace: Path) -> None:
    """Clone arize-skills and symlink the instrumentation skill into .claude/skills/."""
    skills_dir = workspace / "_arize_skills"

    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--sparse", "--depth=1",
         ARIZE_SKILLS_REPO, str(skills_dir)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "sparse-checkout", "set", "skills/arize-instrumentation"],
        cwd=skills_dir, check=True, capture_output=True, text=True,
    )

    # Symlink into .claude/skills/
    claude_skills = workspace / ".claude" / "skills"
    claude_skills.mkdir(parents=True, exist_ok=True)

    skill_source = skills_dir / "skills" / "arize-instrumentation"
    skill_link = claude_skills / "arize-instrumentation"

    if skill_source.exists():
        skill_link.symlink_to(skill_source.resolve())
    else:
        raise FileNotFoundError(f"Skill not found after clone: {skill_source}")


def audit_workspace(workspace: Path, tool_calls: list[dict]) -> list[str]:
    """Post-run security audit: check if the agent accessed sensitive files."""
    warnings = []
    for call in tool_calls:
        tool_input = call.get("input", {})
        # Check Read/Bash calls for sensitive file access
        for key in ("file_path", "command", "path"):
            value = str(tool_input.get(key, ""))
            for pattern in _SENSITIVE_PATTERNS:
                if pattern in value.lower():
                    warnings.append(
                        f"Agent accessed potentially sensitive path via {call['name']}: {value}"
                    )
    return warnings
