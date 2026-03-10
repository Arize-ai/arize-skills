"""
Test cases for the arize-instrumentation skill.

Verifies that Claude can analyze a codebase and produce correct
instrumentation code. Runs in isolated tmp_path workspaces.
"""

import os

import pytest

from conftest import make_runner
from harness.verifier import (
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
    ToolWasCalledVerifier,
)


@pytest.fixture
def instrumentation_runner(workspace, arize_env, test_model):
    return make_runner(
        "arize-instrumentation",
        workspace,
        arize_env,
        test_model,
        max_turns=60,
        max_budget_usd=2.0,
    )


def write_sample_openai_app(workspace: str) -> None:
    """Write a minimal OpenAI app to the workspace for instrumentation."""
    os.makedirs(os.path.join(workspace, "src"), exist_ok=True)

    with open(os.path.join(workspace, "requirements.txt"), "w") as f:
        f.write("openai>=1.0\n")

    with open(os.path.join(workspace, "src", "app.py"), "w") as f:
        f.write(
            '''import os
from openai import OpenAI

client = OpenAI()

def ask(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    print(ask("Hello!"))
'''
        )


def write_sample_tool_calling_app(workspace: str) -> None:
    """Write an app with tool/function calling for instrumentation."""
    with open(os.path.join(workspace, "requirements.txt"), "w") as f:
        f.write("anthropic>=0.30\n")

    with open(os.path.join(workspace, "agent.py"), "w") as f:
        f.write(
            '''import json
import anthropic

client = anthropic.Anthropic()

tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    }
]

def get_weather(location: str) -> str:
    return json.dumps({"temp": 72, "condition": "sunny", "location": location})

def run_agent(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            return response.content[0].text
        for block in response.content:
            if block.type == "tool_use":
                result = get_weather(block.input["location"])
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result",
                                 "tool_use_id": block.id,
                                 "content": result}]
                })

if __name__ == "__main__":
    print(run_agent("What\'s the weather in SF?"))
'''
        )


class TestInstrumentationPhase1Analysis:
    """Phase 1 only: analyze a codebase and report findings."""

    @pytest.mark.asyncio
    async def test_analyze_openai_app(
        self, instrumentation_runner, workspace, test_report
    ):
        write_sample_openai_app(workspace)

        result = await instrumentation_runner.run(
            "Analyze this codebase for Arize instrumentation. "
            "Only do Phase 1 (analysis) -- do NOT implement anything yet."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Read", "Glob"]),
            OutputContainsVerifier(["openai", "python"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestInstrumentationFullFlow:
    """Full Phase 1 + Phase 2 instrumentation."""

    @pytest.mark.asyncio
    async def test_instrument_openai_app(
        self, instrumentation_runner, workspace, test_report
    ):
        write_sample_openai_app(workspace)

        result = await instrumentation_runner.run(
            "Instrument this codebase with Arize AX tracing. "
            "Do both Phase 1 (analysis) and Phase 2 (implementation). "
            "Proceed with Phase 2 without waiting for my confirmation."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Read", "Glob"]),
            OutputContainsVerifier(["openai", "register"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "instrumentation"]
        test_report.add(result)
        assert result.passed


class TestInstrumentationToolCalling:
    """Instrument an app with tool calling -- should add CHAIN + TOOL spans."""

    @pytest.mark.asyncio
    async def test_instrument_tool_calling_app(
        self, instrumentation_runner, workspace, test_report
    ):
        write_sample_tool_calling_app(workspace)

        result = await instrumentation_runner.run(
            "Instrument this Anthropic agent with Arize AX tracing. "
            "Proceed through both phases without waiting for confirmation."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            ToolWasCalledVerifier(["Read"]),
            OutputContainsVerifier(["CHAIN", "TOOL", "anthropic"]),
        )
        result.verification = verifier.verify(result)
        result.tags = ["e2e", "instrumentation", "tool-calling"]
        test_report.add(result)
        assert result.passed
