"""Text loading and cleaning utilities.

Strips content that would skew style metrics: code blocks (fenced and inline),
URLs, raw HTML tags, citations like [1] or (Smith, 2020), markdown chrome.
Order matters — code blocks are stripped *first* so URLs/citations inside
blocks aren't bled into the prose stream.

Encoding: tries UTF-8 strictly; on failure, falls back to cp1252 then latin-1.
Never substitutes U+FFFD silently — corrupted bytes either decode under a
fallback encoding or surface as an explicit error to the caller.
"""

import re
import warnings
from collections.abc import Iterable
from pathlib import Path

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
NUMERIC_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
PAREN_CITATION_RE = re.compile(r"\([A-Z][a-zA-Z\-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?\)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
# Anchor bullet stripping at line start (not at any leading whitespace) so
# em-dash-led narration like "— she said" doesn't get mistaken for a list.
MD_BULLET_RE = re.compile(r"(?:^|\n)[ \t]*[-*+][ \t]+")
MD_NUMLIST_RE = re.compile(r"(?:^|\n)[ \t]*\d+\.[ \t]+")
WHITESPACE_RE = re.compile(r"[ \t]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB cap protects against runaway regex


def clean_text(raw: str) -> str:
    """Strip artifacts that would distort style metrics, preserving prose.

    Order:
      1. Fenced code blocks (so contents don't bleed into URL/citation passes)
      2. Inline code, HTML, images
      3. Markdown links (keep visible label, drop URL)
      4. Bare URLs, citations
      5. Markdown chrome (headings, bullets, numbered lists)
      6. Whitespace normalization
    """
    t = raw
    t = CODE_BLOCK_RE.sub("", t)
    t = INLINE_CODE_RE.sub("", t)
    t = MD_IMAGE_RE.sub("", t)
    t = HTML_TAG_RE.sub("", t)
    t = MD_LINK_RE.sub(r"\1", t)
    t = URL_RE.sub("", t)
    t = NUMERIC_CITATION_RE.sub("", t)
    t = PAREN_CITATION_RE.sub("", t)
    t = MD_HEADING_RE.sub("", t)
    t = MD_BULLET_RE.sub("\n", t)
    t = MD_NUMLIST_RE.sub("\n", t)
    t = WHITESPACE_RE.sub(" ", t)
    t = MULTI_NEWLINE_RE.sub("\n\n", t)
    return t.strip()


def _read_with_fallback(path: Path) -> str:
    """Read text with explicit encoding fallbacks. Never silently corrupts bytes."""
    raw_bytes = path.read_bytes()
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ValueError(
            f"{path} is {len(raw_bytes):,} bytes; exceeds MAX_FILE_BYTES "
            f"({MAX_FILE_BYTES:,}). Split or sample the corpus."
        )
    # Strip BOM if present
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to decode {path} as utf-8/cp1252/latin-1")


def load_text(path: Path) -> str:
    """Load and clean a single text file."""
    p = Path(path)
    raw = _read_with_fallback(p)
    cleaned = clean_text(raw)
    if not cleaned.strip():
        warnings.warn(f"{p} cleaned to empty — likely all code/markdown/URLs", stacklevel=2)
    return cleaned


def load_corpus(sample_dir: Path, extensions: Iterable[str] = (".txt", ".md")) -> str:
    """Concatenate all sample files in `sample_dir` into one cleaned blob."""
    sample_dir = Path(sample_dir)
    if not sample_dir.is_dir():
        raise FileNotFoundError(f"Sample directory not found: {sample_dir}")
    parts = []
    seen: set = set()
    for ext in extensions:
        # follow_symlinks defaults False on rglob in 3.12+, but we resolve to
        # canonical paths and skip duplicates to defend against symlink loops.
        for p in sorted(sample_dir.rglob(f"*{ext}")):
            try:
                key = p.resolve()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            parts.append(load_text(p))
    if not parts:
        raise ValueError(f"No samples ({extensions}) found in {sample_dir}")
    return "\n\n".join(parts)
