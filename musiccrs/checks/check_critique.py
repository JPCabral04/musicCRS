"""Check the critiques (Part 4, T3 F1.1 and T5 F1.2) on the rock, jazz and pop playlists.

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
Then, for each playlist again (F1.2): R6, "older", "more popular", "older" again, checking
that every song is on the asked side of the median of the list on screen, the filters add
up, and no song comes back. Then the replies with no list, a number out of range, a changed
mind, a tag, "like #2 but older", a filter nothing passes and a missing attribute.
Exits with code 1 if a check fails.
"""
import sys
import time

import numpy as np

from ..handlers.critique import SPACE, handle_critique, lower_tags, year_of
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


def attribute_values(track_ids, attribute, db):
    """The years or the popularities of the tracks (tracks without a year left out)."""
    values = []
    for track_id in track_ids:
        track = db.get(track_id)
        if attribute == "year":
            value = year_of(track)
        else:
            value = track.popularity
        if value is not None:
            values.append(value)
    return values


def middle_value(values):
    """The median of a list of numbers (the middle one once sorted)."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def count_outside(track_ids, attribute, direction, limit, db):
    """How many tracks are NOT on the asked side of the limit (a track without a year counts)."""
    outside = 0
    for track_id in track_ids:
        track = db.get(track_id)
        if attribute == "year":
            value = year_of(track)
        else:
            value = track.popularity
        if value is None:
            outside = outside + 1
        elif direction == "less" and not value < limit:
            outside = outside + 1
        elif direction == "more" and not value > limit:
            outside = outside + 1
    return outside


def check_attributes(name, services, timings):
    """F1.2 on one playlist: R6, "older", "more popular", "older" again.

    Done when: after "older" then "more popular", every song is older than the first list's
    median year and more popular than the median of the list on screen, none shown before.
    """
    print("\n" + name + ": attribute critiques")
    db = services.db
    playlist = build_playlist(services, PLAYLISTS[name])
    state = DialogueState(playlist=list(playlist))

    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    first = list(state.last_shown)
    print_list("R6:", first, db)
    seen_ids = set(first)

    # "older": every song before the first list's median year.
    year_limit = middle_value(attribute_values(first, "year", db))
    second, ms = critique(state, services, {"attribute": "year", "direction": "less"})
    timings.append(ms)
    print_list("older (than " + str(year_limit) + "):", second, db)
    check_new_list(second, seen_ids, playlist)
    outside = count_outside(second, "year", "less", year_limit, db)
    check(outside == 0, "all older than " + str(year_limit) + " (" + str(outside) + " not)")
    for track_id in second:
        seen_ids.add(track_id)

    # "more popular": still older (the filters add up), and above the median on screen.
    popularity_limit = middle_value(attribute_values(second, "popularity", db))
    third, ms = critique(state, services, {"attribute": "popularity", "direction": "more"})
    timings.append(ms)
    print_list("more popular (than " + str(popularity_limit) + "):", third, db)
    check_new_list(third, seen_ids, playlist)
    outside = count_outside(third, "year", "less", year_limit, db)
    check(outside == 0, "still older than " + str(year_limit) + " (" + str(outside) + " not)")
    outside = count_outside(third, "popularity", "more", popularity_limit, db)
    check(outside == 0, "all popularity above " + str(popularity_limit)
          + " (" + str(outside) + " not)")
    check(len(state.critique["filters"]) == 2, "two filters stored")
    for track_id in third:
        seen_ids.add(track_id)

    # "older" again: the new median comes from the already older list on screen.
    second_year_limit = middle_value(attribute_values(third, "year", db))
    fourth, ms = critique(state, services, {"attribute": "year", "direction": "less"})
    timings.append(ms)
    print_list("older again (than " + str(second_year_limit) + "):", fourth, db)
    check(second_year_limit <= year_limit, "the second year limit is not later: "
          + str(year_limit) + " -> " + str(second_year_limit))
    if len(fourth) > 0:
        outside = count_outside(fourth, "year", "less", second_year_limit, db)
        check(outside == 0, "all older than " + str(second_year_limit)
              + " (" + str(outside) + " not)")
    for track_id in fourth:
        check(track_id not in seen_ids, "not shown before: " + db.get(track_id).name)


def check_attribute_edge_cases(services):
    """A tag, a like and a filter in one sentence, a filter nothing passes, a missing slot."""
    print("\nAttribute edge cases")
    db = services.db
    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)

    # "more hard rock": every song has the tag (whatever its case in the catalog).
    tag_list, ms = critique(state, services,
                            {"attribute": "tag", "direction": "more", "tag": "Hard Rock"})
    without = 0
    for track_id in tag_list:
        if "hard rock" not in lower_tags(db.get(track_id)):
            without = without + 1
    check(len(tag_list) > 0 and without == 0,
          "'more hard rock' -> all tagged hard rock (" + str(without) + " not)")

    # "like #2 but older": both the like and the filter.
    liked_id = state.last_shown[1]
    year_limit = middle_value(attribute_values(state.last_shown, "year", db))
    both, ms = critique(state, services,
                        {"like": "2", "attribute": "year", "direction": "less"})
    check(state.critique["liked"] == [liked_id], "'like #2 but older' stores the like")
    outside = count_outside(both, "year", "less", year_limit, db)
    check(len(both) > 0 and outside == 0, "'like #2 but older' -> all older than "
          + str(year_limit) + " (" + str(outside) + " not)")

    # A filter nothing passes is undone: the list and the filters stay as they were.
    before_list = list(state.last_shown)
    before_filters = list(state.critique["filters"])
    reply = handle_critique(ParsedIntent("CRITIQUE",
                                         {"attribute": "tag", "direction": "more", "tag": "polka"}),
                            state, services)
    check(reply.text.startswith("Sorry, no new songs"), "'more polka' -> 'Sorry, no new songs'")
    check(state.last_shown == before_list and state.critique["filters"] == before_filters,
          "'more polka' changes nothing")

    # Only a direction (the parser dropped an unknown attribute, "/critique colour more").
    reply = handle_critique(ParsedIntent("CRITIQUE", {"direction": "more"}), state, services)
    check(reply.text.startswith("I can change the songs"), "no attribute -> 'I can change'")

    # A new recommendation starts a new critique session: no filters.
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    check(state.critique["filters"] == [], "a new recommendation forgets the filters")


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
    for name in ["rock", "jazz", "pop"]:
        check_attributes(name, services, timings)
    check_edge_cases(services)
    check_attribute_edge_cases(services)

    timings.sort()
    print("\nms per critique: median " + str(round(timings[len(timings) // 2]))
          + ", max " + str(round(timings[-1])))

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
