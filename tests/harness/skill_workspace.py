"""
Prepare an isolated workspace that mirrors how Claude Code discovers project skills.

Copies selected skills into ``<cwd>/.claude/skills/<name>/`` so ``setting_sources``
can be limited to ``project`` without touching the developer's real ``.claude/``.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def install_project_skills(
    workspace: Path,
    repo_root: Path,
    *,
    skill_names: list[str] | None = None,
) -> list[str]:
    """Copy ``skills/<name>/`` from the repo into ``workspace/.claude/skills/``.

    If ``skill_names`` is None, every directory under ``repo_root/skills`` that
    contains a ``SKILL.md`` file is installed.

    Returns the list of installed skill directory names.
    """
    src_root = repo_root / "skills"
    dest_root = workspace / ".claude" / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for skill_dir in sorted(src_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        if not (skill_dir / "SKILL.md").is_file():
            continue
        name = skill_dir.name
        if skill_names is not None and name not in skill_names:
            continue
        target = dest_root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill_dir, target)
        installed.append(name)

    return installed


def copy_fixture_tree(workspace: Path, repo_root: Path, relative: str) -> Path:
    """Copy ``repo_root / relative`` into the same relative path under ``workspace``."""
    src = repo_root / relative
    if not src.is_dir():
        raise FileNotFoundError(f"Missing fixture directory: {src}")
    dest = workspace / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest
