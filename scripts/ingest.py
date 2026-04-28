#!/usr/bin/env python3
"""Build a benchmark profile from a folder of writing samples.

Usage:
    python3 scripts/ingest.py --samples samples/ --out benchmarks/default.json [--name default]

Each .txt / .md file in --samples is analyzed independently, then aggregated
(weighted by word count) into a single benchmark JSON.
"""

from __future__ import annotations

import _path  # noqa: F401
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lib.io_utils import load_text
from lib.stats import analyze, aggregate


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a Salix style benchmark from samples.")
    ap.add_argument("--samples", required=True, help="Folder containing .txt/.md samples")
    ap.add_argument("--out", required=True, help="Output JSON path for the benchmark")
    ap.add_argument("--name", default="default", help="Profile name to embed in benchmark")
    ap.add_argument("--min-words", type=int, default=300,
                    help="Skip individual files shorter than this (default 300)")
    args = ap.parse_args()

    samples_dir = Path(args.samples)
    if not samples_dir.is_dir():
        raise SystemExit(f"Samples directory not found: {samples_dir}")

    files = sorted(list(samples_dir.rglob("*.txt")) + list(samples_dir.rglob("*.md")))
    if not files:
        raise SystemExit(f"No .txt or .md files found in {samples_dir}")

    per_file_stats = []
    skipped = []
    for f in files:
        try:
            text = load_text(f)
        except Exception as exc:
            skipped.append({"file": str(f), "reason": f"read error: {exc}"})
            continue
        stats = analyze(text)
        if stats.get("word_count", 0) < args.min_words:
            skipped.append({"file": str(f),
                            "reason": f"too short ({stats.get('word_count', 0)} words)"})
            continue
        stats["_source"] = str(f.relative_to(samples_dir))
        per_file_stats.append(stats)

    if not per_file_stats:
        raise SystemExit("No samples passed the minimum word threshold.")

    aggregated = aggregate(per_file_stats)
    benchmark = {
        "name": args.name,
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(samples_dir.resolve()),
        "files_used": [s["_source"] for s in per_file_stats],
        "skipped": skipped,
        "stats": aggregated,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: stage to a tempfile in the same directory, then rename.
    # Prevents partial-write corruption if the process is interrupted, and
    # avoids races when multiple Claude sessions share a SALIX_HOME.
    import tempfile, os as _os
    fd, tmpname = tempfile.mkstemp(prefix=".salix_", suffix=".json", dir=str(out_path.parent))
    try:
        with _os.fdopen(fd, "w") as fh:
            json.dump(benchmark, fh, indent=2)
        _os.replace(tmpname, out_path)
    except Exception:
        if _os.path.exists(tmpname):
            _os.unlink(tmpname)
        raise
    print(f"Benchmark '{args.name}' written to {out_path}")
    print(f"  Files used:    {len(per_file_stats)}")
    print(f"  Files skipped: {len(skipped)}")
    print(f"  Total words:   {aggregated.get('total_word_count', 0):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
