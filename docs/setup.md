# Arize Skills Setup

These steps are only for first-time setup or environment issues.

## 1) Install prerequisites

If `ax` is not available, install via one of these:

```bash
uv tool install arize-ax-cli        # preferred
# or
pipx install arize-ax-cli
# or
pip3 install --user arize-ax-cli
# or
pip install --user arize-ax-cli
```

After install, the shell may still need `ax` on `PATH`.

```bash
# common install locations
command -v ax || test -x ~/.local/bin/ax && export PATH="$HOME/.local/bin:$PATH"
```

If your environment still can’t find a Python installer (`uv`/`pipx`/`pip`/`pip3`), see the installer guidance in `install.sh` (look for:
`No Python package manager found`).

## 2) Verify `ax` works

Use `ax --version` before running any skill commands.

```bash
ax --version
```

If this fails with certificate errors, try one of:

```bash
# macOS
export SSL_CERT_FILE=/etc/ssl/cert.pem
# Linux (common path)
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```

Retry:

```bash
ax --version
```

On Windows (PowerShell), set `$env:SSL_CERT_FILE` to your system cert bundle path.

## 3) Authenticate

You can authenticate using either mechanism:

- Interactive profile:

```bash
ax profiles create
```

- Or env var:

```bash
export ARIZE_API_KEY=...
```

## 4) Forced onboarding validation (required for testing)

Use this block to force a strict pass/fail gate. If it fails, stop and fix setup before proceeding.

```bash
if ! command -v ax >/dev/null 2>&1; then
  echo "NEEDS_SETUP: ax not found on PATH"
  echo "Run docs setup steps and retry."
  exit 1
fi

if ! ax --version >/dev/null 2>&1; then
  echo "NEEDS_SETUP: ax exists but is not runnable (TLS/path/auth/tooling issue likely)"
  echo "Fix PATH/SSL/tooling, then rerun docs setup steps and test again."
  exit 1
fi

echo "READY_TO_PROCEED"
```

You can treat any output other than `READY_TO_PROCEED` as a hard failure for normal user flow tests.
