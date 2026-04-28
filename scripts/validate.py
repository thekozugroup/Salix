#!/usr/bin/env python3
"""Validation harness — empirical evidence Salix's distance metric works.

**Caveat on the synthetic test below.** The default mode generates corpora
from style knobs that overlap with Salix's own measured features (sentence
length, comma rate, passive rate, hedge rate, vocabulary register). The
attribution result therefore confirms only that the implementation matches
the generator — not that the metric distinguishes real authors. Real-corpus
validation (PAN-13/14 closed-set, Federalist papers, Reuters_50_50) is the
honest test; that pathway is supported via the --corpus-dir flag.

Three checks, in order:

  1. **Attribution accuracy** (closed-set, min-distance classification):
     for each held-out document, predict the author whose benchmark is
     closest. Report overall accuracy and per-author confusion. Synthetic
     mode is a sanity check — real-corpus mode is the meaningful number.

  2. **Topic transfer**: train on topic A, test on topic B. Confirms the
     topic-blind fingerprint generalizes (the point of function-word +
     char-n-gram + Burrows features over raw vocabulary).

  3. **Stability**: leave-one-document-out across samples; per-feature
     drift relative to the full-corpus benchmark. Honest bound on how much
     the fingerprint moves under data perturbation.

Real-corpus mode: pass `--corpus-dir validation/corpora/` where each
sub-directory is one author and contains 4+ .txt/.md files. The harness
holds out one document per author and reports attribution accuracy.

Usage:
    python3 scripts/validate.py [--seed 0] [--authors 5] [--docs-per-author 6]
                                [--corpus-dir <dir>] [--out validation/results.md]
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import _path  # noqa: F401

from lib.distance import compute_gaps
from lib.io_utils import clean_text
from lib.stats import aggregate, analyze

# Topic-specific content vocabularies. Style knobs drive sentence shape;
# topic vocabs only swap in nouns/verbs, leaving the stylistic skeleton
# constant. This mirrors how a real author writes about different topics.
TOPIC_NOUNS = {
    "cooking":  ["sauce", "kitchen", "knife", "onion", "stock", "pan", "salt", "garlic", "broth", "bread"],
    "finance":  ["market", "yield", "asset", "trade", "ledger", "rate", "fund", "bond", "equity", "spread"],
    "biology":  ["cell", "tissue", "enzyme", "gene", "pathway", "protein", "lipid", "membrane", "cascade", "receptor"],
    "music":    ["chord", "tempo", "phrase", "tone", "key", "rhythm", "song", "melody", "voice", "beat"],
    "travel":   ["coast", "valley", "city", "ridge", "harbor", "bridge", "garden", "market", "trail", "square"],
}
TOPIC_VERBS = {
    "cooking":  ["simmer", "fold", "reduce", "season", "rest", "deglaze", "blanch"],
    "finance":  ["allocate", "hedge", "settle", "discount", "compound", "rotate", "rebalance"],
    "biology":  ["bind", "fold", "express", "secrete", "regulate", "inhibit", "activate"],
    "music":    ["resolve", "modulate", "build", "release", "voice", "swell", "rest"],
    "travel":   ["cross", "wander", "follow", "pause", "linger", "ascend", "descend"],
}

# Pseudo-author style knobs. Each author has a distinct combination.
def _style_profile(seed: int) -> dict:
    rng = random.Random(seed)
    return {
        "mean_sl": rng.choice([8, 12, 16, 22, 28]),       # mean sentence length
        "sl_var": rng.choice([2, 4, 7, 10]),              # sentence-length variance
        "comma_rate": rng.choice([0.2, 0.5, 1.0, 1.6]),   # commas per sentence
        "hedge_rate": rng.choice([0.0, 0.05, 0.15, 0.30]),# probability per sentence
        "boost_rate": rng.choice([0.0, 0.05, 0.20]),
        "discourse_rate": rng.choice([0.0, 0.10, 0.25]),
        "formal_vocab": rng.random() > 0.5,               # latinate vs anglo-saxon
        "passive_rate": rng.choice([0.0, 0.10, 0.25]),
    }

ANGLO  = ["good", "thing", "make", "show", "let", "see", "want", "go", "say", "find"]
LATIN  = ["consideration", "proposition", "implication", "structure", "argument", "framework", "tradition", "convention", "operation"]
HEDGES = ["perhaps", "rather", "somewhat", "arguably", "I think", "in some sense"]
BOOSTS = ["clearly", "indeed", "certainly", "definitely"]
DISCS  = ["however", "moreover", "consequently", "nevertheless", "thus", "therefore"]


def _generate_sentence(profile: dict, topic: str, rng: random.Random) -> str:
    target_len = max(3, int(rng.gauss(profile["mean_sl"], profile["sl_var"])))
    nouns = TOPIC_NOUNS[topic]
    verbs = TOPIC_VERBS[topic]
    style_pool = LATIN if profile["formal_vocab"] else ANGLO

    words: list[str] = []

    if rng.random() < profile["discourse_rate"]:
        words.append(rng.choice(DISCS) + ",")

    # Build a noun-phrase + verb + noun-phrase skeleton, padded with style words.
    words += [rng.choice(["the", "a", "this", "every", "some"]),
              rng.choice(nouns),
              rng.choice(["and", "of", "with"]),
              rng.choice(["the", "a", "its"]),
              rng.choice(nouns)]
    if rng.random() < profile["passive_rate"]:
        words += ["was", rng.choice(verbs) + "ed", "by", rng.choice(["the", "a"]), rng.choice(nouns)]
    else:
        words += [rng.choice(verbs) + "s", rng.choice(["the", "a"]), rng.choice(nouns)]

    if rng.random() < profile["hedge_rate"]:
        words.insert(2, rng.choice(HEDGES) + ",")

    if rng.random() < profile["boost_rate"]:
        words.insert(1, rng.choice(BOOSTS))

    while len(words) < target_len:
        words.append(rng.choice(style_pool))

    # Inject commas roughly per profile.comma_rate.
    n_commas = int(profile["comma_rate"])
    for _ in range(n_commas):
        if len(words) > 4:
            idx = rng.randint(2, len(words) - 2)
            if not words[idx].endswith(","):
                words[idx] = words[idx] + ","

    sent = " ".join(words)
    sent = sent[:1].upper() + sent[1:]
    sent = sent.rstrip(",")
    sent += rng.choice([".", ".", ".", ".", "?", "!"])
    return sent


def generate_doc(profile: dict, topic: str, n_sentences: int, seed: int) -> str:
    rng = random.Random(seed)
    sents = [_generate_sentence(profile, topic, rng) for _ in range(n_sentences)]
    paragraphs = []
    cur: list[str] = []
    for s in sents:
        cur.append(s)
        if len(cur) >= rng.randint(2, 5):
            paragraphs.append(" ".join(cur))
            cur = []
    if cur:
        paragraphs.append(" ".join(cur))
    return "\n\n".join(paragraphs)


def attribution_check_real(corpus_dir: Path, kfold: bool = True) -> dict:
    """Attribution accuracy on a user-supplied real corpus.

    Layout: corpus_dir/<author_label>/<doc_N>.{txt,md} with at least 3
    documents per author. By default (kfold=True), runs leave-one-out per
    author: each author's docs are held out one at a time, the rest become
    that author's training set, and every other author's full set is the
    benchmark. Reports total accuracy across all folds.

    With kfold=False, a single rightmost document per author is held out
    (the original behavior).
    """
    from lib.io_utils import load_text
    if not corpus_dir.is_dir():
        raise SystemExit(f"Corpus dir not found: {corpus_dir}")
    author_dirs = sorted(p for p in corpus_dir.iterdir() if p.is_dir())
    if len(author_dirs) < 2:
        raise SystemExit(f"Need >=2 author subdirectories under {corpus_dir}")

    author_files: dict[str, list[Path]] = {}
    for ad in author_dirs:
        files = sorted(list(ad.glob("*.txt")) + list(ad.glob("*.md")))
        if len(files) < 3:
            raise SystemExit(f"Author '{ad.name}' has only {len(files)} docs; need >=3")
        author_files[ad.name] = files

    correct = 0
    total = 0
    confusion: dict[tuple[str, str], int] = {}

    def _classify(target_path: Path, true_label: str,
                  held_idx: int | None) -> str:
        nonlocal correct, total
        # Build benchmarks per author with the held-out doc removed for the
        # true author; every other author uses all their docs.
        benchmarks: dict[str, dict] = {}
        for label, files in author_files.items():
            if label == true_label and held_idx is not None:
                train_files = [f for i, f in enumerate(files) if i != held_idx]
            else:
                train_files = files
            train_stats = [analyze(load_text(f)) for f in train_files]
            benchmarks[label] = aggregate(train_stats)
        target_stats = analyze(load_text(target_path))
        scores = {a: compute_gaps(target_stats, b)["total_distance"]
                  for a, b in benchmarks.items()}
        pred = min(scores, key=scores.get)
        if pred == true_label:
            correct += 1
        total += 1
        confusion[(true_label, pred)] = confusion.get((true_label, pred), 0) + 1
        return pred

    if kfold:
        for label, files in author_files.items():
            for held_idx, held in enumerate(files):
                _classify(held, label, held_idx)
    else:
        for label, files in author_files.items():
            _classify(files[-1], label, len(files) - 1)

    return {
        "mode": "real_corpus" + (" (LOO k-fold)" if kfold else ""),
        "authors": len(author_dirs),
        "docs_per_author": "varies",
        "accuracy": correct / max(total, 1),
        "correct": correct,
        "total": total,
        "confusion": confusion,
    }


def attribution_check(authors: int, docs_per_author: int, seed: int,
                      sentences_per_doc: int = 60) -> dict:
    profiles = [_style_profile(seed + i * 1009) for i in range(authors)]
    topics = list(TOPIC_NOUNS.keys())

    benchmarks: dict[int, dict] = {}
    held_out: list[tuple[int, str, str]] = []

    for aid, prof in enumerate(profiles):
        # Hold out 1 doc per author for testing
        train_topic = topics[aid % len(topics)]
        train_docs = [generate_doc(prof, train_topic, sentences_per_doc, seed + aid * 17 + i)
                      for i in range(docs_per_author - 1)]
        held = generate_doc(prof, train_topic, sentences_per_doc, seed + aid * 17 + docs_per_author)
        per_doc_stats = [analyze(clean_text(d)) for d in train_docs]
        benchmarks[aid] = aggregate(per_doc_stats)
        held_out.append((aid, train_topic, held))

    correct = 0
    confusion: dict[tuple[int, int], int] = {}
    for true_id, topic, doc in held_out:
        target_stats = analyze(clean_text(doc))
        scores = {aid: compute_gaps(target_stats, b)["total_distance"]
                  for aid, b in benchmarks.items()}
        pred = min(scores, key=scores.get)
        if pred == true_id:
            correct += 1
        confusion[(true_id, pred)] = confusion.get((true_id, pred), 0) + 1

    return {
        "authors": authors,
        "docs_per_author": docs_per_author,
        "accuracy": correct / max(len(held_out), 1),
        "correct": correct,
        "total": len(held_out),
        "confusion": confusion,
    }


def topic_transfer_check(authors: int, seed: int, sentences_per_doc: int = 60) -> dict:
    profiles = [_style_profile(seed + i * 1009) for i in range(authors)]
    topics = list(TOPIC_NOUNS.keys())
    if len(topics) < 2:
        return {"accuracy": None, "note": "need >=2 topics"}

    same_dist = []
    cross_dist = []

    for aid, prof in enumerate(profiles):
        topic_a = topics[aid % len(topics)]
        topic_b = topics[(aid + 1) % len(topics)]
        # Build benchmark on topic A
        train_docs = [generate_doc(prof, topic_a, sentences_per_doc, seed + aid * 31 + i)
                      for i in range(4)]
        bench = aggregate([analyze(clean_text(d)) for d in train_docs])
        # Same-author test on topic B
        held_b = generate_doc(prof, topic_b, sentences_per_doc, seed + aid * 31 + 99)
        d_same = compute_gaps(analyze(clean_text(held_b)), bench)["total_distance"]
        same_dist.append(d_same)
        # Other-author test on topic B
        other_aid = (aid + 1) % authors
        other_prof = profiles[other_aid]
        held_o = generate_doc(other_prof, topic_b, sentences_per_doc, seed + aid * 31 + 199)
        d_cross = compute_gaps(analyze(clean_text(held_o)), bench)["total_distance"]
        cross_dist.append(d_cross)

    n = len(same_dist)
    correct_separation = sum(1 for s, c in zip(same_dist, cross_dist) if s < c)
    return {
        "authors": authors,
        "mean_same_author_distance": sum(same_dist) / n,
        "mean_other_author_distance": sum(cross_dist) / n,
        "correct_separations": correct_separation,
        "total_pairs": n,
        "separation_accuracy": correct_separation / n,
    }


def stability_check(seed: int, sentences_per_doc: int = 60) -> dict:
    """Leave-one-out stability: drop each sample, re-aggregate, measure drift."""
    prof = _style_profile(seed)
    topic = "cooking"
    docs = [generate_doc(prof, topic, sentences_per_doc, seed + i * 7) for i in range(8)]
    per_doc = [analyze(clean_text(d)) for d in docs]

    full_bench = aggregate(per_doc)
    drifts = []
    for i in range(len(per_doc)):
        loo = aggregate(per_doc[:i] + per_doc[i+1:])
        gap = compute_gaps(loo, full_bench)
        drifts.append(gap["total_distance"])

    return {
        "samples": len(docs),
        "loo_drifts": [round(d, 4) for d in drifts],
        "mean_drift": sum(drifts) / len(drifts),
        "max_drift": max(drifts),
    }


def render_report(attribution, topic_transfer, stability) -> str:
    lines = ["# Salix Validation Report", ""]
    mode = attribution.get("mode", "synthetic")
    if mode == "synthetic":
        lines.append("> ⚠️ Synthetic-corpus mode. The pseudo-author style knobs overlap with")
        lines.append("> Salix's own measured features, so a high accuracy here demonstrates")
        lines.append("> implementation correctness, not real authorship-attribution power.")
        lines.append("> Run with --corpus-dir against PAN/Federalist/Reuters_50_50 for the")
        lines.append("> meaningful number.")
        lines.append("")
    lines.append(f"## 1. Attribution accuracy ({mode})")
    lines.append("")
    lines.append(f"- Authors: **{attribution['authors']}**")
    if mode == "synthetic":
        lines.append(f"- Documents per author (training set): **{attribution['docs_per_author'] - 1}**")
    else:
        lines.append(f"- Documents per author: **{attribution['docs_per_author']}**")
    lines.append(f"- Held-out documents: **{attribution['total']}**")
    lines.append(f"- **Accuracy: {attribution['accuracy']:.1%}** "
                 f"({attribution['correct']}/{attribution['total']}; "
                 f"chance = {1.0/attribution['authors']:.1%})")
    lines.append("")
    if attribution["confusion"]:
        lines.append("Confusion (true → predicted):")
        for (t, p), n in sorted(attribution["confusion"].items()):
            mark = "✓" if t == p else "✗"
            lines.append(f"  - {mark} author {t} → predicted {p}: {n}")
    lines.append("")

    lines.append("## 2. Topic transfer")
    lines.append("")
    lines.append("Each author trained on topic A, tested on topic B. The "
                 "fingerprint should rank a same-author document closer than "
                 "an other-author document, even on the unseen topic.")
    lines.append("")
    lines.append(f"- Mean same-author distance:  **{topic_transfer['mean_same_author_distance']:.3f}**")
    lines.append(f"- Mean other-author distance: **{topic_transfer['mean_other_author_distance']:.3f}**")
    lines.append(f"- Correct separations: **{topic_transfer['correct_separations']}/{topic_transfer['total_pairs']}** "
                 f"({topic_transfer['separation_accuracy']:.1%})")
    lines.append("")

    lines.append("## 3. Benchmark stability")
    lines.append("")
    lines.append("Leave-one-out: drop each sample, re-aggregate, measure the "
                 "distance between the leave-one-out and full-corpus benchmarks. "
                 "Lower = more stable.")
    lines.append("")
    lines.append(f"- Samples: **{stability['samples']}**")
    lines.append(f"- Mean LOO drift: **{stability['mean_drift']:.3f}**")
    lines.append(f"- Max LOO drift:  **{stability['max_drift']:.3f}**")
    lines.append(f"- Per-sample drifts: {stability['loo_drifts']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Salix validation harness.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--authors", type=int, default=5)
    ap.add_argument("--docs-per-author", type=int, default=6)
    ap.add_argument("--sentences-per-doc", type=int, default=60)
    ap.add_argument("--corpus-dir", default=None,
                    help="Real-corpus dir; subdirs are authors. Overrides synthetic mode.")
    ap.add_argument("--out", default=None, help="Optional path to save the report")
    args = ap.parse_args()

    if args.corpus_dir:
        print(f"Running attribution check on real corpus: {args.corpus_dir}")
        attr = attribution_check_real(Path(args.corpus_dir))
    else:
        print("Running attribution check (synthetic — see harness docstring on circularity)...")
        attr = attribution_check(args.authors, args.docs_per_author, args.seed,
                                 args.sentences_per_doc)
    print("Running topic-transfer check...")
    tt = topic_transfer_check(args.authors, args.seed, args.sentences_per_doc)
    print("Running stability check...")
    stab = stability_check(args.seed, args.sentences_per_doc)

    report = render_report(attr, tt, stab)
    print()
    print(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report)
        print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
