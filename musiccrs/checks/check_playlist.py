"""Check R8 playlists from a description (T9): the length rule and four descriptions.

Run from the repo root:
    python -m musiccrs.checks.check_playlist

The length rule cases always run (no LLM, no DB). Then each description is sent to
handle_create_playlist with the rock playlist of check_recs already in the state, and the
check prints the query, the minutes, the songs and the ms per call. It checks that each
playlist has 8-25 songs, no repeats, replaced the old one and cleared the pending options,
and (only with LLM_API_KEY) that the descriptions got at least 2 different lengths.
Exits with code 1 if a check fails.
"""
import sys
import time

from ..handlers.recs import MAX_LENGTH, MIN_LENGTH, handle_create_playlist, plan_playlist, playlist_length
from ..musiccrs import create_services
from ..state import DialogueState, ParsedIntent
from .check_recs import PLAYLISTS, build_playlist

# (minutes, expected songs). The rule: round(minutes * 60 / 239.7), clamped to 8-25.
LENGTH_CASES = [
    (5, 8),
    (45, 11),
    (60, 15),
    (90, 23),
    (180, 25),
]

# The spec's two examples, plus a short and a long occasion (different lengths expected).
DESCRIPTIONS = [
    "sad love songs",
    "energetic music for a gym session",
    "a few songs for a short coffee break",
    "music for a long road trip",
]


def check_lengths():
    """Runs the length rule cases and returns the problems found."""
    problems = []
    for minutes, expected in LENGTH_CASES:
        got = playlist_length(minutes)
        print("  " + str(minutes) + " min -> " + str(got) + " songs")
        if got != expected:
            problems.append(str(minutes) + " min gave " + str(got) + ", expected " + str(expected))
    return problems


def check_description(services, old_playlist, description):
    """Runs handle_create_playlist once, prints the playlist and returns (problems, length, ms)."""
    # Only to print what the LLM planned; the handler makes the same call again
    # (temperature 0, so the answer is the same).
    query, minutes = plan_playlist(description, services.llm)
    print("  query: '" + query + "', " + str(minutes) + " min -> "
          + str(playlist_length(minutes)) + " songs")

    # A state with an old playlist and old options, to see both being replaced.
    state = DialogueState(playlist=list(old_playlist))
    state.pending_options = list(old_playlist)
    state.pending_kind = "recommendation"
    parsed = ParsedIntent("CREATE_PLAYLIST", {"description": description})

    start = time.perf_counter()
    reply = handle_create_playlist(parsed, state, services)
    ms = 1000 * (time.perf_counter() - start)

    for track_id in state.playlist:
        track = services.db.get(track_id)
        print("    " + track.name + " — " + track.artists[0])

    problems = []
    length = len(state.playlist)
    if length < MIN_LENGTH or length > MAX_LENGTH:
        problems.append(description + ": " + str(length) + " songs")

    seen = []
    for track_id in state.playlist:
        if track_id in seen:
            problems.append(description + ": a song is in the playlist twice")
        seen.append(track_id)

    replaced_note = "replaced your previous playlist of " + str(len(old_playlist)) + " songs"
    if replaced_note not in reply.text:
        problems.append(description + ": the reply does not say the old playlist was replaced")

    if len(state.pending_options) > 0 or state.pending_kind is not None:
        problems.append(description + ": the old pending options were not cleared")

    return problems, length, ms


def main():
    all_problems = []

    print("Length rule:")
    all_problems.extend(check_lengths())

    services = create_services()
    if services.llm is None:
        print("\nNo LLM_API_KEY: every description uses the fallback "
              "(the description as the query, 45 minutes).")

    old_playlist = build_playlist(services, PLAYLISTS["rock"])

    lengths = []
    all_ms = []
    for description in DESCRIPTIONS:
        print("\n'" + description + "':")
        problems, length, ms = check_description(services, old_playlist, description)
        all_problems.extend(problems)
        lengths.append(length)
        all_ms.append(ms)

    # Different occasions must give different lengths (only the LLM gives the minutes).
    if services.llm is not None:
        different_lengths = []
        for length in lengths:
            if length not in different_lengths:
                different_lengths.append(length)
        if len(different_lengths) < 2:
            all_problems.append("every description got the same length")

    print("\nlengths: " + str(lengths))
    print("ms per call (plan LLM call + retrieval): mean " + str(round(sum(all_ms) / len(all_ms)))
          + ", max " + str(round(max(all_ms))))

    if len(all_problems) > 0:
        print("FAIL:")
        for problem in all_problems:
            print("  " + problem)
        sys.exit(1)
    print("OK: " + str(len(DESCRIPTIONS)) + " playlists of 8-25 songs, each replacing the old one.")


if __name__ == "__main__":
    main()
