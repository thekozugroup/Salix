#!/usr/bin/env python3
"""Stamatatos (2009) baseline — char-3gram + cosine attribution.

Implements the canonical character-trigram baseline from Stamatatos 2009
("A Survey of Modern Authorship Attribution Methods"): for each author,
compute the author's normalized top-N character-3gram frequency vector;
classify a held-out document by cosine similarity to each author profile;
predict the author with the highest similarity.

Use it head-to-head against Salix's full-feature distance to verify Salix
is at least as good as the published baseline on the same corpus.

Usage:
    python3 scripts/stamatatos_baseline.py --corpus-dir validation/corpora/
    python3 scripts/stamatatos_baseline.py --top-k 1000  # vocabulary size

Layout: corpus_dir/<author>/<doc_N>.{txt,md}
"""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from pathlib import Path

import _path  # noqa: F401

from lib.io_utils import load_text


def char_3gram_vector(text: str, top_k: int) -> dict[str, float]:
    """Top-K char-3gram frequency vector. Lowercased, alpha+space only."""
    norm = re.sub(r"\s+", " ", text.lower())
    norm = "".join(ch for ch in norm if ch.isalpha() or ch == " ")
    if len(norm) < 3:
        return {}
    counter: Counter = Counter()
    for i in range(len(norm) - 2):
        counter[norm[i:i + 3]] += 1
    total = sum(counter.values()) or 1
    return {g: c / total for g, c in counter.most_common(top_k)}


def author_profile(texts: list[str], top_k: int) -> dict[str, float]:
    """Author profile = pooled normalized vector across the author's docs."""
    pooled: Counter = Counter()
    for t in texts:
        norm = re.sub(r"\s+", " ", t.lower())
        norm = "".join(ch for ch in norm if ch.isalpha() or ch == " ")
        for i in range(len(norm) - 2):
            pooled[norm[i:i + 3]] += 1
    total = sum(pooled.values()) or 1
    return {g: c / total for g, c in pooled.most_common(top_k)}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def attribute(corpus_dir: Path, top_k: int) -> dict:
    author_dirs = sorted(p for p in corpus_dir.iterdir() if p.is_dir())
    if len(author_dirs) < 2:
        raise SystemExit(f"Need >=2 author subdirs under {corpus_dir}")

    profiles: dict[str, dict[str, float]] = {}
    held_out: list[tuple[str, Path]] = []
    for ad in author_dirs:
        files = sorted(list(ad.glob("*.txt")) + list(ad.glob("*.md")))
        if len(files) < 3:
            raise SystemExit(f"Author '{ad.name}' has only {len(files)} docs")
        train_texts = [load_text(f) for f in files[:-1]]
        profiles[ad.name] = author_profile(train_texts, top_k)
        held_out.append((ad.name, files[-1]))

    correct = 0
    confusion: dict[tuple[str, str], int] = {}
    for true_label, doc_path in held_out:
        target = char_3gram_vector(load_text(doc_path), top_k)
        scores = {a: cosine(target, p) for a, p in profiles.items()}
        pred = max(scores, key=scores.get)
        if pred == true_label:
            correct += 1
        confusion[(true_label, pred)] = confusion.get((true_label, pred), 0) + 1

    return {
        "method": "stamatatos_2009_char3gram_cosine",
        "top_k": top_k,
        "authors": len(author_dirs),
        "total_held_out": len(held_out),
        "correct": correct,
        "accuracy": correct / max(len(held_out), 1),
        "confusion": confusion,
    }


def main() -> int:
    import json
    import sys
    ap = argparse.ArgumentParser(description="Stamatatos 2009 char-3gram baseline.")
    ap.add_argument("--corpus-dir", required=True,
                    help="Corpus root: subdirs are author labels.")
    ap.add_argument("--top-k", type=int, default=1000,
                    help="Vocabulary size for the char-3gram profile (default 1000).")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of human text.")
    args = ap.parse_args()

    res = attribute(Path(args.corpus_dir), args.top_k)
    if args.json:
        # Confusion has tuple keys; serialize as list-of-pairs for JSON.
        payload = dict(res)
        payload["confusion"] = [{"true": t, "pred": p, "count": n}
                                for (t, p), n in res["confusion"].items()]
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"Method:          {res['method']}")
    print(f"Vocabulary size: {res['top_k']}")
    print(f"Authors:         {res['authors']}")
    print(f"Held-out docs:   {res['total_held_out']}")
    print(f"Correct:         {res['correct']}")
    print(f"Accuracy:        {res['accuracy']:.1%}")
    if res["confusion"]:
        print("\nConfusion:")
        for (t, p), n in sorted(res["confusion"].items()):
            mark = "✓" if t == p else "✗"
            print(f"  {mark} {t} → {p}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
