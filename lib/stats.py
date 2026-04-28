"""Linguistic feature extraction — pure stdlib."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from .function_words import FUNCTION_WORDS
from .tone import tone_metrics, heylighen_f_score

# Sentence boundary regex. Naive but fast: split on . ! ? followed by whitespace
# and a capital. Avoids splitting on common abbreviations.
_ABBR = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "cf", "fig", "vol", "no", "p", "pp", "ch", "inc", "ltd",
    "co", "corp", "u.s", "u.k",
}
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SYLLABLE_VOWEL_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)

PUNCT_TRACKED = [
    ("comma", ","),
    ("semicolon", ";"),
    ("colon", ":"),
    ("emdash", "—"),
    ("hyphen", "-"),
    ("lparen", "("),
    ("question", "?"),
    ("exclaim", "!"),
    ("dquote", '"'),
    ("squote", "'"),
    ("ellipsis", "…"),
]


def split_sentences(text: str) -> list[str]:
    """Sentence segmentation with abbreviation guard."""
    # Mask known abbreviations so the splitter doesn't cut after them.
    masked = text
    for abbr in _ABBR:
        masked = re.sub(
            rf"\b{re.escape(abbr)}\.\s",
            lambda m, a=abbr: f"{a}· ",  # interpunct as placeholder
            masked,
            flags=re.IGNORECASE,
        )
    parts = SENT_SPLIT_RE.split(masked)
    sents = [p.replace("·", ".").strip() for p in parts if p.strip()]
    return sents


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens. Punctuation handled separately."""
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]


def estimate_syllables(word: str) -> int:
    """Heuristic syllable count. Handles silent-e, common patterns."""
    w = word.lower()
    if not w:
        return 0
    # strip silent trailing e (but not for short words like "be", "the")
    if len(w) > 3 and w.endswith("e") and not w.endswith("le"):
        w = w[:-1]
    groups = SYLLABLE_VOWEL_RE.findall(w)
    n = max(len(groups), 1)
    return n


def punctuation_rates(text: str, total_words: int) -> dict[str, float]:
    """Counts per 1000 words for tracked punctuation."""
    if total_words == 0:
        return {f"punct_{name}_per1k": 0.0 for name, _ in PUNCT_TRACKED}
    per1k = 1000.0 / total_words
    out = {}
    for name, ch in PUNCT_TRACKED:
        out[f"punct_{name}_per1k"] = text.count(ch) * per1k
    # also approximate em-dash as "--" if no unicode dash present
    if out["punct_emdash_per1k"] == 0.0:
        out["punct_emdash_per1k"] = text.count("--") * per1k
    return out


def lexical_features(tokens: list[str]) -> dict[str, float]:
    n = len(tokens)
    if n == 0:
        return {
            "word_count": 0, "type_count": 0, "ttr": 0.0, "mean_word_len": 0.0,
            "long_word_ratio": 0.0,
        }
    types = set(tokens)
    ttr = len(types) / n
    mean_len = sum(len(t) for t in tokens) / n
    long_words = sum(1 for t in tokens if len(t) >= 7)
    return {
        "word_count": n,
        "type_count": len(types),
        "ttr": ttr,
        "mean_word_len": mean_len,
        "long_word_ratio": long_words / n,
    }


def mtld(tokens: list[str], threshold: float = 0.72) -> float:
    """Measure of Textual Lexical Diversity. More stable than TTR for varying lengths."""
    if not tokens:
        return 0.0

    def _factor_count(seq: list[str]) -> float:
        factors = 0
        types: set[str] = set()
        running = 0
        for tok in seq:
            running += 1
            types.add(tok)
            cur_ttr = len(types) / running
            if cur_ttr <= threshold:
                factors += 1
                running = 0
                types = set()
        if running > 0:
            partial = (1 - cur_ttr) / (1 - threshold) if cur_ttr < 1 else 1
            factors += partial
        return factors if factors > 0 else 1.0

    forward = _factor_count(tokens)
    backward = _factor_count(list(reversed(tokens)))
    avg_factors = (forward + backward) / 2
    return len(tokens) / avg_factors


def sentence_features(sentences: list[str]) -> dict[str, float]:
    if not sentences:
        return {
            "sentence_count": 0, "mean_sent_len": 0.0, "stdev_sent_len": 0.0,
            "max_sent_len": 0, "short_sent_ratio": 0.0, "long_sent_ratio": 0.0,
            "comma_per_sentence": 0.0,
        }
    lens = [len(tokenize(s)) for s in sentences]
    n = len(lens)
    mean = sum(lens) / n
    var = sum((x - mean) ** 2 for x in lens) / n
    stdev = math.sqrt(var)
    short = sum(1 for x in lens if x < 8) / n
    long_ = sum(1 for x in lens if x > 25) / n
    commas_per_sent = sum(s.count(",") for s in sentences) / n
    return {
        "sentence_count": n,
        "mean_sent_len": mean,
        "stdev_sent_len": stdev,
        "max_sent_len": max(lens),
        "short_sent_ratio": short,
        "long_sent_ratio": long_,
        "comma_per_sentence": commas_per_sent,
    }


def readability(tokens: list[str], sentences: list[str]) -> dict[str, float]:
    n_words = len(tokens)
    n_sents = max(len(sentences), 1)
    if n_words == 0:
        return {"flesch_kincaid_grade": 0.0, "gunning_fog": 0.0, "ari": 0.0}
    syllables = sum(estimate_syllables(t) for t in tokens)
    complex_words = sum(1 for t in tokens if estimate_syllables(t) >= 3)
    words_per_sent = n_words / n_sents

    fk = 0.39 * words_per_sent + 11.8 * (syllables / n_words) - 15.59
    fog = 0.4 * (words_per_sent + 100.0 * complex_words / n_words)
    chars = sum(len(t) for t in tokens)
    ari = 4.71 * (chars / n_words) + 0.5 * words_per_sent - 21.43
    return {"flesch_kincaid_grade": fk, "gunning_fog": fog, "ari": ari}


# Top-N function words to track by individual frequency (per 1000 words).
# Rest of FUNCTION_WORDS are still used for n-gram fingerprints.
FW_TRACKED = [
    "the", "of", "and", "to", "a", "in", "that", "is", "it", "for",
    "as", "with", "on", "be", "this", "by", "but", "not", "or", "are",
    "i", "we", "you", "they", "he", "she",
    "perhaps", "rather", "quite", "indeed", "however", "moreover",
    "though", "therefore", "thus", "actually", "really", "very",
    "which", "would", "could", "should", "must", "may", "might",
    "if", "when", "while", "because", "since", "although",
]


def function_word_rates(tokens: list[str], total_words: int) -> dict[str, float]:
    if total_words == 0:
        return {f"fw_{w}_per1k": 0.0 for w in FW_TRACKED}
    counts = Counter(tokens)
    per1k = 1000.0 / total_words
    return {f"fw_{w}_per1k": counts.get(w, 0) * per1k for w in FW_TRACKED}


def function_word_ngrams(tokens: list[str], n: int = 2, top_k: int = 25) -> list[list]:
    """Top-K function-word n-grams with normalized frequencies.

    Tokens are first filtered to function words only — this strips topic-specific
    vocabulary, leaving a topic-blind stylistic skeleton.
    """
    fw_seq = [t if t in FUNCTION_WORDS else "_X_" for t in tokens]
    grams = []
    for i in range(len(fw_seq) - n + 1):
        window = fw_seq[i : i + n]
        if "_X_" in window:
            continue
        grams.append(" ".join(window))
    counter = Counter(grams)
    total = sum(counter.values()) or 1
    items = counter.most_common(top_k)
    return [[g, round(c / total, 6)] for g, c in items]


def sentence_starters(sentences: list[str], top_k: int = 15) -> list[list]:
    """Distribution of first words. Captures cadence."""
    starters = []
    for s in sentences:
        toks = tokenize(s)
        if toks:
            starters.append(toks[0])
    if not starters:
        return []
    counter = Counter(starters)
    total = sum(counter.values())
    return [[w, round(c / total, 6)] for w, c in counter.most_common(top_k)]


def pos_proxies(tokens: list[str]) -> dict[str, int]:
    """Coarse POS counts via lexical proxies for the formality score.

    Pronoun, article, prep counts come from FUNCTION_WORDS membership. Others
    use suffix heuristics — imperfect but consistent across texts.
    """
    PRONOUNS = {
        "i", "me", "my", "mine", "we", "us", "our", "ours",
        "you", "your", "yours", "he", "him", "his", "she", "her", "hers",
        "it", "its", "they", "them", "their", "theirs",
        "this", "that", "these", "those", "who", "whom", "what", "which",
    }
    ARTICLES = {"a", "an", "the"}
    PREPS = {
        "of", "in", "on", "at", "by", "to", "from", "with", "for",
        "about", "into", "over", "through", "between", "among", "against",
        "during", "without", "within", "across",
    }
    INTERJ = {"oh", "ah", "well", "okay", "ok", "yes", "no", "right", "wow"}

    counts = {"noun": 0, "adj": 0, "adv": 0, "verb": 0,
              "pron": 0, "article": 0, "prep": 0, "interj": 0}

    for t in tokens:
        if t in PRONOUNS:
            counts["pron"] += 1
            continue
        if t in ARTICLES:
            counts["article"] += 1
            continue
        if t in PREPS:
            counts["prep"] += 1
            continue
        if t in INTERJ:
            counts["interj"] += 1
            continue
        if t.endswith("ly") and len(t) > 4:
            counts["adv"] += 1
            continue
        if t.endswith(("ous", "ive", "ful", "less", "able", "ible", "al")) and len(t) > 5:
            counts["adj"] += 1
            continue
        if t.endswith(("ing", "ed", "ize", "ise")) and len(t) > 4:
            counts["verb"] += 1
            continue
        if t.endswith(("tion", "sion", "ment", "ness", "ity", "ship", "hood")) and len(t) > 5:
            counts["noun"] += 1
            continue
        # default: noun-ish content word
        if t not in FUNCTION_WORDS:
            counts["noun"] += 1
    return counts


def passive_proxy_rate(text: str, total_words: int) -> float:
    """Approximate passive-voice rate: be-verb followed by a past participle.

    Crude regex; counts forms like "is built", "was created", "have been ...ed".
    Useful as a relative metric across the same author.
    """
    if total_words == 0:
        return 0.0
    pattern = re.compile(
        r"\b(is|are|was|were|be|been|being|am|got|gets|getting)\s+"
        r"(\w+ed|\w+en|done|made|seen|known|given|taken|written|"
        r"shown|found|brought|caught|held|kept|left|sent|told|set|put)\b",
        re.IGNORECASE,
    )
    return 1000.0 * len(pattern.findall(text)) / total_words


def paragraph_features(text: str) -> dict[str, float]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return {"paragraph_count": 0, "mean_paragraph_sents": 0.0, "mean_paragraph_words": 0.0}
    sent_counts = [len(split_sentences(p)) for p in paragraphs]
    word_counts = [len(tokenize(p)) for p in paragraphs]
    n = len(paragraphs)
    return {
        "paragraph_count": n,
        "mean_paragraph_sents": sum(sent_counts) / n,
        "mean_paragraph_words": sum(word_counts) / n,
    }


def analyze(text: str) -> dict:
    """Top-level: compute the full feature dict for a text."""
    sentences = split_sentences(text)
    tokens = tokenize(text)
    n_words = len(tokens)
    text_lower = text.lower()

    features: dict = {}
    features.update(lexical_features(tokens))
    features["mtld"] = round(mtld(tokens), 3)
    features.update({k: round(v, 4) for k, v in sentence_features(sentences).items() if isinstance(v, float)} |
                    {k: v for k, v in sentence_features(sentences).items() if not isinstance(v, float)})
    features.update({k: round(v, 4) for k, v in punctuation_rates(text, n_words).items()})
    features.update({k: round(v, 4) for k, v in readability(tokens, sentences).items()})
    features.update({k: round(v, 4) for k, v in function_word_rates(tokens, n_words).items()})

    pos = pos_proxies(tokens)
    features["formality_f_score"] = round(heylighen_f_score(pos, n_words), 3)
    features["passive_per1k"] = round(passive_proxy_rate(text, n_words), 3)

    features.update({k: round(v, 4) for k, v in tone_metrics(tokens, text_lower, n_words).items()})

    features.update({k: round(v, 4) for k, v in paragraph_features(text).items() if isinstance(v, float)})
    features["paragraph_count"] = paragraph_features(text)["paragraph_count"]

    # Lists kept separately — distance.py treats these as distribution comparisons
    features["fw_bigrams"] = function_word_ngrams(tokens, n=2, top_k=25)
    features["fw_trigrams"] = function_word_ngrams(tokens, n=3, top_k=25)
    features["sentence_starters"] = sentence_starters(sentences, top_k=15)

    return features


def aggregate(stats_list: Iterable[dict]) -> dict:
    """Average scalar features across multiple texts; merge n-gram distributions.

    Used by ingest.py to combine many sample files into one benchmark.
    """
    stats_list = list(stats_list)
    if not stats_list:
        return {}
    if len(stats_list) == 1:
        return stats_list[0]

    out = {}
    list_keys = {"fw_bigrams", "fw_trigrams", "sentence_starters"}

    def _is_scalar(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    scalar_keys = [k for k, v in stats_list[0].items()
                   if k not in list_keys and _is_scalar(v)]

    # weighted by word_count for stability
    total_w = sum(s.get("word_count", 0) for s in stats_list) or 1
    for key in scalar_keys:
        weighted_sum = sum(
            (s.get(key, 0) if _is_scalar(s.get(key, 0)) else 0) * s.get("word_count", 0)
            for s in stats_list
        )
        out[key] = round(weighted_sum / total_w, 4)

    for lk in list_keys:
        merged: Counter = Counter()
        for s in stats_list:
            for item, freq in s.get(lk, []):
                merged[item] += freq * s.get("word_count", 0)
        total = sum(merged.values()) or 1
        top = merged.most_common(25 if "starters" not in lk else 15)
        out[lk] = [[g, round(c / total, 6)] for g, c in top]

    out["sample_count"] = len(stats_list)
    out["total_word_count"] = total_w
    return out
