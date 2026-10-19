"""Recommendation handlers: RECOMMEND (R6), and later CREATE_PLAYLIST (R8, T9).

R6 reuses the Part 1 FinalRetriever: the playlist plays the role of the tracks
already played in a dataset session.
"""
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation

from retrieval.context import SessionPolicy, TurnContext

from .data.db import normalize
from .handlers_playlist import describe_track
from .state import Reply

# How many songs R6 shows (the spec asks for 3-5).
NUM_RECOMMENDATIONS = 5

# "Something different": how many candidates to fetch before the playlist's artists
# are filtered out (most of the top ones can be by those artists).
NUM_CANDIDATES_DIFFERENT = 50

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


def playlist_artists(playlist, db):
    """The normalized names of every artist in the playlist.

    [Smells Like Teen Spirit, It's My Life] -> {"nirvana", "bon jovi"}
    """
    artists = set()
    for track_id in playlist:
        track = db.get(track_id)
        for artist in track.artists:
            artists.add(normalize(artist))
    return artists


def drop_playlist_artists(candidate_ids, playlist, db, limit):
    """The first `limit` candidates that share no artist with the playlist.

    Playlist by Nirvana and Bon Jovi: ["Come As You Are" (Nirvana), "Yellow" (Coldplay), ...]
    -> ["Yellow", ...]
    """
    artists_to_avoid = playlist_artists(playlist, db)
    kept = []
    for track_id in candidate_ids:
        track = db.get(track_id)

        shares_an_artist = False
        for artist in track.artists:
            if normalize(artist) in artists_to_avoid:
                shares_an_artist = True

        if not shares_an_artist:
            kept.append(track_id)
        if len(kept) == limit:
            break
    return kept


def handle_recommend(parsed, state, services):
    """RECOMMEND (R6): 5 songs related to the playlist, none already in it."""
    if len(state.playlist) == 0:
        state.pending_options = []
        state.pending_kind = None
        return Reply("Your playlist is empty, so I have nothing to base recommendations on. "
                     "Add a few songs first, or ask me to make a playlist for you "
                     "(for example: 'make me a playlist for the gym').")

    # The parser sets the "different" slot only when it is true
    # ("recommend something different, not the same artists").
    different = False
    if "different" in parsed.slots:
        different = True

    ctx = recommend_context(state.playlist)
    if different:
        # Same-artist list off, then the playlist's artists are left out of the result.
        policy = SessionPolicy(use_same_artist=False)
        candidate_ids = services.retriever.retrieve(ctx, NUM_CANDIDATES_DIFFERENT, policy)
        track_ids = drop_playlist_artists(candidate_ids, state.playlist, services.db,
                                          NUM_RECOMMENDATIONS)
    else:
        # Default policy: songs already in the playlist are never recommended.
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

    if different:
        text = "Something different from the artists in your playlist:\n<ol>\n"
    else:
        text = "Based on your playlist, you might like:\n<ol>\n"
    for track in tracks:
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>\n"
    text = text + "Say 'add the first two', 'add all of them' or 'none'."

    return Reply(text, [options_act(tracks)])
