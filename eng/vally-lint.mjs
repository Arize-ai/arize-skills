#!/usr/bin/env node
// Run Vally's static skill lint over every skill in skills/.
//
// Mirrors awesome-copilot's "Vally lint" quality gate
// (eng/external-plugin-quality-gates.mjs -> runVallyLintGate). Vally has no CLI
// bin, so we invoke its programmatic runLint() API directly. This is a static
// lint (spec-compliance + valid file references) — no Copilot/LLM token needed.
//
// Usage: node eng/vally-lint.mjs [skillsDir]
// Exits non-zero if any skill fails the lint.

import { runLint, LintConsoleReporter } from "@microsoft/vally";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skillsDir = path.resolve(repoRoot, process.argv[2] ?? "skills");

if (!fs.existsSync(skillsDir) || !fs.statSync(skillsDir).isDirectory()) {
  console.error(`ERROR: skills directory not found: ${skillsDir}`);
  process.exit(1);
}

const targets = fs
  .readdirSync(skillsDir)
  .filter((entry) => !entry.startsWith("."))
  .map((entry) => path.join(skillsDir, entry))
  .filter((p) => fs.statSync(p).isDirectory())
  .sort();

if (targets.length === 0) {
  console.error(`ERROR: no skill directories found in ${skillsDir}`);
  process.exit(1);
}

let anyFailure = false;
for (const target of targets) {
  const result = await runLint({ rootPath: target });
  const reporter = new LintConsoleReporter({ verbose: true });
  await reporter.report(result);
  if (!result.passed) {
    anyFailure = true;
  }
}

console.log(`\n${targets.length} skill(s) linted with Vally.`);
if (anyFailure) {
  console.error("Vally lint failed.");
  process.exit(1);
}
console.log("All skills passed Vally lint.");
