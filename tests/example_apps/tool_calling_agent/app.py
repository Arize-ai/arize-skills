"""
Tool-calling agent that produces traces with tool execution errors.

Error modes:
1. Tool raises ValueError on certain inputs (rate > 1)
2. Tool returns malformed JSON for user IDs starting with "bad_"
3. Agent loop exceeds max iterations

Run: python app.py
Traces will be sent to Arize under project "skill-test-tool-agent".

Prerequisites:
    ARIZE_API_KEY, ARIZE_SPACE_ID, OPENAI_API_KEY must be set.
    pip install phoenix openai openinference-instrumentation-openai
"""

import json
import os

from opentelemetry.trace import StatusCode, get_tracer
from phoenix.otel import register

tracer_provider = register(
    project_name="skill-test-tool-agent",
    auto_instrument=True,
    endpoint="https://otlp.arize.com/v1/traces",
    headers={"space_id": os.environ["ARIZE_SPACE_ID"]},
    api_key=os.environ.get("ARIZE_API_KEY"),
)

from openai import OpenAI

tracer = get_tracer("tool-agent", "1.0.0")
client = OpenAI()

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "calculate_loan_payment",
            "description": "Calculate monthly loan payment",
            "parameters": {
                "type": "object",
                "properties": {
                    "principal": {"type": "number"},
                    "rate": {
                        "type": "number",
                        "description": "Annual rate as decimal",
                    },
                    "years": {"type": "integer"},
                },
                "required": ["principal", "rate", "years"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_credit_score",
            "description": "Check credit score for a user",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
]


def calculate_loan_payment(principal: float, rate: float, years: int) -> str:
    """Intentionally buggy: fails if rate > 1 (not normalized)."""
    if rate > 1:
        raise ValueError(
            f"Rate {rate} is > 1. Expected decimal form (e.g., 0.05 for 5%)."
        )
    if years <= 0:
        raise ValueError("Years must be positive.")
    monthly_rate = rate / 12
    num_payments = years * 12
    payment = principal * (monthly_rate * (1 + monthly_rate) ** num_payments) / (
        (1 + monthly_rate) ** num_payments - 1
    )
    return json.dumps({"monthly_payment": round(payment, 2)})


def check_credit_score(user_id: str) -> str:
    """Intentionally buggy: returns malformed JSON for certain user IDs."""
    if user_id.startswith("bad_"):
        return '{"user_id": "' + user_id + '", "score": 750'
    return json.dumps({"user_id": user_id, "score": 720, "tier": "good"})


TOOL_MAP = {
    "calculate_loan_payment": calculate_loan_payment,
    "check_credit_score": check_credit_score,
}


def run_agent(user_message: str, max_iterations: int = 5) -> str:
    with tracer.start_as_current_span("agent_run") as chain_span:
        chain_span.set_attribute("openinference.span.kind", "CHAIN")
        chain_span.set_attribute("input.value", user_message)

        messages = [
            {
                "role": "system",
                "content": "You are a loan advisor. Use tools to help users.",
            },
            {"role": "user", "content": user_message},
        ]

        for iteration in range(max_iterations):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS_SPEC,
            )

            choice = response.choices[0]
            if choice.finish_reason == "stop":
                final = choice.message.content
                chain_span.set_attribute("output.value", final)
                return final

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    with tracer.start_as_current_span(
                        tc.function.name
                    ) as tool_span:
                        tool_span.set_attribute(
                            "openinference.span.kind", "TOOL"
                        )
                        tool_span.set_attribute(
                            "input.value", tc.function.arguments
                        )

                        try:
                            fn = TOOL_MAP[tc.function.name]
                            args = json.loads(tc.function.arguments)
                            result = fn(**args)
                            tool_span.set_attribute("output.value", result)
                        except Exception as e:
                            error_msg = f"Error: {type(e).__name__}: {e}"
                            tool_span.set_attribute("output.value", error_msg)
                            tool_span.set_status(StatusCode.ERROR, str(e))
                            tool_span.set_attribute(
                                "error.type", type(e).__name__
                            )
                            tool_span.set_attribute("error.message", str(e))
                            result = error_msg

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            }
                        )

        chain_span.set_status(StatusCode.ERROR, "Max iterations exceeded")
        chain_span.set_attribute(
            "output.value", "Error: max iterations exceeded"
        )
        return "Error: agent could not complete the task."


if __name__ == "__main__":
    scenarios = [
        "What would my monthly payment be for a $300,000 loan at 5% for 30 years?",
        "Calculate loan for $200,000 at 7% interest over 15 years.",
        "Check the credit score for user bad_user_123.",
        "Check credit score for user_456 and suggest a loan amount.",
    ]

    for scenario in scenarios:
        print(f"\n{'=' * 60}")
        print(f"User: {scenario}")
        try:
            result = run_agent(scenario)
            print(f"Agent: {result}")
        except Exception as e:
            print(f"CRASH: {e}")
