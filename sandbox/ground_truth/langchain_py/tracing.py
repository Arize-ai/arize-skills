"""Arize AX tracing configuration for LangChain app."""

import os

from arize.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor

tracer_provider = register(
    space_id=os.getenv("ARIZE_SPACE_ID"),
    api_key=os.getenv("ARIZE_API_KEY"),
    project_name=os.getenv("ARIZE_PROJECT_NAME", "langchain-app"),
)

LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
