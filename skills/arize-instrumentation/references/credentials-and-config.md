# Credentials and configuration

How to resolve, source, and safely handle Arize credentials during instrumentation and verification. The values involved: **API key**, **Space** (name or base64 ID), **project name**, and **collector endpoint** (US default `otlp.arize.com`; EU alternative available). For getting an API key and profile setup, see [ax-profiles.md](ax-profiles.md).

## Configuration precedence

When a value (project name, space, endpoint) is defined in more than one place, resolve it in this order — highest wins — and **never silently override a lower source the app actually uses**:

1. **Explicit user instruction this session** — treat as an override only *after* you confirm it, not a silent default.
2. **Target app config** — the app's own `.env`, process environment, or config file. The source of truth for what the running app exports.
3. **Active `ax` profile** — used for verification.
4. **Generated defaults** — e.g. a project name you propose when none exists (say so explicitly).

If a prompt value or `ax` profile disagrees with the app config, surface the mismatch and ask which to use — do not rewrite the app's config to line things up.

## Same credential context for export and verification

The app emits traces with **its** exporter config; you verify with the **`ax`** profile. If those target different spaces, keys, or endpoints, a successfully-exported trace looks missing.

- Before verifying, compare the app's exporter target (space/endpoint/project) against the active `ax` profile (`ax profiles show`).
- If they diverge, report a **credential-context blocker** (which space/project the app exported to vs. which `ax` is querying) instead of switching profiles or reporting the trace as missing.

## Finding credentials — where to look, where not to

- **Read only the target app's own configuration** to learn what it exports — its `.env`, its process environment, or an `ax` profile the user points you to.
- **Never search sibling repositories, unrelated `.env` files, or shell startup files** (`.bashrc`, `.zshrc`, `.profile`) for credentials — reusing another project's key silently sends traces to the wrong account.
- If credentials are missing, ask the user to set them (below) — do not hunt elsewhere.
- **Never ask the user to paste an API key into the chat**, and never surface a secret value. Reference the env var name only (see [ax-profiles.md](ax-profiles.md) for key handling).

## Safe environment parsing

- **Surface malformed `.env`/config entries** (unmatched quote, missing `=`, stray whitespace) as a warning naming the affected key — do not treat them as harmless or guess the intended value.
- Keep suggested verification probes **shell-portable**: avoid bash-only constructs (`[[ ]]`, process substitution). Prefer `printenv NAME` or the app's own config loader.

## Missing credentials — what to tell the user

The user sets these in their own terminal or app config — never in chat:

- **API key** — from https://app.arize.com → Settings → API Keys; a **scoped service key** is recommended for app/CI use.
- **Space** — the workspace. Its **name** and base64 **Space ID** are distinct: the `ARIZE_SPACE_ID` exporter env var needs the **base64 ID** (the name is only accepted for `ax` CLI resolution). Find the ID with `ax spaces list`.
- **Project name** — the logical grouping traces land in; the user chooses it, and it's created on first export.

Keep the three distinct — **space name** ≠ **space ID** ≠ **project name** — since conflating them is a common cause of "wrong account" verification failures. For the export commands and `ax profiles create` setup, see [ax-profiles.md](ax-profiles.md).
