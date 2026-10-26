"""Check R6 recommendations (T4) on five playlists: rock, jazz, pop, mixed and one artist.

Run from the repo root (no API key needed, the LLM is not used):
    python -m musiccrs.checks.check_recs

For each playlist it prints the 5 normal and the 5 "something different"
recommendations (name, artist, popularity) and checks that there are 5 songs,
none already in the playlist, no main artist more often than the per-artist limit,
and, for "different", none by a playlist artist. Then "songs like Numb by Linkin Park"
(a named song instead of the playlist), and a named song that is not in the catalog.
Then it prints the ms per call. Exits with code 1 if a check fails.
"""
import sys
import time

from ..handlers.recs import (MAX_PER_ARTIST, NUM_RECOMMENDATIONS, handle_recommend,
                             main_artist_key, per_artist_limit, playlist_artists)
from ..data.db import normalize
from ..musiccrs import create_services
from ..state import DialogueState, ParsedIntent

# (track name, artist) pairs, all checked to be in the catalog on Oct 19.
PLAYLISTS = {
    "rock": [("smells like teen spirit", "nirvana"),
             ("hotel california", "eagles"),
             ("its my life", "bon jovi")],
    "jazz": [("take five", "the dave brubeck quartet"),
             ("my favorite things", "john coltrane"),
             ("what a wonderful world", "louis armstrong")],
    "pop": [("shape of you", "ed sheeran"),
            ("toxic", "britney spears"),
            ("wrecking ball", "miley cyrus")],
    # Three songs by one artist next to others: at most 2 Linkin Park songs may come back.
    "mixed": [("yellow", "coldplay"),
              ("numb", "linkin park"),
              ("in the end", "linkin park"),
              ("faint", "linkin park"),
              ("bank account", "21 savage")],
    # Only one artist: more songs by that artist are allowed.
    "one artist": [("yellow", "coldplay"),
                   ("viva la vida", "coldplay")],
}


def build_playlist(services, pairs):
    """Track IDs for the (name, artist) pairs, most popular match of each."""
    playlist = []
    for name, artist in pairs:
        matches = services.db.find_by_name(name, artist)
        if len(matches) == 0:
            print("Not in the catalog: " + name + " by " + artist)
            sys.exit(1)
        playlist.append(matches[0].track_id)
    return playlist


def check_recommendations(services, playlist, slots):
    """Runs handle_recommend once, prints the songs and returns (problems, ms)."""
    state = DialogueState(playlist=list(playlist))
    parsed = ParsedIntent("RECOMMEND", slots)

    start = time.perf_counter()
    handle_recommend(parsed, state, services)
    ms = 1000 * (time.perf_counter() - start)

    # The handler stores the shown songs in pending_options.
    track_ids = state.pending_options
    artists_to_avoid = playlist_artists(playlist, services.db)

    problems = []
    if len(track_ids) != NUM_RECOMMENDATIONS:
        problems.append("got " + str(len(track_ids)) + " songs")

    for track_id in track_ids:
        track = services.db.get(track_id)
        print("    " + track.name + " — " + track.artists[0]
              + " (popularity " + str(track.popularity) + ")")

        if track_id in playlist:
            problems.append(track.name + " is already in the playlist")

        if "different" in slots:
            for artist in track.artists:
                if normalize(artist) in artists_to_avoid:
                    problems.append(track.name + " is by a playlist artist")

    # No main artist may take more places than the handler allows.
    if "different" in slots:
        max_per_artist = MAX_PER_ARTIST
    else:
        max_per_artist = per_artist_limit(playlist, services.db)
    counts = {}
    for track_id in track_ids:
        key = main_artist_key(services.db.get(track_id))
        if key not in counts:
            counts[key] = 0
        counts[key] = counts[key] + 1
    for key in counts:
        if counts[key] > max_per_artist:
            problems.append(str(counts[key]) + " songs by " + key
                            + " (limit " + str(max_per_artist) + ")")

    return problems, ms


def check_named_seed(services):
    """'songs like Numb by Linkin Park' with a playlist that holds one Linkin Park song.

    Returns the problems: 5 songs are expected, neither Numb nor the playlist song among them.
    """
    playlist = build_playlist(services, [("in the end", "linkin park")])
    state = DialogueState(playlist=list(playlist))
    parsed = ParsedIntent("RECOMMEND", {"track": "numb", "artist": "linkin park"})
    reply = handle_recommend(parsed, state, services)

    print("\nSONGS LIKE Numb by Linkin Park (playlist: In the End):")
    numb = services.db.find_by_name("numb", "linkin park")[0]
    problems = []
    if len(state.pending_options) != NUM_RECOMMENDATIONS:
        problems.append("songs like Numb: got " + str(len(state.pending_options)) + " songs")
    for track_id in state.pending_options:
        track = services.db.get(track_id)
        print("    " + track.name + " — " + track.artists[0])
        if track_id == numb.track_id or track_id in playlist:
            problems.append("songs like Numb: " + track.name + " should not be recommended")
    if "Songs like <b>Numb" not in reply.text:
        problems.append("songs like Numb: the reply does not name the song")

    # A song that is not in the catalog gives a clear answer and no options.
    state = DialogueState()
    parsed = ParsedIntent("RECOMMEND", {"track": "always", "artist": "bon jovi"})
    reply = handle_recommend(parsed, state, services)
    if "could not find" not in reply.text or len(state.pending_options) != 0:
        problems.append("songs like Always by Bon Jovi (not in the catalog): no clear refusal")
    return problems


def main():
    services = create_services(use_llm=False)

    all_problems = []
    all_ms = []
    for genre in PLAYLISTS:
        playlist = build_playlist(services, PLAYLISTS[genre])

        print("\n" + genre.upper() + " playlist:")
        for track_id in playlist:
            track = services.db.get(track_id)
            print("    " + track.name + " — " + track.artists[0])

        print("  recommend:")
        problems, ms = check_recommendations(services, playlist, {})
        all_problems.extend(problems)
        all_ms.append(ms)

        print("  recommend something different:")
        problems, ms = check_recommendations(services, playlist, {"different": True})
        all_problems.extend(problems)
        all_ms.append(ms)

    all_problems.extend(check_named_seed(services))

    print("\nms per call: mean " + str(round(sum(all_ms) / len(all_ms)))
          + ", max " + str(round(max(all_ms))))

    if len(all_problems) > 0:
        print("FAIL:")
        for problem in all_problems:
            print("  " + problem)
        sys.exit(1)
    print("OK: every playlist got " + str(NUM_RECOMMENDATIONS) + " new songs.")


if __name__ == "__main__":
    main()
