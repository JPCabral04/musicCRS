"""CRITIQUE (Part 4, F1): "more like the second one", "less like the one by Bon Jovi",
"older", "more popular", "more acoustic".

T3 builds the example critiques (F1.1) with Rocchio relevance feedback: the list the
critiques started from is one vector (the mean of its tracks' audio vectors), each
liked track pulls it closer, each disliked track pushes it away. T5 adds the attribute
critiques (F1.2).
"""
import html

import numpy as np

from ..state import Reply
from .playlist import describe_track, options_act
from .recs import NUM_RECOMMENDATIONS
from .shown import pick_shown, show_tracks

# Rocchio weights (the classic SMART values): the list the critiques started from counts
# fully, liked tracks pull a bit less, disliked tracks push only a little.
ALPHA = 1.0
BETA = 0.75
GAMMA = 0.15

# The vector space the critiques move in (one of TrackVectors.matrices). Audio, not
# metadata: on Oct 30, "more like Bad Medicine (Bon Jovi)" gave Pearl Jam, Ratt and Bon Jovi
# in audio, but Bad Seeds, Adderall and Bad Business in metadata (it matches title words).
SPACE = "audio"


def mean_vector(track_ids, vectors):
    """The mean of the tracks' vectors in SPACE, or None if none of them has one.

    (["id-a", "id-b"], vectors) with vectors [1, 0] and [0, 1] -> [0.5, 0.5]
    A track without a vector is left out of the mean.
    """
    total = None
    count = 0
    for track_id in track_ids:
        vector = vectors.vector(SPACE, track_id)
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


def names_text(track_ids, db):
    """Track names for the reply: one -> "<b>Numb</b> by Linkin Park", two or more joined by ", "."""
    names = []
    for track_id in track_ids:
        names.append("<b>" + describe_track(db.get(track_id)) + "</b>")
    return ", ".join(names)


def critique_text(critique, db):
    """What the critique session asks for, as the first line of the reply.

    liked [It's My Life], disliked [Toxic] -> "More like <b>It's My Life by Bon Jovi</b>,
                                              less like <b>Toxic by Britney Spears</b>:"
    disliked only [Toxic]                  -> "Less like <b>Toxic by Britney Spears</b>:"
    """
    text = ""
    if len(critique["liked"]) > 0:
        text = "More like " + names_text(critique["liked"], db)
    if len(critique["disliked"]) > 0:
        if text == "":
            text = "Less like " + names_text(critique["disliked"], db)
        else:
            text = text + ", less like " + names_text(critique["disliked"], db)
    return text + ":"


def handle_critique(parsed, state, services):
    """CRITIQUE (F1.1): add the like / dislike to the critique session, rank again with the
    Rocchio query, show the 5 nearest tracks never shown before.

    After "/recommend" on a rock playlist, "/like 2" (or "more like the second one")
        -> "More like <b>It's My Life by Bon Jovi</b>:" + 5 new tracks near the new query
    """
    slots = parsed.slots
    if "like" not in slots and "dislike" not in slots:
        # "older", "more acoustic": attribute critiques come in T5.
        understood = html.escape(str(slots), quote=False)
        return Reply("Critiques by year, popularity or tag are not built yet. "
                     "I understood: " + understood)

    if state.critique is None or len(state.last_shown) == 0:
        return Reply("Ask me for recommendations first, then tell me which ones you like, "
                     "for example 'more like the second one' or 'less like the one by Bon Jovi'.")

    # Both slots are looked up before anything changes, so a wrong one changes nothing.
    liked_id = None
    if "like" in slots:
        liked_id = pick_shown(slots["like"], state, services.db)
        if liked_id is None:
            return not_found_reply(slots["like"])
    disliked_id = None
    if "dislike" in slots:
        disliked_id = pick_shown(slots["dislike"], state, services.db)
        if disliked_id is None:
            return not_found_reply(slots["dislike"])

    # A liked or disliked song is never on screen again (it is in state.shown), so it
    # cannot be picked twice: a plain append is enough.
    critique = state.critique
    if liked_id is not None:
        critique["liked"].append(liked_id)
    if disliked_id is not None:
        critique["disliked"].append(disliked_id)

    query = critique_query(critique, services.vectors)
    if query is None:
        return Reply("Sorry, I cannot compare these songs, so I cannot change the list.")

    # Never show a track again, and never one already in the playlist.
    exclude_ids = set(state.shown)
    for track_id in state.playlist:
        exclude_ids.add(track_id)

    results = services.vectors.nearest(SPACE, query, NUM_RECOMMENDATIONS, exclude_ids)
    if len(results) == 0:
        return Reply("Sorry, I could not find any new songs for that.")

    # Why each track is here (F3): the critique so far, plus its own cosine to the query.
    track_ids = []
    tracks = []
    signals_by_id = {}
    for track_id, score in results:
        track_ids.append(track_id)
        tracks.append(services.db.get(track_id))
        signals_by_id[track_id] = {
            "source": "critique",
            "liked": list(critique["liked"]),
            "disliked": list(critique["disliked"]),
            "filters": list(critique["filters"]),
            "similarity": round(score, 3),
        }
    # new_list=False: the base list, likes and dislikes are kept for the next critique.
    show_tracks(state, track_ids, signals_by_id, new_list=False)

    text = critique_text(critique, services.db) + "\n<ol>\n"
    for track in tracks:
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>\n"
    text = text + ("Say 'add the first two', 'more like the third one' "
                   "or 'less like the fourth one'.")
    return Reply(text, [options_act(tracks)])


def not_found_reply(value):
    """The reply when a like / dislike names no track of the last list: "7", "queen"."""
    asked = html.escape(str(value), quote=False)
    return Reply("I could not find '" + asked + "' in the last list. "
                 "Use its number (for example 'more like the second one') or its artist.")
