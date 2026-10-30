"""CRITIQUE (Part 4, F1): "more like the second one", "less like the one by Bon Jovi",
"older", "more popular", "more acoustic".

T3 builds the example critiques (F1.1) with Rocchio relevance feedback: the list the
critiques started from is one vector (the mean of its tracks' metadata vectors), each
liked track pulls it closer, each disliked track pushes it away. T5 adds the attribute
critiques (F1.2).
"""
import html

import numpy as np

from ..state import Reply

# Rocchio weights (the classic SMART values): the list the critiques started from counts
# fully, liked tracks pull a bit less, disliked tracks push only a little.
ALPHA = 1.0
BETA = 0.75
GAMMA = 0.15


def mean_vector(track_ids, vectors):
    """The mean of the tracks' metadata vectors, or None if none of them has one.

    (["id-a", "id-b"], vectors) with vectors [1, 0] and [0, 1] -> [0.5, 0.5]
    A track without a metadata vector is left out of the mean.
    """
    total = None
    count = 0
    for track_id in track_ids:
        vector = vectors.vector("metadata", track_id)
        if vector is None:
            continue
        if total is None:
            total = np.array(vector, dtype=np.float32)
        else:
            total = total + vector
        count = count + 1

    if count == 0:
        return None
    return total / count


def critique_query(critique, vectors):
    """The Rocchio query vector of a critique session, L2-normalized, or None.

    critique = {"base_ids": [5 rock songs], "liked": [It's My Life], "disliked": [], ...}
        -> ALPHA * mean(5 rock songs) + BETA * It's My Life, scaled to length 1
    In 2 numbers: base [1, 0], liked [0, 1] -> [1, 0.75] -> [0.8, 0.6]
    None when the base list has no vectors (nothing to start from).
    """
    base = mean_vector(critique["base_ids"], vectors)
    if base is None:
        return None
    query = ALPHA * base

    liked = mean_vector(critique["liked"], vectors)
    if liked is not None:
        query = query + BETA * liked

    disliked = mean_vector(critique["disliked"], vectors)
    if disliked is not None:
        query = query - GAMMA * disliked

    # Length 1, so nearest() returns cosine similarities.
    length = np.linalg.norm(query)
    if length == 0:
        return None
    return query / length


def handle_critique(parsed, state, services):
    """CRITIQUE: not built yet (T3, T5). Says what was understood.

    "/like 2" -> "Critiques are not built yet. I understood: {'like': '2'}"
    """
    understood = html.escape(str(parsed.slots), quote=False)
    return Reply("Critiques are not built yet. I understood: " + understood)
