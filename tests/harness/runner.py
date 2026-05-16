"""
SkillTestRunner — drives Claude Code via the Agent SDK and collects metrics.

Usage:
    runner = SkillTestRunner(
        skill_name="arize-trace",
        system_prompt="...",
        cwd="/tmp/test-workspace",
        env={"ARIZE_API_KEY": "..."},
    )
    result = await runner.run("Export the error traces from project 'test-project'")
"""

import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)
from claude_agent_sdk.types import TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock

from .result import TestResult


class SkillTestRunner:
    def __init__(
        self,
        skill_name: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        permission_mode: str = "bypassPermissions",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        max_turns: int | None = 50,
        max_budget_usd: float | None = 1.0,
        model: str | None = None,
    ):
        self.skill_name = skill_name
        self.options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools
            or ["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
            permission_mode=permission_mode,
            cwd=cwd,
            env=env or {},
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            model=model,
        )

    async def run(self, prompt: str) -> TestResult:
        """Execute a prompt through Claude Code and capture all metrics."""
        tool_calls: list[dict[str, Any]] = []
        text_blocks: list[str] = []
        result_message: ResultMessage | None = None

        wall_start = time.monotonic()

        async for message in query(prompt=prompt, options=self.options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_blocks.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(
                            {"tool": block.name, "input": block.input}
                        )
            elif isinstance(message, ResultMessage):
                result_message = message

        wall_end = time.monotonic()
        wall_duration_ms = int((wall_end - wall_start) * 1000)

        return TestResult(
            skill_name=self.skill_name,
            prompt=prompt,
            wall_duration_ms=wall_duration_ms,
            num_turns=result_message.num_turns if result_message else 0,
            total_cost_usd=result_message.total_cost_usd if result_message else None,
            usage=result_message.usage if result_message else None,
            is_error=result_message.is_error if result_message else True,
            stop_reason=result_message.stop_reason if result_message else None,
            session_id=result_message.session_id if result_message else None,
            text_output="\n".join(text_blocks),
            tool_calls=tool_calls,
        )
