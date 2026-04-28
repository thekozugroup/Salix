"""Tone, hedging, and formality heuristics — lexicon-based, no ML deps."""

from __future__ import annotations

# Hedges weaken a claim ("perhaps", "might")
HEDGES = frozenset([
    "perhaps", "maybe", "possibly", "probably", "presumably", "supposedly",
    "apparently", "seemingly", "ostensibly", "arguably", "allegedly",
    "might", "may", "could", "would", "should",
    "somewhat", "fairly", "rather", "quite", "kind", "sort",
    "approximately", "roughly", "nearly", "almost", "about",
    "tend", "tends", "tended", "tending",
    "suggests", "suggest", "indicates", "indicate", "appears", "appear", "seems", "seem",
    "i think", "i believe", "i guess", "in my view",  # multi-word checked separately
])

# Boosters strengthen a claim ("clearly", "definitely")
BOOSTERS = frozenset([
    "clearly", "obviously", "definitely", "certainly", "surely",
    "undoubtedly", "absolutely", "completely", "entirely", "totally",
    "really", "very", "highly", "extremely", "deeply", "strongly",
    "always", "never", "must", "indeed", "truly", "actually",
    "of course",
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

# Sentiment seed — small, deliberate. For nuance, swap in VADER later.
POSITIVE = frozenset([
    "good", "great", "excellent", "wonderful", "fantastic", "amazing",
    "best", "better", "love", "loved", "loves", "happy", "glad",
    "useful", "helpful", "valuable", "powerful", "strong", "clear",
    "right", "correct", "successful", "succeed", "win", "wins", "won",
    "improve", "improved", "improves", "elegant", "robust",
])
NEGATIVE = frozenset([
    "bad", "worst", "worse", "terrible", "awful", "horrible", "poor",
    "hate", "hated", "hates", "sad", "unhappy", "fail", "failed", "fails",
    "broken", "weak", "wrong", "incorrect", "useless", "harmful",
    "problem", "problems", "issue", "issues", "bug", "bugs",
    "difficult", "hard", "complicated", "confusing",
])


def count_overlap(tokens: list[str], lex: frozenset[str]) -> int:
    return sum(1 for t in tokens if t in lex)


def count_phrases(text_lower: str, phrases: list[str]) -> int:
    return sum(text_lower.count(p) for p in phrases)


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
    hedge_count = count_overlap(tokens, HEDGES) + count_phrases(
        text_lower, ["i think", "i believe", "i guess", "in my view"]
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
