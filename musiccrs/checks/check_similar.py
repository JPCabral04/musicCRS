"""Check sounds like (Part 4, T6 F2.1) and lyrics search (T8 F2.2).

Run from the repo root (no API key needed, the LLM is not used; about 1 min, most of it
loading the retriever, whose dense scorer encodes the lyrics themes):
    python -m musiccrs.checks.check_similar

It prints each list and checks that
- the handler returns a Reply whose text names the seed song (or the theme)
  and whose OPTIONS act has one button per song;
- each list has 5 songs: not the seed, not another version of it, never shown before;
- each song is stored with its signal ("audio" or "lyrics"), for "why this song?";
- three themes give three different lists;
- an unknown song or an empty slot gets a plain reply, not a crash.
Exits with code 1 if a check fails.
"""
import sys

from ..data.db import base_name
from ..data.resolver import resolve
from ..handlers.recs import NUM_RECOMMENDATIONS
from ..handlers.similar import handle_lyrics_search, handle_sounds_like
from ..musiccrs import create_services
from ..state import DialogueState, ParsedIntent, Reply

problems = []

THEMES = ["leaving home", "heartbreak", "partying all night"]


def check(condition, message):
    """Print the result of one check and remember it when it fails."""
    if condition:
        print("  ok    " + message)
    else:
        print("  FAIL  " + message)
        problems.append(message)


def print_list(state, db):
    """Print the last list shown: "  1. Come As You Are by Nirvana (0.912)"."""
    number = 1
    for track_id in state.last_shown:
        track = db.get(track_id)
        similarity = state.signals[track_id]["similarity"]
        print("    " + str(number) + ". " + track.name + " by " + track.artists[0]
              + " (" + str(round(similarity, 3)) + ")")
        number = number + 1


def check_list(reply, state, source, label):
    """The checks every shown list must pass."""
    check(isinstance(reply, Reply), label + ": the handler returns a Reply")
    check(len(state.last_shown) == NUM_RECOMMENDATIONS,
          label + ": " + str(NUM_RECOMMENDATIONS) + " songs")

    options = None
    for act in reply.dialogue_acts:
        if str(act.intent) == "OPTIONS":
            options = act
    check(options is not None and len(options.annotations) == len(state.last_shown),
          label + ": one OPTIONS button per song")

    all_have_signal = True
    for track_id in state.last_shown:
        if state.signals[track_id]["source"] != source:
            all_have_signal = False
    check(all_have_signal, label + ": every song has the signal '" + source + "'")


def check_sounds_like(services):
    """/sounds numb: 5 songs near Numb in the audio space, Numb itself left out."""
    db = services.db
    print("Sounds like (T6)")
    state = DialogueState()
    parsed = ParsedIntent("SOUNDS_LIKE", {"track": "numb", "artist": "linkin park"})
    reply = handle_sounds_like(parsed, state, services)
    print_list(state, db)

    check_list(reply, state, "audio", "/sounds numb")
    check("Numb" in reply.text, "/sounds numb: the reply names the seed song")

    no_seed_version = True
    for track_id in state.last_shown:
        track = db.get(track_id)
        if base_name(track.name) == "numb" and track.artists[0] == "Linkin Park":
            no_seed_version = False
    check(no_seed_version, "/sounds numb: no version of Numb by Linkin Park")
    seed_id = resolve(db, "numb", "linkin park")[0].track_id
    check(seed_id in state.shown, "/sounds numb: the seed counts as shown (no critique brings it back)")

    # The same question again: 5 new songs, none of the first list (F1.2).
    first_list = list(state.last_shown)
    handle_sounds_like(parsed, state, services)
    no_repeat = True
    for track_id in state.last_shown:
        if track_id in first_list:
            no_repeat = False
    check(no_repeat, "/sounds numb again: no song of the first list comes back")

    unknown = handle_sounds_like(ParsedIntent("SOUNDS_LIKE", {"track": "xqzvwk"}),
                                 DialogueState(), services)
    check("could not find" in unknown.text, "/sounds with an unknown song: a plain reply")
    empty = handle_sounds_like(ParsedIntent("SOUNDS_LIKE", {}), DialogueState(), services)
    check(empty.text != "", "/sounds with no song: a plain reply")


def check_lyrics_search(services):
    """/about <theme> for three themes: 5 songs each, three different lists."""
    db = services.db
    print("Lyrics search (T8)")
    lists = []
    for theme in THEMES:
        state = DialogueState()
        reply = handle_lyrics_search(ParsedIntent("LYRICS_SEARCH", {"theme": theme}),
                                     state, services)
        print("  /about " + theme)
        print_list(state, db)
        check_list(reply, state, "lyrics", "/about " + theme)
        check(theme in reply.text, "/about " + theme + ": the reply names the theme")
        lists.append(list(state.last_shown))

    check(lists[0] != lists[1] and lists[1] != lists[2] and lists[0] != lists[2],
          "three themes give three different lists")

    empty = handle_lyrics_search(ParsedIntent("LYRICS_SEARCH", {}), DialogueState(), services)
    check(empty.text != "", "/about with no theme: a plain reply")


def main():
    services = create_services(use_llm=False)
    check_sounds_like(services)
    check_lyrics_search(services)

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
