#!/usr/bin/env python3
"""Copy an allowlisted standalone skill; updates never touch style stores."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import _path  # noqa: F401

from lib.io_utils import load_json
from lib.package_files import package_files

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".salix-install.json"


def managed(target: Path) -> bool:
    if target.is_symlink():
        return target.resolve() == ROOT
    try:
        marker = load_json(target / MARKER, max_bytes=65536)
        return (isinstance(marker, dict) and marker.get("managed_by") == "salix"
                and marker.get("format") == 1)
    except (OSError, ValueError):
        return False


def remove_code(target: Path) -> None:
    if target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(target)


def has_legacy_data(target: Path) -> bool:
    return (target / "config.json").exists() or any(
        path.name != ".gitkeep" for folder in ("samples", "benchmarks")
        for path in (target / folder).glob("*")
    )


def unknown_files(target: Path) -> list[str]:
    if target.is_symlink():
        return []
    try:
        marker = load_json(target / MARKER, max_bytes=65536)
        declared = marker.get("files", []) if isinstance(marker, dict) else []
    except (OSError, ValueError):
        declared = []
    allowed = set(declared if isinstance(declared, list) and all(isinstance(x, str) for x in declared) else [])
    allowed.update(package_files(ROOT))
    allowed.update({MARKER, "config.json"})
    unknown = []
    for path in target.rglob("*"):
        rel = path.relative_to(target)
        if (path.is_dir() and not path.is_symlink()) or "__pycache__" in rel.parts:
            continue
        if rel.parts[0] in {"samples", "benchmarks"} or path.name == ".DS_Store":
            continue
        if str(rel) not in allowed:
            unknown.append(str(rel))
    return sorted(unknown)


def preflight(target: Path, *, force: bool, uninstall: bool) -> None:
    exists = target.exists() or target.is_symlink()
    if exists and not target.is_symlink() and ROOT.is_relative_to(target.resolve()):
        raise ValueError(f"Refusing to replace a directory containing the source checkout: {target}")
    if not exists:
        return
    if not managed(target) and (uninstall or not force):
        raise ValueError(f"Unmanaged skill at {target}; use --force to back up before replacement.")
    if uninstall and not target.is_symlink() and has_legacy_data(target):
        raise ValueError(f"Legacy style data inside {target}; move it to ~/.salix before uninstalling.")
    if managed(target):
        unknown = unknown_files(target)
        if unknown and (uninstall or not force):
            raise ValueError(f"Unknown files inside {target}: {', '.join(unknown[:5])}. "
                             "Move them out first, or use --force for a backed-up update.")


def install(target: Path, *, link: bool, force: bool, uninstall: bool) -> str:
    preflight(target, force=force, uninstall=uninstall)
    exists = target.exists() or target.is_symlink()
    if exists and target.resolve() == ROOT and not target.is_symlink():
        raise ValueError(f"Refusing to replace the source checkout: {target}")
    was_managed = exists and managed(target)
    is_managed = was_managed and not unknown_files(target)
    if uninstall:
        if not exists:
            return f"Already absent: {target}"
        if not is_managed:
            raise ValueError(f"Unmanaged skill at {target}; remove it manually after checking its contents.")
        remove_code(target)
        return f"Removed skill code: {target} (profiles retained)"
    if exists and not is_managed and not force:
        raise ValueError(f"Existing skill at {target}; use --force to back it up before replacement.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".salix-stage-", dir=target.parent))
    backup = None
    try:
        if link:
            staged.rmdir()
            staged.symlink_to(ROOT, target_is_directory=True)
        else:
            for rel in package_files(ROOT):
                source = ROOT / rel
                destination = staged / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            (staged / "salix").chmod(0o755)
            (staged / MARKER).write_text(json.dumps({"managed_by": "salix", "format": 1,
                                                    "files": package_files(ROOT)}) + "\n")
            if was_managed and not target.is_symlink():
                for folder in ("samples", "benchmarks"):
                    if (target / folder).is_dir():
                        shutil.copytree(target / folder, staged / folder, dirs_exist_ok=True, symlinks=True)
                if (target / "config.json").is_file():
                    shutil.copy2(target / "config.json", staged / "config.json")
        if link and was_managed and not target.is_symlink() and has_legacy_data(target):
            raise ValueError("Move legacy style data outside the install before switching to --link.")
        if exists:
            backup = target.with_name(f"salix.backup-{uuid.uuid4().hex[:8]}")
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
            raise
        if backup is not None and is_managed:
            remove_code(backup)
        suffix = f"; previous contents at {backup}" if backup and not is_managed else ""
        return f"Installed {'link' if link else 'skill'}: {target}{suffix}"
    finally:
        if staged.is_symlink():
            staged.unlink()
        elif staged.exists():
            shutil.rmtree(staged)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--codex", action="store_true")
    targets.add_argument("--claude", action="store_true")
    targets.add_argument("--both", action="store_true")
    scopes = parser.add_mutually_exclusive_group()
    scopes.add_argument("--project", action="store_true")
    scopes.add_argument("--global", dest="global_scope", action="store_true")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--link", action="store_true")
    modes.add_argument("--copy", action="store_true")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    base = args.project_dir.expanduser().resolve() if args.project else Path.home()
    destinations = []
    if not args.claude:
        destinations.append(base / ".agents" / "skills" / "salix")
    if not args.codex:
        destinations.append(base / ".claude" / "skills" / "salix")
    try:
        for destination in destinations:
            preflight(destination, force=args.force, uninstall=args.uninstall)
        if not args.uninstall:
            package_files(ROOT)
        for destination in destinations:
            print(install(destination, link=args.link, force=args.force, uninstall=args.uninstall))
    except (OSError, ValueError) as exc:
        print(f"Install error: {exc}", file=sys.stderr)
        return 1
    if not args.uninstall:
        print("\nOpen a new agent session. Codex: $salix. Claude Code: /salix.")
        print('Then ask: "Build my Salix profile from these writing samples."')
        print(f"Verify: {sys.executable} {destinations[0] / 'salix'} doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
