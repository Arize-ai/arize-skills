#!/usr/bin/env python3
"""
run_skill.py — Interactive skill runner for developers.

Streams Claude's output in real time as it processes a prompt through a skill's
system prompt, then saves the full session as a JSON file for later analysis.

Usage:
    python tests/run_skill.py arize-trace "Export the last 10 error traces from project my-app"
    python tests/run_skill.py arize-dataset "Create a dataset named test-data with 5 examples"
    python tests/run_skill.py arize-trace "Debug my app" --model claude-sonnet-4-6
    python tests/run_skill.py arize-link "Get a link to trace abc123" --output-dir sessions/
"""

import argparse
import asyncio
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

# Add tests/ to sys.path so harness is importable when run from the project root
_tests_dir = pathlib.Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from dotenv import load_dotenv

# Load .env from the repository root (parent of tests/)
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

from harness.result import TestResult

SKILLS_DIR = pathlib.Path(__file__).parent.parent / "skills"
AVAILABLE_SKILLS = sorted(
    d.name
    for d in SKILLS_DIR.iterdir()
    if d.is_dir() and (d / "SKILL.md").exists()
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def load_skill_prompt(skill_name: str) -> str:
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        print(
            f"Error: skill '{skill_name}' not found.\n"
            f"Available skills: {', '.join(AVAILABLE_SKILLS)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return skill_path.read_text(encoding="utf-8")


def _fmt_tool_call(tool: str, input_data: dict) -> str:
    if tool == "Bash":
        cmd = input_data.get("command", "")
        desc = input_data.get("description", "")
        return f"  $ {cmd}" + (f"  # {desc}" if desc else "")
    if tool in ("Read", "Write", "Edit"):
        path = input_data.get("file_path", input_data.get("notebook_path", ""))
        return f"  {path}"
    if tool == "Glob":
        return f"  pattern={input_data.get('pattern', '')} path={input_data.get('path', '.')}"
    if tool == "Grep":
        return f"  pattern={input_data.get('pattern', '')} in {input_data.get('path', '.')}"
    return f"  {json.dumps(input_data, ensure_ascii=False)[:160]}"


def save_session(result: TestResult, output_dir: str) -> pathlib.Path:
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out / f"session_{result.skill_name}_{ts}.json"
    path.write_text(result.to_json(), encoding="utf-8")
    return path


def _divider(width: int = 70) -> str:
    return "─" * width


def print_summary(result: TestResult, session_path: pathlib.Path) -> None:
    print(f"\n{_divider()}")
    status = "ERROR" if result.is_error else "OK"
    dur_s = result.wall_duration_ms / 1000
    cost = f"${result.total_cost_usd:.4f}" if result.total_cost_usd is not None else "n/a"
    print(f"Status:   {status}")
    print(f"Turns:    {result.num_turns}")
    print(f"Duration: {dur_s:.1f}s")
    print(f"Cost:     {cost}")
    if result.usage:
        in_tok = result.usage.get("input_tokens", 0)
        out_tok = result.usage.get("output_tokens", 0)
        cache_r = result.usage.get("cache_read_input_tokens", 0)
        print(f"Tokens:   {in_tok} in / {out_tok} out / {cache_r} cache-read")
    if result.session_id:
        print(f"Session:  {result.session_id}")
    print(f"Saved:    {session_path}")
    print(_divider())


# ── Core async runner ─────────────────────────────────────────────────────────


async def run_streaming(
    skill_name: str,
    prompt: str,
    model: str | None,
    workspace: str,
    arize_env: dict,
    max_turns: int,
    max_budget_usd: float,
) -> TestResult:
    """Run the skill and stream each message to stdout in real time."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )
    from claude_agent_sdk.types import TextBlock, ThinkingBlock, ToolUseBlock

    system_prompt = load_skill_prompt(skill_name)
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        # bypassPermissions is safe here because:
        #   1. The agent runs in a temporary workspace (tempfile.mkdtemp) that is
        #      cleaned up after execution.
        #   2. Dangerous bash commands (rm -rf, curl, etc.) are blocked via the
        #      Claude Code settings.json denylist — see the README warning.
        #   3. Arize credentials are passed explicitly via `env`; no production
        #      secrets leak through the ambient environment.
        # WARNING: Do NOT use bypassPermissions without a properly configured
        # settings.json. See README for required restrictions.
        permission_mode="bypassPermissions",
        cwd=workspace,
        env=arize_env,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        model=model,
    )

    tool_calls: list[dict] = []
    text_blocks: list[str] = []
    result_message: ResultMessage | None = None
    turn = 0

    # Print run header
    print(f"\n{_divider()}")
    print(f"Skill:  {skill_name}")
    print(f"Prompt: {prompt}")
    if model:
        print(f"Model:  {model}")
    print(f"{_divider()}\n")

    wall_start = time.monotonic()

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            turn += 1
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    print(block.text, flush=True)
                    text_blocks.append(block.text)
                elif isinstance(block, ThinkingBlock):
                    # Omit internal reasoning from stdout
                    pass
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append({"tool": block.name, "input": block.input})
                    print(f"\n[{block.name}]", flush=True)
                    print(_fmt_tool_call(block.name, block.input), flush=True)
        elif isinstance(message, ResultMessage):
            result_message = message

    wall_duration_ms = int((time.monotonic() - wall_start) * 1000)

    return TestResult(
        skill_name=skill_name,
        prompt=prompt,
        wall_duration_ms=wall_duration_ms,
        num_turns=result_message.num_turns if result_message else turn,
        total_cost_usd=result_message.total_cost_usd if result_message else None,
        usage=result_message.usage if result_message else None,
        is_error=result_message.is_error if result_message else True,
        stop_reason=result_message.stop_reason if result_message else None,
        session_id=result_message.session_id if result_message else None,
        text_output="\n".join(text_blocks),
        tool_calls=tool_calls,
        model=model or "",
    )


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an Arize skill interactively and record the session.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available skills:
  {chr(10).join('  ' + s for s in AVAILABLE_SKILLS)}

Examples:
  python tests/run_skill.py arize-trace "Export the last 10 error traces from project my-app"
  python tests/run_skill.py arize-dataset "Create a dataset named test-data with 5 examples"
  python tests/run_skill.py arize-link "Get a link to trace abc123" --output-dir sessions/
  python tests/run_skill.py arize-trace "Debug my app" --model claude-sonnet-4-6
""",
    )
    parser.add_argument("skill", help="Skill name (e.g. arize-trace, arize-dataset)")
    parser.add_argument("prompt", help="The prompt to send to the skill")
    parser.add_argument(
        "--model",
        default=None,
        help="Claude model override (e.g. claude-sonnet-4-6). Falls back to TEST_MODEL env var.",
    )
    parser.add_argument(
        "--output-dir",
        default="sessions",
        help="Directory to save the session JSON (default: sessions/)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Maximum agent turns before stopping (default: 50)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=1.0,
        help="Maximum spend in USD before stopping (default: 1.0)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Working directory for the agent (default: a temporary directory)",
    )
    args = parser.parse_args()

    # Validate environment
    arize_api_key = os.environ.get("ARIZE_API_KEY")
    arize_space_id = os.environ.get("ARIZE_SPACE_ID")
    if not arize_api_key:
        print("Error: ARIZE_API_KEY is not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)
    if not arize_space_id:
        print("Error: ARIZE_SPACE_ID is not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    arize_env = {
        "ARIZE_API_KEY": arize_api_key,
        "ARIZE_SPACE_ID": arize_space_id,
        "ARIZE_DEFAULT_PROJECT": os.environ.get("TEST_PROJECT_NAME", "skill-tests"),
        "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.local/bin"),
    }

    # Workspace: use the provided path or a temporary directory
    if args.workspace:
        workspace = args.workspace
        os.makedirs(workspace, exist_ok=True)
        cleanup = False
    else:
        workspace = tempfile.mkdtemp(prefix="arize-skill-run-")
        cleanup = True

    result: TestResult | None = None
    try:
        result = asyncio.run(
            run_streaming(
                skill_name=args.skill,
                prompt=args.prompt,
                model=args.model or os.environ.get("TEST_MODEL"),
                workspace=workspace,
                arize_env=arize_env,
                max_turns=args.max_turns,
                max_budget_usd=args.budget,
            )
        )
        session_path = save_session(result, args.output_dir)
        print_summary(result, session_path)
    finally:
        if cleanup:
            shutil.rmtree(workspace, ignore_errors=True)

    sys.exit(1 if (result is None or result.is_error) else 0)


if __name__ == "__main__":
    main()
