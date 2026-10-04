#!/usr/bin/env python3
"""Build a Claude-uploadable Salix.skill bundle.

The bundle is a ZIP archive with a .skill extension. It contains one top-level
`salix/` skill folder with SKILL.md plus runtime support files.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tempfile
import zipfile
from pathlib import Path

import _path  # noqa: F401

from lib.package_files import package_files

ROOT = Path(__file__).resolve().parents[1]


def _zipinfo(path: Path, arcname: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname)
    mode = stat.S_IFREG | (0o755 if path.name == "salix" else 0o644)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def build_bundle(out_path: Path, plugin: bool = False) -> None:
    files = package_files(ROOT, plugin=plugin)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".salix-bundle-", dir=out_path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in files:
                source = ROOT / rel
                zf.writestr(_zipinfo(source, f"salix/{rel}"), source.read_bytes())
        os.replace(temporary, out_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/Salix.skill")
    parser.add_argument("--out", default="dist/Salix.skill")
    parser.add_argument("--release", action="store_true", help="Also build Salix.zip, plugin ZIP, checksums")
    args = parser.parse_args()
    out_path = Path(args.out)
    build_bundle(out_path)
    print(f"Wrote {out_path}")
    if args.release:
        zip_path = out_path.parent / "Salix.zip"
        plugin_path = out_path.parent / "Salix-plugin.zip"
        zip_path.write_bytes(out_path.read_bytes())
        build_bundle(plugin_path, plugin=True)
        artifacts = [out_path, zip_path, plugin_path]
        checksum_path = out_path.parent / "SHA256SUMS"
        checksum_path.write_text("".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts
        ))
        print(f"Wrote {zip_path}, {plugin_path}, {checksum_path}")
    print("Upload this bundle in Claude: Customize > Skills > + > Upload a skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
