#!/usr/bin/env python3
"""Write a new template version of an Arize evaluator, changing only its template.

Dry run unless --execute. The dry run reads the current version with `ax`, checks the commit message, and prints
a unified diff of the template and every field that will be copied unchanged.

With --execute it saves the current evaluator JSON to --out-dir (for rollback), creates the version from the
current version's full template_config with the Arize SDK (the ax CLI can't set use_structured_output), reads the
evaluator back, compares every template_config field, and prints the switch time (the new version's created_at).

The commit message is the evaluator's changelog, so it must read:
  Rubric vN, YYYY-MM-DD (criterion change|judge change): what changed

--execute imports the SDK and the ax client factory, so run it with the Python that runs ax:
  "$(head -1 "$(command -v ax)" | sed 's/^#!//')" write_version.py ...

Example:
  write_version.py --space SPACE --evaluator EVALUATOR --template-file template_v3.txt \\
    --commit-message "Rubric v3, 2026-10-19 (criterion change): empty validated filters count as produced" \\
    --out-dir align/ [--execute]
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys

COMMIT_FORMAT = re.compile(r"^\s*Rubric (v[\w.]+), (\d{4}-\d{2}-\d{2}) \((criterion change|judge change)\):\s*\S")
SDK_HINT = ("--execute needs the arize SDK and the ax CLI's client factory (`ax.core.client_factory`). Run this "
            "script with the Python that runs ax: \"$(head -1 \"$(command -v ax)\" | sed 's/^#!//')\" write_version.py ...")


def run_ax(ax, args):
    proc = subprocess.run([ax] + args + ["-o", "json"], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ax {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"ax {' '.join(args)} did not return JSON; run `ax --version` and upgrade.")


def get_evaluator(a):
    ev = run_ax(a.ax, ["evaluators", "get", a.evaluator, "--space", a.space])
    ev = ev.get("data", ev)
    tc = (ev.get("version") or {}).get("template_config")
    if (ev.get("type") or "").upper() not in ("", "TEMPLATE") or not tc or "template" not in tc:
        sys.exit("The evaluator's current version has no template_config.template; only template evaluators are supported.")
    return ev


def new_config(current, template):
    """The current template_config with only the template replaced; empty LLM settings are left out, not sent as null."""
    cfg = dict(current)
    cfg["template"] = template
    cfg["llm_config"] = {k: v for k, v in (current.get("llm_config") or {}).items() if v is not None}
    return cfg


def model_settings(current):
    """Model settings the current version sets, such as temperature: every non-null entry of invocation_parameters
    and provider_parameters, including those nested in additional_properties."""
    found = {}
    for group in ("invocation_parameters", "provider_parameters"):
        params = (current.get("llm_config") or {}).get(group) or {}
        for k, v in params.items():
            if k == "additional_properties" and isinstance(v, dict):
                found.update({f"{group}.{x}": y for x, y in v.items() if y is not None})
            elif v is not None:
                found[f"{group}.{k}"] = v
    return found


def without_nulls(v):
    """A null setting and a missing one mean the same to the API, so they compare equal."""
    if isinstance(v, dict):
        return {k: without_nulls(x) for k, x in v.items() if x is not None}
    return v


def compare_fields(before, after, template):
    """Fields that differ after the write: every field must match the old version, except the template, which must
    match the new text."""
    diffs = []
    for k in sorted(set(before) | set(after)):
        want = template if k == "template" else before.get(k)
        if without_nulls(after.get(k)) != without_nulls(want):
            diffs.append(k)
    return diffs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", required=True)
    p.add_argument("--evaluator", required=True, help="Evaluator name or ID")
    p.add_argument("--template-file", required=True, help="The approved new template text")
    p.add_argument("--commit-message", required=True,
                   help="Rubric vN, YYYY-MM-DD (criterion change|judge change): what changed")
    p.add_argument("--out-dir", help="Where to save the current evaluator JSON for rollback (required with --execute)")
    p.add_argument("--ax", default="ax", help="Path to the ax binary")
    p.add_argument("--execute", action="store_true", help="Create the version (otherwise a dry run)")
    a = p.parse_args(argv)

    if not COMMIT_FORMAT.match(a.commit_message):
        sys.exit("The commit message is the changelog and must read "
                 "'Rubric vN, YYYY-MM-DD (criterion change|judge change): what changed'; got " + repr(a.commit_message))
    template = open(a.template_file).read()
    ev = get_evaluator(a)
    version = ev["version"]
    current = version["template_config"]
    if template == current["template"]:
        sys.exit("The new template is identical to the current version's; nothing to write.")

    print(f"# Evaluator `{ev.get('name')}`: new version from `{version.get('id')}` "
          f"(created {version.get('created_at')})\n")
    print(f"Commit message: {a.commit_message}\n")
    print("Copied unchanged: " + ", ".join(f"`{k}`" for k in sorted(current) if k != "template") + "\n")
    print("```diff")
    sys.stdout.writelines(difflib.unified_diff(current["template"].splitlines(True), template.splitlines(True),
                                               "current", "new"))
    print("```\n")
    settings = model_settings(current)
    if settings:
        print("**Warning: the new version won't keep the current model settings** ("
              + ", ".join(f"`{k}` = {json.dumps(v)}" for k, v in settings.items())
              + "). The Arize API drops them when a version is written, through the CLI or the SDK. "
              "After writing, set them again in the Arize UI.\n")
    if not a.execute:
        print("Dry run: nothing written. Pass --execute after the user approves this diff.")
        return 0

    if not a.out_dir:
        sys.exit("--execute needs --out-dir, to save the current version for rollback first.")
    try:
        from ax.core.client_factory import make_client
        from arize.evaluators.types import TemplateConfigInput
    except ImportError:
        sys.exit(SDK_HINT)
    os.makedirs(a.out_dir, exist_ok=True)
    rollback = os.path.join(a.out_dir, f"rollback_{version.get('id')}.json")
    with open(rollback, "w") as f:
        json.dump(ev, f, indent=1)
    print(f"Saved the current version for rollback: {rollback}")

    client, _ = make_client()
    created = client.evaluators.create_template_version(
        evaluator=ev["id"], space=ev.get("space_id") or a.space, commit_message=a.commit_message,
        template_config=TemplateConfigInput.model_validate(new_config(current, template)))
    created = created.model_dump(mode="json") if hasattr(created, "model_dump") else created

    back = get_evaluator(a)
    bv = back["version"]
    diffs = compare_fields(current, bv["template_config"], template)
    if bv.get("id") != created.get("id"):
        print(f"Warning: the evaluator resolves to `{bv.get('id')}`, not the new version `{created.get('id')}`.")
    if diffs:
        print("Read-back differs from the intended config in: " + ", ".join(f"`{k}`" for k in diffs)
              + ". Report this to the user; set any dropped setting in the Arize UI.")
    else:
        print("Read-back: every template_config field matches the previous version, and the template matches the new text.")
    print(f"New version `{created.get('id')}`. Switch time (created_at): {created.get('created_at') or bv.get('created_at')}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
