#!/usr/bin/env bash
# Install Salix as a Claude Code skill via symlink.
#
# Usage:
#   ./install.sh           # interactive prompt on overwrite
#   ./install.sh --force   # non-interactive overwrite (CI / dotfiles)
#
# Requires Python 3.9+.
set -euo pipefail

FORCE=false
for arg in "$@"; do
    case "${arg}" in
        -f|--force) FORCE=true ;;
        -h|--help)
            grep -E "^# " "$0" | sed 's/^# //'
            exit 0
            ;;
        *) echo "Unknown flag: ${arg}"; exit 2 ;;
    esac
done

# Validate Python version before linking — dict[str, X] generics need 3.9+.
PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Error: ${PYTHON_BIN} not found on PATH."
    exit 1
fi
PY_OK="$(${PYTHON_BIN} -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    && echo yes || echo no)"
if [[ "${PY_OK}" != "yes" ]]; then
    echo "Error: Python 3.9+ required. Found: $(${PYTHON_BIN} --version 2>&1)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude/skills/salix"

mkdir -p "${HOME}/.claude/skills"

if [[ -L "${TARGET}" || -e "${TARGET}" ]]; then
    if [[ "${FORCE}" == "true" ]]; then
        rm -rf "${TARGET}"
    else
        echo "Existing entry at ${TARGET}"
        read -r -p "Overwrite? [y/N] " ans
        if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
            echo "Aborted."
            exit 1
        fi
        rm -rf "${TARGET}"
    fi
fi

ln -s "${SCRIPT_DIR}" "${TARGET}"
echo "Salix linked: ${TARGET} -> ${SCRIPT_DIR}"
echo
echo "Next steps:"
echo "  1. Restart Claude Code (or reload skills)."
echo "  2. Drop writing samples into ${SCRIPT_DIR}/samples/"
echo "  3. Ask Claude: 'Build my Salix profile' or 'Make this sound like me'"
