"""Playlist handlers: ADD, REMOVE, SHOW, CLEAR (R2), R4 disambiguation, and HELP (R3).

T7, T8 & T12 implementation. Replaces the T2 skeleton.
"""
import html
import numpy as np
import json
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
        anno = Annotation("option", label)
        anno.slot = "option"
        annotations.append(anno)
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
        return Reply(
            text="Added " + describe_track(track) + " to your playlist.",
            dialogue_acts=[_playlist_act(state.playlist, services.db)]
        )

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
    return Reply(
        text=text,
        dialogue_acts=[_playlist_act(state.playlist, services.db)]
    )


def handle_remove(parsed, state, services):
    """Handles removing a track from the playlist by track ID or fuzzy title search."""
    slots = parsed.slots or {}
    track_id = slots.get("track_id") or slots.get("id")
    track_query = slots.get("track") or slots.get("query") or parsed.raw_text

    # 1. Direct match by track_id (e.g., triggered by clicking 'X' in the React frontend panel)
    if track_id and track_id in state.playlist:
        track = services.db.get(track_id)
        t_name = track.name if track else track_id
        state.playlist.remove(track_id)
        return Reply(
            text=f"Removed {t_name} from your playlist.",
            dialogue_acts=[_playlist_act(state.playlist, services.db)]
        )

    # 2. Search for matching track title inside the active playlist
    if track_query:
        for tid in list(state.playlist):
            track = services.db.get(tid)
            if track and (track_query.lower() in track.name.lower() or track_query.strip() == tid):
                state.playlist.remove(tid)
                return Reply(
                    text=f"Removed {track.name} from your playlist.",
                    dialogue_acts=[_playlist_act(state.playlist, services.db)]
                )

    # 3. Track not found in playlist
    return Reply(
        text="That track is not in your playlist.",
        dialogue_acts=[_playlist_act(state.playlist, services.db)]
    )


def handle_clear(parsed, state, services):
    """CLEAR: empty the playlist (R2)."""
    count = len(state.playlist)
    if count == 0:
        return Reply("Your playlist is already empty.")

    state.playlist.clear()
    state.pending_options.clear()
    state.pending_kind = None
    return Reply(
        text="Cleared your playlist (" + str(count) + " songs removed).",
        dialogue_acts=[_playlist_act([], services.db)]
    )

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

def _playlist_act(playlist_ids, db):
    annotations = []
    for tid in playlist_ids:
        track = db.get(tid)
        if track:
            track_data = {
                "id": track.track_id,
                "name": track.name,
                "artist": track.artists[0] if track.artists else "Unknown",
                "duration_ms": getattr(track, "duration_ms", 0) or 0
            }
            anno = Annotation("track", json.dumps(track_data))
            anno.slot = "track"
            anno.slot_address = "track"
            annotations.append(anno)
    return DialogueAct(intent=Intent("PLAYLIST"), annotations=annotations)
