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

