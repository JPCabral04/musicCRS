"""Recommendation handlers: RECOMMEND (R6), and later CREATE_PLAYLIST (R8, T9).

R6 reuses the Part 1 FinalRetriever: the playlist plays the role of the tracks
already played in a dataset session.
"""
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation

from retrieval.context import SessionPolicy, TurnContext

from .handlers_playlist import describe_track
from .state import Reply

# How many songs R6 shows (the spec asks for 3-5).
NUM_RECOMMENDATIONS = 5

_INTENT_OPTIONS = Intent("OPTIONS")


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


def options_act(tracks):
    """The shown songs as one OPTIONS dialogue act (for the UI and the simulator).

    One annotation per song, numbered from 1:
    SlotValueAnnotation("option", "1. Come As You Are — Nirvana")
    """
    annotations = []
    number = 1
    for track in tracks:
        value = str(number) + ". " + track.name + " — " + track.artists[0]
        annotations.append(SlotValueAnnotation("option", value))
        number = number + 1
    return DialogueAct(intent=_INTENT_OPTIONS, annotations=annotations)


def handle_recommend(parsed, state, services):
    """RECOMMEND (R6): 5 songs related to the playlist, none already in it."""
    if len(state.playlist) == 0:
        state.pending_options = []
        state.pending_kind = None
        return Reply("Your playlist is empty, so I have nothing to base recommendations on. "
                     "Add a few songs first, or ask me to make a playlist for you "
                     "(for example: 'make me a playlist for the gym').")

    # Default policy: songs already in the playlist are never recommended.
    ctx = recommend_context(state.playlist)
    policy = SessionPolicy()
    track_ids = services.retriever.retrieve(ctx, NUM_RECOMMENDATIONS, policy)

    if len(track_ids) == 0:
        return Reply("Sorry, I could not find any songs to recommend right now.")

    tracks = []
    for track_id in track_ids:
        tracks.append(services.db.get(track_id))

    # Remember what was shown, so "add the first two" (R7, T11) knows what it refers to.
    state.pending_options = track_ids
    state.pending_kind = "recommendation"

    text = "Based on your playlist, you might like:\n<ol>\n"
    for track in tracks:
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>\n"
    text = text + "Say 'add the first two', 'add all of them' or 'none'."

    return Reply(text, [options_act(tracks)])
