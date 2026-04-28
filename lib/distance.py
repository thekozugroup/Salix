"""Compare a target text's stats against a benchmark profile.

The output is a ranked list of feature gaps with direction and a human-readable
suggestion. The host model uses the top gaps to drive the next edit pass.

Distance is z-score-style L1: each scalar feature's deviation is normalized by
a fixed expected sigma derived from typical English-prose variance, so features
on different scales (counts vs ratios) contribute proportionally.

For list-valued features (n-grams, sentence starters), distance is the
Jensen-Shannon-flavoured distribution distance over the union of keys.
"""

from __future__ import annotations

import math

# Per-feature expected sigma for normalization. Derived from analysis of
# heterogeneous English prose corpora; tunable. The values are deliberately
# approximate — they only need to scale features so no single one dominates.
EXPECTED_SIGMA = {
    "ttr": 0.06,
    "mtld": 25.0,
    "mean_word_len": 0.6,
    "long_word_ratio": 0.05,
    "mean_sent_len": 6.0,
    "stdev_sent_len": 4.0,
    "short_sent_ratio": 0.10,
    "long_sent_ratio": 0.10,
    "comma_per_sentence": 0.6,
    "flesch_kincaid_grade": 3.0,
    "gunning_fog": 3.5,
    "ari": 3.5,
    "formality_f_score": 6.0,
    "passive_per1k": 8.0,
    "hedging_rate": 4.0,
    "booster_rate": 4.0,
    "discourse_rate": 4.0,
    "positive_rate": 5.0,
    "negative_rate": 5.0,
    "sentiment_polarity": 0.4,
    "mean_paragraph_sents": 2.0,
    "mean_paragraph_words": 40.0,
}

# Default sigma for any tracked feature without a custom value.
DEFAULT_SIGMA_PUNCT = 4.0
DEFAULT_SIGMA_FW = 3.0

# Feature category weights — what matters most when judging "voice".
WEIGHTS = {
    "punctuation": 1.2,
    "function_words": 1.5,
    "sentence_shape": 1.4,
    "lexical": 1.0,
    "readability": 0.6,
    "tone": 1.3,
    "paragraph": 0.8,
    "ngrams": 1.1,
}

# Excluded from gap report (not directly editable, or dependent on length)
SKIP_FEATURES = {
    "word_count", "type_count", "sentence_count", "max_sent_len",
    "paragraph_count", "sample_count", "total_word_count",
}


def _sigma_for(feature: str) -> float:
    if feature in EXPECTED_SIGMA:
        return EXPECTED_SIGMA[feature]
    if feature.startswith("punct_"):
        return DEFAULT_SIGMA_PUNCT
    if feature.startswith("fw_") and feature.endswith("_per1k"):
        return DEFAULT_SIGMA_FW
    return 1.0


def _category_for(feature: str) -> str:
    if feature.startswith("punct_"):
        return "punctuation"
    if feature.startswith("fw_") and feature.endswith("_per1k"):
        return "function_words"
    if feature in {"mean_sent_len", "stdev_sent_len", "short_sent_ratio",
                   "long_sent_ratio", "comma_per_sentence"}:
        return "sentence_shape"
    if feature in {"ttr", "mtld", "mean_word_len", "long_word_ratio"}:
        return "lexical"
    if feature in {"flesch_kincaid_grade", "gunning_fog", "ari"}:
        return "readability"
    if feature in {"hedging_rate", "booster_rate", "discourse_rate",
                   "positive_rate", "negative_rate", "sentiment_polarity",
                   "formality_f_score", "passive_per1k"}:
        return "tone"
    if feature.startswith("mean_paragraph"):
        return "paragraph"
    return "lexical"


def _suggestion(feature: str, target: float, benchmark: float) -> str:
    direction = "↑ raise" if target < benchmark else "↓ lower"
    delta = abs(target - benchmark)
    pretty = feature.replace("_per1k", " (per 1k words)").replace("_", " ")
    return f"{direction} {pretty} (target {target:.3f} vs benchmark {benchmark:.3f}, Δ {delta:.3f})"


def _distribution_distance(target_pairs, benchmark_pairs) -> tuple[float, list]:
    """Symmetric distribution distance over n-gram lists. Returns (distance, top_diffs)."""
    t_map = {k: v for k, v in target_pairs}
    b_map = {k: v for k, v in benchmark_pairs}
    keys = set(t_map) | set(b_map)
    if not keys:
        return 0.0, []
    diffs = []
    total = 0.0
    for k in keys:
        t = t_map.get(k, 0.0)
        b = b_map.get(k, 0.0)
        d = abs(t - b)
        total += d
        diffs.append((k, t, b, d))
    diffs.sort(key=lambda x: -x[3])
    top = [{"item": k, "target": round(t, 5), "benchmark": round(b, 5),
            "delta": round(d, 5)} for k, t, b, d in diffs[:8]]
    # divide by 2 for proper TVD-like scaling
    return total / 2.0, top


def compute_gaps(target: dict, benchmark: dict) -> dict:
    scalar_gaps = []
    category_totals: dict[str, float] = {}
    category_counts: dict[str, int] = {}

    for feature, t_val in target.items():
        if feature in SKIP_FEATURES:
            continue
        if isinstance(t_val, list):
            continue
        b_val = benchmark.get(feature)
        if b_val is None or not isinstance(b_val, (int, float)):
            continue
        sigma = _sigma_for(feature) or 1.0
        z = (t_val - b_val) / sigma
        cat = _category_for(feature)
        category_totals[cat] = category_totals.get(cat, 0.0) + abs(z)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        scalar_gaps.append({
            "feature": feature,
            "category": cat,
            "target": round(float(t_val), 4),
            "benchmark": round(float(b_val), 4),
            "z_distance": round(z, 3),
            "abs_z": round(abs(z), 3),
            "suggestion": _suggestion(feature, float(t_val), float(b_val)),
        })

    # n-gram distribution distances
    ngram_gaps = {}
    for list_feature in ("fw_bigrams", "fw_trigrams", "sentence_starters"):
        t_list = target.get(list_feature, [])
        b_list = benchmark.get(list_feature, [])
        dist, top = _distribution_distance(t_list, b_list)
        ngram_gaps[list_feature] = {
            "distance": round(dist, 4),
            "top_divergent": top,
        }
        category_totals["ngrams"] = category_totals.get("ngrams", 0.0) + dist * 5.0
        category_counts["ngrams"] = category_counts.get("ngrams", 0) + 1

    # Weighted total
    total = 0.0
    weight_sum = 0.0
    cat_summary = {}
    for cat, raw in category_totals.items():
        n = max(category_counts.get(cat, 1), 1)
        avg = raw / n
        w = WEIGHTS.get(cat, 1.0)
        cat_summary[cat] = {"avg_z": round(avg, 3), "weight": w,
                            "weighted": round(avg * w, 3)}
        total += avg * w
        weight_sum += w
    total_distance = total / weight_sum if weight_sum else 0.0

    scalar_gaps.sort(key=lambda g: -g["abs_z"])

    return {
        "total_distance": round(total_distance, 4),
        "category_summary": cat_summary,
        "top_gaps": scalar_gaps[:10],
        "ngram_gaps": ngram_gaps,
        "all_scalar_gaps": scalar_gaps,
    }
