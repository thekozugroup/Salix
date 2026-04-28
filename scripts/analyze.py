#!/usr/bin/env python3
"""Analyze a single text file or stdin and emit the stats JSON.

Usage:
    python3 scripts/analyze.py path/to/draft.md > stats.json
    cat draft.md | python3 scripts/analyze.py -
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _path  # noqa: F401

from lib.io_utils import clean_text, load_text
from lib.stats import analyze


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze a text and emit Salix style stats.")
    ap.add_argument("path", help="Path to the file, or '-' for stdin")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = ap.parse_args()

    if args.path == "-":
        text = clean_text(sys.stdin.read())
    else:
        text = load_text(Path(args.path))

    if not text.strip():
        raise SystemExit("Empty text after cleaning.")

    stats = analyze(text)
    indent = 2 if args.pretty else None
    json.dump(stats, sys.stdout, indent=indent)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
