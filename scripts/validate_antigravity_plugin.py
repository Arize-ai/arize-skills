#!/usr/bin/env python3
"""Pre-flight check for the Antigravity plugin, based on the Antigravity
Plugin Marketplace Publishing Guide. Run from the repo root:

    python3 scripts/validate_antigravity_plugin.py [plugin-root]

Exits 1 on any error. Warnings do not fail the run. This is not a
replacement for `agy plugin validate`; run both.
"""
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")
RUNTIME_VARS = {"PLUGIN_ROOT", "PLUGIN_DATA"}
SKILL_KEYS = {"name", "description", "license", "compatibility"}

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def frontmatter(text):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    out = {}
    key = None
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        if line[0] not in " \t" and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            out[key] = val.strip().strip('"').strip("'")
        elif key:
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def main(root):
    root = Path(root).resolve()
    manifest_path = root / ".antigravity-plugin" / "plugin.json"
    if not manifest_path.exists():
        manifest_path = root / "plugin.json"
    if not manifest_path.exists():
        err("No plugin.json at root or .antigravity-plugin/")
        return
    print(f"Manifest: {manifest_path.relative_to(root)}")
    m = json.loads(manifest_path.read_text())

    # Core fields
    name = m.get("name", "")
    if not NAME_RE.match(name) or not 1 <= len(name) <= 64:
        err(f"name '{name}' is not kebab-case 1-64 chars")
    if name != root.name:
        warn(f"name '{name}' does not match directory '{root.name}' (the guide requires a match)")
    desc = m.get("description", "")
    if not desc:
        err("description missing")
    elif not 120 <= len(desc) <= 160:
        warn(f"description is {len(desc)} chars; 120-160 recommended")

    # Marketplace-required fields
    for f in ("displayName", "logo", "suggestedPrompts", "version", "author"):
        if not m.get(f):
            err(f"{f} missing (required for Marketplace)")
    dn = m.get("displayName", "")
    if re.search(r"\b(plugin|mcp)\b", dn, re.I):
        warn(f"displayName '{dn}' contains 'Plugin' or 'MCP'; the guide says omit these")
    if not re.match(r"^\d+\.\d+\.\d+$", m.get("version", "")):
        err("version is not MAJOR.MINOR.PATCH")
    prompts = [p for p in m.get("suggestedPrompts", []) if p]
    if len(prompts) > 3:
        warn(f"{len(prompts)} suggestedPrompts; only the first 3 are shown")
    for f in ("homepage", "license", "keywords", "category"):
        if not m.get(f):
            warn(f"{f} missing (recommended)")
    kw = m.get("keywords") or m.get("tags") or []
    if any(k != k.lower() for k in kw):
        warn("keywords should be lowercase")

    # Logo
    logo = m.get("logo", "")
    if logo and not logo.startswith("https://"):
        lp = root / logo
        if not lp.exists():
            err(f"logo file {logo} not found")
        elif "PLACEHOLDER" in lp.read_text(errors="ignore"):
            warn("logo is still the placeholder; swap in the brand-approved mark")

    # Nothing but plugin.json inside .antigravity-plugin/
    dot = root / ".antigravity-plugin"
    if dot.exists():
        extra = [p.name for p in dot.iterdir() if p.name != "plugin.json"]
        if extra:
            err(f".antigravity-plugin/ must only hold plugin.json; found {extra}")

    # README
    if not (root / "README.md").exists():
        warn("README.md missing (rendered on the Marketplace detail page)")

    # Skills
    skill_dirs = m.get("skills", ["skills"])
    if isinstance(skill_dirs, str):
        skill_dirs = [skill_dirs]
    count = 0
    for sd in skill_dirs:
        base = root / sd
        if not base.is_dir():
            err(f"skills path {sd} not found")
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            sm = d / "SKILL.md"
            if not sm.exists():
                warn(f"{d.relative_to(root)} has no SKILL.md")
                continue
            count += 1
            fm = frontmatter(sm.read_text())
            if fm is None:
                err(f"{sm.relative_to(root)}: no YAML frontmatter")
                continue
            sn = fm.get("name", "")
            if sn != d.name:
                err(f"{d.name}: frontmatter name '{sn}' does not match folder")
            if not NAME_RE.match(sn) or len(sn) > 64:
                err(f"{d.name}: name not kebab-case 1-64")
            sdsc = fm.get("description", "")
            if not 1 <= len(sdsc) <= 1024:
                err(f"{d.name}: description length {len(sdsc)} outside 1-1024")
            unknown = set(fm) - SKILL_KEYS
            if unknown:
                warn(f"{d.name}: frontmatter keys not in the guide: {sorted(unknown)}")
            if "compatibility" not in fm:
                warn(f"{d.name}: no compatibility field (users won't see the ax CLI / Python prerequisite)")
    print(f"Skills found: {count}")

    # MCP config
    mcp_path = root / m.get("mcpServers", "mcp_config.json")
    if not mcp_path.exists():
        warn(f"MCP config {mcp_path.name} not found (plugin will have no MCP servers)")
        return
    cfg = json.loads(mcp_path.read_text())
    servers = cfg.get("mcpServers", {})
    if not servers:
        err("mcp config has no mcpServers")
    declared = {v.get("name") for v in cfg.get("variables", [])}
    for key, s in servers.items():
        if not NAME_RE.match(key):
            warn(f"server key '{key}' is not kebab-case")
        if "serverUrl" in s:
            if not s["serverUrl"].startswith("https://"):
                err(f"{key}: serverUrl must be https")
        elif "command" not in s:
            err(f"{key}: needs serverUrl or command")
        used = set(VAR_RE.findall(json.dumps(s))) - RUNTIME_VARS
        for v in used - declared:
            err(f"{key}: ${{{v}}} used but not declared in variables")
        print(f"MCP server: {name}-{key}")
    for v in cfg.get("variables", []):
        if not v.get("title"):
            warn(f"variable {v.get('name')} has no title")
        if "KEY" in v.get("name", "") or "TOKEN" in v.get("name", ""):
            if not v.get("secret"):
                err(f"variable {v.get('name')} looks like a secret but secret is not true")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)
