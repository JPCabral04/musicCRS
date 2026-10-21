"""Check the resolver and the playlist, help and question handlers (T6, T7, T8, T10, T12).

Run from the repo root (no API key and no retriever needed, takes about a second):
    python -m musiccrs.checks.check_handlers

Started by Alejandro as a print script (check_playlist.py + check_qa.py, Oct 19); turned
into checks by JP (Oct 21). The handlers are called directly with ParsedIntents, as the
parser would give them, so no LLM call is made. The not-in-catalog songs come from the
course simulator's scripts. Exits with code 1 if a check fails.
"""
import sys

from ..data.db import TrackDB
from ..data.resolver import resolve, resolve_artist
from ..handlers.playlist import (NUM_OPTIONS, handle_add, handle_clear, handle_help,
                                 handle_remove, handle_show, rank_options)
from ..handlers.qa import _format_duration, handle_ask_artist, handle_ask_track
from ..handlers.selection import handle_select
from ..nlu.parser import parse_command
from ..state import DialogueState, ParsedIntent, Services

problems = []


def check(condition, message):
    """Print the result of one check and remember it when it fails."""
    if condition:
        print("  ok    " + message)
    else:
        print("  FAIL  " + message)
        problems.append(message)


def main_artists(tracks):
    """The main artist of each track: [It's My Life (Bon Jovi), ...] -> ["Bon Jovi", ...]."""
    names = []
    for track in tracks:
        names.append(track.artists[0])
    return names


def check_resolver(db):
    print("Resolver (T6):")
    for text in ["its my life", "IT'S MY LIFE!"]:
        tracks = resolve(db, text, None)
        check(len(tracks) > 0 and tracks[0].artists[0] == "Bon Jovi",
              "'" + text + "' -> Bon Jovi first")
    tracks = resolve(db, "it's my life by bon jovi", None)
    check(main_artists(tracks) == ["Bon Jovi"], "'it's my life by bon jovi' -> only Bon Jovi")

    # Not in the catalog with that artist: nothing, never a song by another artist.
    missing = [("always", "bon jovi"), ("money, money, money", "abba"),
               ("we believe", "good charlotte"), ("goodbye", "chris young")]
    for name, artist in missing:
        tracks = resolve(db, name, artist)
        check(len(tracks) == 0, "'" + name + "' by '" + artist + "' -> not found")

    tracks = resolve(db, "hotel california", "the eagles")
    only_eagles = len(tracks) > 0
    for name in main_artists(tracks):
        if name != "Eagles":
            only_eagles = False
    check(only_eagles, "'hotel california' by 'the eagles' -> only Eagles tracks")

    tracks = resolve(db, "smells like teen sprit", "nirvana")
    check(main_artists(tracks) == ["Nirvana"], "typo 'smells like teen sprit' by nirvana -> Nirvana")

    check(len(resolve_artist(db, "the eagles")) > 0, "artist 'the eagles' -> Eagles tracks")
    check(len(resolve_artist(db, "beatles")) > 0, "artist 'beatles' -> The Beatles tracks")


def check_add_and_select(services, state):
    print("\nADD (R2), disambiguation (R4) and /select (R7):")
    db = services.db

    reply = handle_add(ParsedIntent("ADD", {"track": "smells like teen spirit", "artist": "nirvana"}),
                       state, services)
    check(len(state.playlist) == 1, "add Smells Like Teen Spirit by Nirvana -> added")

    reply = handle_add(ParsedIntent("ADD", {"track": "smells like teen spirit", "artist": "nirvana"}),
                       state, services)
    check("already in your playlist" in reply.text and len(state.playlist) == 1,
          "add it again -> 'already in your playlist'")

    reply = handle_add(ParsedIntent("ADD", {"track": "always", "artist": "bon jovi"}), state, services)
    check("could not find" in reply.text and len(state.playlist) == 1 and state.pending_kind is None,
          "add Always by Bon Jovi -> refused, no options")

    reply = handle_add(ParsedIntent("ADD", {"track": "love"}), state, services)
    option_count = 0
    if len(reply.dialogue_acts) == 1:
        option_count = len(reply.dialogue_acts[0].annotations)
    check(len(state.pending_options) == NUM_OPTIONS and state.pending_kind == "disambiguation"
          and option_count == NUM_OPTIONS,
          "add Love -> " + str(NUM_OPTIONS) + " options in an OPTIONS act")

    second_choice = state.pending_options[1]
    parsed = parse_command("/select 2")
    check(parsed.name == "SELECT" and parsed.slots == {"selection": "2"},
          "'/select 2' -> SELECT with selection '2'")
    handle_select(parsed, state, services)
    check(len(state.playlist) == 2 and state.playlist[1] == second_choice
          and state.pending_kind is None,
          "/select 2 -> the second option added, options cleared")

    # The ranking: a candidate by an artist already in the playlist moves to the top.
    candidates = resolve(db, "love", None)
    plain_order = rank_options(candidates, [], services)
    third = plain_order[2]
    other_tracks = resolve_artist(db, third.artists[0])
    same_artist_track = None
    for track in other_tracks:
        if track.track_id != third.track_id:
            same_artist_track = track
            break
    if same_artist_track is not None:
        boosted_order = rank_options(candidates, [same_artist_track.track_id], services)
        check(boosted_order[0].track_id == third.track_id,
              "R4 ranking: with a " + third.artists[0] + " song in the playlist, its 'Love' comes first")

    handle_add(ParsedIntent("ADD", {"track": "bad medicine", "artist": "bon jovi"}), state, services)
    handle_add(ParsedIntent("ADD", {"track": "its my life by bon jovi"}), state, services)
    check(len(state.playlist) == 4, "add Bad Medicine, then 'its my life by bon jovi' -> 4 songs")


def check_remove_show_clear(services, state):
    print("\nREMOVE, SHOW, CLEAR (R2):")
    reply = handle_remove(ParsedIntent("REMOVE", {"track": "teen spirit"}), state, services)
    check("Removed" in reply.text and len(state.playlist) == 3, "remove 'teen spirit' -> removed (part of the title)")

    reply = handle_remove(ParsedIntent("REMOVE", {"artist": "bon jovi"}), state, services)
    check("Several songs" in reply.text and len(state.playlist) == 3,
          "remove 'the Bon Jovi song' with two Bon Jovi songs -> asks which one")

    reply = handle_remove(ParsedIntent("REMOVE", {"track": "bad medicine", "artist": "bon jovi"}),
                          state, services)
    check(len(state.playlist) == 2, "remove Bad Medicine by Bon Jovi -> removed")

    reply = handle_remove(ParsedIntent("REMOVE", {"artist": "queen"}), state, services)
    check("not in your playlist" in reply.text and len(state.playlist) == 2,
          "remove 'the Queen song' (none) -> not in your playlist")

    reply = handle_remove(ParsedIntent("REMOVE", {"track_id": "not-a-real-id"}), state, services)
    check("not in your playlist" in reply.text, "/remove <unknown id> -> not in your playlist, no crash")

    first_id = state.playlist[0]
    reply = handle_remove(ParsedIntent("REMOVE", {"track_id": first_id}), state, services)
    check(len(state.playlist) == 1 and first_id not in state.playlist, "/remove <id> (the panel's remove button) -> removed")

    reply = handle_remove(ParsedIntent("REMOVE", {}), state, services)
    check("Which song" in reply.text, "remove with no song -> asks which one")

    reply = handle_show(ParsedIntent("SHOW", {}), state, services)
    check("1 song:" in reply.text, "show with 1 song -> '1 song'")

    reply = handle_clear(ParsedIntent("CLEAR", {}), state, services)
    check(len(state.playlist) == 0 and "1 song removed" in reply.text, "clear -> empty")
    reply = handle_clear(ParsedIntent("CLEAR", {}), state, services)
    check("already empty" in reply.text, "clear again -> already empty")


def check_help(services, state):
    print("\nHELP (R3):")
    reply = handle_help(ParsedIntent("HELP", {}), state, services)
    has_all = True
    for words in ["Add songs", "Remove songs", "Ask questions", "Get recommendations",
                  "Create a playlist", "Choose from a list"]:
        if words not in reply.text:
            has_all = False
    check(has_all, "'what can you do?' -> every feature, including R8")
    reply = handle_help(ParsedIntent("HELP", {"topic": "remove"}), state, services)
    check(reply.text.startswith("<b>Remove songs"), "'how do I remove a song?' -> only the remove help")


def check_questions(services, state):
    print("\nQuestions (R5), 4 for tracks and 4 for artists:")
    db = services.db

    reply = handle_ask_track(ParsedIntent("ASK_TRACK", {"track": "hotel california", "question": "artist"}),
                             state, services)
    check("Eagles" in reply.text, "who sings Hotel California? -> Eagles")

    nirvana = resolve(db, "smells like teen spirit", "nirvana")[0]
    reply = handle_ask_track(ParsedIntent("ASK_TRACK", {"track": "smells like teen spirit",
                                                        "artist": "nirvana", "question": "album"}),
                             state, services)
    check(nirvana.album in reply.text, "album of Smells Like Teen Spirit -> " + nirvana.album)

    life = resolve(db, "its my life", "bon jovi")[0]
    reply = handle_ask_track(ParsedIntent("ASK_TRACK", {"track": "its my life", "artist": "bon jovi",
                                                        "question": "release_year"}),
                             state, services)
    check(life.release_date[:4] in reply.text, "release year of It's My Life -> " + life.release_date[:4])

    medicine = resolve(db, "bad medicine", "bon jovi")[0]
    reply = handle_ask_track(ParsedIntent("ASK_TRACK", {"track": "bad medicine", "question": "duration"}),
                             state, services)
    duration = _format_duration(medicine.duration_ms)
    check(duration in reply.text, "how long is Bad Medicine? -> " + duration)

    bon_jovi = resolve_artist(db, "bon jovi")
    reply = handle_ask_artist(ParsedIntent("ASK_ARTIST", {"artist": "bon jovi", "question": "track_count"}),
                              state, services)
    check("<b>" + str(len(bon_jovi)) + "</b> tracks" in reply.text,
          "how many songs does Bon Jovi have? -> " + str(len(bon_jovi)))

    nirvana_tracks = resolve_artist(db, "nirvana")
    reply = handle_ask_artist(ParsedIntent("ASK_ARTIST", {"artist": "nirvana", "question": "top_track"}),
                              state, services)
    check(nirvana_tracks[0].name in reply.text, "most popular Nirvana song -> " + nirvana_tracks[0].name)

    reply = handle_ask_artist(ParsedIntent("ASK_ARTIST", {"artist": "queen", "question": "albums"}),
                              state, services)
    check("Albums by <b>Queen</b>" in reply.text, "albums by Queen -> a list")

    reply = handle_ask_artist(ParsedIntent("ASK_ARTIST", {"artist": "the eagles", "question": "genres"}),
                              state, services)
    check("tags/genres for <b>Eagles</b>" in reply.text, "genres of 'the eagles' -> Eagles tags")


def main():
    db = TrackDB()
    services = Services(db=db, retriever=None, llm=None)
    state = DialogueState()

    check_resolver(db)
    check_add_and_select(services, state)
    check_remove_show_clear(services, state)
    check_help(services, state)
    check_questions(services, state)

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
