#!/usr/bin/env python3
"""Simulate the iterative rewrite loop *without* an LLM.

Applies deterministic, rule-based edits chosen by the gap report — adding
commas, splitting long sentences, inserting hedges/discourse markers, etc.
The point is not to be a good rewriter, but to validate:

  1. Distance decreases across iterations (loop logic is sound)
  2. The gap report's `top_gaps` are actionable (edits informed by them help)
  3. Convergence threshold is reachable for matched-style targets

Usage:
    python3 scripts/simulate_loop.py \
        --target-text path/to/draft.md \
        --benchmark benchmarks/default.json \
        [--max-iter 6] [--threshold 0.15] [--verbose]
"""

from __future__ import annotations

import argparse
import random
import re
from pathlib import Path

import _path  # noqa: F401

from lib.distance import compute_gaps
from lib.io_utils import load_text
from lib.stats import analyze, split_sentences

HEDGES_BANK = ["perhaps", "rather", "indeed", "though", "however"]
DISCOURSE_BANK = ["moreover", "thus", "consequently", "nevertheless"]


def _splice_sentence(text: str, old: str, new: str) -> str:
    """Replace `old` in `text` with `new`, but only when `old` sits at a
    real sentence boundary: start-of-text, or preceded by a terminator
    `.!?…` followed by one-or-more whitespace characters (spaces, tabs,
    newlines, double-newline paragraph breaks). The previous regex required
    exactly one whitespace char and missed paragraph-internal boundaries.

    No literal-find fallback: if no boundary match exists, the edit is
    skipped (returning the original text) and the caller tries the next
    gap — guaranteeing collision-free edits.
    """
    # Use a non-fixed-width approach: split into "preceding text" via
    # finditer over (terminator, whitespace) pairs, then check each match.
    needle_re = re.compile(re.escape(old))
    for m in needle_re.finditer(text):
        start = m.start()
        if start == 0:
            return text[:start] + new + text[start + len(old):]
        # Walk back over whitespace, then look for a terminator.
        i = start - 1
        while i >= 0 and text[i] in " \t\n\r":
            i -= 1
        if i >= 0 and text[i] in ".!?…":
            return text[:start] + new + text[start + len(old):]
    return text


def _add_comma(text: str) -> str:
    """Insert a comma at a likely natural pause.

    Tries, in order: before coordinating conjunctions, before relative pronouns,
    after sentence-initial adverbs, then after the second word of any sentence
    longer than ~6 words.
    """
    # 1. Before coord/sub conjunctions ("and", "but", ...) and relatives.
    conj_pattern = re.compile(r"(?<!,)\s(and|but|or|yet|so|which|because|while|though|although|when|where|if|since)\s")
    matches = list(conj_pattern.finditer(text))
    if matches:
        m = random.choice(matches)
        return text[: m.start()] + "," + text[m.start():]

    # 2. After sentence-initial adverb/connector.
    adverb_pattern = re.compile(
        r"(\.\s+|^)(However|Moreover|Indeed|Perhaps|Actually|Therefore|Thus|Still|Yet)\s",
        re.MULTILINE,
    )
    matches = list(adverb_pattern.finditer(text))
    if matches:
        m = random.choice(matches)
        end = m.end() - 1  # position of the trailing space
        return text[:end] + "," + text[end:]

    # 3. Insert comma after second word of a long sentence with no commas.
    sentences = split_sentences(text)
    candidates = [s for s in sentences if "," not in s and len(s.split()) >= 7]
    if candidates:
        s = random.choice(candidates)
        words = s.split()
        rebuilt = " ".join(words[:2]) + ", " + " ".join(words[2:])
        return _splice_sentence(text, s, rebuilt)
    return text


def _remove_comma(text: str) -> str:
    """Remove a single comma not adjacent to a digit."""
    matches = [m.start() for m in re.finditer(r",\s", text) if not text[max(m.start()-1, 0)].isdigit()]
    if not matches:
        return text
    i = random.choice(matches)
    return text[:i] + text[i+1:]


def _split_long_sentence(text: str) -> str:
    """Find the longest sentence; split at a comma into two."""
    sentences = split_sentences(text)
    if not sentences:
        return text
    longest = max(sentences, key=lambda s: len(s.split()))
    if "," not in longest or len(longest.split()) < 16:
        return text
    parts = longest.split(", ", 1)
    if len(parts) != 2:
        return text
    rebuilt = parts[0] + ". " + parts[1][:1].upper() + parts[1][1:]
    return _splice_sentence(text, longest, rebuilt)


def _join_short_sentences(text: str) -> str:
    """Join two adjacent short sentences with ', and'."""
    sentences = split_sentences(text)
    for i in range(len(sentences) - 1):
        a, b = sentences[i], sentences[i+1]
        if len(a.split()) < 9 and len(b.split()) < 9:
            joined = a.rstrip(".!?") + ", and " + b[:1].lower() + b[1:]
            return _splice_sentence(text, a + " " + b, joined)
    return text


def _insert_hedge(text: str) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return text
    target = random.choice(sentences)
    hedge = random.choice(HEDGES_BANK)
    new = re.sub(r"^(\w+\s+\w+)", lambda m: f"{m.group(1)}, {hedge},", target, count=1)
    return _splice_sentence(text, target, new)


def _insert_discourse_marker(text: str) -> str:
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return text
    target = sentences[1]
    marker = random.choice(DISCOURSE_BANK).capitalize()
    new = f"{marker}, {target[:1].lower()}{target[1:]}"
    return _splice_sentence(text, target, new)


# Map gap features to candidate edit functions. The simulator picks the first
# function whose direction matches the gap.
EDIT_RULES = [
    # (feature_predicate, direction, edit_fn)
    (lambda f: f == "punct_comma_per1k", "raise", _add_comma),
    (lambda f: f == "punct_comma_per1k", "lower", _remove_comma),
    (lambda f: f == "mean_sent_len", "lower", _split_long_sentence),
    (lambda f: f == "mean_sent_len", "raise", _join_short_sentences),
    (lambda f: f == "comma_per_sentence", "raise", _add_comma),
    (lambda f: f == "comma_per_sentence", "lower", _remove_comma),
    (lambda f: f == "long_sent_ratio", "lower", _split_long_sentence),
    (lambda f: f == "short_sent_ratio", "lower", _join_short_sentences),
    (lambda f: f == "hedging_rate", "raise", _insert_hedge),
    (lambda f: f == "discourse_rate", "raise", _insert_discourse_marker),
]


def pick_edits(gap_report: dict):
    """Yield (edit_fn, gap) pairs for every applicable rule across top gaps.

    The caller tries each in order and falls through if a rule produces no
    change. This keeps the loop unstuck when the highest-priority gap has no
    matching edit candidate in the current text.
    """
    for gap in gap_report["top_gaps"]:
        direction = "raise" if gap["z_distance"] < 0 else "lower"
        for predicate, want_dir, fn in EDIT_RULES:
            if predicate(gap["feature"]) and want_dir == direction:
                yield fn, gap


def run_loop(target_text: str, benchmark_stats: dict, max_iter: int, threshold: float,
             verbose: bool = False) -> dict:
    def finish(final_text: str, stop_reason: str) -> dict:
        initial = history[0]["distance"] if history else 0.0
        final = history[-1]["distance"] if history else 0.0
        improvement = initial - final
        improvement_pct = (improvement / initial * 100.0) if initial else 0.0
        return {
            "final_text": final_text,
            "history": history,
            "stop_reason": stop_reason,
            "initial_distance": initial,
            "final_distance": final,
            "improvement_pct": improvement_pct,
        }

    history = []
    text = target_text
    last_distance = None
    plateau = 0

    for i in range(max_iter):
        stats = analyze(text)
        gap = compute_gaps(stats, benchmark_stats)
        entry = {"iter": i, "distance": gap["total_distance"]}
        if gap["top_gaps"]:
            entry["top_gap"] = gap["top_gaps"][0]["feature"]
            entry["top_gap_z"] = gap["top_gaps"][0]["z_distance"]
        history.append(entry)

        if verbose:
            top = gap["top_gaps"][:1]
            top_str = top[0]["feature"] if top else "—"
            print(f"  iter {i}: distance={gap['total_distance']:.4f}  top_gap={top_str}")

        if gap["total_distance"] < threshold:
            history[-1]["status"] = "converged"
            return finish(text, "converged")

        if last_distance is not None and abs(gap["total_distance"] - last_distance) < 0.001:
            plateau += 1
            if plateau >= 2:
                return finish(text, "plateau")
        else:
            plateau = 0
        last_distance = gap["total_distance"]

        new_text = text
        chosen_gap = None
        for edit_fn, gap_item in pick_edits(gap):
            attempt = edit_fn(text)
            if attempt != text:
                attempt_distance = compute_gaps(analyze(attempt), benchmark_stats)["total_distance"]
                if attempt_distance <= gap["total_distance"] + 0.001:
                    new_text = attempt
                    chosen_gap = gap_item
                    break
        if new_text == text:
            return finish(text, "no_applicable_rule_changed_text")
        if verbose and chosen_gap:
            print(f"           applied edit for {chosen_gap['feature']}")
        if chosen_gap:
            history[-1]["applied_edit"] = chosen_gap["feature"]
        text = new_text

    return finish(text, "max_iter")


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate Salix's rewrite loop without an LLM.")
    ap.add_argument("--target-text", required=True, help="Path to the draft to rewrite")
    ap.add_argument("--benchmark", required=True, help="Path to benchmark JSON")
    ap.add_argument("--max-iter", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", help="Optional path to save the rewritten text")
    args = ap.parse_args()

    random.seed(args.seed)
    import json
    bench = json.loads(Path(args.benchmark).read_text())
    bench_stats = bench.get("stats", bench)
    target_text = load_text(Path(args.target_text))

    if args.verbose:
        print(f"Initial text:\n{target_text[:200]}{'...' if len(target_text) > 200 else ''}\n")

    result = run_loop(target_text, bench_stats, args.max_iter, args.threshold, args.verbose)

    print(f"\nStop reason: {result['stop_reason']}")
    print(f"Iterations:  {len(result['history'])}")
    print("Distance trajectory:", " → ".join(f"{h['distance']:.3f}" for h in result["history"]))
    initial = result["history"][0]["distance"]
    final = result["history"][-1]["distance"]
    delta = initial - final
    print(f"Improvement: {initial:.3f} → {final:.3f} (Δ {delta:+.3f})")

    if args.out:
        Path(args.out).write_text(result["final_text"])
        print(f"Final text written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
