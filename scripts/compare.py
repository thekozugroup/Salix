#!/usr/bin/env python3
"""Compare a target's stats against a benchmark and emit a gap report.

Usage:
    python3 scripts/compare.py --target stats.json --benchmark benchmarks/default.json
    python3 scripts/compare.py --target-text draft.md --benchmark benchmarks/default.json
"""

from __future__ import annotations

import _path  # noqa: F401
import argparse
import json
import sys
from pathlib import Path

from lib.distance import compute_gaps
from lib.io_utils import load_text
from lib.stats import analyze


def _load_target(args) -> dict:
    if args.target:
        return json.loads(Path(args.target).read_text())
    if args.target_text:
        return analyze(load_text(Path(args.target_text)))
    raise SystemExit("Must pass --target <stats.json> or --target-text <file>")


def _load_benchmark(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    return data.get("stats", data)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare target text against benchmark profile.")
    ap.add_argument("--target", help="Path to a stats JSON (output of analyze.py)")
    ap.add_argument("--target-text", help="Path to raw text — analyzed on the fly")
    ap.add_argument("--benchmark", required=True, help="Path to benchmark JSON")
    ap.add_argument("--out", help="Optional path to write the gap report JSON")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON to stdout")
    args = ap.parse_args()

    target = _load_target(args)
    benchmark = _load_benchmark(Path(args.benchmark))
    report = compute_gaps(target, benchmark)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"Gap report written to {args.out}", file=sys.stderr)
    indent = 2 if args.pretty else None
    json.dump(report, sys.stdout, indent=indent)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
