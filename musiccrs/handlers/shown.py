"""Remembering the tracks shown to the user (Part 4, T1).

Every list of recommended tracks goes through show_tracks(), so three things are kept
in one place:
- pending_options: "add the first two" (R7) knows what it refers to;
- shown:           a track already shown is never shown again (F1.2);
- signals:         why each track was shown, which "why this song?" (F3) reads.
pick_shown() finds one track of the last list from "2" or a loose name, for the
critiques ("more like the second one") and "why the second one?".
"""
from ..data.db import normalize


def same_signals(track_ids, signals):
    """The same signals for every track of a list, one copy each.

    (["id-a", "id-b"], {"source": "recommend"})
        -> {"id-a": {"source": "recommend"}, "id-b": {"source": "recommend"}}
    Each track gets its own copy, so a later change to one track's signals
    (T7 adds its retriever ranks) does not change the others.
    """
    signals_by_id = {}
    for track_id in track_ids:
        signals_by_id[track_id] = dict(signals)
    return signals_by_id


def remember_tracks(state, track_ids, signals_by_id):
    """Add the tracks to state.shown and store each track's signals in state.signals.

    (["id-a"], {"id-a": {"source": "playlist", "description": "sad songs"}})
        -> "id-a" in state.shown, state.signals["id-a"] = {"source": "playlist", ...}
    A track shown a second time keeps only its newest signals.
    Used alone by R8, whose songs go straight into the playlist (no options to pick from).
    """
    for track_id in track_ids:
        state.shown.add(track_id)
        if track_id in signals_by_id:
            state.signals[track_id] = signals_by_id[track_id]


def show_tracks(state, track_ids, signals_by_id, new_list=True):
    """Remember a list of recommended tracks that is about to be shown.

    1. remember_tracks: shown + signals.
    2. pending_options + pending_kind "recommendation": "add the first two" (R7) works.
    3. last_shown: "more like the second one" and "why the second one?" work,
       even after the options were picked.
    4. new_list=True (R6, sounds like, lyrics) starts a new critique session from this list.
       The critique handler passes new_list=False, so its likes and filters are kept.
    """
    remember_tracks(state, track_ids, signals_by_id)

    state.pending_options = list(track_ids)
    state.pending_kind = "recommendation"
    state.last_shown = list(track_ids)

    if new_list:
        state.critique = {
            "base_ids": list(track_ids),
            "liked": [],
            "disliked": [],
            "filters": [],
        }


def pick_shown(value, state, db):
    """The track ID of one track of the last list shown, from a number or a loose name.

    last_shown = [Numb (Linkin Park), It's My Life (Bon Jovi), Toxic (Britney Spears)]
    "2"           -> the ID of It's My Life        (numbers count from 1)
    "bon jovi"    -> the ID of It's My Life        (part of an artist name)
    "toxic"       -> the ID of Toxic               (part of the title)
    "7", "queen"  -> None                          (no such option)
    With two matches, the first one in the list is taken.
    """
    if value is None:
        return None
    text = str(value).strip()

    # A number: its position in the list.
    if text.isdigit():
        number = int(text)
        if number >= 1 and number <= len(state.last_shown):
            return state.last_shown[number - 1]
        return None

    # A name: the first track whose normalized title or artist contains the text.
    wanted = normalize(text)
    if wanted == "":
        return None
    for track_id in state.last_shown:
        track = db.get(track_id)
        if wanted in normalize(track.name):
            return track_id
        for artist in track.artists:
            if wanted in normalize(artist):
                return track_id
    return None
