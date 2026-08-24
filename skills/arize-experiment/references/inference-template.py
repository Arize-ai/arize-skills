"""Template for scoring a dataset export against a real model API.

Usage: ax datasets export DATASET_NAME --space SPACE --stdout | python3 infer.py > runs.json

Before running: inspect the exported dataset JSON to find the correct input
field name (replace "input"/"question"/"prompt" below if needed), install the
target provider's SDK, set its API key env var, then uncomment exactly one
provider block. Never fabricate or simulate a model response.
"""

import json, sys, time

examples = json.load(sys.stdin)
runs = []

for ex in examples:
    user_input = ex.get("input") or ex.get("question") or ex.get("prompt") or str(ex)
    start = time.time()

    # === CALL THE REAL MODEL API — never fabricate/simulate. Uncomment one provider: ===
    # OpenAI (pip install openai, OPENAI_API_KEY):
    # from openai import OpenAI
    # output_text = OpenAI().chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": user_input}]).choices[0].message.content
    # Anthropic (pip install anthropic, ANTHROPIC_API_KEY):
    # import anthropic
    # output_text = anthropic.Anthropic().messages.create(model="claude-sonnet-4-6", max_tokens=1024, messages=[{"role": "user", "content": user_input}]).content[0].text
    # Google Gemini (pip install google-genai, GOOGLE_API_KEY):
    # from google import genai
    # output_text = genai.Client().models.generate_content(model="gemini-2.5-pro", contents=user_input).text
    # Custom/OpenAI-compatible proxy — Azure OpenAI, NVIDIA NIM, Ollama, etc. (pip install openai, CUSTOM_BASE_URL + CUSTOM_API_KEY):
    # from openai import OpenAI
    # import os
    # output_text = OpenAI(base_url=os.environ["CUSTOM_BASE_URL"], api_key=os.environ.get("CUSTOM_API_KEY", "none")).chat.completions.create(model=os.environ.get("CUSTOM_MODEL", "default"), messages=[{"role": "user", "content": user_input}]).choices[0].message.content

    latency_ms = round((time.time() - start) * 1000)
    runs.append({"example_id": ex["id"], "output": output_text, "metadata": {"model": "MODEL_NAME", "latency_ms": latency_ms}})
    print(f"  {ex['id']}: {latency_ms}ms", file=sys.stderr)

json.dump(runs, sys.stdout, indent=2)
