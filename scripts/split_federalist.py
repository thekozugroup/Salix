#!/usr/bin/env python3
"""Split the Project Gutenberg Federalist Papers text into per-author files.

The Federalist Papers are public domain. Project Gutenberg's edition (id
1404) is the canonical machine-readable copy. This script:

  1. strips the Gutenberg header / footer
  2. splits at "FEDERALIST No. N" boundaries
  3. parses the byline ("HAMILTON" / "MADISON" / "JAY" / "HAMILTON OR
     MADISON" — the disputed papers)
  4. writes each essay to corpora/<author>/fed_NN.txt

Usage:
    python3 scripts/split_federalist.py \\
        --input  validation/corpora/federalist/raw.txt \\
        --out    validation/corpora/federalist

The disputed papers go into a separate `disputed/` subdir so they don't
contaminate the labeled training set; classify them with `salix compare`
against author-specific benchmarks if you want to play Mosteller-Wallace.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

START_MARKER_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS)? PROJECT GUTENBERG.*$",
                             re.IGNORECASE | re.MULTILINE)
END_MARKER_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS)? PROJECT GUTENBERG.*$",
                           re.IGNORECASE | re.MULTILINE)
ESSAY_HEADER_RE = re.compile(r"^FEDERALIST\.?\s*No\.\s*(\d+)", re.MULTILINE | re.IGNORECASE)
BYLINE_RE = re.compile(
    r"\b(HAMILTON\s+OR\s+MADISON|HAMILTON\s+AND\s+MADISON|HAMILTON|MADISON|JAY)\b",
    re.IGNORECASE,
)


def author_dir(byline: str) -> str:
    b = byline.upper()
    if "OR" in b or "AND" in b:
        return "disputed"
    if "HAMILTON" in b:
        return "hamilton"
    if "MADISON" in b:
        return "madison"
    if "JAY" in b:
        return "jay"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Split Federalist Papers by author.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    # Strip Gutenberg boilerplate
    m_start = START_MARKER_RE.search(text)
    m_end = END_MARKER_RE.search(text)
    if m_start:
        text = text[m_start.end():]
    if m_end:
        text = text[: m_end.start() - (m_end.start() - text.find("***", m_start.end()))]

    # Split on essay headers
    pieces = ESSAY_HEADER_RE.split(text)
    # pieces[0] is the preamble; subsequent pairs are (number, body)
    out_root = Path(args.out)
    written = {"hamilton": 0, "madison": 0, "jay": 0, "disputed": 0, "unknown": 0}
    for i in range(1, len(pieces), 2):
        num = pieces[i].strip()
        body = pieces[i + 1] if i + 1 < len(pieces) else ""
        # First few hundred chars contain the byline
        head = body[:1500]
        bm = BYLINE_RE.search(head)
        author = author_dir(bm.group(1) if bm else "")
        sub = out_root / author
        sub.mkdir(parents=True, exist_ok=True)
        target = sub / f"fed_{int(num):02d}.txt"
        # Preserve only the body (post-byline) for cleaner training text.
        if bm:
            body_clean = body[bm.end():]
        else:
            body_clean = body
        target.write_text(body_clean.strip())
        written[author] += 1

    for k, v in written.items():
        print(f"  {k:10}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
