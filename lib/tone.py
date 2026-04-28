"""Tone, hedging, and formality heuristics — lexicon-based, no ML deps.

Hedges and boosters carry context-dependent senses ("may" can be a modal hedge
or the calendar month; "right" can be agreement or direction). The lexicon
counts use simple disambiguation rules (see `_count_hedges`) to suppress the
most common false positives without requiring a POS tagger.
"""

from __future__ import annotations

import re

# "Pure" hedges — only entries whose hedging sense overwhelmingly dominates
# the alternative senses. "kind" / "sort" / "rather" removed: their head-noun
# and emphatic uses ("kind person", "sort the list", "rather than") flip
# polarity and pollute the rate. "fairly" kept (almost always degree-adverb).
HEDGES = frozenset([
    "perhaps", "maybe", "possibly", "probably", "presumably", "supposedly",
    "apparently", "seemingly", "ostensibly", "arguably", "allegedly",
    "somewhat", "fairly",
    "approximately", "roughly", "nearly", "almost",
    "tend", "tends", "tended", "tending",
    "suggests", "suggest", "indicates", "indicate", "appears", "appear", "seems", "seem",
])

# Modal hedges — count only when followed by an infinitive verb. "may 2024"
# (calendar) and "could you" (request) are excluded by the contextual filter.
MODAL_HEDGES = frozenset(["might", "may", "could", "would", "should"])

# Multi-word hedges checked via substring match (hedging_rate function).
HEDGE_PHRASES = ["i think", "i believe", "i guess", "in my view",
                 "in my opinion", "if anything", "for the most part"]

MONTH_NAMES = frozenset([
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
])

# Boosters strengthen a claim ("clearly", "definitely"). "must" excluded —
# it's a deontic modal whose epistemic sense ("must be") is already counted
# as a modal hedge in `count_modal_hedges`. "of course" handled as phrase.
BOOSTERS = frozenset([
    "clearly", "obviously", "definitely", "certainly", "surely",
    "undoubtedly", "absolutely", "completely", "entirely", "totally",
    "really", "very", "highly", "extremely", "deeply", "strongly",
    "always", "never", "indeed", "truly", "actually",
])

# Stance / discourse — markers of structured argument
DISCOURSE = frozenset([
    "however", "moreover", "furthermore", "nevertheless", "nonetheless",
    "consequently", "therefore", "thus", "hence", "accordingly",
    "meanwhile", "otherwise", "instead", "besides", "anyway",
    "first", "firstly", "second", "secondly", "third", "thirdly",
    "finally", "ultimately", "lastly",
    "specifically", "particularly", "notably", "especially", "namely",
])

# Sentiment lexicon. Calibrated against AFINN signs and Hu-Liu opinion lists,
# trimmed to high-precision items for short prose. For full NLP-grade accuracy
# users should layer VADER on top; this stays self-contained.
POSITIVE = frozenset([
    # Affect / evaluation
    "good", "great", "excellent", "wonderful", "fantastic", "amazing",
    "outstanding", "remarkable", "exceptional", "superb", "stellar",
    "brilliant", "delightful", "lovely", "beautiful", "splendid",
    "best", "better", "fine", "nice", "pleasant", "satisfying", "rewarding",
    "love", "loved", "loves", "loving", "happy", "glad", "joyful", "cheerful",
    # Capability / quality
    "useful", "helpful", "valuable", "powerful", "strong", "clear",
    "elegant", "robust", "reliable", "efficient", "effective", "smart",
    "thoughtful", "graceful", "clean", "solid", "sturdy", "polished",
    # Outcome — "right" and "correct" excluded: directional ("turn right")
    # and agreement ("right, ok") senses dominate in conversational prose.
    "accurate", "successful", "succeed", "succeeds",
    "win", "wins", "won", "achieved", "improve", "improved", "improves",
    "thrive", "thrives", "flourish", "flourishes", "advance", "progress",
])
NEGATIVE = frozenset([
    # Affect
    "bad", "worst", "worse", "terrible", "awful", "horrible", "ugly",
    "dreadful", "miserable", "depressing", "frustrating", "annoying",
    "poor", "mediocre", "lousy", "lame",
    "hate", "hated", "hates", "loathe", "loathed", "despise",
    "sad", "unhappy", "angry", "upset", "disappointing",
    # Capability
    "broken", "buggy", "weak", "fragile", "flawed", "faulty", "shoddy",
    "useless", "worthless", "harmful", "dangerous", "risky", "unreliable",
    "slow", "sluggish", "clunky", "ugly", "ugly", "messy",
    # Outcome
    "wrong", "incorrect", "inaccurate", "fail", "failed", "fails", "failing",
    "lose", "loses", "lost", "stuck", "blocked", "delayed",
    "problem", "problems", "issue", "issues", "bug", "bugs",
    "difficult", "hard", "complicated", "confusing", "convoluted",
    "tedious", "painful", "exhausting",
])


def count_overlap(tokens: list[str], lex: frozenset[str]) -> int:
    return sum(1 for t in tokens if t in lex)


def count_phrases(text_lower: str, phrases: list[str]) -> int:
    return sum(text_lower.count(p) for p in phrases)


_INFINITIVE_RE = re.compile(r"\b(?:might|may|could|would|should)\s+([a-z]+)\b", re.IGNORECASE)


def count_modal_hedges(tokens: list[str], text_lower: str) -> int:
    """Modal hedges, contextually filtered.

    A modal counts as a hedge only when followed by a plain-verb-shaped token
    (>=3 letters, not the modal itself, not the calendar 'may' usage). False
    positives like 'May 2024', 'could you', or interjections ('may I?') don't
    count.
    """
    count = 0
    matches = list(_INFINITIVE_RE.finditer(text_lower))
    for m in matches:
        modal = m.group(0).split()[0].lower()
        following = m.group(1).lower()
        if modal == "may" and following in MONTH_NAMES:
            continue
        # Reject if next word is itself a modal or pronoun (request form).
        if following in {"i", "you", "we", "they", "he", "she", "it"}:
            continue
        if len(following) < 2:
            continue
        count += 1
    return count


def heylighen_f_score(pos_counts: dict[str, int], total_words: int) -> float:
    """Approximate Heylighen-Dewaele formality score using POS proxy counts.

    F = ((noun + adj + prep + article) - (pron + verb + adv + interj) + 100) / 2
    Range 0-100. Higher = more formal/contextual; lower = more involved/casual.

    We pass coarse counts derived from regex/lexicon proxies — not true POS.
    Good enough as a comparative metric across an author's own writings.
    """
    formal = pos_counts.get("noun", 0) + pos_counts.get("adj", 0) + pos_counts.get("prep", 0) + pos_counts.get("article", 0)
    informal = pos_counts.get("pron", 0) + pos_counts.get("verb", 0) + pos_counts.get("adv", 0) + pos_counts.get("interj", 0)
    if total_words == 0:
        return 50.0
    formal_pct = 100.0 * formal / total_words
    informal_pct = 100.0 * informal / total_words
    return (formal_pct - informal_pct + 100.0) / 2.0


def tone_metrics(tokens: list[str], text_lower: str, total_words: int) -> dict:
    if total_words == 0:
        return {
            "hedging_rate": 0.0, "booster_rate": 0.0, "discourse_rate": 0.0,
            "positive_rate": 0.0, "negative_rate": 0.0, "sentiment_polarity": 0.0,
        }
    hedge_count = (
        count_overlap(tokens, HEDGES)
        + count_modal_hedges(tokens, text_lower)
        + count_phrases(text_lower, HEDGE_PHRASES)
    )
    boost_count = count_overlap(tokens, BOOSTERS) + count_phrases(text_lower, ["of course"])
    disc_count = count_overlap(tokens, DISCOURSE)
    pos_count = count_overlap(tokens, POSITIVE)
    neg_count = count_overlap(tokens, NEGATIVE)

    per1k = 1000.0 / total_words
    return {
        "hedging_rate": hedge_count * per1k,
        "booster_rate": boost_count * per1k,
        "discourse_rate": disc_count * per1k,
        "positive_rate": pos_count * per1k,
        "negative_rate": neg_count * per1k,
        "sentiment_polarity": (pos_count - neg_count) / max(pos_count + neg_count, 1),
    }
