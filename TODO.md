# TODO

## Publish Phoenix skills as a separate plugin

Phoenix skills currently live in `Arize-ai/phoenix` under `.agents/skills/` and are not part of this repo. Per the multi-marketplace pivot (Claude Code, Cursor, awesome-copilot, npx skills), Phoenix should publish itself independently rather than being bundled into `arize-skills`. This keeps versioning independent, lets the Phoenix team own their plugin, and avoids cross-repo sync workflows.

The three supported Phoenix skills (per its README): `phoenix-cli`, `phoenix-evals`, `phoenix-tracing`.

### Work needed in `Arize-ai/phoenix`

1. **Add `.claude-plugin/plugin.json`** at the repo root:
   ```json
   {
     "name": "arize-phoenix",
     "version": "1.0.0",
     "description": "Phoenix skills for tracing, evaluating, and debugging LLM applications using OpenInference semantic conventions and the Phoenix CLI.",
     "author": { "name": "Arize AI", "email": "support@arize.com", "url": "https://arize.com" },
     "homepage": "https://arize.com/docs/phoenix",
     "repository": "https://github.com/Arize-ai/phoenix",
     "license": "<match phoenix LICENSE>",
     "keywords": ["phoenix", "openinference", "tracing", "evals", "llm", "observability"],
     "skills": [
       "./.agents/skills/phoenix-cli/",
       "./.agents/skills/phoenix-evals/",
       "./.agents/skills/phoenix-tracing/"
     ]
   }
   ```
   Skills are referenced from their existing `.agents/skills/` location — no file moves needed.

2. **Add `.claude-plugin/marketplace.json`** for the Claude Code marketplace listing:
   ```json
   {
     "name": "arize-phoenix",
     "metadata": { "description": "Phoenix skills for LLM tracing, evaluation, and debugging." },
     "owner": { "name": "Arize AI", "email": "support@arize.com" },
     "plugins": [
       {
         "name": "arize-phoenix",
         "source": "./",
         "description": "Phoenix skills for tracing, evaluating, and debugging LLM applications.",
         "version": "1.0.0",
         "category": "observability",
         "homepage": "https://arize.com/docs/phoenix",
         "repository": "https://github.com/Arize-ai/phoenix",
         "license": "<match phoenix LICENSE>"
       }
     ]
   }
   ```

3. **Add `.cursor-plugin/plugin.json`** at the repo root for the Cursor Marketplace. Skills auto-discover from `.agents/skills/` if that path is added, or move skills to `skills/` (Cursor's default discovery path). Easier: declare `skills` explicitly in the manifest (Cursor supports custom paths via the `skills` field).

4. **Verify SKILL.md frontmatter** for all three skills:
   - `name` and `description` must be strings
   - `name` should match the directory name (kebab-case)
   - No `metadata.internal: true` (would hide from `npx skills` default installs)

5. **Tag a release** (`v1.0.0`) so external marketplaces can pin to an immutable ref.

### Submissions (after the above lands and a tag is cut)

- **Claude Code marketplace**: usable immediately via `/plugin marketplace add Arize-ai/phoenix` + `/plugin install arize-phoenix@arize-phoenix`.
- **Cursor Marketplace**: submit at https://cursor.com/marketplace/publish.
- **awesome-copilot**: open the [external-plugin issue form](https://github.com/github/awesome-copilot/issues/new?template=external-plugin.yml) with `source: github`, `repo: Arize-ai/phoenix`, `ref: v1.0.0`, `path: ""`.
- **npx skills**: works without submission — `npx skills add Arize-ai/phoenix` discovers the three SKILL.md files automatically. Update Arize docs (https://arize.com/docs/phoenix/...) to mention it.

### Out-of-scope for this repo

- No skill bundling in `Arize-ai/arize-skills` for Phoenix. The previous `sync-to-awesome-copilot.yml` workflow that copied Phoenix skills into a PR has been deleted.
- Versioning of `arize-phoenix` is independent from `arize-skills`.

### Coordination

Ping the Phoenix team to assign ownership of this work. The plugin manifest + tag is the only blocking artifact; marketplace submissions are quick follow-ups.
