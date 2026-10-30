"""Check "why this song?" (Part 4, T7 F3) for a song from each source.

Run from the repo root (no API key needed, the LLM is not used; about 1 min, most of it
loading the retriever):
    python -m musiccrs.checks.check_explain

It prints each explanation and checks that
- retrieve_with_sources gives the same IDs as retrieve (Part 1 unchanged), with and
  without same_artist, and the stored ranks are the real places in each component list;
- a song from each source (recommend, "something different", critique, sounds like,
  lyrics) gets 1 to 4 sentences that name its source;
- every number in an explanation (outside song names and tags, which come from the DB)
  is a stored value: a retriever rank, a similarity, a filter value or a list size;
- no list, no option, a wrong number and a name give the right reply, and asking "why"
  changes nothing in the state.
The sounds-like and lyrics songs are found here with vectors.nearest and stored with the
signals format of part4_plan_detailed.md §3.3.
shortcut: hand-made audio / lyrics signals, switch to handle_sounds_like and
handle_lyrics_search once Alejandro's similar.py is merged into main.
Exits with code 1 if a check fails.
"""
import re
import sys
import time

from retrieval.context import SessionPolicy
from retrieval.methods.fusion import DEPTH

from ..handlers.critique import handle_critique
from ..handlers.explain import handle_explain
from ..handlers.playlist import describe_track
from ..handlers.recs import NUM_CANDIDATES, handle_recommend, recommend_context
from ..handlers.shown import show_tracks
from ..musiccrs import create_services
from ..state import DialogueState, ParsedIntent
from .check_recs import PLAYLISTS, build_playlist

problems = []
timings = []


def check(condition, message):
    """Print the result of one check and remember it when it fails."""
    if condition:
        print("  ok    " + message)
    else:
        print("  FAIL  " + message)
        problems.append(message)


def explain(state, services, slots):
    """Run handle_explain once, print the reply and return its text."""
    start = time.perf_counter()
    reply = handle_explain(ParsedIntent("EXPLAIN", slots), state, services)
    timings.append(1000 * (time.perf_counter() - start))
    for line in reply.text.split("\n"):
        if line != "":
            print("      | " + line)
    return reply.text


def numbers_in(text):
    """The numbers of a reply, leaving out song names (<b>...</b>) and tags (<i>...</i>).

    "Why <b>1979 by Smashing Pumpkins</b>: ... (#3) ... similarity 0.82" -> ["3", "0.82"]
    """
    text = re.sub(r"<b>.*?</b>", "", text)
    text = re.sub(r"<i>.*?</i>", "", text)
    return re.findall(r"\d+(?:\.\d+)?", text)


def stored_numbers(signals):
    """Every number an explanation may use, as text, read from the stored signals only."""
    numbers = set()
    if "retrievers" in signals:
        for name in signals["retrievers"]:
            numbers.add(str(signals["retrievers"][name]))
    if "similarity" in signals:
        numbers.add(str(round(float(signals["similarity"]), 2)))
    if "filters" in signals:
        for one_filter in signals["filters"]:
            numbers.add(str(one_filter["value"]))
    if "base_ids" in signals:
        numbers.add(str(len(signals["base_ids"])))
    return numbers


def check_explanation(text, signals, wanted):
    """1 to 4 sentences, the wanted words are there, and every number is a stored value."""
    sentences = text.count("<li>")
    check(sentences >= 1 and sentences <= 4, "1 to 4 sentences (got " + str(sentences) + ")")
    check(wanted in text, "says '" + wanted + "'")

    allowed = stored_numbers(signals)
    found = numbers_in(text)
    untraced = []
    for number in found:
        if number not in allowed:
            untraced.append(number)
    check(len(untraced) == 0, "every number is stored (found " + str(found)
          + ", not stored " + str(untraced) + ")")


def check_sources(services, ctx, policy, track_id, stored):
    """The stored ranks of one track are its places in each component list, played tracks left out."""
    played = set(ctx.played_track_ids)
    for name, scorer in services.retriever.fusion.scorers.items():
        ranked = scorer.score(ctx, DEPTH)
        place = None
        count = 0
        for candidate_id, _ in ranked:
            if candidate_id in played:
                continue
            count = count + 1
            if candidate_id == track_id:
                place = count
                break
        if name == "same_artist" and not policy.use_same_artist:
            check(name not in stored, name + " is off, not stored")
        elif place is None:
            check(name not in stored, name + " did not find it, not stored")
        else:
            check(stored.get(name) == place, name + " rank " + str(place)
                  + " (stored " + str(stored.get(name)) + ")")


def check_retriever(services):
    """retrieve_with_sources = retrieve, and the ranks are real (rock playlist)."""
    print("\nretrieve_with_sources (rock)")
    retriever = services.retriever
    playlist = build_playlist(services, PLAYLISTS["rock"])
    ctx = recommend_context(playlist)

    for policy in [SessionPolicy(), SessionPolicy(use_same_artist=False)]:
        plain = retriever.retrieve(ctx, NUM_CANDIDATES, policy)
        track_ids, sources = retriever.retrieve_with_sources(ctx, NUM_CANDIDATES, policy)
        label = "use_same_artist=" + str(policy.use_same_artist)
        check(track_ids == plain, label + ": same " + str(len(plain)) + " IDs as retrieve()")
        check(len(sources) == len(track_ids), label + ": ranks for every track")
        check_sources(services, ctx, policy, track_ids[0], sources[track_ids[0]])


def check_recommend(services):
    """R6 on the rock playlist, then "why the second one?" and "why <a title>?"."""
    print("\nrecommend (rock)")
    db = services.db
    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    first = list(state.last_shown)

    empty = 0
    for track_id in first:
        if len(state.signals[track_id]["retrievers"]) == 0:
            empty = empty + 1
    check(empty == 0, "every recommended song has its retriever ranks (" + str(empty) + " empty)")

    second_id = first[1]
    text = explain(state, services, {"option": "2"})
    check(describe_track(db.get(second_id)) in text, "explains #2 (" + db.get(second_id).name + ")")
    check_explanation(text, state.signals[second_id], "I recommended it for")
    check("It was found by" in text, "says which retrievers found it")
    check(state.pending_options == first and state.last_shown == first,
          "asking 'why' changes nothing (options still pending)")

    title = db.get(first[0]).name.lower()
    text = explain(state, services, {"option": title})
    check(describe_track(db.get(first[0])) in text, "'" + title + "' -> explains #1 by its name")


def check_different(services):
    """'Something different', then the song is added to the playlist before asking why."""
    print("\nrecommend something different (rock), #1 added to the playlist")
    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {"different": True}), state, services)
    first_id = state.last_shown[0]
    state.playlist.append(first_id)

    text = explain(state, services, {"option": "1"})
    check_explanation(text, state.signals[first_id], "you asked for something different")
    check("being by an artist of your songs" not in text, "same_artist was off, not a reason")
    check("is already in your playlist" not in text,
          "the song itself in the playlist is not a reason")


def check_critique_source(services):
    """R6, "more like the second one", "older", then "why the first one?"."""
    print("\ncritique (rock): like #2, then older")
    db = services.db
    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)
    liked_id = state.last_shown[1]
    handle_critique(ParsedIntent("CRITIQUE", {"like": "2"}), state, services)
    handle_critique(ParsedIntent("CRITIQUE", {"attribute": "year", "direction": "less"}),
                    state, services)
    first_id = state.last_shown[0]

    text = explain(state, services, {"option": "1"})
    check_explanation(text, state.signals[first_id], "It came from your critique")
    check("older than" in text, "names the 'older' filter")
    check(describe_track(db.get(liked_id)) in text, "names the liked song")


def check_audio_source(services):
    """The 5 audio neighbours of Smells Like Teen Spirit, stored as "sounds like" would."""
    print("\nsounds like Smells Like Teen Spirit (hand-made signals)")
    vectors = services.vectors
    seed_id = build_playlist(services, [("smells like teen spirit", "nirvana")])[0]
    matches = vectors.nearest("audio", vectors.vector("audio", seed_id), 5, {seed_id})
    track_ids = []
    signals_by_id = {}
    for track_id, score in matches:
        track_ids.append(track_id)
        signals_by_id[track_id] = {"source": "audio", "seed_id": seed_id, "similarity": score}
    state = DialogueState()
    show_tracks(state, track_ids, signals_by_id)

    text = explain(state, services, {"option": "1"})
    check_explanation(text, state.signals[track_ids[0]],
                      "It sounds close to <b>Smells Like Teen Spirit by Nirvana</b>")


def check_lyrics_source(services):
    """The 5 nearest lyrics to 'leaving home', stored as the lyrics search would."""
    print("\nlyrics about 'leaving home' (hand-made signals)")
    dense = services.retriever.fusion.scorers["dense"]
    query = dense.encode_queries(["leaving home"])[0]
    matches = services.vectors.nearest("lyrics", query, 5, set())
    track_ids = []
    signals_by_id = {}
    for track_id, score in matches:
        track_ids.append(track_id)
        signals_by_id[track_id] = {"source": "lyrics", "theme": "leaving home",
                                   "similarity": score}
    state = DialogueState()
    show_tracks(state, track_ids, signals_by_id)

    text = explain(state, services, {"option": "1"})
    check_explanation(text, state.signals[track_ids[0]],
                      "Its lyrics are close to the theme 'leaving home'")
    check("shares the tag" not in text, "a theme has no songs to share tags with")


def check_edge_cases(services):
    """No list yet, no option, a number out of range, a name that is not there."""
    print("\nEdge cases")
    state = DialogueState()
    text = explain(state, services, {"option": "2"})
    check(text.startswith("There is no list"), "no list yet -> 'There is no list'")

    playlist = build_playlist(services, PLAYLISTS["rock"])
    state = DialogueState(playlist=list(playlist))
    handle_recommend(ParsedIntent("RECOMMEND", {}), state, services)

    text = explain(state, services, {})
    check(text.startswith("Which song?"), "no option -> 'Which song?'")
    text = explain(state, services, {"option": "7"})
    check(text.startswith("I could not find '7'"), "'7' -> 'I could not find'")
    text = explain(state, services, {"option": "zzzz"})
    check(text.startswith("I could not find 'zzzz'"), "'zzzz' -> 'I could not find'")


def main():
    services = create_services(use_llm=False)
    check_retriever(services)
    check_recommend(services)
    check_different(services)
    check_critique_source(services)
    check_audio_source(services)
    check_lyrics_source(services)
    check_edge_cases(services)

    timings.sort()
    print("\nms per explanation: median " + str(round(timings[len(timings) // 2], 1))
          + ", max " + str(round(timings[-1], 1)))

    if len(problems) > 0:
        print("\nFAIL: " + str(len(problems)) + " checks failed.")
        sys.exit(1)
    print("\nOK: every check passed.")


if __name__ == "__main__":
    main()
