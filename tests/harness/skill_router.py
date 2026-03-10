"""
SkillSelectionRunner — tests whether Claude Code selects the correct skill
for a given prompt. Runs Claude Code with all skills installed and checks
which skill(s) it invokes.

This evaluates the specificity and accuracy of skill name/description pairs
for vague, ambiguous, and multi-skill prompts.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)
from claude_agent_sdk.types import TextBlock, ToolUseBlock

from .result import TestResult, VerificationResult


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


# All known skill names
ALL_SKILLS = [
    "arize-trace",
    "arize-instrumentation",
    "arize-dataset",
    "arize-experiment",
    "arize-prompt-optimization",
    "arize-link",
]


class SkillSelectionRunner:
    """
    Runs Claude Code with a system prompt that lists all available skills
    and asks it to identify which skill(s) to use for a given prompt.

    Instead of executing the full skill, we just ask Claude to select and
    name the skill — keeping token usage and duration minimal.
    """

    SELECTION_SYSTEM_PROMPT = """\
You are an AI assistant with access to these Arize skills:

1. **arize-trace**: INVOKE THIS SKILL when downloading or exporting Arize traces and spans. Covers exporting traces by ID, sessions by ID, and debugging LLM application issues using the ax CLI.

2. **arize-instrumentation**: INVOKE THIS SKILL when adding Arize AX tracing to an application. Follow the Agent-Assisted Tracing two-phase flow: analyze the codebase (read-only), then implement instrumentation after user confirmation.

3. **arize-dataset**: INVOKE THIS SKILL when creating, managing, or querying Arize datasets and examples. Covers dataset CRUD, appending examples, exporting data, and file-based dataset creation using the ax CLI.

4. **arize-experiment**: INVOKE THIS SKILL when creating, running, or analyzing Arize experiments. Covers experiment CRUD, exporting runs, comparing results, and evaluation workflows using the ax CLI.

5. **arize-prompt-optimization**: INVOKE THIS SKILL when optimizing, improving, or debugging LLM prompts using production trace data, evaluations, and annotations.

6. **arize-link**: Generate deep links to traces, spans, and sessions in the Arize UI. Use when the user wants a clickable URL to open a specific trace, span, or session.

Given the user's request, respond with ONLY the skill name(s) you would invoke, one per line. Format:
SELECTED_SKILL: <skill-name>

If multiple skills are needed, list each on its own line. Do NOT explain your reasoning. Do NOT invoke any tools.
"""

    def __init__(
        self,
        model: str | None = None,
        max_budget_usd: float = 0.10,
    ):
        self.model = model
        self.options = ClaudeAgentOptions(
            system_prompt=self.SELECTION_SYSTEM_PROMPT,
            allowed_tools=[],  # No tools needed for selection
            permission_mode="bypassPermissions",
            max_turns=1,
            max_budget_usd=max_budget_usd,
            model=model,
        )

    async def select(self, prompt: str) -> tuple[list[str], ResultMessage | None, str]:
        """Run Claude Code to select which skill(s) match the prompt.

        Returns (selected_skills, result_message, text_output).
        """
        text_blocks: list[str] = []
        result_message: ResultMessage | None = None

        async for message in query(prompt=prompt, options=self.options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_blocks.append(block.text)
            elif isinstance(message, ResultMessage):
                result_message = message

        text_output = "\n".join(text_blocks)

        # Parse selected skills from output
        selected = []
        for line in text_output.splitlines():
            match = re.search(r"SELECTED_SKILL:\s*(\S+)", line)
            if match:
                skill_name = match.group(1).strip().lower()
                if skill_name in ALL_SKILLS:
                    selected.append(skill_name)

        return selected, result_message, text_output

    async def test_prompt(
        self,
        prompt: str,
        expected_skills: list[str],
        tags: list[str] | None = None,
    ) -> SkillSelectionResult:
        """Test a single prompt and return the selection result."""
        wall_start = time.monotonic()
        selected, result_msg, text_output = await self.select(prompt)
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
