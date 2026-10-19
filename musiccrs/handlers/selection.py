"""Selection handler: SELECT (R7), a choice among the options just shown.

T11. Rules first, with no LLM, for the common answers ("all", "none", "the first two",
"1 and 3"). Anything the rules do not fully understand ("all except the one by Metallica")
goes to the LLM.
"""
from ..data.db import normalize

# Words that pick every option: "all of them", "everything".
ALL_WORDS = ("all", "everything", "every")

# Words that pick no option: "none", "no thanks".
NONE_WORDS = ("none", "nothing", "neither", "no", "nope")

# Ordinal words -> position, counted from 1. "last" depends on the number of options,
# so it is handled in rule_indices.
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
}

# Number words used after "first" or "last": "the first two", "the last three".
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}

# Words that carry no choice and are skipped (after normalize: "I'll" -> "ill", "I'd" -> "id").
FILLER_WORDS = (
    "the", "a", "and", "add", "one", "ones", "of", "them", "it", "those", "these",
    "song", "songs", "track", "tracks", "to", "my", "playlist", "in", "on",
    "i", "ill", "id", "take", "want", "like", "would", "give", "me", "put",
    "just", "only", "please", "ok", "okay", "yes", "sure", "thanks", "thank", "you",
)


def number_value(word):
    """The number a word stands for, or 0 if it is not a number.

    "two" -> 2, "3" -> 3, "songs" -> 0
    """
    if word in NUMBER_WORDS:
        return NUMBER_WORDS[word]
    if word.isdigit():
        return int(word)
    return 0


def rule_indices(text, count):
    """The chosen options as 0-based indices, by rules only (no LLM).

    With count = 5 options:
    "all of them"     -> [0, 1, 2, 3, 4]
    "no thanks"       -> []
    "the first two"   -> [0, 1]
    "1 and 3"         -> [0, 2]
    "the last one"    -> [4]
    "the sixth"       -> None  (there is no sixth option)
    "all except the one by Metallica" -> None  ("except", "by", "metallica" are unknown words)

    None means "not understood by the rules": every word must be known, otherwise
    the LLM decides, so "the first one by Metallica" is never read as just "the first one".
    """
    words = normalize(text).split()

    picks_all = False
    picks_none = False
    positions = []   # counted from 1, in the order the user said them

    i = 0
    while i < len(words):
        word = words[i]

        # The word after this one, or "" at the end of the text.
        if i + 1 < len(words):
            next_word = words[i + 1]
        else:
            next_word = ""

        # "the first two" / "the last 3": a block of options at the start or the end.
        size = number_value(next_word)
        if (word == "first" or word == "last") and size >= 2:
            if word == "first":
                start = 1
            else:
                start = count - size + 1
            for position in range(start, start + size):
                positions.append(position)
            i = i + 2   # the number word is used up too
            continue

        if word == "last":
            positions.append(count)
        elif word in ORDINALS:
            positions.append(ORDINALS[word])
        elif word.isdigit():
            positions.append(int(word))
        elif word in ALL_WORDS:
            picks_all = True
        elif word == "both":
            # "both" only makes sense when exactly two options were shown.
            if count != 2:
                return None
            picks_all = True
        elif word in NONE_WORDS:
            picks_none = True
        elif word in FILLER_WORDS:
            pass
        else:
            # An unknown word ("except", "metallica", "but"): let the LLM decide.
            return None
        i = i + 1

    # "none" together with anything else ("no, the second one") is unclear.
    if picks_none:
        if picks_all or len(positions) > 0:
            return None
        return []

    # "all" together with a position ("all 5", "all but the 2nd") is unclear too.
    if picks_all:
        if len(positions) > 0:
            return None
        all_indices = []
        for index in range(count):
            all_indices.append(index)
        return all_indices

    # Only filler words ("yes please"): no choice was made.
    if len(positions) == 0:
        return None

    # Positions 1..count -> indices 0..count-1, without repeats.
    indices = []
    for position in positions:
        if position < 1 or position > count:
            return None
        index = position - 1
        if index not in indices:
            indices.append(index)
    return indices
