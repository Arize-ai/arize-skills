#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"

# Defaults
GLOBAL=false
COPY_MODE=false
FORCE=false
SKIP_CLI=false
YES=false
UNINSTALL=false
LIST=false
PROJECT_DIR=""
MANUAL_AGENTS=()
SELECTED_SKILLS=()

usage() {
  cat <<'USAGE'
Arize Skills Installer

Usage: ./install.sh --project <dir> [flags]
       ./install.sh --global [flags]
       ./install.sh --list

One of --project or --global is required (except with --list).

Flags:
  --project <dir>   Install into a specific project directory (required unless --global)
  --global          Install to ~/.<agent>/skills/ instead of project-level
  --copy            Copy files instead of symlinking
  --force           Overwrite existing skills with same names
  --skip-cli        Don't install ax CLI even if missing
  --agent <name>    Manually specify agent (cursor, claude, codex) — repeatable
  --skill <name>    Only install/uninstall specific skills — repeatable
  --yes             Skip confirmation prompts
  --uninstall       Remove previously installed skill symlinks
  --list            List all available skills and exit
  --help            Show this help

Examples:
  ./install.sh --list                                                           # Show available skills
  ./install.sh --project ~/my-app --agent claude                                # Install all skills
  ./install.sh --project ~/my-app --agent claude --skill arize-trace            # Install one skill
  ./install.sh --project . --agent claude --skill arize-trace --skill arize-dataset  # Install two skills
  ./install.sh --project . --agent cursor --yes                                 # Current dir, Cursor only
  ./install.sh --global                                                          # Install globally (auto-detects agents)
  ./install.sh --project ~/my-app --agent claude --copy                         # Copy instead of symlink
  ./install.sh --project ~/my-app --agent claude --uninstall                    # Remove all installed symlinks
  ./install.sh --project ~/my-app --agent claude --uninstall --skill arize-trace  # Remove one skill
USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)     GLOBAL=true; shift ;;
    --project)    PROJECT_DIR="$2"; shift 2 ;;
    --copy)       COPY_MODE=true; shift ;;
    --force)      FORCE=true; shift ;;
    --skip-cli)   SKIP_CLI=true; shift ;;
    --agent)      MANUAL_AGENTS+=("$2"); shift 2 ;;
    --skill)      SELECTED_SKILLS+=("$2"); shift 2 ;;
    --yes)        YES=true; shift ;;
    --uninstall)  UNINSTALL=true; shift ;;
    --list)       LIST=true; shift ;;
    --help|-h)    usage ;;
    *)            echo "Unknown flag: $1"; usage ;;
  esac
done

# --- List mode ---

if [[ "$LIST" == true ]]; then
  echo "Available skills:"
  for skill in "$SKILLS_SRC"/*/; do
    [[ -d "$skill" ]] || continue
    echo "  $(basename "$skill")"
  done
  exit 0
fi

# --- Validate --skill names ---

if [[ ${#SELECTED_SKILLS[@]} -gt 0 ]]; then
  for name in "${SELECTED_SKILLS[@]}"; do
    if [[ ! -d "$SKILLS_SRC/$name" ]]; then
      echo "Error: unknown skill '$name'"
      echo ""
      echo "Available skills:"
      for skill in "$SKILLS_SRC"/*/; do
        [[ -d "$skill" ]] || continue
        echo "  $(basename "$skill")"
      done
      exit 1
    fi
  done
fi

# --- Agent detection ---

AGENTS=()

agent_skills_dir() {
  local agent="$1" base="$2"
  case "$agent" in
    cursor) echo "$base/.cursor/skills" ;;
    claude) echo "$base/.claude/skills" ;;
    codex)  echo "$base/.codex/skills" ;;
    *)      echo "$base/.$agent/skills" ;;
  esac
}

detect_agents() {
  local base="$1"
  if [[ -d "$base/.cursor" ]]; then AGENTS+=("cursor"); fi
  if [[ -d "$base/.claude" ]]; then AGENTS+=("claude"); fi
  if [[ -d "$base/.codex" ]];  then AGENTS+=("codex"); fi
}

pick_ssl_cert_file() {
  local candidate

  if [[ -n "${SSL_CERT_FILE:-}" && -f "$SSL_CERT_FILE" ]]; then
    echo "$SSL_CERT_FILE"
    return 0
  fi

  for candidate in \
    /etc/ssl/cert.pem \
    /etc/pki/tls/certs/ca-bundle.crt \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/ssl/certs/ca-bundle.crt \
    /usr/local/share/ca-certificates/ca-bundle.crt; do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

is_tls_failure() {
  local message="$1"
  grep -qiE "certificate verify failed|self[- ]signed|x509|unable to get local issuer|certificate has expired|ssl:|tlsv1|tls.*certificate|ssl certificate" <<<"$message"
}

run_ax_version_check() {
  local cert_file="$1"
  if [[ -n "$cert_file" ]]; then
    SSL_CERT_FILE="$cert_file" "$AX_BIN" --version 2>&1
  else
    "$AX_BIN" --version 2>&1
  fi
}

find_ax_binary() {
  local pattern
  local candidate

  if command -v ax &>/dev/null; then
    echo "$(command -v ax)"
    return 0
  fi

  local -a candidates=(
    "$HOME/.local/bin/ax"
    "$HOME/.local/pipx/venvs/arize-ax-cli/bin/ax"
    "$HOME/.local/share/pipx/venvs/arize-ax-cli/bin/ax"
    "$HOME/Library/Python/*/bin/ax"
    "/Library/Frameworks/Python.framework/Versions/*/bin/ax"
    "/usr/local/bin/ax"
    "/opt/homebrew/bin/ax"
  )

  shopt -s nullglob
  for pattern in "${candidates[@]}"; do
    for candidate in $pattern; do
      [[ -x "$candidate" ]] && {
        echo "$candidate"
        shopt -u nullglob
        return 0
      }
    done
  done
  shopt -u nullglob
  return 1
}

if [[ "$GLOBAL" != true && -z "$PROJECT_DIR" ]]; then
  echo "Error: --project <dir> is required (or use --global for global install)."
  echo ""
  usage
fi

if [[ ${#MANUAL_AGENTS[@]} -gt 0 ]]; then
  AGENTS=("${MANUAL_AGENTS[@]}")
elif [[ "$GLOBAL" == true ]]; then
  detect_agents "$HOME"
else
  detect_agents "$PROJECT_DIR"
fi

if [[ ${#AGENTS[@]} -eq 0 ]]; then
  echo "No agents detected (looked for .cursor/, .claude/, .codex/)."
  echo "Use --agent <name> to specify manually, e.g.: ./install.sh --agent cursor"
  exit 1
fi

# --- Resolve base directory ---

if [[ "$GLOBAL" == true ]]; then
  BASE="$HOME"
else
  BASE="$PROJECT_DIR"
fi

echo "Arize Skills Installer"
echo "======================"
echo ""
echo "Detected agents: ${AGENTS[*]}"
if [[ "$GLOBAL" == true ]]; then
  echo "Scope: global (~/$HOME)"
else
  echo "Scope: project ($BASE)"
fi
echo ""

# --- Install or uninstall ---

install_skill() {
  local skill_src="$1" target="$2" skill_name
  skill_name="$(basename "$skill_src")"

  if [[ -e "$target" ]]; then
    if [[ "$FORCE" == true ]]; then
      rm -rf "$target"
    else
      echo "  Skipped $skill_name (already exists, use --force to overwrite)"
      return
    fi
  fi

  if [[ "$COPY_MODE" == true ]]; then
    cp -r "$skill_src" "$target"
    echo "  Copied  $skill_name -> $target"
  else
    ln -sfn "$skill_src" "$target"
    echo "  Linked  $skill_name -> $target"
  fi
}

uninstall_skill() {
  local skill_src="$1" target="$2" skill_name
  skill_name="$(basename "$skill_src")"

  if [[ -L "$target" && "$(readlink "$target")" == "$skill_src" ]]; then
    rm "$target"
    echo "  Removed $skill_name ($target)"
  elif [[ -L "$target" ]]; then
    echo "  Skipped $skill_name (symlink points elsewhere)"
  elif [[ -d "$target" ]]; then
    echo "  Skipped $skill_name (is a directory, not a symlink from this repo)"
  fi
}

# Build list of skills to process
SKILL_DIRS=()
if [[ ${#SELECTED_SKILLS[@]} -gt 0 ]]; then
  for name in "${SELECTED_SKILLS[@]}"; do
    SKILL_DIRS+=("$SKILLS_SRC/$name")
  done
else
  for skill in "$SKILLS_SRC"/*/; do
    [[ -d "$skill" ]] || continue
    SKILL_DIRS+=("$skill")
  done
fi

for agent in "${AGENTS[@]}"; do
  skills_dir="$(agent_skills_dir "$agent" "$BASE")"
  mkdir -p "$skills_dir"
  echo "Agent: $agent ($skills_dir)"

  for skill in "${SKILL_DIRS[@]}"; do
    [[ -d "$skill" ]] || continue
    target="$skills_dir/$(basename "$skill")"

    if [[ "$UNINSTALL" == true ]]; then
      uninstall_skill "$skill" "$target"
    else
      install_skill "$skill" "$target"
    fi
  done
done

echo ""

if [[ "$UNINSTALL" == true ]]; then
  echo "Done! Skills uninstalled."
  exit 0
fi

# --- Output directory setup ---

if [[ "$GLOBAL" != true && -n "$PROJECT_DIR" ]]; then
  mkdir -p "$PROJECT_DIR/.arize-tmp-traces"
  if [[ -f "$PROJECT_DIR/.gitignore" ]]; then
    grep -qxF '.arize-tmp-traces/' "$PROJECT_DIR/.gitignore" 2>/dev/null \
      || echo '.arize-tmp-traces/' >> "$PROJECT_DIR/.gitignore"
  else
    echo '.arize-tmp-traces/' > "$PROJECT_DIR/.gitignore"
  fi
  echo "Output directory: $PROJECT_DIR/.arize-tmp-traces/ (added to .gitignore)"
fi

# --- CLI installation ---

install_ax_cli() {
  if command -v uv &>/dev/null; then
    echo "Installing ax CLI via uv..."
    uv tool install --force arize-ax-cli
  elif command -v pipx &>/dev/null; then
    echo "Installing ax CLI via pipx..."
    pipx install --force arize-ax-cli
  elif command -v pip3 &>/dev/null; then
    echo "Installing ax CLI via pip3..."
    pip3 install --user arize-ax-cli
  elif command -v pip &>/dev/null; then
    echo "Installing ax CLI via pip..."
    pip install arize-ax-cli 2>/dev/null || pip install --user arize-ax-cli
  else
    echo "Warning: No Python package manager found (tried uv, pipx, pip3, pip)."
    echo "Install ax manually: https://github.com/Arize-ai/arize-ax-cli"
    return 1
  fi
}

AX_BIN=""

if command -v ax &>/dev/null; then
  AX_BIN="$(command -v ax)"
  ax_version="$(ax --version 2>/dev/null || echo "unknown")"
  echo "ax CLI: installed ($ax_version)"
elif [[ "$SKIP_CLI" == true ]]; then
  echo "ax CLI: not found (skipped with --skip-cli)"
  echo "  Install manually: pipx install arize-ax-cli"
else
  if install_ax_cli; then
    AX_BIN="$(find_ax_binary || true)"
    if [[ -n "$AX_BIN" ]]; then
      echo "ax CLI: installed"
    else
      echo "ax CLI: installation complete but binary was not found in known locations"
      echo "  Check your Python environment and PATH"
    fi
  else
    echo "ax CLI: installation failed (install manually)"
    AX_BIN=""
  fi
fi

if [[ -n "$AX_BIN" ]]; then
  ax_cli_version=""
  ax_cli_error=""
  if ax_cli_version="$(run_ax_version_check "${SSL_CERT_FILE:-}")"; then
    echo "ax CLI check: ${ax_cli_version}"
  else
    ax_cli_error="${ax_cli_version}"
    if is_tls_failure "${ax_cli_error}"; then
      if [[ -n "${SSL_CERT_FILE:-}" ]] && ax_cli_version="$(run_ax_version_check "$SSL_CERT_FILE")"; then
        echo "ax CLI check: ${ax_cli_version}"
        echo "Note: this environment needs SSL_CERT_FILE set."
        echo "  export SSL_CERT_FILE=$SSL_CERT_FILE"
      elif ax_ssl_file="$(pick_ssl_cert_file || true)" && ax_cli_version="$(run_ax_version_check "$ax_ssl_file")"; then
        echo "ax CLI check: ${ax_cli_version}"
        echo "Note: this environment needs SSL_CERT_FILE set to your cert bundle:"
        echo "  export SSL_CERT_FILE=$ax_ssl_file"
      else
        echo "Warning: ax CLI is installed at $AX_BIN but not runnable."
        echo "  Error: ${ax_cli_error}"
        echo "  Run: $AX_BIN --version to reproduce."
      fi
    else
      echo "Warning: ax CLI is installed at $AX_BIN but not runnable."
      echo "  Error: ${ax_cli_error}"
      echo "  Run: $AX_BIN --version for exact output."
    fi
    if is_tls_failure "${ax_cli_error}"; then
      echo "If this is a TLS problem, set SSL_CERT_FILE to a cert bundle and retry."
    fi
  fi

  if ! command -v ax &>/dev/null; then
    echo ""
    echo "ax was not found on PATH. Add it with:"
    echo "  export PATH=\"$(dirname "$AX_BIN"):\$PATH\""
    echo "Example:"
    if [[ "$SHELL" == */zsh ]]; then
      echo "  echo 'export PATH=\"$(dirname "$AX_BIN"):\$PATH\"' >> ~/.zshrc"
    else
      echo "  echo 'export PATH=\"$(dirname "$AX_BIN"):\$PATH\"' >> ~/.bashrc"
    fi
    echo "Then restart your terminal."
  fi
fi

echo ""
if [[ "$COPY_MODE" == true ]]; then
  echo "Done! Skills copied into place."
else
  echo "Done! Skills are ready to use."
  echo "Keep this directory in place -- skills are symlinked here."
  echo "To make standalone copies instead, re-run with --copy."
fi
