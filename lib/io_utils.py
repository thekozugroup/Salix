"""Text loading and cleaning utilities.

Strips out content that would skew style metrics: code blocks, URLs,
inline code spans, raw HTML tags, citations like [1] or (Smith, 2020).
"""

import re
from pathlib import Path
from typing import Iterable

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
NUMERIC_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
PAREN_CITATION_RE = re.compile(r"\([A-Z][a-zA-Z\-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?\)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
MD_BULLET_RE = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
MD_NUMLIST_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
WHITESPACE_RE = re.compile(r"[ \t]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """Strip artifacts that would distort style metrics, preserving prose."""
    t = raw
    t = MD_IMAGE_RE.sub("", t)
    t = CODE_BLOCK_RE.sub("", t)
    t = INLINE_CODE_RE.sub("", t)
    t = HTML_TAG_RE.sub("", t)
    t = MD_LINK_RE.sub(r"\1", t)  # keep visible link text, drop URL
    t = URL_RE.sub("", t)
    t = NUMERIC_CITATION_RE.sub("", t)
    t = PAREN_CITATION_RE.sub("", t)
    t = MD_HEADING_RE.sub("", t)
    t = MD_BULLET_RE.sub("", t)
    t = MD_NUMLIST_RE.sub("", t)
    t = WHITESPACE_RE.sub(" ", t)
    t = MULTI_NEWLINE_RE.sub("\n\n", t)
    return t.strip()


def load_text(path: Path) -> str:
    """Load and clean a single text file."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    return clean_text(raw)


def load_corpus(sample_dir: Path, extensions: Iterable[str] = (".txt", ".md")) -> str:
    """Concatenate all sample files in `sample_dir` into one cleaned blob."""
    sample_dir = Path(sample_dir)
    if not sample_dir.is_dir():
        raise FileNotFoundError(f"Sample directory not found: {sample_dir}")
    parts = []
    for ext in extensions:
        for p in sorted(sample_dir.rglob(f"*{ext}")):
            parts.append(load_text(p))
    if not parts:
        raise ValueError(f"No samples ({extensions}) found in {sample_dir}")
    return "\n\n".join(parts)
