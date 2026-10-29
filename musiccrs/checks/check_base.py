"""Check the Part 4 base (T1): slash commands, shown tracks, pick_shown and nearest().

Run from the repo root (no API key and no retriever needed; about 12 s, most of it
loading the catalog for the track order):
    python -m musiccrs.checks.check_base

The parser and the handlers are called directly, so no LLM call is made.
The LLM side of the Part 4 intents is checked by check_nlu.
Exits with code 1 if a check fails.
"""
import sys

from retrieval.data_loader import MusicCatalogLoader
from retrieval.methods.dense import DEFAULT_FIELD, load_track_matrix

from ..data.db import TrackDB
from ..data.resolver import resolve
from ..data.vectors import TrackVectors
from ..handlers.selection import clear_pending
from ..handlers.shown import pick_shown, remember_tracks, same_signals, show_tracks
from ..musiccrs import HANDLERS
from ..nlu.parser import clean_slot_value, parse_command
from ..state import DialogueState

problems = []

# Every Part 4 slash command: (text, intent, slots).
SLASH_COMMANDS = [
    ("/like 2", "CRITIQUE", {"like": "2"}),
    ("/dislike bon jovi", "CRITIQUE", {"dislike": "bon jovi"}),
    ("/critique year less", "CRITIQUE", {"attribute": "year", "direction": "less"}),
    ("/critique popularity more", "CRITIQUE", {"attribute": "popularity", "direction": "more"}),
    ("/critique tag less hard rock", "CRITIQUE",
     {"attribute": "tag", "direction": "less", "tag": "hard rock"}),
    ("/critique colour more", "CRITIQUE", {"direction": "more"}),
    ("/sounds nirvana: in bloom", "SOUNDS_LIKE", {"artist": "nirvana", "track": "in bloom"}),
    ("/sounds numb", "SOUNDS_LIKE", {"track": "numb"}),
    ("/about leaving home", "LYRICS_SEARCH", {"theme": "leaving home"}),
    ("/why 2", "EXPLAIN", {"option": "2"}),
    ("/why", "EXPLAIN", {}),
]

# Five catalog songs used as a shown list: (track, artist).
SHOWN_SONGS = [
    ("numb", "linkin park"),
    ("its my life", "bon jovi"),
    ("toxic", "britney spears"),
    ("yellow", "coldplay"),
    ("hotel california", "eagles"),
]


def check(condition, message):
    """Print the result of one check and remember it when it fails."""
    if condition:
        print("  ok    " + message)
    else:
        print("  FAIL  " + message)
        problems.append(message)


def check_slash_commands():
    """Every Part 4 slash command gives the right intent and slots, and reaches a handler."""
    print("Slash commands")
    for text, intent, slots in SLASH_COMMANDS:
        parsed = parse_command(text)
        check(parsed.name == intent and parsed.slots == slots,
              text + " -> " + intent + " " + str(slots))
        check(parsed.name in HANDLERS, text + " has a handler")
        reply = HANDLERS[parsed.name](parsed, DialogueState(), None)
        check(reply.text != "", text + " gets a reply")


def check_slot_values():
    """The fixed-value slots of CRITIQUE keep only allowed values."""
    print("CRITIQUE slot values")
    check(clean_slot_value("attribute", "Year", "CRITIQUE") == "year", "attribute 'Year' -> 'year'")
    check(clean_slot_value("attribute", "colour", "CRITIQUE") is None, "attribute 'colour' dropped")
    check(clean_slot_value("direction", "LESS", "CRITIQUE") == "less", "direction 'LESS' -> 'less'")
    check(clean_slot_value("direction", "older", "CRITIQUE") is None, "direction 'older' dropped")
    check(clean_slot_value("like", 2, "CRITIQUE") == "2", "like 2 (a number) -> '2'")


def shown_ids(db):
    """The track IDs of SHOWN_SONGS, best match of each."""
    track_ids = []
    for track_name, artist in SHOWN_SONGS:
        matches = resolve(db, track_name, artist)
        track_ids.append(matches[0].track_id)
    return track_ids


def check_show_tracks(track_ids):
    """show_tracks fills pending options, last_shown, shown, signals and the critique session."""
    print("show_tracks")
    state = DialogueState()
    signals = {"source": "recommend", "base_ids": ["seed"]}
    show_tracks(state, track_ids, same_signals(track_ids, signals))

    check(state.pending_options == track_ids, "pending_options = the list")
    check(state.pending_kind == "recommendation", "pending_kind = 'recommendation'")
    check(state.last_shown == track_ids, "last_shown = the list")
    check(len(state.shown) == 5, "5 tracks in shown")
    check(state.signals[track_ids[0]]["source"] == "recommend", "signals stored")

    # Each track has its own copy: changing one does not change the others.
    state.signals[track_ids[0]]["retrievers"] = {"dense": 1}
    check("retrievers" not in state.signals[track_ids[1]], "signals are one copy per track")

    check(state.critique is not None and state.critique["base_ids"] == track_ids,
          "a new critique session starts from the list")
    check(state.critique["liked"] == [] and state.critique["filters"] == [],
          "the new session has no likes and no filters")

    # A critique adds a like, then shows a new list with new_list=False: the like stays.
    state.critique["liked"].append(track_ids[1])
    show_tracks(state, track_ids[:2], {}, new_list=False)
    check(state.critique["liked"] == [track_ids[1]], "new_list=False keeps the critique session")
    check(state.critique["base_ids"] == track_ids, "new_list=False keeps the base list")

    # "add the first two" clears the pending options, but last_shown stays.
    clear_pending(state)
    check(state.pending_options == [] and len(state.last_shown) == 2,
          "after a selection, last_shown is kept")


def check_remember_tracks(track_ids):
    """remember_tracks (R8) adds to shown and signals, but sets no pending options."""
    print("remember_tracks")
    state = DialogueState()
    remember_tracks(state, track_ids, same_signals(track_ids, {"source": "playlist"}))
    check(len(state.shown) == 5, "5 tracks in shown")
    check(state.pending_options == [] and state.last_shown == [], "no pending options, no last_shown")
    check(state.critique is None, "no critique session")


def check_pick_shown(track_ids, db):
    """pick_shown finds a track of last_shown by number or loose name."""
    print("pick_shown (Numb, It's My Life, Toxic, Yellow, Hotel California)")
    state = DialogueState(last_shown=list(track_ids))
    check(pick_shown("2", state, db) == track_ids[1], "'2' -> It's My Life")
    check(pick_shown(" 5 ", state, db) == track_ids[4], "' 5 ' -> Hotel California")
    check(pick_shown("Bon Jovi", state, db) == track_ids[1], "'Bon Jovi' -> It's My Life")
    check(pick_shown("TOXIC", state, db) == track_ids[2], "'TOXIC' -> Toxic")
    check(pick_shown("hotel", state, db) == track_ids[4], "'hotel' -> Hotel California")
    check(pick_shown("0", state, db) is None, "'0' -> None")
    check(pick_shown("6", state, db) is None, "'6' -> None")
    check(pick_shown("queen", state, db) is None, "'queen' -> None")
    check(pick_shown("  ", state, db) is None, "empty text -> None")
    check(pick_shown(None, state, db) is None, "None -> None")
    check(pick_shown("2", DialogueState(), db) is None, "nothing shown -> None")


def check_nearest(db):
    """nearest returns k tracks, best first, never an excluded one or one without a vector."""
    print("TrackVectors.nearest")
    catalog = MusicCatalogLoader()
    track_ids = list(catalog.metadata_dict)
    metadata_matrix, metadata_has_vector = load_track_matrix(DEFAULT_FIELD, track_ids)
    vectors = TrackVectors(track_ids, metadata_matrix, metadata_has_vector)

    seed_id = resolve(db, "smells like teen spirit", "nirvana")[0].track_id
    seed_vector = vectors.vector("audio", seed_id)
    check(seed_vector is not None and len(seed_vector) == 512, "the seed has a 512-number audio vector")

    results = vectors.nearest("audio", seed_vector, 5, {seed_id})
    result_ids = []
    scores = []
    for track_id, score in results:
        result_ids.append(track_id)
        scores.append(score)
    check(len(results) == 5, "5 results")
    check(seed_id not in result_ids, "the excluded seed is not among them")
    check(scores == sorted(scores, reverse=True), "best first")

    # Without the exclusion, a track is its own nearest neighbour (cosine 1).
    own = vectors.nearest("audio", seed_vector, 1, set())
    check(own[0][0] == seed_id and own[0][1] > 0.999, "without exclusion, the seed itself comes first")

    # Excluding the first 5 gives 5 other tracks: the exclusion does not shorten the list.
    excluded = set(result_ids)
    excluded.add(seed_id)
    more = vectors.nearest("audio", seed_vector, 5, excluded)
    overlap = False
    for track_id, score in more:
        if track_id in excluded:
            overlap = True
    check(len(more) == 5 and not overlap, "excluding the first 5 still gives 5 new tracks")

    # A track without a vector is never returned, and vector() gives None for it.
    no_vector_id = None
    for row in range(len(track_ids)):
        if not vectors.usable["audio"][row]:
            no_vector_id = track_ids[row]
            break
    check(vectors.vector("audio", no_vector_id) is None, "vector() of a track without one -> None")
    check(vectors.vector("audio", "not-a-track-id") is None, "vector() of an unknown ID -> None")


def main():
    db = TrackDB()
    check_slash_commands()
    check_slot_values()

    track_ids = shown_ids(db)
    check_show_tracks(track_ids)
    check_remember_tracks(track_ids)
    check_pick_shown(track_ids, db)
    check_nearest(db)

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
