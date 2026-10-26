"""Playlist handlers: ADD, REMOVE, SHOW, CLEAR (R2), R4 disambiguation, and HELP (R3).

T7, T8 and T12 by Alejandro (Oct 19-21). Adapted by JP (Oct 21): REMOVE by title and/or
artist with normalize (it crashed without a track slot), the BPR signal of the R4 ranking
read from the Part 1 retriever, and the PLAYLIST act left to the agent (musiccrs.py), which
sends it once whenever the playlist changed.

Text replies are HTML (the chat renders them), so names go through html.escape.
"""
import html

import numpy as np
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation

from ..data.db import base_name, normalize
from ..data.resolver import artist_key, resolve
from ..state import Reply

_INTENT_OPTIONS = Intent("OPTIONS")

# R4: how many same-name choices are shown.
NUM_OPTIONS = 5

# R4 ranking: score = popularity / MAX_POPULARITY
#                   + SAME_ARTIST_WEIGHT * (shares an artist with the playlist)
#                   + BPR_WEIGHT * (BPR cosine with the playlist centroid)
MAX_POPULARITY = 93.0      # the highest popularity in the catalog
SAME_ARTIST_WEIGHT = 1.5
BPR_WEIGHT = 1.0

# R3: one explanation per HELP topic (the topics the parser may give, see HELP_TOPICS).
TOPIC_EXPLANATIONS = {
    "add": "<b>Add songs:</b> type <i>'add Smells Like Teen Spirit'</i> or "
           "<i>'add It's My Life by Bon Jovi'</i>, or use the box above the playlist. "
           "If several songs have that name, I show them and you pick one.",
    "remove": "<b>Remove songs:</b> type <i>'remove Smells Like Teen Spirit'</i> or "
              "<i>'remove the Bon Jovi song'</i>, or click the × next to the song in the playlist.",
    "show": "<b>Show playlist:</b> type <i>'show my playlist'</i> or <i>'/list'</i>. "
            "The playlist is also always shown next to the chat.",
    "clear": "<b>Clear playlist:</b> type <i>'clear my playlist'</i> or <i>'/clear'</i>, "
             "or click 'Clear Playlist'.",
    "questions": "<b>Ask questions:</b> about a song (<i>'who sings Hotel California?'</i>, "
                 "<i>'what album is Toxic on?'</i>, <i>'when was It's My Life released?'</i>, "
                 "<i>'how long is Bad Medicine?'</i>) or an artist (<i>'how many songs does "
                 "Queen have?'</i>, <i>'what is Nirvana's most popular song?'</i>, "
                 "<i>'which albums does Adele have?'</i>, <i>'what genre is Metallica?'</i>).",
    "recommend": "<b>Get recommendations:</b> type <i>'recommend something'</i> to get 5 songs "
                 "like the ones in your playlist, <i>'something different'</i> for other artists, "
                 "or <i>'songs like Numb by Linkin Park'</i> for songs like one song or artist.",
    "create_playlist": "<b>Create a playlist:</b> describe it, for example "
                       "<i>'make me a playlist of sad love songs'</i> or <i>'music for the gym'</i>. "
                       "I choose the length from the description.",
    "select": "<b>Choose from a list:</b> click a button, or type <i>'the first two'</i>, "
              "<i>'all of them'</i>, <i>'none'</i> or <i>'all except the Bon Jovi one'</i>.",
}

# R3: the order of the topics in the full help.
HELP_ORDER = ("add", "remove", "show", "clear", "questions", "recommend",
              "create_playlist", "select")


def describe_track(track):
    """One line for a track: "Smells Like Teen Spirit by Nirvana".

    Escapes HTML characters ("<", ">", "&") while leaving single and double
    quotes intact (quote=False).
    """
    name = html.escape(track.name, quote=False)
    main_artist = html.escape(track.artists[0], quote=False)
    return name + " by " + main_artist


def options_act(tracks):
    """The shown songs as one OPTIONS dialogue act (for the UI buttons and the simulator).

    Used by R4 here and by R6/R8 in recs.py. One annotation per song, numbered from 1:
    SlotValueAnnotation("option", "1. Come As You Are — Nirvana")
    """
    annotations = []
    number = 1
    for track in tracks:
        value = str(number) + ". " + track.name + " — " + track.artists[0]
        annotations.append(SlotValueAnnotation("option", value))
        number = number + 1
    return DialogueAct(intent=_INTENT_OPTIONS, annotations=annotations)


def describe_version(track):
    """A track with its album and year, so two versions of one song can be told apart.

    Yellow (Coldplay, album Parachutes, 2000-07-10) -> "Yellow by Coldplay <i>(Parachutes, 2000)</i>"
    no album and no date                             -> "Yellow by Coldplay"
    """
    details = []
    if track.album != "":
        details.append(html.escape(track.album, quote=False))
    if len(track.release_date) >= 4:
        details.append(track.release_date[:4])

    text = describe_track(track)
    if len(details) > 0:
        text = text + " <i>(" + ", ".join(details) + ")</i>"
    return text


def track_list_html(tracks):
    """Songs as a numbered HTML list, with album and year, for replies that ask "which one?"."""
    text = "<ol>\n"
    for track in tracks:
        text = text + "<li>" + describe_version(track) + "</li>\n"
    return text + "</ol>"


def bpr_scorer(services):
    """The Part 1 BPR scorer inside the retriever, or None (the checks run without a retriever)."""
    if services.retriever is None:
        return None
    scorers = services.retriever.fusion.scorers
    if "bpr_sim" not in scorers:
        return None
    return scorers["bpr_sim"]


def playlist_centroid(playlist_ids, scorer):
    """The mean BPR vector of the playlist songs that have one, at unit length; None if none."""
    vectors = []
    for track_id in playlist_ids:
        if track_id in scorer.tid_to_idx:
            row = scorer.tid_to_idx[track_id]
            if scorer.has_vector[row]:
                vectors.append(scorer.matrix[row])
    if len(vectors) == 0:
        return None

    centroid = np.mean(vectors, axis=0)
    length = np.linalg.norm(centroid)
    if length == 0:
        return None
    return centroid / length


def bpr_similarity(track_id, centroid, scorer):
    """Cosine between a track's BPR vector and the playlist centroid (0.0 when unknown).

    The rows of scorer.matrix already have length 1, so the dot product is the cosine.
    """
    if centroid is None:
        return 0.0
    if track_id not in scorer.tid_to_idx:
        return 0.0
    row = scorer.tid_to_idx[track_id]
    if not scorer.has_vector[row]:
        return 0.0
    return float(np.dot(scorer.matrix[row], centroid))


def rank_options(candidates, playlist_ids, services):
    """R4: the NUM_OPTIONS best candidates, by popularity and similarity to the playlist.

    Empty playlist -> popularity only ("add Love": the most popular "Love" songs first).
    Playlist with Nirvana -> a Nirvana candidate gets +1.5 and comes first.
    """
    playlist_artist_keys = []
    for track_id in playlist_ids:
        track = services.db.get(track_id)
        for name in track.artists:
            playlist_artist_keys.append(artist_key(name))

    scorer = bpr_scorer(services)
    centroid = None
    if scorer is not None:
        centroid = playlist_centroid(playlist_ids, scorer)

    # (score, position) pairs: sorting them never compares two Track objects.
    scored = []
    position = 0
    for candidate in candidates:
        score = candidate.popularity / MAX_POPULARITY

        same_artist = False
        for name in candidate.artists:
            if artist_key(name) in playlist_artist_keys:
                same_artist = True
        if same_artist:
            score = score + SAME_ARTIST_WEIGHT

        if scorer is not None:
            score = score + BPR_WEIGHT * bpr_similarity(candidate.track_id, centroid, scorer)

        scored.append((score, position))
        position = position + 1

    scored.sort(reverse=True)

    best = []
    for score, position in scored[:NUM_OPTIONS]:
        best.append(candidates[position])
    return best


def handle_add(parsed, state, services):
    """ADD: add a track to the playlist (R2), or ask which one when several match (R4)."""
    track_name = parsed.slots.get("track")
    artist = parsed.slots.get("artist")

    if track_name is None and artist is None:
        return Reply("Which song should I add? For example: add Smells Like Teen Spirit")

    # T6 resolver: exact normalized match first, then typos; keeps the artist if given.
    candidates = resolve(services.db, track_name, artist)

    if len(candidates) == 0:
        if track_name is None:
            safe_artist = html.escape(artist, quote=False)
            return Reply("Sorry, I could not find any songs by '" + safe_artist + "' in the catalog.")
        safe_track = html.escape(track_name, quote=False)
        if artist is not None:
            safe_artist = html.escape(artist, quote=False)
            return Reply("Sorry, I could not find '" + safe_track + "' by '" + safe_artist
                         + "' in the catalog.")
        return Reply("Sorry, I could not find '" + safe_track + "' in the catalog.")

    # Exactly one match: add it directly.
    if len(candidates) == 1:
        track = candidates[0]
        if track.track_id in state.playlist:
            return Reply(describe_track(track) + " is already in your playlist.")
        state.playlist.append(track.track_id)
        return Reply("Added " + describe_track(track) + " to your playlist.")

    # Several matches: show the best ones and let the user pick (R4, chosen with SELECT in T11).
    options = rank_options(candidates, state.playlist, services)
    state.pending_options = []
    for track in options:
        state.pending_options.append(track.track_id)
    state.pending_kind = "disambiguation"

    if track_name is not None:
        intro = "I found several songs called '" + html.escape(track_name, quote=False) + "'."
    else:
        intro = "Here are some songs by '" + html.escape(artist, quote=False) + "'."
    text = (intro + " Which one do you mean? Click it, or say for example 'the second one'.\n"
            + track_list_html(options))
    return Reply(text, [options_act(options)])


def name_matches(name, track):
    """True if `name` refers to this playlist track: same normalized or base name, or part of it.

    ("bad medicine", Bad Medicine)                   -> True
    ("hotel california", "Hotel California - 2013 Remaster") -> True
    ("teen spirit", Smells Like Teen Spirit)         -> True (part of the title)
    """
    wanted = normalize(name)
    if wanted == "":
        return False
    full = normalize(track.name)
    if wanted == full:
        return True
    if wanted == base_name(track.name):
        return True
    if wanted in full:
        return True
    return False


def artist_matches(artist, track):
    """True if one of the track's artists is `artist` ("the eagles" matches "Eagles")."""
    wanted = artist_key(artist)
    for name in track.artists:
        if artist_key(name) == wanted:
            return True
    return False


def handle_remove(parsed, state, services):
    """REMOVE: remove a track by its ID (the × button), by title, by artist, or by both (R2).

    "/remove <id>"              -> that track
    "remove bad medicine"       -> the playlist track with that title
    "remove the Queen song"     -> the only Queen track in the playlist
    two Queen tracks            -> asks which one
    """
    # 1. By ID, sent by the remove button of the playlist panel.
    if "track_id" in parsed.slots:
        track_id = parsed.slots["track_id"]
        if track_id not in state.playlist:
            return Reply("That song is not in your playlist.")
        track = services.db.get(track_id)
        state.playlist.remove(track_id)
        return Reply("Removed " + describe_track(track) + " from your playlist.")

    track_name = parsed.slots.get("track")
    artist = parsed.slots.get("artist")
    if track_name is None and artist is None:
        return Reply("Which song should I remove? For example: remove Bad Medicine")

    if len(state.playlist) == 0:
        return Reply("Your playlist is empty.")

    # 2. The playlist tracks that match the title and/or the artist.
    matches = []
    for track_id in state.playlist:
        track = services.db.get(track_id)
        if track_name is not None and not name_matches(track_name, track):
            continue
        if artist is not None and not artist_matches(artist, track):
            continue
        matches.append(track)

    if len(matches) == 0:
        what = ""
        if track_name is not None:
            what = "'" + html.escape(track_name, quote=False) + "'"
        if artist is not None:
            if what != "":
                what = what + " by "
            what = what + "'" + html.escape(artist, quote=False) + "'"
        return Reply(what + " is not in your playlist.")

    if len(matches) > 1:
        return Reply("Several songs in your playlist match:\n" + track_list_html(matches)
                     + "\nWhich one should I remove? Say its title, for example 'remove "
                     + html.escape(matches[0].name, quote=False) + "'.")

    track = matches[0]
    state.playlist.remove(track.track_id)
    return Reply("Removed " + describe_track(track) + " from your playlist.")


def handle_show(parsed, state, services):
    """SHOW: list the current playlist as an HTML ordered list (R2)."""
    count = len(state.playlist)
    if count == 0:
        return Reply("Your playlist is empty.")

    if count == 1:
        text = "Your playlist has 1 song:\n<ol>\n"
    else:
        text = "Your playlist has " + str(count) + " songs:\n<ol>\n"
    for track_id in state.playlist:
        track = services.db.get(track_id)
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>"
    return Reply(text)


def handle_clear(parsed, state, services):
    """CLEAR: empty the playlist (R2)."""
    count = len(state.playlist)
    if count == 0:
        return Reply("Your playlist is already empty.")

    state.playlist.clear()
    state.pending_options.clear()
    state.pending_kind = None
    if count == 1:
        return Reply("Cleared your playlist (1 song removed).")
    return Reply("Cleared your playlist (" + str(count) + " songs removed).")


def handle_help(parsed, state, services):
    """HELP: explain what the system can do, or one feature (R3, T12).

    "what can you do?"         -> every feature, with examples
    "how do I remove a song?"  -> topic "remove" -> only that explanation
    """
    topic = parsed.slots.get("topic")
    if topic is not None and topic in TOPIC_EXPLANATIONS:
        return Reply(TOPIC_EXPLANATIONS[topic])

    text = "<b>Here is what I can do for you:</b><br>"
    for name in HELP_ORDER:
        text = text + "• " + TOPIC_EXPLANATIONS[name] + "<br>"
    text = text + "You can also type /help at any time."
    return Reply(text)
