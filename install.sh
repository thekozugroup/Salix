#!/usr/bin/env bash
# Install Salix as a Claude Code skill via symlink.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude/skills/salix"

mkdir -p "${HOME}/.claude/skills"

if [[ -L "${TARGET}" || -e "${TARGET}" ]]; then
    echo "Existing entry at ${TARGET}"
    read -r -p "Overwrite? [y/N] " ans
    if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
        echo "Aborted."
        exit 1
    fi
    rm -rf "${TARGET}"
fi

ln -s "${SCRIPT_DIR}" "${TARGET}"
echo "Salix linked: ${TARGET} -> ${SCRIPT_DIR}"
echo
echo "Next steps:"
echo "  1. Restart Claude Code (or reload skills)."
echo "  2. Drop writing samples into ${SCRIPT_DIR}/samples/"
echo "  3. Ask Claude: 'Build my Salix profile' or 'Make this sound like me'"
