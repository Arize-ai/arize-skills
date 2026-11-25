# Starting from a built-in template

Use a built-in template when the user wants a standard judge (for example hallucination or correctness) and has not supplied a prompt. Run `ax evaluators list-templates --help` and `ax evaluators create-evaluator template --help` for flags.

1. **List the templates.** Run `ax evaluators list-templates -o json` and read every returned record before choosing. Match a template to the user's goal by its name and prompt text. When several fit, present the candidates and ask the user which one.
2. **Map it onto the create flags.** Carry the template's prompt into `--template`, its label set into `--classification-choices`, and choose `--template-name` (the eval column name) and the evaluator `--name`. Keep the `{variable}` placeholders unchanged; the task's column mappings wire them to real fields later.
3. **Create the evaluator** with `ax evaluators create-evaluator template` as in Workflow A, Step 4 (the AI integration and model are required), then continue with that workflow.

## Gotchas

- `ax evaluators list-templates` takes no `--space` and lists the built-in templates only. Check existing evaluators with `ax evaluators list --space SPACE`; evaluator names must be unique within the space.
- `--classification-choices` keys must exactly match the label strings the prompt tells the judge to return.
- `--data-granularity` (`span|trace|session`) sets the unit scored. `{conversation}` renders as the turn list only at `session` granularity; see Data Granularity in [SKILL.md](../SKILL.md).
- To change a created evaluator's prompt later, add a version with `ax evaluators create-evaluator-version template`; `ax evaluators update` changes only name and description.
