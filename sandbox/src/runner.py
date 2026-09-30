"""Claude Agent SDK wrapper for running the instrumentation skill.

Security notes:
- Credentials are passed via SDK env dict (process environment), not written to disk.
- The agent is restricted to an explicit allowlist of tools (no Agent, no WebFetch, no WebSearch).
- disallowed_tools blocks network-capable tools as a defense-in-depth measure.
- max_turns caps runaway agents.
- max_budget_usd caps spend per run.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .config import get_anthropic_api_key, get_arize_api_key, get_arize_space_id

# Maximum spend per agent run (USD). Fail-safe against runaway loops.
MAX_BUDGET_USD = 2.0

# Tools the agent is allowed to use. Intentionally excludes network tools
# (WebFetch, WebSearch) and Agent (no sub-agent spawning).
ALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]

# Explicitly blocked tools — defense in depth even if permission_mode changes.
DISALLOWED_TOOLS = ["WebFetch", "WebSearch", "Agent"]


@dataclass
class RunResult:
    tool_calls: list[dict] = field(default_factory=list)
    text_output: str = ""
    cost_usd: float = 0.0
    tokens: int = 0
    duration_ms: int = 0
    num_turns: int = 0
    is_error: bool = False
    session_id: str = ""


DEFAULT_PROMPT = (
    "Instrument this Python app with Arize AX tracing. "
    "Analyze the codebase first, then implement. "
    "Use the arize-instrumentation skill in .claude/skills/arize-instrumentation/."
)


def _load_skill_prompt(workspace: Path) -> str | None:
    """Try to load the SKILL.md as additional context for the system prompt."""
    skill_md = workspace / ".claude" / "skills" / "arize-instrumentation" / "SKILL.md"
    if skill_md.exists():
        return skill_md.read_text()
    return None


async def _run_agent(
    workspace: Path,
    prompt: str = DEFAULT_PROMPT,
    verbose: bool = False,
) -> RunResult:
    """Run the Claude agent with the instrumentation skill in the sandbox workspace."""
    skill_prompt = _load_skill_prompt(workspace)
    system_prompt = skill_prompt if skill_prompt else (
        "You are an expert at adding observability instrumentation to applications. "
        "Use arize-otel and openinference to add tracing."
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        cwd=str(workspace),
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        max_turns=30,
        max_budget_usd=MAX_BUDGET_USD,
        permission_mode="acceptEdits",
        env={
            "ANTHROPIC_API_KEY": get_anthropic_api_key(),
            "ARIZE_API_KEY": get_arize_api_key(),
            "ARIZE_SPACE_ID": get_arize_space_id(),
        },
    )

    result = RunResult()
    text_parts: list[str] = []
    start_time = time.monotonic()

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    if verbose:
                        print(block.text)
                elif isinstance(block, ToolUseBlock):
                    result.tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    if verbose:
                        print(f"[tool] {block.name}")

        elif isinstance(message, ResultMessage):
            result.is_error = message.is_error
            result.num_turns = message.num_turns
            result.session_id = message.session_id
            result.cost_usd = message.total_cost_usd or 0.0
            if message.usage:
                result.tokens = (
                    message.usage.get("input_tokens", 0)
                    + message.usage.get("output_tokens", 0)
                )

    result.duration_ms = int((time.monotonic() - start_time) * 1000)
    result.text_output = "\n".join(text_parts)
    return result


def run_agent(
    workspace: Path,
    prompt: str = DEFAULT_PROMPT,
    verbose: bool = False,
) -> RunResult:
    """Synchronous entry point for running the agent."""
    return anyio.run(_run_agent, workspace, prompt, verbose)
