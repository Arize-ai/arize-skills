# ax CLI Setup

Verify `ax` is installed and working before proceeding:

1. Resolve the executable path first instead of assuming `ax` is on PATH:
   - macOS/Linux: `command -v ax`
   - Windows: `Get-Command ax` or `where.exe ax`
2. If not found, check common install locations:
   - macOS/Linux: `~/.local/bin/ax`, `~/Library/Python/*/bin/ax`, `/Library/Frameworks/Python.framework/Versions/*/bin/ax`
   - Windows: `%APPDATA%\Python\Scripts\ax.exe`, `%LOCALAPPDATA%\Programs\Python\Python*\Scripts\ax.exe`
3. If multiple copies exist, run `--version` on each and keep using the explicit path to the newest working binary for the rest of the session.
4. If still not found, install it (requires shell access to install packages):
   - Preferred: `uv tool install arize-ax-cli`
   - Alternative: `pipx install arize-ax-cli`
   - Fallback: `pip install arize-ax-cli`
5. After install, if `ax` is not on PATH:
   - macOS/Linux: `export PATH="$HOME/.local/bin:$PATH"`
   - Windows (PowerShell): `$env:PATH = "$env:APPDATA\Python\Scripts;$env:PATH"`
6. If `ax --version` fails with an SSL/certificate error, set `SSL_CERT_FILE` and retry:
   - macOS: `export SSL_CERT_FILE=/etc/ssl/cert.pem`
   - Linux: `export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`
   - Any OS with Python available: `python -c "import certifi; print(certifi.where())"` and use that path
7. Check the version: `ax --version` must show `0.3.0` or higher. If the version is lower, upgrade it:
   - `uv tool install --force --reinstall arize-ax-cli`
   - `pipx upgrade arize-ax-cli`
   - `pip install --upgrade arize-ax-cli`
8. Probe capabilities before relying on a subcommand:
   - `ax --help`
   - `ax projects --help`
   - `ax spaces --help` if space discovery will be needed
9. If a documented command is unavailable in the installed CLI, continue with the closest supported alternative and mention that limitation in your response.
10. If `ax --version` still fails entirely, stop and ask the user for help.
