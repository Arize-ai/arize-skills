# Local quality checks — mirror the CI in .github/workflows/quality-checks.yml.
# Run `make check` before pushing to catch what the awesome-copilot quality
# gates would flag.

.PHONY: check validate-skills validate-manifests vally-lint codespell line-endings install-deps

# Everything runnable without a Node install. The Vally lint and plugin install
# smoke test run in CI (and via `make vally-lint` once dependencies are installed).
check: validate-skills validate-manifests codespell line-endings

validate-skills:
	python3 scripts/validate_skills.py

validate-manifests:
	python3 scripts/validate_manifests.py

vally-lint:
	npm install --no-save @microsoft/vally@0.10.0
	node eng/vally-lint.mjs

codespell:
	codespell

line-endings:
	bash scripts/check_line_endings.sh

install-deps:
	pip install -r scripts/requirements.txt codespell
