#!/usr/bin/env python3
"""Validate all skills in the skills/ directory.

Checks each skill directory for:
  - SKILL.md exists
  - Valid YAML frontmatter (opening and closing ---)
  - Required fields: name, description
  - Naming constraints: kebab-case, matches directory name
  - Description length: 10–500 characters
"""

import os
import re
import sys

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SKILLS_DIR = "skills"
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
MIN_DESCRIPTION_LENGTH = 10
MAX_DESCRIPTION_LENGTH = 500


def parse_frontmatter(content):
    """Return (dict, error_string). Parses YAML between opening and closing ---."""
    if not content.startswith("---"):
        return None, "missing opening '---' frontmatter delimiter"

    end = content.find("\n---", 3)
    if end == -1:
        return None, "missing closing '---' frontmatter delimiter"

    yaml_text = content[3:end].strip()
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"

    if not isinstance(data, dict):
        return None, "frontmatter must be a YAML mapping"

    return data, None


def validate_skill(skill_dir):
    """Return a list of error strings for the given skill directory."""
    errors = []
    dir_name = os.path.basename(skill_dir)
    skill_md = os.path.join(skill_dir, "SKILL.md")

    # SKILL.md must exist
    if not os.path.isfile(skill_md):
        errors.append("SKILL.md not found")
        return errors

    with open(skill_md, encoding="utf-8") as f:
        content = f.read()

    data, err = parse_frontmatter(content)
    if err:
        errors.append(err)
        return errors

    # Required fields
    for field in ("name", "description"):
        value = data.get(field)
        if value is None:
            errors.append(f"missing required field '{field}'")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"field '{field}' must be a non-empty string")

    if errors:
        return errors  # skip further checks if fields are missing

    name = data["name"].strip()
    description = data["description"].strip()

    # Naming: kebab-case
    if not NAME_PATTERN.match(name):
        errors.append(
            f"'name' must be kebab-case (lowercase letters, digits, hyphens, "
            f"starting with a letter) — got '{name}'"
        )

    # Naming: must match directory name
    if name != dir_name:
        errors.append(
            f"'name' field '{name}' must match directory name '{dir_name}'"
        )

    # Description length
    desc_len = len(description)
    if desc_len < MIN_DESCRIPTION_LENGTH:
        errors.append(
            f"'description' too short ({desc_len} chars, minimum {MIN_DESCRIPTION_LENGTH})"
        )
    if desc_len > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"'description' too long ({desc_len} chars, maximum {MAX_DESCRIPTION_LENGTH})"
        )

    return errors


def main():
    # Support running from repo root or scripts/ directory
    if not os.path.isdir(SKILLS_DIR):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.chdir(root)

    if not os.path.isdir(SKILLS_DIR):
        print(f"ERROR: '{SKILLS_DIR}/' directory not found", file=sys.stderr)
        sys.exit(1)

    skill_dirs = sorted(
        os.path.join(SKILLS_DIR, entry)
        for entry in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, entry))
        and not entry.startswith(".")
    )

    if not skill_dirs:
        print(f"WARNING: no skill directories found in '{SKILLS_DIR}/'")
        sys.exit(0)

    all_errors = []
    for skill_dir in skill_dirs:
        errors = validate_skill(skill_dir)
        label = "OK  " if not errors else "FAIL"
        print(f"  {label}  {skill_dir}")
        for error in errors:
            print(f"        {error}")
        all_errors.extend(
            f"{skill_dir}: {e}" for e in errors
        )

    print()
    if all_errors:
        print(f"{len(all_errors)} error(s) found.")
        sys.exit(1)
    else:
        print(f"All {len(skill_dirs)} skill(s) valid.")


if __name__ == "__main__":
    main()
