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
    "_sigma",
}


def _sigma_for(feature: str, empirical: dict | None = None) -> float:
    """Return the standard deviation to use for normalizing a feature's z-score.

    Resolution order:
      1. Empirical within-author sigma from the benchmark's `_sigma` dict
         (computed at ingest from per-document variance). Skipped if the value
         is too small to be meaningful (avoids dividing by ~0 noise).
      2. Hand-tuned `EXPECTED_SIGMA` prior for known features.
      3. Default sigma by feature family (punct_, fw_).
      4. 1.0 fallback.
    """
    if empirical:
        emp = empirical.get(feature)
        if emp is not None and emp > 1e-6:
            # Floor empirical sigma at 25% of the prior (when one exists) so a
            # single-author corpus that happens to be very consistent on a
            # feature doesn't explode every small deviation into a giant z.
            prior = EXPECTED_SIGMA.get(feature)
            if prior is not None:
                return max(emp, 0.25 * prior)
            return emp
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


# Concrete edit hints the host model can act on directly. Keyed by
# (feature_match, direction) where direction is "raise" (target < benchmark)
# or "lower" (target > benchmark).
EDIT_HINTS: dict[tuple[str, str], str] = {
    ("punct_comma_per1k", "raise"):
        "Add commas around interjections, after introductory phrases, and before "
        "coordinating conjunctions in compound sentences. Use them to mark "
        "subordinate clauses and parenthetical asides.",
    ("punct_comma_per1k", "lower"):
        "Remove unnecessary commas. Trim parenthetical asides and prefer simpler "
        "main-clause sentences over those layered with subordinate fragments.",
    ("punct_semicolon_per1k", "raise"):
        "Use semicolons to join two related independent clauses where the second "
        "extends or qualifies the first, in place of a period or 'and'.",
    ("punct_emdash_per1k", "raise"):
        "Use em-dashes — like this — to mark sharp asides, abrupt shifts, or "
        "emphasis. Replace some parenthesis/comma pairs with dashes.",
    ("punct_question_per1k", "raise"):
        "Pose more rhetorical questions to the reader; convert some declarative "
        "statements into interrogative ones.",
    ("mean_sent_len", "lower"):
        "Break long sentences at natural pause points (commas, conjunctions). "
        "Target a mix that averages closer to the benchmark length.",
    ("mean_sent_len", "raise"):
        "Combine adjacent short sentences using subordinate clauses, semicolons, "
        "or coordinating conjunctions. Avoid choppy staccato.",
    ("stdev_sent_len", "raise"):
        "Increase variation in sentence length. Place a very short sentence next "
        "to a much longer one to create rhythm.",
    ("stdev_sent_len", "lower"):
        "Even out sentence length. Avoid extreme outliers — split very long "
        "sentences and pad terse ones with qualifying clauses.",
    ("short_sent_ratio", "lower"):
        "Combine or expand sentences shorter than ~8 words.",
    ("long_sent_ratio", "lower"):
        "Split sentences longer than ~25 words at clause boundaries.",
    ("comma_per_sentence", "raise"):
        "Add subordinate clauses and parenthetical asides set off by commas.",
    ("comma_per_sentence", "lower"):
        "Tighten sentences. Drop subordinate asides; prefer simple main clauses.",
    ("ttr", "raise"):
        "Vary word choice — replace repeated content words with synonyms; "
        "introduce more distinct vocabulary.",
    ("ttr", "lower"):
        "Reuse key terms instead of seeking synonyms. Repetition is permitted.",
    ("mean_word_len", "raise"):
        "Prefer longer, often Latinate words over short Anglo-Saxon ones where "
        "register permits.",
    ("mean_word_len", "lower"):
        "Prefer short, plain Anglo-Saxon words over longer Latinate ones.",
    ("long_word_ratio", "raise"):
        "Use more multisyllabic words; lean into precise technical or formal "
        "vocabulary.",
    ("long_word_ratio", "lower"):
        "Replace long words with shorter, more direct alternatives.",
    ("hedging_rate", "raise"):
        "Soften absolute claims with hedges: 'perhaps', 'rather', 'somewhat', "
        "'might', 'seems to', 'tends to'. Avoid declaring certainty.",
    ("hedging_rate", "lower"):
        "Strip hedges. Make assertions directly. Cut 'perhaps', 'maybe', "
        "'somewhat', 'might', 'tends to'.",
    ("booster_rate", "raise"):
        "Add emphatic boosters where claims are made: 'clearly', 'indeed', "
        "'certainly', 'truly', 'definitely'.",
    ("booster_rate", "lower"):
        "Remove emphatic boosters. Let claims stand on their substance.",
    ("discourse_rate", "raise"):
        "Add explicit discourse markers between sentences: 'however', "
        "'moreover', 'consequently', 'thus', 'nevertheless'.",
    ("discourse_rate", "lower"):
        "Reduce explicit discourse markers. Let logical relations be implicit.",
    ("formality_f_score", "raise"):
        "Raise formality: expand contractions, prefer noun phrases over verbs, "
        "use Latinate vocabulary, reduce first/second-person pronouns, replace "
        "fillers with precise terms.",
    ("formality_f_score", "lower"):
        "Lower formality: use contractions, more first/second-person pronouns, "
        "shorter Anglo-Saxon words, conversational fillers where natural.",
    ("passive_per1k", "lower"):
        "Convert passive constructions to active voice. 'X was done by Y' → "
        "'Y did X'. Identify the agent and put it first.",
    ("passive_per1k", "raise"):
        "Use passive constructions where the agent is unimportant or unknown, "
        "or where the patient deserves topic position.",
    ("positive_rate", "raise"):
        "Increase use of affirming language: 'good', 'strong', 'clear', "
        "'helpful', 'useful', 'elegant'.",
    ("positive_rate", "lower"):
        "Reduce overtly positive evaluative language. Stay more neutral.",
    ("negative_rate", "lower"):
        "Soften critical phrasing. Replace 'bad', 'wrong', 'broken' with more "
        "neutral or hedged alternatives.",
    ("mean_paragraph_sents", "raise"):
        "Develop paragraphs further before breaking. Combine short paragraphs "
        "where they share a single idea.",
    ("mean_paragraph_sents", "lower"):
        "Break dense paragraphs into shorter ones. One topic per paragraph.",
}


def _hint_for(feature: str, direction: str) -> str:
    """Look up a concrete edit hint for a (feature, direction) pair.

    Function-word features (`fw_perhaps_per1k`) are handled by template since
    there are dozens of them and each maps to the same kind of edit.
    """
    key = (feature, direction)
    if key in EDIT_HINTS:
        return EDIT_HINTS[key]
    if feature.startswith("fw_") and feature.endswith("_per1k"):
        word = feature[len("fw_"):-len("_per1k")]
        if direction == "raise":
            return (f"Use the word '{word}' more often where natural — it is a "
                    f"signature of the benchmark style.")
        return (f"Use the word '{word}' less often. The benchmark style uses it "
                f"sparingly.")
    if feature.startswith("punct_") and feature.endswith("_per1k"):
        mark = feature[len("punct_"):-len("_per1k")].replace("_", " ")
        verb = "more" if direction == "raise" else "less"
        return f"Use the '{mark}' mark {verb} often."
    return ""


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

    empirical_sigma = benchmark.get("_sigma") if isinstance(benchmark, dict) else None

    for feature, t_val in target.items():
        if feature in SKIP_FEATURES or feature.startswith("_"):
            continue
        if isinstance(t_val, list):
            continue
        b_val = benchmark.get(feature)
        if b_val is None or not isinstance(b_val, (int, float)):
            continue
        sigma = _sigma_for(feature, empirical_sigma) or 1.0
        z = (t_val - b_val) / sigma
        cat = _category_for(feature)
        category_totals[cat] = category_totals.get(cat, 0.0) + abs(z)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        direction = "raise" if t_val < b_val else "lower"
        scalar_gaps.append({
            "feature": feature,
            "category": cat,
            "target": round(float(t_val), 4),
            "benchmark": round(float(b_val), 4),
            "z_distance": round(z, 3),
            "abs_z": round(abs(z), 3),
            "direction": direction,
            "suggestion": _suggestion(feature, float(t_val), float(b_val)),
            "edit_hint": _hint_for(feature, direction),
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
