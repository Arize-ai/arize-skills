---
name: arize-evaluator-templates
description: Finds Arize's built-in LLM-as-judge evaluator templates with `ax evaluators list-templates` and turns one into a working template evaluator in a space. Use when the user asks for a built-in evaluator, a starter or prebuilt judge prompt, an evaluator template such as hallucination or correctness, list evaluator templates, or wants an evaluator without writing the judge prompt from scratch. For writing a custom judge prompt, running evaluation tasks, or code evaluators, use arize-evaluator.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.39.0) and a configured Arize profile.
---

# Arize Evaluator Templates Skill

Use a built-in template when the user wants a standard judge (for example hallucination or correctness) and has not supplied their own prompt. Use **arize-evaluator** when the user supplies the judge prompt or needs code evaluators, evaluation tasks, or column mappings.

Run `ax evaluators list-templates --help` and `ax evaluators create-evaluator template --help` for flags. This skill covers sequencing and gotchas.

## Prerequisites

Run `ax profiles show`; when no profile is active, follow the setup in **arize-evaluator**. Resolve the space with `ax spaces get SPACE_NAME`.

## Workflow

1. **List the templates.** Run `ax evaluators list-templates -o json` and read every returned record before choosing. Match a template to the user's goal by its name and prompt text. When several fit, present the candidates and ask the user which one.
2. **Adapt it to the user's data.** Map the template onto the flags of `ax evaluators create-evaluator template`: the evaluator name, the eval column name (`--template-name`), the prompt (`--template`), and `--classification-choices` when the template returns labels. Keep the template's `{variable}` placeholders unchanged; the evaluation task wires them to real span or run fields later.
3. **Pick the judge model.** `--ai-integration-id` and `--model-name` are required. Run `ax ai-integrations list` to find an integration, and follow **arize-ai-provider-integration** when none exists.
4. **Create the evaluator.** Run `ax evaluators create-evaluator template` with `--space`, a name unique within the space, and `--commit-message`. Confirm with `ax evaluators get NAME --space SPACE`.
5. **Hand off to arize-evaluator** for column mappings, backfill, and continuous runs.

## Gotchas

- Pass `--template` in single quotes in bash, with single-brace `{var}` placeholders; double quotes expand `$` and break the prompt.
- `--classification-choices` keys must exactly match the label strings the template tells the judge to return (spelling and casing). When the template output is a label, set the keys to those labels and map each to a numeric score.
- Evaluator names must be unique within the space (`--name` help); list existing evaluators with `ax evaluators list --space SPACE` before choosing one.
- Template granularity (`--data-granularity span|trace|session`) controls what unit gets scored. Choose it from the template's variables: `{conversation}` renders as the turn list only at `session` granularity (see **arize-evaluator**).
- `ax evaluators list-templates` takes no `--space`; it lists the built-in templates only, so existing evaluators come from `ax evaluators list`.
- To change a created evaluator's prompt later, add a version with `ax evaluators create-evaluator-version template`; `ax evaluators update` changes only name and description.
