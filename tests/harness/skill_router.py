"""
SkillSelectionRunner — tests whether Claude Code selects the correct skill
for a given prompt.

Runs Claude Code with all skills installed (loaded from the repo's
.claude/skills/ which symlink to /skills/) and checks which Skill tool
invocation Claude Code makes. The Skill tool call is intercepted via
can_use_tool and denied so the skill body never executes — we only care
about which skill was chosen.

This evaluates the specificity and accuracy of skill name/description pairs
for vague, ambiguous, and multi-skill prompts.
"""

import json
import re
import shutil
import subprocess
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)
from claude_agent_sdk.types import (
    TextBlock,
    ToolUseBlock,
)

# Repo root — two levels up from tests/harness/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class SkillSelectionResult:
    """Result of a skill selection test."""

    prompt: str
    expected_skills: list[str]
    selected_skills: list[str]
    correct: bool
    wall_duration_ms: int
    total_cost_usd: float | None
    usage: dict[str, Any] | None
    num_turns: int
    model: str
    text_output: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "expected_skills": self.expected_skills,
            "selected_skills": self.selected_skills,
            "correct": self.correct,
            "wall_duration_ms": self.wall_duration_ms,
            "total_cost_usd": self.total_cost_usd,
            "usage": self.usage,
            "num_turns": self.num_turns,
            "model": self.model,
            "text_output": self.text_output[:500],
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


def _discover_skill_names() -> list[str]:
    """Read valid skill names from /skills/*/SKILL.md frontmatter."""
    skills_dir = _REPO_ROOT / "skills"
    names: list[str] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        # Parse the name from YAML frontmatter (between --- markers)
        text = skill_md.read_text()
        match = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if match:
            for line in match.group(1).splitlines():
                m = re.match(r"name:\s*(.+)", line)
                if m:
                    names.append(m.group(1).strip().strip('"').strip("'"))
                    break
    return names


# Discover at import time so ALL_SKILLS reflects the actual /skills/ directory
ALL_SKILLS = _discover_skill_names()
_TEST_TOOLS = [
    "Task",
    "TaskOutput",
    "Bash",
    "Glob",
    "Grep",
    "ExitPlanMode",
    "Read",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "TodoWrite",
    "WebSearch",
    "TaskStop",
    "AskUserQuestion",
    "Skill",
]


def _extract_issue_lines(text: str) -> list[str]:
    """Extract actionable issue/error lines from CLI output."""
    if not text:
        return []

    issue_patterns = [
        r"\[ERROR\]",
        r'"type":"error"',
        r'"authentication_error"',
        r"\binvalid x-api-key\b",
        r"\b401\b",
        r"\bforbidden\b",
        r"\bunauthorized\b",
        r"\bexception\b",
        r"\berror\b",
    ]
    combined = re.compile("|".join(issue_patterns), re.IGNORECASE)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not combined.search(line):
            continue

        # Normalize JSON stream lines into concise issue text.
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                error_name = payload.get("error")
                message_text = ""
                nested_message = payload.get("message")
                if isinstance(nested_message, dict):
                    content = nested_message.get("content")
                    if (
                        isinstance(content, list)
                        and content
                        and isinstance(content[0], dict)
                    ):
                        message_text = str(content[0].get("text", "")).strip()
                if error_name or message_text:
                    concise = f"{error_name or 'error'}: {message_text}".strip()
                    lines.append(concise.rstrip(": "))
                    continue
            except Exception:
                # Fall back to raw line if JSON parsing fails.
                pass

        lines.append(line)

    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)

    return deduped[:20]


def _capture_cli_failure_context(prompt: str) -> str:
    """Best-effort direct CLI invocation to capture concise issue lines."""
    cli_path = shutil.which("claude")
    if not cli_path:
        return "(diagnostic skipped: 'claude' binary not found in PATH)"

    user_message = {
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
    }
    cmd = [
        cli_path,
        "--output-format",
        "stream-json",
        "--verbose",
        "--system-prompt",
        "",
        "--tools",
        ",".join(_TEST_TOOLS),
        "--max-turns",
        "5",
        "--max-budget-usd",
        "0.1",
        "--setting-sources",
        "project",
        "--permission-mode",
        "default",
        "--input-format",
        "stream-json",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            input=f"{json.dumps(user_message)}\n",
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception as error:
        return f"(diagnostic run failed: {error})"

    stdout_issues = _extract_issue_lines(result.stdout or "")
    stderr_issues = _extract_issue_lines(result.stderr or "")
    issues = stdout_issues + [line for line in stderr_issues if line not in stdout_issues]

    if not issues:
        return (
            f"diagnostic_return_code={result.returncode}\n"
            "diagnostic_issues: (none found; no error lines matched)"
        )

    return (
        f"diagnostic_return_code={result.returncode}\n"
        "diagnostic_issues:\n"
        + "\n".join(f"- {line}" for line in issues)
    )


class SkillSelectionRunner:
    """
    Runs Claude Code with all skills installed and intercepts which Skill tool
    invocation(s) Claude Code makes in response to a user prompt.

    Skills are loaded naturally by Claude Code from .claude/skills/ (which
    symlink to /skills/). The Skill tool call is intercepted via can_use_tool
    and denied with interrupt=True so the skill body never executes.
    """

    def __init__(
        self,
        model: str | None = None,
        max_budget_usd: float = 0.10,
    ):
        self.model = model
        self.max_budget_usd = max_budget_usd

    @staticmethod
    async def _prompt_stream(text: str) -> AsyncIterable[dict[str, Any]]:
        """Wrap a string prompt as the AsyncIterable that streaming mode expects."""
        yield {
            "type": "user",
            "message": {"role": "user", "content": text},
            "parent_tool_use_id": None,
            "session_id": "",
        }

    async def select(
        self, prompt: str, stop_after: int = 1
    ) -> tuple[list[str], ResultMessage | None, str]:
        """Run Claude Code and capture which Skill tool(s) it attempts to invoke.

        stop_after: interrupt the session once this many distinct valid skills
        have been recorded (use len(expected_skills) from the caller).

        Returns (selected_skills, result_message, text_output).
        """
        text_blocks: list[str] = []
        text_output = ""
        result_message: ResultMessage | None = None
        selected_skills: list[str] = []
        stderr_lines: list[str] = []
        def _capture_stderr(line: str) -> None:
            stderr_lines.append(line)

        # Give more turns for multi-skill prompts so the agent has room to
        # invoke each skill in sequence.  5 turns per expected skill, min 5.
        max_turns = max(5, stop_after * 5)

        options = ClaudeAgentOptions(
            permission_mode="default",
            setting_sources=["project"],
            # Typical list of tools (to exclude all unknown tools of the tester)
            tools=_TEST_TOOLS,
            max_turns=max_turns,
            max_budget_usd=self.max_budget_usd,
            model=self.model,
            cwd=str(_REPO_ROOT),
            stderr=_capture_stderr,
            # Don't pollute the user's Claude Code session history with test runs
            extra_args={"no-session-persistence": None},
        )

        try:
            async for message in query(prompt=self._prompt_stream(prompt), options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_blocks.append(block.text)
                        if isinstance(block, ToolUseBlock):
                            if block.name == "Skill":
                                skill_name = block.input.get("skill", "").strip()
                                selected_skills.append(skill_name)
                elif isinstance(message, ResultMessage):
                    result_message = message
                # Exit early once we've captured the target number of distinct skills
                if len(selected_skills) >= stop_after:
                    break
        except Exception as e:
            stderr_text = "\n".join(stderr_lines) if stderr_lines else "(no stderr captured)"
            diagnostic = ""
            if not stderr_lines:
                diagnostic = (
                    "\n\nCLI direct diagnostic:\n"
                    f"{_capture_cli_failure_context(prompt)}"
                )
            raise type(e)(f"{e}\n\nCLI stderr:\n{stderr_text}{diagnostic}") from e
        text_output = "\n".join(text_blocks)
        return selected_skills, result_message, text_output

    async def test_prompt(
        self,
        prompt: str,
        expected_skills: list[str],
        tags: list[str] | None = None,
    ) -> SkillSelectionResult:
        """Test a single prompt and return the selection result."""
        wall_start = time.monotonic()
        selected, result_msg, text_output = await self.select(
            prompt, stop_after=max(len(expected_skills), 1)
        )
        wall_end = time.monotonic()

        # Check correctness: selected must match expected (order-independent)
        correct = set(selected) == set(expected_skills)

        return SkillSelectionResult(
            prompt=prompt,
            expected_skills=expected_skills,
            selected_skills=selected,
            correct=correct,
            wall_duration_ms=int((wall_end - wall_start) * 1000),
            total_cost_usd=result_msg.total_cost_usd if result_msg else None,
            usage=result_msg.usage if result_msg else None,
            num_turns=result_msg.num_turns if result_msg else 0,
            model=self.model or "default",
            text_output=text_output,
            tags=tags or [],
        )
