"""Playlist handlers: ADD, REMOVE, SHOW, CLEAR (R2), R4 disambiguation, and HELP (R3).

T7, T8 & T12 implementation. Replaces the T2 skeleton.
"""
import html
import numpy as np
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.annotation import Annotation

from ..state import Reply
from ..data.resolver import resolve


def describe_track(track):
    """One line for a track: "Smells Like Teen Spirit by Nirvana".

    Escapes HTML characters ("<", ">", "&") while leaving single and double
    quotes intact (quote=False).
    """
    name = html.escape(track.name, quote=False)
    main_artist = html.escape(track.artists[0] if track.artists else "Unknown", quote=False)
    return name + " by " + main_artist

def _options_act(options):
    """Creates a DialogueAct with OPTIONS annotations for UI quick-reply buttons."""
    annotations = []
    for idx, t in enumerate(options, 1):
        artist = t.artists[0] if t.artists else "Unknown"
        label = f"{idx}. {t.name} — {artist}"
        annotations.append(Annotation("option", label))
    return DialogueAct(intent=Intent("OPTIONS"), annotations=annotations)


def _rank_disambiguation_candidates(candidates, playlist_ids, services):
    """Ranks R4 candidates using popularity and BPR vector / same-artist signals."""
    if not candidates:
        return []

    # Popularity normalized to [0, 1]
    pop_scores = [c.popularity / 93.0 for c in candidates]

    # Check same-artist overlap with the current playlist
    playlist_tracks = [services.db.get(tid) for tid in playlist_ids if services.db.get(tid)]
    playlist_artists = {a for t in playlist_tracks if t for a in t.artists}

    artist_scores = [
        1.0 if any(a in playlist_artists for a in c.artists) else 0.0
        for c in candidates
    ]

    # Calculate BPR vector similarity if tracks and playlist have BPR embeddings
    bpr_scores = [0.0] * len(candidates)
    if playlist_ids and hasattr(services, "bpr_matrix") and services.bpr_matrix is not None:
        try:
            p_indices = [services.track_id_to_idx[tid] for tid in playlist_ids if tid in services.track_id_to_idx]
            if p_indices:
                centroid = np.mean(services.bpr_matrix[p_indices], axis=0)
                for i, c in enumerate(candidates):
                    if c.track_id in services.track_id_to_idx:
                        c_idx = services.track_id_to_idx[c.track_id]
                        vec = services.bpr_matrix[c_idx]
                        norm = np.linalg.norm(centroid) * np.linalg.norm(vec)
                        if norm > 0:
                            bpr_scores[i] = float(np.dot(centroid, vec) / norm)
        except Exception:
            pass

    # Final combined scoring
    scored = []
    for idx, c in enumerate(candidates):
        score = pop_scores[idx] + (1.5 * artist_scores[idx]) + (1.0 * bpr_scores[idx])
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [track for _, track in scored[:5]]

def handle_add(parsed, state, services):
    """ADD: add a track to the playlist (R2), or ask for disambiguation (R4)."""
    raw_track = parsed.slots.get("track")
    raw_artist = parsed.slots.get("artist")

    if not raw_track and not raw_artist:
        return Reply("Which song should I add? For example: add Smells Like Teen Spirit")

    # Resolve loose references using T6 resolver
    candidates = resolve(services.db, raw_track, raw_artist)

    if not candidates:
        safe_track = html.escape(raw_track or "", quote=False)
        if raw_artist:
            safe_artist = html.escape(raw_artist, quote=False)
            return Reply("Sorry, I could not find '" + safe_track + "' by '" + safe_artist + "' in the catalog.")
        return Reply("Sorry, I could not find '" + safe_track + "' in the catalog.")

    # Exactly one match -> Add directly
    if len(candidates) == 1:
        track = candidates[0]
        if track.track_id in state.playlist:
            return Reply(describe_track(track) + " is already in your playlist.")
        
        state.playlist.append(track.track_id)
        return Reply("Added " + describe_track(track) + " to your playlist.")

    # Multiple candidates -> Disambiguation (R4)
    top_candidates = _rank_disambiguation_candidates(candidates, state.playlist, services)
    state.pending_options = [c.track_id for c in top_candidates]
    state.pending_kind = "disambiguation"

    opt_lines = []
    for idx, c in enumerate(top_candidates, 1):
        a_str = html.escape(c.artists[0] if c.artists else "Unknown", quote=False)
        t_str = html.escape(c.name, quote=False)
        opt_lines.append(f"{idx}. <b>{t_str}</b> — {a_str}")

    text = "I found multiple matches. Which one did you mean?<br>" + "<br>".join(opt_lines)
    return Reply(text=text, dialogue_acts=[_options_act(top_candidates)])


def handle_show(parsed, state, services):
    """SHOW: list the current playlist as an HTML ordered list (R2)."""
    if len(state.playlist) == 0:
        return Reply("Your playlist is empty.")

    text = "Your playlist has " + str(len(state.playlist)) + " songs:\n<ol>\n"
    for track_id in state.playlist:
        track = services.db.get(track_id)
        if track:
            text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>"
    return Reply(text)


def handle_remove(parsed, state, services):
    """REMOVE: take a track out of the playlist by ID (/remove) or loose reference (R2)."""
    if "track_id" in parsed.slots:
        track_id = parsed.slots["track_id"]
        if track_id not in state.playlist:
            return Reply("That song is not in your playlist.")
        state.playlist.remove(track_id)
        track = services.db.get(track_id)
        t_name = describe_track(track) if track else "Track"
        return Reply("Removed " + t_name + " from your playlist.")

    raw_track = parsed.slots.get("track")
    raw_artist = parsed.slots.get("artist")

    if not raw_track and not raw_artist:
        return Reply("Which song should I remove? For example: remove Smells Like Teen Spirit")

    current_tracks = [services.db.get(tid) for tid in state.playlist if services.db.get(tid)]
    norm_track = (raw_track or "").lower()
    norm_artist = (raw_artist or "").lower()

    for t in current_tracks:
        if t:
            name_match = norm_track in t.name.lower() if norm_track else True
            artist_match = any(norm_artist in a.lower() for a in t.artists) if norm_artist else True
            if name_match and artist_match and (norm_track or norm_artist):
                state.playlist.remove(t.track_id)
                return Reply("Removed " + describe_track(t) + " from your playlist.")

    candidates = resolve(services.db, raw_track, raw_artist)
    for c in candidates:
        if c.track_id in state.playlist:
            state.playlist.remove(c.track_id)
            return Reply("Removed " + describe_track(c) + " from your playlist.")

    safe_track = html.escape(raw_track or "", quote=False)
    return Reply("'" + safe_track + "' is not in your playlist.")


def handle_clear(parsed, state, services):
    """CLEAR: empty the playlist (R2)."""
    count = len(state.playlist)
    if count == 0:
        return Reply("Your playlist is already empty.")

    state.playlist.clear()
    state.pending_options.clear()
    state.pending_kind = None
    return Reply("Cleared your playlist (" + str(count) + " songs removed).")

def handle_help(parsed, state, services):
    """HELP: explain system capabilities or topic-specific features (R3 - T12)."""
    topic = parsed.slots.get("topic")

    topic_explanations = {
        "add": "<b>Add songs:</b> Type <i>'add Smells Like Teen Spirit'</i> or <i>'add It's My Life by Bon Jovi'</i>.",
        "remove": "<b>Remove songs:</b> Type <i>'remove Smells Like Teen Spirit'</i> or click the remove button in the playlist panel.",
        "show": "<b>Show playlist:</b> Type <i>'show my playlist'</i> or <i>'/list'</i>.",
        "clear": "<b>Clear playlist:</b> Type <i>'clear my playlist'</i> or <i>'/clear'</i>.",
        "questions": "<b>Ask questions:</b> You can ask <i>'who sings Hotel California?'</i> or <i>'when was It's My Life released?'</i>.",
        "recommend": "<b>Get recommendations:</b> Type <i>'recommend something'</i> to get 5 songs based on your playlist.",
        "create_playlist": "<b>Create a playlist:</b> Type <i>'make me a playlist for the gym'</i>.",
        "select": "<b>Select options:</b> Type <i>'add the first two'</i> or <i>'all except the Bon Jovi one'</i>."
    }

    if topic and topic in topic_explanations:
        return Reply(text=topic_explanations[topic])

    full_help = (
        "<b>Here is what I can do for you:</b><br>"
        "• <b>Manage playlist:</b> Add, remove, view, or clear songs.<br>"
        "• <b>Questions:</b> Ask about track artists, release dates, albums, or track counts.<br>"
        "• <b>Recommendations:</b> Ask for recommendations based on your current playlist.<br>"
        "• <b>Smart Selection:</b> Choose options by saying 'the first two', 'all', or 'all except X'."
    )
    return Reply(text=full_help)
