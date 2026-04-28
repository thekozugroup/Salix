"""Closed-class function-word allowlist.

Used as a topic filter: vocabulary statistics consider only words in this set,
so the resulting style fingerprint reflects *how* the author writes, not
*what* they write about. Includes pronouns, determiners, auxiliaries,
conjunctions, prepositions, common quantifiers, and discourse/stance markers.

Stance and hedging markers are deliberately included — they are stylistic
choices ("perhaps", "rather", "indeed") that correlate strongly with voice.
"""

FUNCTION_WORDS = frozenset(
    w.lower()
    for w in [
        # pronouns — personal
        "i", "me", "my", "mine", "myself",
        "you", "your", "yours", "yourself", "yourselves",
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "it", "its", "itself",
        "we", "us", "our", "ours", "ourselves",
        "they", "them", "their", "theirs", "themselves",
        "one", "ones", "oneself",
        # pronouns — demonstrative / interrogative / relative
        "this", "that", "these", "those",
        "who", "whom", "whose", "which", "what",
        "whoever", "whomever", "whichever", "whatever",
        # determiners / articles / quantifiers
        "a", "an", "the",
        "some", "any", "no", "every", "each", "all", "both", "either", "neither",
        "many", "much", "few", "fewer", "little", "less", "more", "most", "several",
        "enough", "plenty",
        "another", "other", "others",
        # auxiliaries / modals
        "be", "am", "is", "are", "was", "were", "been", "being",
        "have", "has", "had", "having",
        "do", "does", "did", "doing", "done",
        "can", "could", "may", "might", "must", "shall", "should", "will", "would",
        "ought", "need", "dare", "used",
        # negation / contractions stems
        "not", "n't",
        # conjunctions — coordinating
        "and", "or", "but", "nor", "yet", "so", "for",
        # conjunctions — subordinating
        "if", "unless", "until", "till", "while", "whilst", "when", "whenever",
        "where", "wherever", "because", "since", "as", "though", "although",
        "even", "whether", "before", "after", "once",
        # prepositions
        "of", "in", "on", "at", "by", "to", "from", "with", "without",
        "into", "onto", "upon", "about", "across", "after", "against",
        "along", "among", "around", "before", "behind", "below", "beneath",
        "beside", "between", "beyond", "during", "except", "inside",
        "near", "off", "outside", "over", "past", "through", "throughout",
        "toward", "towards", "under", "underneath", "until", "up", "via",
        "within", "concerning", "regarding", "despite", "amid", "amidst",
        # adverbs of degree / frequency / time
        "very", "really", "quite", "rather", "fairly", "somewhat", "slightly",
        "extremely", "highly", "deeply", "totally", "utterly", "absolutely",
        "nearly", "almost", "barely", "hardly", "scarcely",
        "always", "never", "often", "sometimes", "occasionally", "rarely",
        "seldom", "usually", "frequently", "normally", "typically",
        "now", "then", "soon", "later", "already", "still", "yet",
        "today", "tomorrow", "yesterday", "ago",
        "here", "there", "everywhere", "anywhere", "somewhere", "nowhere",
        "again", "once", "twice",
        # discourse markers / stance / hedges / boosters
        "perhaps", "maybe", "possibly", "probably", "presumably", "supposedly",
        "apparently", "seemingly", "ostensibly", "arguably", "allegedly",
        "indeed", "certainly", "surely", "obviously", "clearly", "definitely",
        "actually", "really", "truly", "essentially", "basically", "fundamentally",
        "however", "moreover", "furthermore", "nevertheless", "nonetheless",
        "consequently", "therefore", "thus", "hence", "accordingly",
        "meanwhile", "otherwise", "instead", "besides", "anyway", "anyhow",
        "though", "still", "yet", "also", "too", "even",
        "first", "firstly", "second", "secondly", "third", "thirdly",
        "finally", "ultimately", "lastly", "initially", "originally",
        "specifically", "particularly", "notably", "especially", "namely",
        "generally", "broadly", "largely", "mainly", "mostly", "primarily",
        # interjections / fillers (rare in formal but show up in voice)
        "oh", "ah", "well", "okay", "ok", "yes", "no", "right",
        # comparison / link words
        "than", "as", "like", "unlike", "such", "same", "different",
        # placeholder / generic
        "thing", "things", "way", "ways",
    ]
)


def is_function_word(token: str) -> bool:
    """True if token (already lowercased, punctuation stripped) is closed-class."""
    if not token:
        return False
    if token in FUNCTION_WORDS:
        return True
    # handle "n't" attached forms split off elsewhere
    if token.endswith("n't") and token[:-3] in FUNCTION_WORDS:
        return True
    return False
