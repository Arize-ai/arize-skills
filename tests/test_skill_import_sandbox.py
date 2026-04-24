"""
Sandboxed Claude Agent SDK checks that a project skill can be imported (loaded).

Uses a disposable workspace with ``.claude/skills/`` populated from this repo,
``skills`` allowlisted to a single lightweight skill, Claude Code bash sandboxing
enabled, and a permissive ``can_use_tool`` hook so the session can complete
without interactive prompts.

Requires ``ANTHROPIC_API_KEY`` and a working Claude Code CLI (or the SDK bundled CLI).

Run:
  pytest tests/test_skill_import_sandbox.py -v --timeout=120
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


pytest.importorskip("claude_agent_sdk", reason="claude-agent-sdk not installed")

import claude_agent_sdk

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import PermissionResultAllow, TextBlock, ToolUseBlock

from harness.skill_workspace import copy_fixture_tree, install_project_skills


async def _prompt_stream(text: str) -> AsyncIterable[dict[str, Any]]:
    yield {
        "type": "user",
        "message": {"role": "user", "content": text},
        "parent_tool_use_id": None,
        "session_id": "",
    }


def _repo_has_cli_or_bundled() -> bool:
    if shutil.which("claude"):
        return True
    sdk_root = Path(claude_agent_sdk.__file__).resolve().parent
    bundled = sdk_root / "_bundled" / ("claude.exe" if sys.platform == "win32" else "claude")
    return bundled.is_file()


requires_anthropic = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
requires_cli = pytest.mark.skipif(
    not _repo_has_cli_or_bundled(),
    reason="Claude Code CLI not found (install @anthropic-ai/claude-code or use SDK bundle)",
)
skip_windows_sandbox = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Bash sandbox mode is not the primary target on Windows",
)


@pytest.fixture
def skill_sandbox_workspace(tmp_path: Path) -> Path:
    """Isolated cwd with ``arize-link`` only plus the sample financial agent tree."""
    install_project_skills(tmp_path, _REPO_ROOT, skill_names=["arize-link"])
    copy_fixture_tree(tmp_path, _REPO_ROOT, "fixtures/financial_agent")
    return tmp_path


@requires_anthropic
@requires_cli
@skip_windows_sandbox
@pytest.mark.asyncio
async def test_skill_tool_loads_in_sandbox(skill_sandbox_workspace: Path) -> None:
    """Claude Code loads the ``arize-link`` skill from the sandbox workspace without error."""
    skill_invocations: list[str] = []

    async def allow_tools(
        _tool_name: str,
        _tool_input: dict,
        _ctx,
    ):
        return PermissionResultAllow()

    options = ClaudeAgentOptions(
        system_prompt=(
            "You are validating an Arize agent-skills install. "
            "Call the Skill tool once with skill name exactly: arize-link "
            "(load that skill's instructions). "
            "Do not use Bash. After the skill is loaded, reply with one line "
            "containing the text: SKILL_IMPORT_OK"
        ),
        cwd=str(skill_sandbox_workspace),
        setting_sources=["project"],
        skills=["arize-link"],
        permission_mode="default",
        can_use_tool=allow_tools,
        max_turns=8,
        max_budget_usd=0.2,
        sandbox={"enabled": True, "autoAllowBashIfSandboxed": True},
        extra_args={"no-session-persistence": None},
        model=os.environ.get("TEST_MODEL"),
    )

    prompt = "Load the arize-link skill and confirm as instructed in the system prompt."

    result_msg: ResultMessage | None = None
    text_chunks: list[str] = []
    async for message in query(prompt=_prompt_stream(prompt), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock) and block.name == "Skill":
                    skill_invocations.append(
                        str(block.input.get("skill", "")).strip()
                    )
                elif isinstance(block, TextBlock):
                    text_chunks.append(block.text)
        elif isinstance(message, ResultMessage):
            result_msg = message

    assert result_msg is not None
    assert not result_msg.is_error, (
        f"Claude session ended with error: {result_msg.stop_reason!r}"
    )
    assert "arize-link" in skill_invocations, (
        f"Expected Skill tool for arize-link, saw: {skill_invocations!r}"
    )
    combined = "\n".join(text_chunks)
    assert "SKILL_IMPORT_OK" in combined, (
        f"Expected confirmation token in assistant text; got: {combined[:800]!r}"
    )
