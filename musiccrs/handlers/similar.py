"""Handlers for audio sound similarity (T6) and lyrics theme search (T8)."""

import html

from ..data.db import base_name
from ..data.resolver import resolve
from ..state import Reply
from .playlist import describe_track, options_act
from .recs import NUM_RECOMMENDATIONS
from .shown import show_tracks


def list_text(title, tracks):
    """The reply text: a title, then the songs as a numbered list.

    "Songs that sound like <b>Smells Like Teen Spirit by Nirvana</b>:", [Track, ...]
    -> "Songs that sound like ...:\n<ol>\n<li>Come As You Are by Nirvana</li>\n...</ol>\n..."
    """
    text = title + "\n<ol>\n"
    for track in tracks:
        text = text + "<li>" + describe_track(track) + "</li>\n"
    text = text + "</ol>\n"
    text = text + "Say 'add the first two', 'more like the third one' or 'why the second one?'."
    return text


def handle_sounds_like(parsed, state, services):
    """F2.1 / T6: songs whose audio (CLAP vector) is closest to one named song.

    "/sounds smells like teen spirit" -> 5 songs nearest to it in the audio space,
    leaving out other versions of the same song.
    """
    track_name = parsed.slots.get("track", "")
    artist_name = parsed.slots.get("artist", "")

    if track_name == "":
        return Reply("Tell me a song, for example '/sounds smells like teen spirit'.")

    # 1. The seed: the best match of the resolver (it ranks the most popular first).
    candidates = resolve(services.db, track_name, artist_name)
    if len(candidates) == 0:
        return Reply("I could not find '" + html.escape(track_name, quote=False)
                     + "' in the catalog.")
    seed_track = candidates[0]
    seed_id = seed_track.track_id

    seed_vec = services.vectors.vector("audio", seed_id)
    if seed_vec is None:
        return Reply("Sorry, I have no audio for " + describe_track(seed_track) + ".")

    # 2. Never show a song again (F1.2), nor one already in the playlist, nor the seed.
    exclude = set(state.shown)
    for track_id in state.playlist:
        exclude.add(track_id)
    exclude.add(seed_id)

    # 3. The 20 nearest, so 5 are left after dropping other versions of the seed.
    nearest_matches = services.vectors.nearest("audio", seed_vec, k=20, exclude_ids=exclude)

    seed_base = base_name(seed_track.name)
    seed_artist = seed_track.artists[0].lower()

    tracks = []
    signals_by_id = {}
    for track_id, score in nearest_matches:
        track = services.db.get(track_id)
        if track is None:
            continue
        # "Smells Like Teen Spirit - Remastered" by Nirvana is the seed again: skip it.
        same_song = base_name(track.name) == seed_base
        same_artist = track.artists[0].lower() == seed_artist
        if same_song and same_artist:
            continue

        tracks.append(track)
        signals_by_id[track_id] = {
            "source": "audio",
            "seed_id": seed_id,
            "seed_name": seed_track.name,
            "similarity": float(score),
        }
        if len(tracks) == NUM_RECOMMENDATIONS:
            break

    if len(tracks) == 0:
        return Reply("Sorry, I could not find new songs that sound like "
                     + describe_track(seed_track) + ".")

    # 4. Remember the list: "add the first two", "why the second one?" and critiques work.
    track_ids = []
    for track in tracks:
        track_ids.append(track.track_id)
    show_tracks(state, track_ids, signals_by_id, new_list=True)

    title = "Songs that sound like <b>" + describe_track(seed_track) + "</b>:"
    return Reply(list_text(title, tracks), [options_act(tracks)])


def handle_lyrics_search(parsed, state, services):
    """F2.2 / T8: songs whose lyrics (Qwen3 vector) are closest to a theme.

    "/about leaving home" -> the theme is encoded like a retrieval query,
    then the 5 nearest lyrics vectors are shown.
    """
    theme = parsed.slots.get("theme", "")
    if theme == "":
        return Reply("Tell me a theme, for example '/about leaving home'.")

    # 1. Encode the theme with the same model as the lyrics vectors.
    dense_scorer = services.retriever.fusion.scorers["dense"]
    query_vec = dense_scorer.encode_queries([theme])[0]

    # 2. Never show a song again (F1.2), nor one already in the playlist.
    exclude = set(state.shown)
    for track_id in state.playlist:
        exclude.add(track_id)

    matches = services.vectors.nearest("lyrics", query_vec, k=NUM_RECOMMENDATIONS,
                                       exclude_ids=exclude)

    tracks = []
    signals_by_id = {}
    for track_id, score in matches:
        track = services.db.get(track_id)
        if track is None:
            continue
        tracks.append(track)
        signals_by_id[track_id] = {"source": "lyrics", "theme": theme, "similarity": float(score)}

    theme_text = html.escape(theme, quote=False)
    if len(tracks) == 0:
        return Reply("Sorry, I could not find new songs about '" + theme_text + "'.")

    # 3. Remember the list, as for sounds like.
    track_ids = []
    for track in tracks:
        track_ids.append(track.track_id)
    show_tracks(state, track_ids, signals_by_id, new_list=True)

    title = "Songs whose lyrics are about <b>" + theme_text + "</b>:"
    return Reply(list_text(title, tracks), [options_act(tracks)])
