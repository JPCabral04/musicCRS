"""Playlist handlers: ADD, REMOVE, SHOW, CLEAR (R2).

T2 version: exact-name lookup with TrackDB.find_by_name, most popular match first.
Alejandro takes this file over in T7 (track resolver, refusal messages) and T8
(disambiguation when several tracks match). The function signatures stay the same.
"""
import html

from ..state import Reply


def describe_track(track):
    """One line for a track: "Smells Like Teen Spirit by Nirvana".

    The chat renders replies as HTML, so "<", ">" and "&" are escaped:
    "Simon & Garfunkel" -> "Simon &amp; Garfunkel". quote=False keeps "It's" as it is
    (quotes only matter inside HTML attributes, and the simulator reads the raw text).
    """
    name = html.escape(track.name, quote=False)
    main_artist = html.escape(track.artists[0], quote=False)
    return name + " by " + main_artist


def handle_add(parsed, state, services):
    """ADD: put a track at the end of the playlist."""
    if "track" not in parsed.slots:
        return Reply("Which song should I add? For example: /add nirvana: smells like teen spirit")
    track_text = parsed.slots["track"]

    artist_text = None
    if "artist" in parsed.slots:
        artist_text = parsed.slots["artist"]

    # Exact match on the normalized name (and artist). Most popular first.
    matches = services.db.find_by_name(track_text, artist_text)
    if len(matches) == 0:
        # The user's own text goes back into HTML, so escape it too.
        safe_track = html.escape(track_text, quote=False)
        if artist_text is None:
            return Reply("Sorry, I could not find '" + safe_track + "' in the catalog.")
        safe_artist = html.escape(artist_text, quote=False)
        return Reply("Sorry, I could not find '" + safe_track + "' by '"
                     + safe_artist + "' in the catalog.")

    # Several matches: take the most popular one (T8 will ask the user instead).
    track = matches[0]

    if track.track_id in state.playlist:
        return Reply(describe_track(track) + " is already in your playlist.")

    state.playlist.append(track.track_id)
    return Reply("Added " + describe_track(track) + " to your playlist.")


def handle_show(parsed, state, services):
    """SHOW: list the playlist as a numbered HTML list (the chat renders HTML)."""
    if len(state.playlist) == 0:
        return Reply("Your playlist is empty.")

    text = "Your playlist has " + str(len(state.playlist)) + " songs:\n<ol>\n"
    for track_id in state.playlist:
        track = services.db.get(track_id)
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>"
    return Reply(text)


def handle_remove(parsed, state, services):
    """REMOVE: take a track out of the playlist, by ID (/remove) or by name (/del)."""
    # Case 1: "/remove <track_id>" from the remove button of the playlist panel.
    if "track_id" in parsed.slots:
        track_id = parsed.slots["track_id"]
        if track_id not in state.playlist:
            return Reply("That song is not in your playlist.")
        state.playlist.remove(track_id)
        track = services.db.get(track_id)
        return Reply("Removed " + describe_track(track) + " from your playlist.")

    # Case 2: "/del [artist]: [track]", by name.
    if "track" not in parsed.slots:
        return Reply("Which song should I remove? For example: /del nirvana: smells like teen spirit")
    track_text = parsed.slots["track"]

    artist_text = None
    if "artist" in parsed.slots:
        artist_text = parsed.slots["artist"]

    # Look for the first matching track that is in the playlist
    # (the most popular match may not be the version the user added).
    matches = services.db.find_by_name(track_text, artist_text)
    for track in matches:
        if track.track_id in state.playlist:
            state.playlist.remove(track.track_id)
            return Reply("Removed " + describe_track(track) + " from your playlist.")

    safe_track = html.escape(track_text, quote=False)
    return Reply("'" + safe_track + "' is not in your playlist.")


def handle_clear(parsed, state, services):
    """CLEAR: empty the playlist."""
    count = len(state.playlist)
    if count == 0:
        return Reply("Your playlist is already empty.")

    state.playlist = []
    return Reply("Cleared your playlist (" + str(count) + " songs removed).")
