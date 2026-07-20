#!/usr/bin/env python3
"""Validate plugin manifest consistency and metadata constraints.

Mirrors awesome-copilot's version-match gate (`external-plugin-quality-gates.mjs`)
and plugin/manifest validation (`external-plugin-validation.mjs`). This catches
the kind of finding that flags an external-plugin submission with
`requires-submitter-fixes` before we ever open the intake issue.

`version.txt` is the single source of truth (release-please bumps it first, then
propagates it into the JSON manifests via `release-please-config.json`).

Checks:
  - version.txt matches $.version in plugin.json, .claude-plugin/plugin.json,
    .cursor-plugin/plugin.json; $.plugins[0].version in
    .claude-plugin/marketplace.json; and the "." entry in
    .release-please-manifest.json
  - shared metadata (name, description, keywords, license, repository, homepage)
    is identical across the plugin manifests
  - metadata constraints: name <= 50 chars & lowercase-hyphen; description
    <= 500 chars; version <= 100 chars; keywords 1-10 entries, each
    lowercase/digits/hyphens & <= 30 chars; repository is an https github.com
    URL; license is non-empty
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VERSION_FILE = "version.txt"

# (path, jsonpath-ish accessor, human label) for every place a version lives.
VERSION_LOCATIONS = [
    ("plugin.json", ("version",), "$.version"),
    (".claude-plugin/plugin.json", ("version",), "$.version"),
    (".cursor-plugin/plugin.json", ("version",), "$.version"),
    (".claude-plugin/marketplace.json", ("plugins", 0, "version"), "$.plugins[0].version"),
    (".release-please-manifest.json", (".",), '$["."]'),
]

# Manifests whose shared metadata must agree. Each entry maps a canonical field
# name to the accessor path within that file.
METADATA_MANIFESTS = [
    ("plugin.json", {
        "name": ("name",),
        "description": ("description",),
        "keywords": ("keywords",),
        "license": ("license",),
        "repository": ("repository",),
        "homepage": ("homepage",),
    }),
    (".claude-plugin/plugin.json", {
        "name": ("name",),
        "description": ("description",),
        "keywords": ("keywords",),
        "license": ("license",),
        "repository": ("repository",),
        "homepage": ("homepage",),
    }),
    (".cursor-plugin/plugin.json", {
        "name": ("name",),
        "description": ("description",),
        "keywords": ("keywords",),
        "license": ("license",),
        "repository": ("repository",),
        "homepage": ("homepage",),
    }),
    (".claude-plugin/marketplace.json", {
        "name": ("plugins", 0, "name"),
        "description": ("plugins", 0, "description"),
        "keywords": ("plugins", 0, "keywords"),
        "license": ("plugins", 0, "license"),
        "repository": ("plugins", 0, "repository"),
        "homepage": ("plugins", 0, "homepage"),
    }),
]

NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
KEYWORD_PATTERN = re.compile(r"^[a-z0-9-]+$")
GITHUB_REPO_PATTERN = re.compile(r"^https://github\.com/[^/]+/[^/]+/?$")

MAX_NAME_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 500
MAX_VERSION_LENGTH = 100
MAX_KEYWORDS = 10
MIN_KEYWORDS = 1
MAX_KEYWORD_LENGTH = 30


def load_json(rel_path, errors):
    path = os.path.join(REPO_ROOT, rel_path)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        errors.append(f"{rel_path}: file not found")
    except json.JSONDecodeError as exc:
        errors.append(f"{rel_path}: invalid JSON: {exc}")
    return None


def dig(data, accessor):
    """Walk a (key/index, ...) accessor path; return (value, found)."""
    cur = data
    for step in accessor:
        try:
            cur = cur[step]
        except (KeyError, IndexError, TypeError):
            return None, False
    return cur, True


def check_versions(errors):
    version_path = os.path.join(REPO_ROOT, VERSION_FILE)
    try:
        with open(version_path, encoding="utf-8") as f:
            source_version = f.read().strip()
    except FileNotFoundError:
        errors.append(f"{VERSION_FILE}: file not found (source of truth for version)")
        return None

    if not source_version:
        errors.append(f"{VERSION_FILE}: is empty")
        return None

    if len(source_version) > MAX_VERSION_LENGTH:
        errors.append(
            f"{VERSION_FILE}: version '{source_version}' exceeds "
            f"{MAX_VERSION_LENGTH} chars"
        )

    for rel_path, accessor, label in VERSION_LOCATIONS:
        data = load_json(rel_path, errors)
        if data is None:
            continue
        value, found = dig(data, accessor)
        if not found:
            errors.append(f"{rel_path}: missing {label}")
        elif value != source_version:
            errors.append(
                f"{rel_path}: {label} is '{value}' but {VERSION_FILE} is "
                f"'{source_version}'"
            )

    return source_version


def check_metadata_consistency(errors):
    """Ensure shared metadata fields agree across manifests; return canonical values."""
    # field -> list of (rel_path, value)
    collected = {}
    for rel_path, field_map in METADATA_MANIFESTS:
        data = load_json(rel_path, errors)
        if data is None:
            continue
        for field, accessor in field_map.items():
            value, found = dig(data, accessor)
            if not found:
                errors.append(f"{rel_path}: missing metadata field '{field}'")
                continue
            collected.setdefault(field, []).append((rel_path, value))

    canonical = {}
    for field, entries in collected.items():
        first_path, first_value = entries[0]
        canonical[field] = first_value
        for rel_path, value in entries[1:]:
            if value != first_value:
                errors.append(
                    f"metadata '{field}' mismatch: {first_path}={first_value!r} "
                    f"vs {rel_path}={value!r}"
                )
    return canonical


def check_metadata_constraints(meta, errors):
    name = meta.get("name")
    if isinstance(name, str):
        if len(name) > MAX_NAME_LENGTH:
            errors.append(f"name '{name}' exceeds {MAX_NAME_LENGTH} chars")
        if not NAME_PATTERN.match(name):
            errors.append(f"name '{name}' must be lowercase letters, digits, hyphens")
    elif name is not None:
        errors.append("name must be a string")

    description = meta.get("description")
    if isinstance(description, str):
        if len(description) > MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"description exceeds {MAX_DESCRIPTION_LENGTH} chars "
                f"({len(description)})"
            )
    elif description is not None:
        errors.append("description must be a string")

    license_ = meta.get("license")
    if not (isinstance(license_, str) and license_.strip()):
        errors.append("license must be a non-empty string")

    repository = meta.get("repository")
    if isinstance(repository, str):
        if not GITHUB_REPO_PATTERN.match(repository):
            errors.append(
                f"repository '{repository}' must be an https://github.com/owner/repo URL"
            )
    elif repository is not None:
        errors.append("repository must be a string")

    keywords = meta.get("keywords")
    if isinstance(keywords, list):
        if not MIN_KEYWORDS <= len(keywords) <= MAX_KEYWORDS:
            errors.append(
                f"keywords must have {MIN_KEYWORDS}-{MAX_KEYWORDS} entries "
                f"(got {len(keywords)})"
            )
        for kw in keywords:
            if not isinstance(kw, str) or not KEYWORD_PATTERN.match(kw):
                errors.append(f"keyword {kw!r} must be lowercase letters, digits, hyphens")
            elif len(kw) > MAX_KEYWORD_LENGTH:
                errors.append(f"keyword '{kw}' exceeds {MAX_KEYWORD_LENGTH} chars")
    elif keywords is not None:
        errors.append("keywords must be a list")


def main():
    errors = []

    version = check_versions(errors)
    if version:
        print(f"  version.txt = {version}")

    meta = check_metadata_consistency(errors)
    check_metadata_constraints(meta, errors)

    print()
    if errors:
        for error in errors:
            print(f"  ERROR: {error}")
        print()
        print(f"{len(errors)} error(s) found.")
        sys.exit(1)
    print("All manifests consistent and valid.")


if __name__ == "__main__":
    main()
