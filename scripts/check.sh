#!/usr/bin/env bash
# Run the local quality checks (see AGENTS.md): skill validation, manifest
# validation, spelling, and line endings. The Vally lint and plugin install
# smoke test need Node and run in CI (or run them manually — see AGENTS.md).
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "==> validate skills"
python3 scripts/validate_skills.py

echo "==> validate manifests"
python3 scripts/validate_manifests.py

echo "==> codespell"
codespell

echo "==> line endings"
bash scripts/check_line_endings.sh

echo "All local quality checks passed."
