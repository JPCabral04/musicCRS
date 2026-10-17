"""Playlist handlers: ADD, REMOVE, SHOW, CLEAR (R2).

T2 version: exact-name lookup with TrackDB.find_by_name, most popular match first.
Alejandro takes this file over in T7 (track resolver, refusal messages) and T8
(disambiguation when several tracks match). The function signatures stay the same.
"""
import html

from .state import Reply


def describe_track(track):
    """One line for a track: "Smells Like Teen Spirit by Nirvana".

    The chat renders replies as HTML, so names are escaped: "<" -> "&lt;", "&" -> "&amp;".
    """
    name = html.escape(track.name)
    main_artist = html.escape(track.artists[0])
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
        safe_track = html.escape(track_text)
        if artist_text is None:
            return Reply("Sorry, I could not find '" + safe_track + "' in the catalog.")
        safe_artist = html.escape(artist_text)
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
