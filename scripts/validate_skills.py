#!/usr/bin/env python3
"""Validate all skills in the skills/ directory.

Mirrors the structural checks awesome-copilot runs in `eng/validate-skills.mjs`
(the "Skill validation" quality gate) plus this repo's authoring rules in
AGENTS.md. Content-quality linting is handled separately by Vally
(see eng/vally-lint.mjs).

Checks each skill directory for:
  - SKILL.md exists
  - Valid YAML frontmatter (opening and closing ---)
  - Required fields: name, description
  - name: kebab-case, 3-64 chars, matches directory name, unique across skills
  - description length: 10-500 characters
  - assets (if present): each path resolves inside the skill dir and is <= 5 MB
  - Markdown links with relative targets resolve to existing files
  - SKILL.md is <= 500 lines (spec / AGENTS.md guidance)

Warnings (non-blocking):
  - Bare relative doc paths (e.g. references/FOO.md) in prose that should be
    Markdown links per AGENTS.md
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
MIN_NAME_LENGTH = 3
MAX_NAME_LENGTH = 64
MIN_DESCRIPTION_LENGTH = 10
MAX_DESCRIPTION_LENGTH = 500
MAX_ASSET_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_SKILL_LINES = 500

# Markdown inline link: [text](target)
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Fenced code block delimiters (``` or ~~~)
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
# Inline code spans (`...`)
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
# Bare reference to a doc under references/ (used for the AGENTS.md warning)
BARE_REF_PATTERN = re.compile(r"(?<![\(/\w.])references/[\w./-]+")
# Targets we never treat as local file references
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")


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


def strip_code(content):
    """Return content with fenced code blocks and inline code spans removed.

    Used so prose-only heuristics (the bare-path warning) don't flag literal
    commands or code samples.
    """
    lines = []
    in_fence = False
    for line in content.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lines.append(INLINE_CODE_PATTERN.sub("", line))
    return "\n".join(lines)


def check_links(skill_dir, content):
    """Return error strings for Markdown links whose relative target is missing."""
    errors = []
    for target in LINK_PATTERN.findall(content):
        target = target.strip()
        # A link may be "path "title"" — drop any title component.
        target = target.split()[0] if target else target
        if not target or target.lower().startswith(EXTERNAL_LINK_PREFIXES):
            continue
        if target.startswith("/"):
            continue  # absolute paths are out of scope
        # Strip anchor / query fragments before resolving on disk.
        path_part = re.split(r"[#?]", target, maxsplit=1)[0]
        if not path_part:
            continue
        resolved = os.path.normpath(os.path.join(skill_dir, path_part))
        if not os.path.exists(resolved):
            errors.append(f"broken relative link: [...]({target}) -> missing '{path_part}'")
    return errors


def check_assets(skill_dir, data):
    """Return error strings for declared assets that are missing or too large."""
    errors = []
    assets = data.get("assets")
    if assets is None:
        return errors
    if not isinstance(assets, list):
        return ["frontmatter 'assets' must be a list"]
    for asset in assets:
        if not isinstance(asset, str) or not asset.strip():
            errors.append(f"'assets' entry must be a non-empty string — got {asset!r}")
            continue
        resolved = os.path.normpath(os.path.join(skill_dir, asset))
        # Keep assets inside the skill directory.
        if os.path.relpath(resolved, skill_dir).startswith(".."):
            errors.append(f"asset '{asset}' resolves outside the skill directory")
            continue
        if not os.path.isfile(resolved):
            errors.append(f"asset '{asset}' not found")
            continue
        size = os.path.getsize(resolved)
        if size > MAX_ASSET_BYTES:
            errors.append(
                f"asset '{asset}' is {size / 1024 / 1024:.1f} MB "
                f"(maximum {MAX_ASSET_BYTES / 1024 / 1024:.0f} MB)"
            )
    return errors


def check_bare_paths(content):
    """Return warning strings for bare references/ paths that should be links."""
    warnings = []
    prose = strip_code(content)
    # Remove markdown-link targets so genuine links aren't flagged.
    prose = LINK_PATTERN.sub("", prose)
    seen = set()
    for match in BARE_REF_PATTERN.findall(prose):
        if match not in seen:
            seen.add(match)
            warnings.append(
                f"bare path '{match}' in prose — use a Markdown link per AGENTS.md"
            )
    return warnings


def validate_skill(skill_dir):
    """Return (name, errors, warnings) for the given skill directory."""
    errors = []
    warnings = []
    dir_name = os.path.basename(skill_dir)
    skill_md = os.path.join(skill_dir, "SKILL.md")

    # SKILL.md must exist
    if not os.path.isfile(skill_md):
        errors.append("SKILL.md not found")
        return None, errors, warnings

    with open(skill_md, encoding="utf-8") as f:
        content = f.read()

    data, err = parse_frontmatter(content)
    if err:
        errors.append(err)
        return None, errors, warnings

    # Required fields
    for field in ("name", "description"):
        value = data.get(field)
        if value is None:
            errors.append(f"missing required field '{field}'")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"field '{field}' must be a non-empty string")

    if errors:
        return None, errors, warnings  # skip further checks if fields are missing

    name = data["name"].strip()
    description = data["description"].strip()

    # Naming: kebab-case
    if not NAME_PATTERN.match(name):
        errors.append(
            f"'name' must be kebab-case (lowercase letters, digits, hyphens, "
            f"starting with a letter) — got '{name}'"
        )

    # Naming: length
    if not MIN_NAME_LENGTH <= len(name) <= MAX_NAME_LENGTH:
        errors.append(
            f"'name' must be {MIN_NAME_LENGTH}-{MAX_NAME_LENGTH} chars "
            f"(got {len(name)})"
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

    # SKILL.md length
    line_count = content.count("\n") + 1
    if line_count > MAX_SKILL_LINES:
        errors.append(
            f"SKILL.md is {line_count} lines (maximum {MAX_SKILL_LINES}); "
            f"move detail into references/"
        )

    errors.extend(check_assets(skill_dir, data))
    errors.extend(check_links(skill_dir, content))
    warnings.extend(check_bare_paths(content))

    return name, errors, warnings


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
    all_warnings = []
    names_seen = {}  # lower-cased name -> first skill dir that used it

    for skill_dir in skill_dirs:
        name, errors, warnings = validate_skill(skill_dir)

        # Duplicate name detection (case-insensitive) across all skills.
        if name is not None:
            key = name.lower()
            if key in names_seen:
                errors.append(
                    f"duplicate skill name '{name}' (also used by '{names_seen[key]}')"
                )
            else:
                names_seen[key] = skill_dir

        label = "OK  " if not errors else "FAIL"
        print(f"  {label}  {skill_dir}")
        for error in errors:
            print(f"        ERROR: {error}")
        for warning in warnings:
            print(f"        WARN:  {warning}")
        all_errors.extend(f"{skill_dir}: {e}" for e in errors)
        all_warnings.extend(f"{skill_dir}: {w}" for w in warnings)

    print()
    if all_warnings:
        print(f"{len(all_warnings)} warning(s).")
    if all_errors:
        print(f"{len(all_errors)} error(s) found.")
        sys.exit(1)
    print(f"All {len(skill_dirs)} skill(s) valid.")


if __name__ == "__main__":
    main()
