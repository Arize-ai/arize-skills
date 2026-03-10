"""
RAG application that produces traces with retrieval + LLM errors.

Error modes:
1. Retrieval returns empty context (simulates vector DB miss)
2. Hallucinated answers when context is empty

Run: python app.py
Traces will be sent to Arize under project "skill-test-rag-app".

Prerequisites:
    ARIZE_API_KEY, ARIZE_SPACE_ID, OPENAI_API_KEY must be set.
    pip install phoenix openai openinference-instrumentation-openai
"""

import json
import os
import random

from opentelemetry.trace import StatusCode, get_tracer
from phoenix.otel import register

tracer_provider = register(
    project_name="skill-test-rag-app",
    auto_instrument=True,
    endpoint="https://otlp.arize.com/v1/traces",
    headers={"space_id": os.environ["ARIZE_SPACE_ID"]},
    api_key=os.environ.get("ARIZE_API_KEY"),
)

from openai import OpenAI

tracer = get_tracer("rag-app", "1.0.0")
client = OpenAI()

DOCUMENTS = {
    "python": "Python is a programming language created by Guido van Rossum.",
    "javascript": "JavaScript is a scripting language for web browsers.",
    "rust": "Rust is a systems programming language focused on safety.",
}


def retrieve_context(query: str) -> str:
    """Simulated retriever — fails 30% of the time."""
    with tracer.start_as_current_span("retrieve_context") as span:
        span.set_attribute("openinference.span.kind", "RETRIEVER")
        span.set_attribute("input.value", query)

        if random.random() < 0.3:
            span.set_attribute("output.value", "")
            span.set_attribute("retrieval.documents", json.dumps([]))
            return ""

        for key, doc in DOCUMENTS.items():
            if key in query.lower():
                span.set_attribute("output.value", doc)
                return doc

        span.set_attribute("output.value", "")
        return ""


def answer_question(question: str) -> str:
    """Full RAG chain: retrieve -> generate."""
    with tracer.start_as_current_span("rag_chain") as chain_span:
        chain_span.set_attribute("openinference.span.kind", "CHAIN")
        chain_span.set_attribute("input.value", question)

        context = retrieve_context(question)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"Answer using ONLY this context: {context}. "
                        f"If context is empty, say 'I don't know'.",
                    },
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
            )
            answer = response.choices[0].message.content
        except Exception as e:
            chain_span.set_status(StatusCode.ERROR, str(e))
            chain_span.set_attribute("error.type", type(e).__name__)
            chain_span.set_attribute("error.message", str(e))
            raise

        chain_span.set_attribute("output.value", answer)
        return answer


if __name__ == "__main__":
    questions = [
        "Tell me about Python",
        "What is JavaScript?",
        "Explain quantum computing",
        "What is Rust?",
        "How does blockchain work?",
        "Tell me about Python",
        "What is machine learning?",
    ]

    for q in questions:
        try:
            answer = answer_question(q)
            print(f"Q: {q}\nA: {answer}\n")
        except Exception as e:
            print(f"Q: {q}\nERROR: {e}\n")
