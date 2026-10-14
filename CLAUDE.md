# CLAUDE.md

Instructions for agents changing this repository. Skill-authoring rules live in [AGENTS.md](AGENTS.md); follow that file instead of copying them here.

## What this repo is

`skills/*/SKILL.md` files are instructions that coding agents load. They describe Arize AX workflows. They are not the platform implementation. State only capabilities the platform actually supports, and name which API surface supports them when REST and GraphQL differ.

## Checks

Run the local suite before pushing:

```bash
bash scripts/check.sh
```

That covers skill structure, manifest consistency, spelling, and LF line endings. CI also runs Vally lint and a plugin install smoke test ([quality checks](.github/workflows/quality-checks.yml)).

## Layout

- `skills/<name>/SKILL.md` — one skill per directory, at or under 500 lines. Put extra detail in `references/`.
- `scripts/validate_skills.py` and `scripts/validate_manifests.py` — structure checks.
- `version.txt` and the plugin manifests — kept in sync by release-please. Do not bump them by hand.

## Platform facts that are easy to get wrong

- A dataset eval task can target a dataset with no experiment. It uses the latest dataset version and writes label, score, and explanation columns back onto the dataset rows.
- The v2 REST API and `ax` still require `experiment_ids` when `dataset_id` is set. The GraphQL `createEvalTask` mutation does not: omit `experiments`, and pass `runContinuously: false` (`samplingRate` is required by that schema). Code evaluators on a dataset need no LLM config.
- Do not document that REST limitation as "evals cannot target a dataset."
