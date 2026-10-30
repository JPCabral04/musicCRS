"""Handlers for audio sound similarity (T6) and lyrics theme search (T8)."""

from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.annotation import Annotation

from musiccrs.data.resolver import resolve
from musiccrs.handlers.shown import show_tracks
from musiccrs.handlers.recs import options_act


def handle_sounds_like(parsed, state, services):
    """F2.1 / T6: Sound similarity search using CLAP audio vectors."""
    track_name = parsed.slots.get("track", "")
    artist_name = parsed.slots.get("artist", "")

    if not track_name:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[Annotation("text", "Please specify a track to find similar sounding songs.")],
        )

    # 1. Resolve seed track
    candidates = resolve(services.db, track_name, artist_name)
    if not candidates:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[Annotation("text", f"I couldn't find a track matching '{track_name}'.")],
        )

    seed_track = max(candidates, key=lambda t: getattr(t, "popularity", 0))
    seed_id = seed_track.track_id

    # 2. Get audio vector
    seed_vec = services.vectors.vector("audio", seed_id)
    if seed_vec is None:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[
                Annotation("text", f"Sorry, no audio features are available for '{seed_track.name}'.")
            ],
        )

    # 3. Build exclude set
    playlist_ids = set(t.track_id if hasattr(t, "track_id") else t for t in state.playlist)
    exclude = state.shown | playlist_ids | {seed_id}

    # 4. Search nearest in audio space using exclude_ids
    nearest_matches = services.vectors.nearest("audio", seed_vec, k=20, exclude_ids=exclude)

    seed_base_name = seed_track.name.split(" - ")[0].lower()
    seed_artist = seed_track.artists[0].lower() if seed_track.artists else ""

    filtered_ids = []
    signals_by_id = {}

    for tid, score in nearest_matches:
        t_obj = services.db.get(tid)
        if t_obj:
            t_base = t_obj.name.split(" - ")[0].lower()
            t_art = t_obj.artists[0].lower() if t_obj.artists else ""
            if t_base == seed_base_name and t_art == seed_artist:
                continue

        filtered_ids.append(tid)
        signals_by_id[tid] = {
            "source": "audio",
            "seed_id": seed_id,
            "seed_name": seed_track.name,
            "similarity": float(score),
        }
        if len(filtered_ids) == 5:
            break

    if not filtered_ids:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[Annotation("text", f"Could not find similar sounding tracks for '{seed_track.name}'.")],
        )

    # 5. Store state
    show_tracks(state, filtered_ids, signals_by_id, new_list=True)

    # 6. Resolve Track objects for options_act(tracks)
    rec_tracks = [services.db.get(tid) for tid in filtered_ids if services.db.get(tid)]
    return options_act(rec_tracks)


def handle_lyrics_search(parsed, state, services):
    """F2.2 / T8: Lyrics theme search using Qwen3 text embeddings."""
    theme = parsed.slots.get("theme", "")
    if not theme:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[Annotation("text", "Please specify a theme for the lyrics search.")],
        )

    # 1. Encode query
    dense_scorer = services.retriever.fusion.scorers["dense"]
    query_vec = dense_scorer.encode_queries([theme])[0]

    # 2. Build exclude set
    playlist_ids = set(t.track_id if hasattr(t, "track_id") else t for t in state.playlist)
    exclude = state.shown | playlist_ids

    # 3. Retrieve matches using exclude_ids
    matches = services.vectors.nearest("lyrics", query_vec, k=5, exclude_ids=exclude)

    if not matches:
        return DialogueAct(
            intent=Intent("RECOMMEND"),
            annotations=[Annotation("text", f"No tracks found matching the lyrics theme '{theme}'.")],
        )

    matched_ids = [tid for tid, _ in matches]
    signals_by_id = {
        tid: {"source": "lyrics", "theme": theme, "similarity": float(score)}
        for tid, score in matches
    }

    # 4. Store state
    show_tracks(state, matched_ids, signals_by_id, new_list=True)

    # 5. Resolve Track objects for options_act(tracks)
    rec_tracks = [services.db.get(tid) for tid in matched_ids if services.db.get(tid)]
    return options_act(rec_tracks)