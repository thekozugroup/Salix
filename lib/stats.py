"""Linguistic feature extraction — pure stdlib."""

from __future__ import annotations

import math
import re

# Optional spaCy: lazily loaded on first call so importing lib.stats stays
# fast (no 200-500 ms model-load tax on every CLI subcommand). The model is
# loaded once per process and cached.
import threading as _threading
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache

from .function_words import FUNCTION_WORDS
from .tone import heylighen_f_score, tone_metrics

_SPACY_NLP: object | None = None
_SPACY_LOAD_ATTEMPTED = False
_SPACY_LOCK = _threading.Lock()


def _get_spacy_nlp():
    """Thread-safe lazy spaCy loader. The model load happens inside the lock,
    but the import itself is moved outside — Python guarantees module imports
    are idempotent under the import lock, and holding our load-lock across
    the import would needlessly block other callers on first-call latency."""
    global _SPACY_NLP, _SPACY_LOAD_ATTEMPTED
    if _SPACY_LOAD_ATTEMPTED:
        return _SPACY_NLP
    try:
        import spacy as _spacy
    except ImportError:
        with _SPACY_LOCK:
            _SPACY_NLP = None
            _SPACY_LOAD_ATTEMPTED = True
        return None
    with _SPACY_LOCK:
        if _SPACY_LOAD_ATTEMPTED:
            return _SPACY_NLP
        try:
            _SPACY_NLP = _spacy.load("en_core_web_sm", disable=["ner", "parser"])
        except OSError:
            _SPACY_NLP = None
        _SPACY_LOAD_ATTEMPTED = True
    return _SPACY_NLP


def _spacy_pos_counts(text: str) -> dict[str, int] | None:
    """Real POS counts via spaCy when available. Returns None if unavailable."""
    nlp = _get_spacy_nlp()
    if nlp is None:
        return None
    doc = nlp(text)
    out = {"noun": 0, "adj": 0, "adv": 0, "verb": 0,
           "pron": 0, "article": 0, "prep": 0, "interj": 0}
    pos_map = {
        "NOUN": "noun", "PROPN": "noun",
        "ADJ": "adj", "ADV": "adv", "VERB": "verb", "AUX": "verb",
        "PRON": "pron", "DET": "article",
        "ADP": "prep", "INTJ": "interj",
    }
    for tok in doc:
        bucket = pos_map.get(tok.pos_)
        if bucket:
            out[bucket] += 1
    return out


def _spacy_pos_sequence(text: str) -> list[str] | None:
    """Coarse POS tag sequence for n-gram features. Universal POS tags."""
    nlp = _get_spacy_nlp()
    if nlp is None:
        return None
    return [tok.pos_ for tok in nlp(text) if tok.pos_ != "SPACE"]


def pos_ngrams(text: str, n: int = 2, top_k: int = 100) -> list[list]:
    """POS-tag n-grams from spaCy. Returns [] if spaCy is unavailable.

    POS n-grams capture syntactic shape independent of vocabulary —
    Argamon-Koppel showed they boost authorship attribution beyond what
    function-word n-grams alone provide.
    """
    seq = _spacy_pos_sequence(text)
    if not seq or len(seq) < n:
        return []
    counter: Counter = Counter()
    for i in range(len(seq) - n + 1):
        counter[" ".join(seq[i:i + n])] += 1
    total = sum(counter.values()) or 1
    items = counter.most_common(top_k)
    return [[g, round(c / total, 6)] for g, c in items]

# Sentence boundary regex. Splits on . ! ? … (or sequences like ?! !? ...) followed
# by whitespace then a non-whitespace token. Lowercase-prose-friendly: does not
# require a capital next char. Abbreviations and decimal numbers are masked first.
_ABBR = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "cf", "fig", "vol", "no", "p", "pp", "ch", "inc", "ltd",
    "co", "corp", "u.s", "u.k", "ph.d", "m.d", "a.m", "p.m",
}
SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])[\"')\]]?\s+(?=\S)")
DECIMAL_RE = re.compile(r"(\d)\.(\d)")

# Word tokenizer. Unicode-aware so accented Latin scripts (French, German,
# Spanish, etc.) are not silently dropped. Greek/Cyrillic also captured.
# CJK characters are individual word units when present (one char = one word).
WORD_RE_LATIN = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)
WORD_RE = WORD_RE_LATIN  # alias kept for backward compatibility
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
    """Sentence segmentation with abbreviation + decimal guard.

    Handles lowercase prose (does not require capital after the boundary), runs
    of terminators (?!, !?, ...), and protects abbreviations and decimal numbers
    from spurious splits.
    """
    # Protect decimals: 3.14 -> 3·14 (interpunct placeholder, restored later)
    masked = DECIMAL_RE.sub(r"\1·\2", text)
    # Protect known abbreviations (case-insensitive).
    for abbr in _ABBR:
        masked = re.sub(
            rf"\b{re.escape(abbr)}\.(?=\s|$)",
            lambda m, a=abbr: f"{a}·",
            masked,
            flags=re.IGNORECASE,
        )
    # Collapse runs of terminators: "..." stays, but "?!" or "!!" should still split.
    parts = SENT_SPLIT_RE.split(masked)
    sents = [p.replace("·", ".").strip() for p in parts if p.strip()]
    return sents


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens. Punctuation handled separately."""
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]


def char_ngrams(text: str, n: int = 3, top_k: int = 200) -> list[list]:
    """Top-K character n-grams with normalized frequencies.

    Character n-grams are the single highest-performing authorship feature in
    Stamatatos (2009) and capture orthographic + morphological habits at once.
    Script coverage matches the tokenizer: Unicode letters (any script) plus
    the apostrophe and a single space; everything else (digits, punctuation,
    symbols) is stripped, so the feature is robust to formatting noise.
    """
    collapsed = re.sub(r"\s+", " ", text.lower())
    norm = "".join(ch for ch in collapsed if ch.isalpha() or ch in (" ", "'"))
    if len(norm) < n:
        return []
    counter: Counter = Counter()
    for i in range(len(norm) - n + 1):
        counter[norm[i:i + n]] += 1
    total = sum(counter.values()) or 1
    items = counter.most_common(top_k)
    return [[g, round(c / total, 6)] for g, c in items]


def burrows_delta_features(tokens: list[str], total_words: int, top_k: int = 150) -> list[list]:
    """Most-frequent-word frequencies for Burrows' Delta.

    Returns the top-K *function-word* frequencies (per 1k words) — the
    topic-blind variant of Burrows that Argamon recommends for cross-topic
    authorship. Distance is computed externally as mean absolute z-score over
    these features (the classic Delta formula).
    """
    if total_words == 0:
        return []
    fw_counts = Counter(t for t in tokens if t in FUNCTION_WORDS)
    items = fw_counts.most_common(top_k)
    per1k = 1000.0 / total_words
    return [[w, round(c * per1k, 4)] for w, c in items]


def yule_k(tokens: list[str]) -> float:
    """Yule's K — vocabulary diversity index, length-robust.

    K = 10000 * (Σ V(i,N) * i² - N) / N²
    where V(i,N) is the number of types occurring exactly i times.
    Lower K = more diverse vocabulary.
    """
    n = len(tokens)
    if n < 2:
        return 0.0
    counts = Counter(tokens)
    freq_of_freq: Counter = Counter(counts.values())
    s2 = sum(i * i * v for i, v in freq_of_freq.items())
    return 10000.0 * (s2 - n) / (n * n)


def honore_r(tokens: list[str]) -> float:
    """Honoré's R — emphasizes hapax legomena.

    R = 100 * log(N) / (1 - V1/V)
    where N=tokens, V=types, V1=hapax legomena (types occurring once).

    Below ~50 tokens the V1/V ratio is unstable (most words are hapaxes simply
    because the document is short) and R explodes; we return 0.0 in that
    regime rather than report a meaningless value. Above the floor we cap the
    1 - V1/V denominator at 0.05 to avoid divergence on very-hapax-heavy
    short inputs.
    """
    n = len(tokens)
    if n < 50:
        return 0.0
    counts = Counter(tokens)
    v = len(counts)
    v1 = sum(1 for c in counts.values() if c == 1)
    if v == 0 or v1 == v:
        return 0.0
    ratio = v1 / v
    denom = max(1 - ratio, 0.05)
    return 100.0 * math.log(n) / denom


def simpson_d(tokens: list[str]) -> float:
    """Simpson's D — probability that two random tokens differ in type.

    D = 1 - Σ n_i*(n_i - 1) / (N*(N - 1))
    Range [0, 1]; higher = more diverse.
    """
    n = len(tokens)
    if n < 2:
        return 0.0
    counts = Counter(tokens)
    num = sum(c * (c - 1) for c in counts.values())
    return 1 - num / (n * (n - 1))


# Optional pyphen for syllable counting. Hyphenation-dictionary-based; far
# more accurate than the vowel-group heuristic on Latinate / affixed words.
_PYPHEN_DIC = None
_PYPHEN_ATTEMPTED = False


def _get_pyphen():
    """Lazily load pyphen for accurate hyphenation-based syllable counts.
    Falls back to the vowel-group heuristic when pyphen is unavailable.
    Emits a one-time UserWarning so users get a nudge to `pip install pyphen`
    for fidelity on Latinate vocabulary in the readability metrics."""
    import warnings
    global _PYPHEN_DIC, _PYPHEN_ATTEMPTED
    if _PYPHEN_ATTEMPTED:
        return _PYPHEN_DIC
    try:
        import pyphen
        _PYPHEN_DIC = pyphen.Pyphen(lang="en_US")
    except ImportError:
        _PYPHEN_DIC = None
        warnings.warn(
            "pyphen not installed — syllable counts (and FK/Fog/ARI scores "
            "derived from them) use a coarse vowel-group heuristic. Install "
            "with `pip install pyphen` for hyphenation-dictionary accuracy.",
            stacklevel=3,
        )
    _PYPHEN_ATTEMPTED = True
    return _PYPHEN_DIC


@lru_cache(maxsize=8192)
def estimate_syllables(word: str) -> int:
    """Syllable count — pyphen if available, vowel-group heuristic fallback.

    Pyphen uses Hyphenation libhyphen dictionaries (the same ones LibreOffice
    ships) and tracks affix and Latinate splits the heuristic misses. Without
    pyphen, falls back to a silent-e + vowel-group estimator that is
    deterministic and zero-dependency but coarse.
    """
    w = word.lower()
    if not w:
        return 0
    pyphen_dic = _get_pyphen()
    if pyphen_dic is not None:
        # Pyphen returns hyphenated form; syllables = hyphens + 1.
        hyphenated = pyphen_dic.inserted(w)
        return max(hyphenated.count("-") + 1, 1)
    # strip silent trailing e (but not for short words like "be", "the")
    if len(w) > 3 and w.endswith("e") and not w.endswith("le"):
        w = w[:-1]
    groups = SYLLABLE_VOWEL_RE.findall(w)
    return max(len(groups), 1)


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


def _quantile(sorted_xs: list, q: float) -> float:
    if not sorted_xs:
        return 0.0
    if len(sorted_xs) == 1:
        return float(sorted_xs[0])
    pos = q * (len(sorted_xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    frac = pos - lo
    return float(sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac)


def sentence_features(sentences: list[str]) -> dict[str, float]:
    if not sentences:
        return {
            "sentence_count": 0, "mean_sent_len": 0.0, "stdev_sent_len": 0.0,
            "max_sent_len": 0, "short_sent_ratio": 0.0, "long_sent_ratio": 0.0,
            "comma_per_sentence": 0.0,
            "sent_len_p25": 0.0, "sent_len_p50": 0.0,
            "sent_len_p75": 0.0, "sent_len_p90": 0.0,
        }
    lens = [len(tokenize(s)) for s in sentences]
    n = len(lens)
    mean = sum(lens) / n
    var = sum((x - mean) ** 2 for x in lens) / n
    stdev = math.sqrt(var)
    short = sum(1 for x in lens if x < 8) / n
    long_ = sum(1 for x in lens if x > 25) / n
    commas_per_sent = sum(s.count(",") for s in sentences) / n
    sorted_lens = sorted(lens)
    return {
        "sentence_count": n,
        "mean_sent_len": mean,
        "stdev_sent_len": stdev,
        "max_sent_len": max(lens),
        "short_sent_ratio": short,
        "long_sent_ratio": long_,
        "comma_per_sentence": commas_per_sent,
        "sent_len_p25": _quantile(sorted_lens, 0.25),
        "sent_len_p50": _quantile(sorted_lens, 0.50),
        "sent_len_p75": _quantile(sorted_lens, 0.75),
        "sent_len_p90": _quantile(sorted_lens, 0.90),
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


def function_word_ngrams(tokens: list[str], n: int = 2, top_k: int = 100) -> list[list]:
    """Top-K function-word n-grams with normalized frequencies.

    The token stream is first reduced to *consecutive runs* of function words.
    Within each run, every n-gram is counted; non-function tokens act as run
    boundaries (no n-gram crosses them). Frequencies are normalized over the
    total number of n-grams *emitted* (not over total bigram positions in the
    raw text), which keeps the distribution well-defined even when content
    words dominate the input.
    """
    runs: list[list[str]] = []
    current: list[str] = []
    for t in tokens:
        if t in FUNCTION_WORDS:
            current.append(t)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    counter: Counter = Counter()
    for run in runs:
        if len(run) < n:
            continue
        for i in range(len(run) - n + 1):
            counter[" ".join(run[i:i + n])] += 1

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
    features["yule_k"] = round(yule_k(tokens), 3)
    features["honore_r"] = round(honore_r(tokens), 3)
    features["simpson_d"] = round(simpson_d(tokens), 4)
    sf = sentence_features(sentences)
    features.update({k: round(v, 4) if isinstance(v, float) else v for k, v in sf.items()})
    features.update({k: round(v, 4) for k, v in punctuation_rates(text, n_words).items()})
    features.update({k: round(v, 4) for k, v in readability(tokens, sentences).items()})
    features.update({k: round(v, 4) for k, v in function_word_rates(tokens, n_words).items()})

    spacy_pos = _spacy_pos_counts(text)
    pos = spacy_pos if spacy_pos is not None else pos_proxies(tokens)
    features["formality_f_score"] = round(heylighen_f_score(pos, n_words), 3)
    features["formality_source"] = "spacy" if spacy_pos is not None else "suffix_proxy"
    features["passive_per1k"] = round(passive_proxy_rate(text, n_words), 3)

    features.update({k: round(v, 4) for k, v in tone_metrics(tokens, text_lower, n_words).items()})

    pf = paragraph_features(text)
    features.update({k: round(v, 4) if isinstance(v, float) else v for k, v in pf.items()})

    # Lists kept separately — distance.py treats these as distribution comparisons
    features["fw_bigrams"] = function_word_ngrams(tokens, n=2, top_k=100)
    features["fw_trigrams"] = function_word_ngrams(tokens, n=3, top_k=100)
    features["char_3grams"] = char_ngrams(text, n=3, top_k=200)
    features["char_4grams"] = char_ngrams(text, n=4, top_k=200)
    features["mfw_top150"] = burrows_delta_features(tokens, n_words, top_k=150)
    features["pos_bigrams"] = pos_ngrams(text, n=2, top_k=100)  # empty if no spaCy
    features["pos_trigrams"] = pos_ngrams(text, n=3, top_k=100)
    features["sentence_starters"] = sentence_starters(sentences, top_k=15)

    return features


def aggregate(stats_list: Iterable[dict]) -> dict:
    """Average scalar features across multiple texts; merge n-gram distributions.

    Computes:
      - weighted means (by word_count) for every scalar feature
      - per-feature within-author standard deviation across the input documents,
        stored in a `_sigma` sub-dict — this replaces the hard-coded
        EXPECTED_SIGMA at compare time and makes z-scores honest
      - merged n-gram distributions, summed as raw counts then renormalized

    Used by ingest.py to combine many sample files into one benchmark.
    """
    import math as _math
    stats_list = list(stats_list)
    if not stats_list:
        return {}

    list_keys = {"fw_bigrams", "fw_trigrams", "sentence_starters",
                 "char_3grams", "char_4grams", "mfw_top150",
                 "pos_bigrams", "pos_trigrams"}

    def _is_scalar(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # Union of scalar keys across all samples (was: keys-of-first-sample only).
    scalar_keys = set()
    for s in stats_list:
        for k, v in s.items():
            if k not in list_keys and _is_scalar(v):
                scalar_keys.add(k)
    scalar_keys = sorted(scalar_keys)

    out: dict = {}
    sigma: dict = {}

    if len(stats_list) == 1:
        # Single-doc fingerprint: scalars copy through, sigma is empty so
        # comparison falls back to EXPECTED_SIGMA defaults.
        only = stats_list[0]
        for k in scalar_keys:
            out[k] = only.get(k, 0)
        out["sample_count"] = 1
        out["total_word_count"] = only.get("word_count", 0)
        out["_sigma"] = {}
        # n-gram lists pass through unchanged
        for lk in list_keys:
            out[lk] = list(only.get(lk, []))
        return out

    total_w = sum(s.get("word_count", 0) for s in stats_list) or 1

    for key in scalar_keys:
        values = [s.get(key, 0) if _is_scalar(s.get(key, 0)) else 0 for s in stats_list]
        weights = [s.get("word_count", 0) for s in stats_list]
        weighted_mean = sum(v * w for v, w in zip(values, weights)) / total_w
        # Unweighted sample stddev across documents — measures within-author
        # variation in the feature, which is exactly what z-scores need.
        n = len(values)
        mean_unw = sum(values) / n
        var = sum((v - mean_unw) ** 2 for v in values) / max(n - 1, 1)
        sigma[key] = round(_math.sqrt(var), 6) if var > 0 else 0.0
        out[key] = round(weighted_mean, 4)

    list_caps = {
        "fw_bigrams": 100, "fw_trigrams": 100,
        "char_3grams": 200, "char_4grams": 200,
        "mfw_top150": 150, "sentence_starters": 15,
        "pos_bigrams": 100, "pos_trigrams": 100,
    }
    pos_sigma: dict[str, float] = {}
    for lk in list_keys:
        if lk == "mfw_top150":
            # Each per-doc list is in per-1k units. The corpus rate is the
            # word-count-weighted average of those rates. Sigma is the across-
            # document stddev of the same per-1k rates, persisted under
            # `_mfw_sigma` for use by the real Burrows Delta formula.
            per_doc_rates: dict[str, list[float]] = {}
            doc_word_counts: list[int] = []
            for s in stats_list:
                doc_word_counts.append(s.get("word_count", 0))
                doc_map = {item: freq for item, freq in s.get(lk, [])}
                # collect every word ever seen in any doc
                for word in doc_map:
                    per_doc_rates.setdefault(word, [])
            # ensure every word has a per-doc rate (0.0 where absent)
            for s_idx, s in enumerate(stats_list):
                doc_map = {item: freq for item, freq in s.get(lk, [])}
                for word in per_doc_rates:
                    per_doc_rates[word].append(doc_map.get(word, 0.0))
            # corpus rate = weighted mean by word_count
            total_w = sum(doc_word_counts) or 1
            corpus_rates = []
            mfw_sigma: dict[str, float] = {}
            for word, rates in per_doc_rates.items():
                weighted_mean = sum(r * w for r, w in zip(rates, doc_word_counts)) / total_w
                corpus_rates.append((word, weighted_mean))
                if len(rates) > 1:
                    mu = sum(rates) / len(rates)
                    var = sum((r - mu) ** 2 for r in rates) / (len(rates) - 1)
                    mfw_sigma[word] = round(_math.sqrt(var), 4) if var > 0 else 0.0
                else:
                    mfw_sigma[word] = 0.0
            corpus_rates.sort(key=lambda x: -x[1])
            cap = list_caps.get(lk, 150)
            out[lk] = [[g, round(r, 4)] for g, r in corpus_rates[:cap]]
            out["_mfw_sigma"] = {g: mfw_sigma.get(g, 0.0) for g, _ in corpus_rates[:cap]}
        else:
            # Reconstruct raw-ish counts: each per-doc list is already
            # normalized over its emitted total. Scale by word_count so a
            # 10k-word doc contributes ten times more weight than a 1k-word
            # doc, then renormalize once over the merged total.
            merged: Counter = Counter()
            for s in stats_list:
                scale = max(s.get("word_count", 0), 1)
                for item, freq in s.get(lk, []):
                    merged[item] += freq * scale
            total = sum(merged.values()) or 1
            cap = list_caps.get(lk, 100)
            top = merged.most_common(cap)
            out[lk] = [[g, round(c / total, 6)] for g, c in top]
            # For POS n-grams, also persist within-author sigma over the
            # per-doc normalized rates of each top n-gram, mirroring the
            # MFW path. Used by distance.py to z-normalize POS n-gram
            # comparisons honestly instead of via raw TVD.
            if lk in ("pos_bigrams", "pos_trigrams"):
                items_kept = {g for g, _ in top}
                # Per-doc rates for each kept n-gram
                doc_rates: dict[str, list[float]] = {g: [] for g in items_kept}
                for s in stats_list:
                    doc_map = {item: freq for item, freq in s.get(lk, [])}
                    for g in items_kept:
                        doc_rates[g].append(doc_map.get(g, 0.0))
                for g, rates in doc_rates.items():
                    if len(rates) > 1:
                        mu = sum(rates) / len(rates)
                        var = sum((r - mu) ** 2 for r in rates) / (len(rates) - 1)
                        pos_sigma[f"{lk}::{g}"] = (
                            round(_math.sqrt(var), 6) if var > 0 else 0.0
                        )

    if pos_sigma:
        out["_pos_sigma"] = pos_sigma

    out["sample_count"] = len(stats_list)
    out["total_word_count"] = total_w
    out["_sigma"] = sigma
    return out
