#!/usr/bin/env python3
"""Opt-in profile context for Claude/Codex SessionStart; never edits files."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

import _path  # noqa: F401

from lib.io_utils import load_json


def main() -> int:
    if os.environ.get("SALIX_HOOKS") is not None and os.environ["SALIX_HOOKS"] != "1":
        return 0
    try:
        event = json.loads(sys.stdin.read(65537))
        if not isinstance(event, dict) or event.get("hook_event_name") != "SessionStart":
            return 0
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not Path(cwd).is_dir():
            return 0
        root = Path(__file__).resolve().parents[1]
        loader = importlib.machinery.SourceFileLoader("salix_hook_cli", str(root / "salix"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        home, scope = module._resolve_home(project_dir=cwd)
        try:
            config = load_json(home / "config.json", max_bytes=65536)
        except (OSError, ValueError):
            config = {}
        enabled = os.environ.get("SALIX_HOOKS")
        if enabled is not None:
            active = enabled == "1"
        else:
            active = isinstance(config, dict) and config.get("hooks_enabled") is True
        if not active:
            return 0
        profiles = list((home / "benchmarks").glob("*.json"))
        context = (
            f"Salix writing skill is available; {len(profiles)} profile(s) in the {scope} store. "
            "Use Salix when the user requests their writing voice or style analysis. "
            f"Run Python against {root / 'salix'} status --json to inspect setup. "
            "Preserve meaning and protected content; measure before and after."
        )
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": context,
        }}))
    except (OSError, ValueError, TypeError, ImportError, RecursionError, SystemExit):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
