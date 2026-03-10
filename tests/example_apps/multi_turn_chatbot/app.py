"""
Multi-turn chatbot that produces session traces with errors.

Error modes:
1. Oversized input triggering context overflow
2. Session tracking via session.id attribute

Run: python app.py
Traces will be sent to Arize under project "skill-test-chatbot".

Prerequisites:
    ARIZE_API_KEY, ARIZE_SPACE_ID, OPENAI_API_KEY must be set.
    pip install phoenix openai openinference-instrumentation-openai
"""

import os
import uuid

from opentelemetry.trace import StatusCode, get_tracer
from phoenix.otel import register

tracer_provider = register(
    project_name="skill-test-chatbot",
    auto_instrument=True,
    endpoint="https://otlp.arize.com/v1/traces",
    headers={"space_id": os.environ["ARIZE_SPACE_ID"]},
    api_key=os.environ.get("ARIZE_API_KEY"),
)

from openai import OpenAI

tracer = get_tracer("chatbot", "1.0.0")
client = OpenAI()


def chat_turn(
    session_id: str, messages: list[dict], user_message: str
) -> str:
    with tracer.start_as_current_span("chat_turn") as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("session.id", session_id)
        span.set_attribute("input.value", user_message)

        messages.append({"role": "user", "content": user_message})

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=200,
            )
            reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})
            span.set_attribute("output.value", reply)
            return reply

        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            raise


if __name__ == "__main__":
    session_id = str(uuid.uuid4())
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Be concise.",
        }
    ]

    conversations = [
        "Hi, I need help planning a trip to Japan.",
        "What's the best time to visit?",
        "How about cherry blossom season?",
        "What cities should I visit?",
        "Can you make a detailed 14-day itinerary?" + " " * 5000,
    ]

    for msg in conversations:
        try:
            reply = chat_turn(session_id, messages, msg)
            print(f"User: {msg[:80]}...")
            print(f"Bot: {reply}\n")
        except Exception as e:
            print(f"ERROR: {e}\n")
