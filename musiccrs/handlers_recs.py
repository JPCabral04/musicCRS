"""Recommendation handlers: RECOMMEND (R6), and later CREATE_PLAYLIST (R8, T9).

R6 reuses the Part 1 FinalRetriever: the playlist plays the role of the tracks
already played in a dataset session.
"""
from retrieval.context import TurnContext


def recommend_context(playlist):
    """The playlist as a Part 1 TurnContext, so FinalRetriever can score it.

    ["id-nirvana", "id-eagles"] ->
        TurnContext(turn_number=3, current_message="",
                    history=(("music", "id-nirvana"), ("music", "id-eagles")),
                    played_track_ids=("id-nirvana", "id-eagles"), ...)

    - played_track_ids: used by same_artist and bpr_sim, and removed from the result.
    - history: one ("music", id) entry per track, so bm25_plus searches their
      names, artists and albums.
    - current_message is empty: the user's words are not a music query here
      ("recommend me something"), so dense returns nothing.
    """
    history = []
    for track_id in playlist:
        history.append(("music", track_id))

    return TurnContext(
        session_id="",
        turn_number=len(playlist) + 1,
        current_message="",
        history=tuple(history),
        played_track_ids=tuple(playlist),
        baseline_query="",
    )
