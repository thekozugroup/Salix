#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Install Salix for Codex and Claude Code. Python 3.9+ required.

  ./install.sh                         Install self-contained user skills
  ./install.sh --codex                 Codex only
  ./install.sh --claude                Claude Code only
  ./install.sh --project --project-dir /path/to/project
  ./install.sh --link                  Link to this checkout (development)
  ./install.sh --uninstall             Remove managed skill code; keep profiles
  ./install.sh --force                 Replace an unmanaged install (backed up)

Run again to update a managed install. Profiles live separately in ~/.salix
or <project>/.salix. Remote use: curl -fsSL .../install.sh | bash
EOF
    exit 0
fi

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python 3.9+ is needed. Install Python from https://www.python.org/downloads/ and run again." >&2
    exit 1
fi
"${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "Python 3.9+ is needed. Set PYTHON to a supported interpreter." >&2
    exit 1
}

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -n "${SCRIPT_DIR}" && -f "${SCRIPT_DIR}/scripts/install.py" ]]; then
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/scripts/install.py" "$@"
fi
for argument in "$@"; do
    if [[ "${argument}" == "--link" ]]; then
        echo "--link requires a local checkout. Remote installation copies the skill." >&2
        exit 1
    fi
done

command -v curl >/dev/null || { echo "curl is required for download." >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip is required for download." >&2; exit 1; }
SALIX_DOWNLOAD_DIR="$(mktemp -d)"
trap 'rm -rf "${SALIX_DOWNLOAD_DIR}"' EXIT
curl -fsSL --retry 2 https://github.com/thekozugroup/Salix/archive/refs/heads/main.zip \
    -o "${SALIX_DOWNLOAD_DIR}/salix.zip"
unzip -q "${SALIX_DOWNLOAD_DIR}/salix.zip" -d "${SALIX_DOWNLOAD_DIR}"
"${PYTHON_BIN}" "${SALIX_DOWNLOAD_DIR}/Salix-main/scripts/install.py" "$@"
