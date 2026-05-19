#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Install Salix as an AI coding skill.

Usage:
  ./install.sh
  ./install.sh --force
  ./install.sh --codex --project
  ./install.sh --claude --global

Defaults:
  target: both Codex and Claude
  scope:  global

Options:
  --codex       Install for Codex only
  --claude      Install for Claude Code only
  --both        Install for Codex and Claude Code
  --global      Install to the user-level skills folder
  --project     Install to this project's skills folder
  -f, --force   Replace an existing Salix skill link
  -h, --help    Show this help

Requirements:
  Python 3.9+
EOF
}

FORCE=false
TARGET="both"
SCOPE="global"

for arg in "$@"; do
    case "${arg}" in
        --codex) TARGET="codex" ;;
        --claude) TARGET="claude" ;;
        --both) TARGET="both" ;;
        --global) SCOPE="global" ;;
        --project) SCOPE="project" ;;
        -f|--force) FORCE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown flag: ${arg}"; usage; exit 2 ;;
    esac
done

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Error: ${PYTHON_BIN} not found on PATH."
    exit 1
fi
PY_OK="$("${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    && echo yes || echo no)"
if [[ "${PY_OK}" != "yes" ]]; then
    echo "Error: Python 3.9+ required. Found: $("${PYTHON_BIN}" --version 2>&1)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_link() {
    local app="$1"
    local target_dir
    local target

    if [[ "${app}" == "codex" ]]; then
        if [[ "${SCOPE}" == "global" ]]; then
            target_dir="${CODEX_HOME:-${HOME}/.codex}/skills"
        else
            target_dir="${PWD}/.agents/skills"
        fi
    else
        if [[ "${SCOPE}" == "global" ]]; then
            target_dir="${HOME}/.claude/skills"
        else
            target_dir="${PWD}/.claude/skills"
        fi
    fi

    target="${target_dir}/salix"
    mkdir -p "${target_dir}"

    if [[ -L "${target}" || -e "${target}" ]]; then
        if [[ "${FORCE}" == "true" ]]; then
            rm -rf "${target}"
        else
            echo "Existing Salix skill at ${target}"
            read -r -p "Overwrite? [y/N] " ans
            if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
                echo "Skipped ${app}."
                return 0
            fi
            rm -rf "${target}"
        fi
    fi

    ln -s "${SCRIPT_DIR}" "${target}"
    echo "Installed for ${app}: ${target} -> ${SCRIPT_DIR}"
}

case "${TARGET}" in
    codex) install_link "codex" ;;
    claude) install_link "claude" ;;
    both)
        install_link "codex"
        install_link "claude"
        ;;
esac

echo
echo "Next:"
echo "  1. Restart or reload your AI coding app."
echo "  2. Ask: \"Build my Salix profile.\""
echo "  3. Verify the CLI:"
echo "     ${SCRIPT_DIR}/salix status"
