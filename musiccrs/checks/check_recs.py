"""Check R6 recommendations (T4) on three playlists: rock, jazz and pop.

Run from the repo root (no API key needed, the LLM is not used):
    python -m musiccrs.checks.check_recs

For each playlist it prints the 5 normal and the 5 "something different"
recommendations (name, artist, popularity) and checks that there are 5 songs,
none already in the playlist, and, for "different", none by a playlist artist.
Then it prints the ms per call. Exits with code 1 if a check fails.
"""
import sys
import time

from ..handlers.recs import NUM_RECOMMENDATIONS, handle_recommend, playlist_artists
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

    return problems, ms


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
