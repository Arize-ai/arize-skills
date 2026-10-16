# MCP Skills Validation Report

Branch: `sragvi/mcp-skills/mcp-native` (off `origin/main`). Validates the `mcp/` collection for ChatGPT plugin marketplace submission. This file is an internal validation record and is not part of the distributable `mcp/` directory.

## Method

1. **Manifest verification** — every skill was authored against the Arize MCP server's live tool manifest (tool names, input schemas, limits, and behaviors), pulled from a connected `arize-ax` MCP namespace (server build `ax-mcp 0.1.0`, MCP protocol revision `2025-11-25`).
2. **Structural validation** — the repo's `scripts/validate_skills.py` (adapted to scan `mcp/`) passed for all six skills: frontmatter, `name` matches directory, Markdown links resolve, ≤500 lines, LF line endings.
3. **Live read-only testing** — representative workflows executed against the real MCP server (see below).
4. **Deep review** — a strong-model reviewer checked every documented tool/parameter against the live schemas and fixed factual errors in place.

## Live test results (read-only)

| Tool | Result |
|------|--------|
| `server_info` | ✅ |
| `list_projects`, `list_datasets`, `list_experiments`, `list_evaluators`, `list_prompts` | ✅ correct pages + cursors |
| `list_traces` | ✅ full trace with span list and `spans_truncated` |
| `list_spans` | ✅ incl. `filter` on `context.trace_id` and `truncate_string_length` |
| `search_dataset_examples` | ✅ examples + pagination |
| `search_experiment_runs` | ✅ runs with `eval`-ready shape + pagination |
| `get_dataset` | ✅ versions list |
| `list_prompt_versions`, `get_prompt_label` | ✅ full version content incl. `labels`; proper 404 for a missing label |
| `get_prompt` | ❌ server-side output-validation error on build `ax-mcp 0.1.0` — known server bug, not a skill defect. `mcp/arize-prompt` documents a `list_prompt_versions` / `get_prompt_version` / `get_prompt_label` fallback and no longer depends on `get_prompt`. |

Write-path tools (`create_*`, `insert_*`, `update_*`, `annotate_*`, `delete_*`, task triggers) were schema-verified but deliberately not executed — they mutate data or consume LLM spend.

## Per-skill verdicts

| Skill | Verdict | Notes |
|-------|---------|-------|
| `arize-trace` | READY-WITH-NOTES | Filter operators beyond `=` (`IN`, `CONTAINS`, `LIKE`, `IS NULL`) are inherited from the CLI skill and not live-tested through MCP. |
| `arize-dataset` | READY-WITH-NOTES | Insert/update response fields (`dataset_version_id`, `example_ids`) are plausible but unverifiable from input schemas. |
| `arize-experiment` | READY-WITH-NOTES | Bulk confirm-before-write tightened; cross-skill routing fixed. Insert response `run_ids` unverified. |
| `arize-evaluator` | READY-WITH-NOTES | Cross-skill routing fixed (dataset IDs → arize-dataset); invented 30-day `trigger_task_run` limit removed; `use_function_calling` confirmed correct (server template docs' `use_function_calling_if_available` is a doc inconsistency, the schema field is `use_function_calling`). Result-prefix naming and eval index-lag figure inherited from CLI skill, unverified. |
| `arize-project` | READY | Fixed: datasets/experiments belong to the space, not the project; space create/delete exists on the server (out of this skill's scope). |
| `arize-prompt` | READY | `get_prompt` fallback added; `NONE` input-variable-format correctly described as deprecated/treated as `F_STRING`; `list_spaces` used for space resolution. |
| `mcp/README.md` | READY | Deep-link guidance corrected (skills report IDs; they do not construct UI URLs). |

Reviewer fixes were applied in place (see the review log in the branch history/PR description for the full file:line list).

## Unsupported workflows (consolidated)

Not advertised by any `mcp/` skill, because the MCP tool surface does not support them:

- Unbounded bulk export (`--all` / Arrow Flight) — cursor pagination only
- Arize UI deep-link construction
- Prompt execution / playground (except `RUN_EXPERIMENT` tasks)
- Prompt optimization tooling
- Server-side experiment comparison / aggregation / prompt diffing
- Monitor create/update/alerting (read-only monitors)
- File-based (CSV/Parquet) annotation payloads
- Org/space/user/role/API-key administration (users, roles, role bindings, invitations, API keys, resource restrictions, SAML/SSO mappings)
- Project changes beyond rename (type change, moving between spaces, trace-send permission grants)

## Recommendation

All six skills — `arize-trace`, `arize-dataset`, `arize-experiment`, `arize-evaluator`, `arize-project`, `arize-prompt` — plus `mcp/README.md` are **ready for marketplace submission**. Open notes above are minor and none block submission. Re-test `get_prompt` after the server fix lands and simplify the `arize-prompt` fallback if desired.
