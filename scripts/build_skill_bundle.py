#!/usr/bin/env python3
"""Build a Claude-uploadable Salix.skill bundle.

The bundle is a ZIP archive with a .skill extension. It contains one top-level
`salix/` skill folder with SKILL.md plus runtime support files.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import zipfile
from pathlib import Path

import _path  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]

INCLUDE_FILES = [
    "SKILL.md",
    "salix",
    "lib/__init__.py",
    "lib/distance.py",
    "lib/function_words.py",
    "lib/io_utils.py",
    "lib/stats.py",
    "lib/social.py",
    "references/social.md",
    "lib/tone.py",
    "scripts/_path.py",
    "scripts/analyze.py",
    "scripts/stamatatos_baseline.py",
    "scripts/compare.py",
    "scripts/ingest.py",
    "scripts/simulate_loop.py",
    "scripts/validate.py",
    "scripts/visualize.py",
    "benchmarks/.gitkeep",
    "samples/.gitkeep",
]


def _zipinfo(path: Path, arcname: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname)
    mode = path.stat().st_mode
    if path.name == "salix":
        mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def build_bundle(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_FILES:
            source = ROOT / rel
            if not source.exists():
                raise SystemExit(f"Missing required bundle file: {source}")
            arcname = f"salix/{rel}"
            zf.writestr(_zipinfo(source, arcname), source.read_bytes())


def build_plugin(out_dir: Path, platform: str) -> Path:
    """Package a self-contained skill under a native Codex or Claude manifest."""
    if platform not in {"codex", "claude"}:
        raise ValueError("platform must be codex or claude")
    plugin_root = out_dir / platform / "salix"
    skill_root = plugin_root / "skills" / "salix"
    for rel in INCLUDE_FILES:
        destination = skill_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, destination)
    manifest = f".{platform}-plugin/plugin.json"
    destination = plugin_root / manifest
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "packaging" / "salix" / manifest, destination)
    archive = out_dir / f"Salix.{platform}-plugin.zip"
    # Explicit allowlist prevents stale/private files from entering rebuilt archives.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in [manifest] + [f"skills/salix/{rel}" for rel in INCLUDE_FILES]:
            source = plugin_root / rel
            zf.writestr(_zipinfo(source, f"salix/{rel}"), source.read_bytes())
    return plugin_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/Salix.skill")
    parser.add_argument("--out", default="dist/Salix.skill")
    parser.add_argument("--all", action="store_true", help="Also build native Codex and Claude plugin directories and ZIPs")
    args = parser.parse_args()
    out_path = Path(args.out)
    build_bundle(out_path)
    print(f"Wrote {out_path}")
    if args.all:
        for platform in ("codex", "claude"):
            print(f"Wrote {build_plugin(out_path.parent, platform)}")
    print("Upload this bundle in Claude: Customize > Skills > + > Upload a skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
