#!/usr/bin/env python3
"""
Tiny financial Q&A helper using the Anthropic Messages API directly (no LangChain).

Used as a stable sample app for skill / tracing experiments. Set ``ANTHROPIC_API_KEY``
in the environment. Override model with ``FINANCIAL_AGENT_MODEL`` if needed.

Examples:
  export ANTHROPIC_API_KEY=sk-ant-...
  python app.py "Should I pay down a 6% loan or invest?"
  python app.py --repl
"""

from __future__ import annotations

import argparse
import os
import sys

from anthropic import Anthropic

DEFAULT_MODEL = "claude-3-5-haiku-20241022"
SYSTEM = (
    "You are a careful personal-finance assistant. Give concise, practical guidance. "
    "If you need numbers the user did not provide, state reasonable assumptions briefly. "
    "This is educational context, not regulated financial advice."
)


def answer(client: Anthropic, question: str, model: str) -> str:
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip() or "(empty model response)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Anthropic financial Q&A")
    parser.add_argument(
        "question",
        nargs="?",
        help="Single question to answer (omit with --repl)",
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Read questions from stdin until EOF",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("FINANCIAL_AGENT_MODEL", DEFAULT_MODEL),
        help=f"Anthropic model id (default: {DEFAULT_MODEL} or FINANCIAL_AGENT_MODEL)",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = Anthropic()
    model: str = args.model

    if args.repl:
        print("Financial agent REPL (empty line to exit). Model:", model)
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                break
            print(answer(client, line, model))
            print()
        return

    if not args.question:
        parser.error("Provide a question or use --repl")
    print(answer(client, args.question, model))


if __name__ == "__main__":
    main()
