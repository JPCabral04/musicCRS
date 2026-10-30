"""Check the example critiques (Part 4, T3, F1.1) on the rock, jazz and pop playlists.

Run from the repo root (no API key needed, the LLM is not used; about 1 min, most of it
loading the retriever for the first recommendation):
    python -m musiccrs.checks.check_critique

For each playlist: R6 recommends 5 songs, then "more like the second one", then
"less like the fourth one". It prints the three lists and checks that
- every list has 5 songs, none shown before and none in the playlist;
- after the like, the songs are closer to #2 than the first list was
  (mean audio cosine to #2, #2 itself left out of the first list's mean);
- after the dislike, the songs are further from the disliked one than the list it was in,
  and the like is still applied.
Then the replies with no list, a number out of range, a changed mind and an attribute
critique. Exits with code 1 if a check fails.
"""
import sys
import time

import numpy as np

from ..handlers.critique import SPACE, handle_critique
from ..handlers.recs import NUM_RECOMMENDATIONS, handle_recommend
from ..musiccrs import create_services
from ..state import DialogueState, ParsedIntent
from .check_recs import PLAYLISTS, build_playlist

problems = []


def check(condition, message):
    """Print the result of one check and remember it when it fails."""
    if condition:
        print("  ok    " + message)
    else:
        print("  FAIL  " + message)
        problems.append(message)


def mean_cosine(track_ids, target_id, vectors):
    """Mean cosine between the tracks and one target track, in the critique space.

    The rows are L2-normalized, so a dot product is a cosine.
    The target itself is left out (its cosine to itself is 1).
    """
    target = vectors.vector(SPACE, target_id)
    total = 0.0
    count = 0
    for track_id in track_ids:
        if track_id == target_id:
            continue
        vector = vectors.vector(SPACE, track_id)
        if vector is None:
            continue
        total = total + float(np.dot(vector, target))
        count = count + 1
    if count == 0:
        return 0.0
    return total / count


def print_list(title, track_ids, db):
    """The songs of one list, one per line."""
    print("  " + title)
    for track_id in track_ids:
        track = db.get(track_id)
        print("      " + track.name + " by " + track.artists[0])


def critique(state, services, slots):
    """Run handle_critique once; returns (the new list, ms)."""
    start = time.perf_counter()
    handle_critique(ParsedIntent("CRITIQUE", slots), state, services)
    ms = 1000 * (time.perf_counter() - start)
    return list(state.last_shown), ms


def check_new_list(track_ids, seen_ids, playlist):
    """5 songs, none shown before, none in the playlist."""
    check(len(track_ids) == NUM_RECOMMENDATIONS,
          str(NUM_RECOMMENDATIONS) + " songs (got " + str(len(track_ids)) + ")")
    repeated = 0
    in_playlist = 0
    for track_id in track_ids:
        if track_id in seen_ids:
            repeated = repeated + 1
        if track_id in playlist:
            in_playlist = in_playlist + 1
    check(repeated == 0, "no song shown before (" + str(repeated) + " repeated)")
    check(in_playlist == 0, "no song from the playlist (" + str(in_playlist) + " found)")


def check_playlist(name, services, timings):
    """R6, then "more like the second one", then "less like the fourth one"."""
    print("\n" + name)
    db = services.db
    vectors = services.vectors
    playlist = build_playlist(services, PLAYLISTS[name])
    state = DialogueState(playlist=list(playlist))

    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    first = list(state.last_shown)
    print_list("R6:", first, db)

    # "more like the second one"
    liked_id = first[1]
    second, ms = critique(state, services, {"like": "2"})
    timings.append(ms)
    print_list("more like #2 (" + db.get(liked_id).name + "):", second, db)
    check_new_list(second, set(first), playlist)
    before = mean_cosine(first, liked_id, vectors)
    after = mean_cosine(second, liked_id, vectors)
    check(after > before, "closer to #2: mean cosine " + str(round(before, 3))
          + " -> " + str(round(after, 3)))
    check(state.critique["liked"] == [liked_id], "the like is stored")
    check(state.signals[second[0]]["source"] == "critique", "signals say 'critique'")

    # "less like the fourth one" (of the new list)
    disliked_id = second[3]
    third, ms = critique(state, services, {"dislike": "4"})
    timings.append(ms)
    print_list("less like #4 (" + db.get(disliked_id).name + "):", third, db)
    seen_ids = set(first)
    for track_id in second:
        seen_ids.add(track_id)
    check_new_list(third, seen_ids, playlist)
    before = mean_cosine(second, disliked_id, vectors)
    after = mean_cosine(third, disliked_id, vectors)
    check(after < before, "further from the disliked song: mean cosine "
          + str(round(before, 3)) + " -> " + str(round(after, 3)))
    check(state.critique["liked"] == [liked_id], "the like is still applied")
    check(state.critique["disliked"] == [disliked_id], "the dislike is stored")
    check(state.critique["base_ids"] == first, "the base list is still the R6 list")


def check_edge_cases(services):
    """No list yet, a wrong number, a changed mind, an attribute critique."""
    print("\nEdge cases")
    state = DialogueState()
    reply = handle_critique(ParsedIntent("CRITIQUE", {"like": "2"}), state, services)
    check(reply.text.startswith("Ask me for recommendations first"),
          "no list yet -> 'Ask me for recommendations first'")

    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    first = list(state.last_shown)

    reply = handle_critique(ParsedIntent("CRITIQUE", {"like": "7"}), state, services)
    check(reply.text.startswith("I could not find '7'"), "'7' -> 'I could not find'")
    check(state.critique["liked"] == [] and state.last_shown == first,
          "'7' changes nothing")

    reply = handle_critique(ParsedIntent("CRITIQUE", {"like": "2", "dislike": "9"}),
                            state, services)
    check(state.critique["liked"] == [], "a wrong dislike also blocks the like")

    # A liked song is never shown again, so "more like" it once more cannot find it.
    liked_id = first[1]
    handle_critique(ParsedIntent("CRITIQUE", {"like": "2"}), state, services)
    check(liked_id not in state.last_shown, "a liked song is not on screen again")
    name = services.db.get(liked_id).name
    reply = handle_critique(ParsedIntent("CRITIQUE", {"like": name}), state, services)
    check(reply.text.startswith("I could not find"),
          "liking it again by name -> 'I could not find' (" + name + ")")

    reply = handle_critique(ParsedIntent("CRITIQUE", {"attribute": "year", "direction": "less"}),
                            state, services)
    check("older than" in reply.text, "'older' -> a list 'older than <median year>'")


def main():
    services = create_services(use_llm=False)
    timings = []
    for name in ["rock", "jazz", "pop"]:
        check_playlist(name, services, timings)
    check_edge_cases(services)

    timings.sort()
    print("\nms per critique: median " + str(round(timings[len(timings) // 2]))
          + ", max " + str(round(timings[-1])))

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
