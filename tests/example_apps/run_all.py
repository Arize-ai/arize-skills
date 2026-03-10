"""
Run all example faulty applications to generate traces in Arize.

Run once before the test suite to populate Arize projects with trace data.

Usage:
    python tests/example_apps/run_all.py

Prerequisites:
    ARIZE_API_KEY, ARIZE_SPACE_ID, and OPENAI_API_KEY must be set (or in .env).
    pip install -r tests/example_apps/requirements.txt
"""

import os
import subprocess
import sys
import time

APPS = [
    ("openai_rag_app", "app.py"),
    ("tool_calling_agent", "app.py"),
    ("multi_turn_chatbot", "app.py"),
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_app(app_dir: str, script: str) -> bool:
    full_path = os.path.join(SCRIPT_DIR, app_dir, script)
    print(f"\n{'=' * 60}")
    print(f"Running: {app_dir}/{script}")
    print(f"{'=' * 60}")

    result = subprocess.run(
        [sys.executable, full_path],
        cwd=os.path.join(SCRIPT_DIR, app_dir),
        timeout=120,
    )
    success = result.returncode == 0
    print(f"Result: {'OK' if success else 'FAILED'}")
    return success


if __name__ == "__main__":
    results = []
    for app_dir, script in APPS:
        try:
            ok = run_app(app_dir, script)
            results.append((app_dir, ok))
        except Exception as e:
            print(f"CRASH: {e}")
            results.append((app_dir, False))

    print(f"\n{'=' * 60}")
    print("Summary:")
    for app_dir, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {app_dir}")

    print("\nWaiting 30 seconds for trace ingestion...")
    time.sleep(30)
    print("Done. Traces should be available in Arize.")
