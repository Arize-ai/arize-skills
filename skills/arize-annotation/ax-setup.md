# ax CLI Setup

Verify `ax` is installed and working before proceeding:

1. Check if `ax` is on PATH: `command -v ax` (Unix) or `where ax` (Windows)
2. If not found, check common install locations:
   - macOS/Linux: `test -x ~/.local/bin/ax && export PATH="$HOME/.local/bin:$PATH"`
   - Windows: check `%APPDATA%\Python\Scripts\ax.exe` or `%LOCALAPPDATA%\Programs\Python\Scripts\ax.exe`
3. If still not found, install it (requires shell access to install packages):
   - Preferred: `uv tool install arize-ax-cli`
   - Alternative: `pipx install arize-ax-cli`
   - Fallback: `pip install arize-ax-cli`
4. After install, if `ax` is not on PATH:
   - macOS/Linux: `export PATH="$HOME/.local/bin:$PATH"`
   - Windows (PowerShell): `$env:PATH = "$env:APPDATA\Python\Scripts;$env:PATH"`
5. If `ax --version` fails with an SSL/certificate error:
   - macOS: `export SSL_CERT_FILE=/etc/ssl/cert.pem`
   - Linux: `export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`
   - Windows (PowerShell): `$env:SSL_CERT_FILE = "C:\Program Files\Common Files\SSL\cert.pem"` (or use `python -c "import certifi; print(certifi.where())"` to find the cert bundle)
6. Check the version: `ax --version` must show `0.3.0` or higher. If the version is lower, upgrade it:
   - `uv tool install --force --reinstall arize-ax-cli`
   - `pipx upgrade arize-ax-cli`
   - `pip install --upgrade arize-ax-cli`
7. If `ax --version` fails entirely, stop and ask the user for help.
