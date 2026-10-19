"""
QA Handlers (T10)
Answers natural language questions about tracks and artists (R5) using
the database directly (no LLM calls required for generating the answer).
"""

import html
from ..state import Reply
from ..data.resolver import resolve


def _format_duration(duration_ms: int) -> str:
    """Converts milliseconds into a user-friendly 'M:SS' format."""
    if not duration_ms or duration_ms <= 0:
        return "unknown duration"
    total_seconds = int(duration_ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def handle_ask_track(parsed, state, services) -> Reply:
    """
    Handles questions about tracks (R5): artist, album, release_year, duration.
    """
    raw_track = parsed.slots.get("track")
    raw_artist = parsed.slots.get("artist")
    question = parsed.slots.get("question")

    if not raw_track and not raw_artist:
        return Reply("Which track are you asking about?")

    candidates = resolve(services.db, raw_track, raw_artist)
    if not candidates:
        safe_t = html.escape(raw_track or "", quote=False)
        return Reply(f"I couldn't find '{safe_t}' in the database.")

    # Pick the top resolved track
    track = candidates[0]
    t_name = html.escape(track.name, quote=False)
    main_artist = html.escape(track.artists[0] if track.artists else "Unknown", quote=False)

    if question == "artist":
        artists_str = ", ".join([html.escape(a, quote=False) for a in track.artists])
        return Reply(f"<b>{t_name}</b> is performed by <b>{artists_str}</b>.")

    elif question == "album":
        album = html.escape(track.album or "Unknown Album", quote=False)
        return Reply(f"<b>{t_name}</b> by {main_artist} is on the album <b>'{album}'</b>.")

    elif question == "release_year":
        date = track.release_date
        year = date[:4] if date and len(date) >= 4 else "unknown"
        if year != "unknown":
            return Reply(f"<b>{t_name}</b> by {main_artist} was released in <b>{year}</b>.")
        return Reply(f"I don't have the release year for <b>{t_name}</b> by {main_artist}.")

    elif question == "duration":
        dur = _format_duration(track.duration_ms)
        return Reply(f"<b>{t_name}</b> by {main_artist} is <b>{dur}</b> long.")

    # General fallback if question slot was unmapped or missing
    dur = _format_duration(track.duration_ms)
    year = track.release_date[:4] if track.release_date and len(track.release_date) >= 4 else "unknown"
    album = html.escape(track.album or "Unknown", quote=False)
    return Reply(
        f"<b>{t_name}</b> by <b>{main_artist}</b> (Album: <i>{album}</i>, Year: {year}, Duration: {dur})."
    )


def handle_ask_artist(parsed, state, services) -> Reply:
    """
    Handles questions about artists (R5): track_count, top_track, albums, genres.
    """
    raw_artist = parsed.slots.get("artist") or parsed.slots.get("track")
    question = parsed.slots.get("question")

    if not raw_artist:
        return Reply("Which artist are you asking about?")

    tracks = services.db.artist_tracks(raw_artist)
    if not tracks:
        safe_a = html.escape(raw_artist, quote=False)
        return Reply(f"I couldn't find any tracks by '{safe_a}' in the catalog.")

    main_artist = html.escape(tracks[0].artists[0] if tracks[0].artists else raw_artist, quote=False)

    if question == "track_count":
        count = len(tracks)
        return Reply(f"We have <b>{count}</b> track{'s' if count != 1 else ''} by <b>{main_artist}</b> in the catalog.")

    elif question == "top_track":
        # Tracks from db.artist_tracks or sorted by popularity
        top_t = max(tracks, key=lambda x: x.popularity)
        t_name = html.escape(top_t.name, quote=False)
        return Reply(f"The most popular track by <b>{main_artist}</b> in our catalog is <b>{t_name}</b>.")

    elif question == "albums":
        albums = list({t.album for t in tracks if t.album})
        if not albums:
            return Reply(f"I couldn't find album information for <b>{main_artist}</b>.")
        
        safe_albums = [html.escape(a, quote=False) for a in albums[:5]]
        text = f"Albums by <b>{main_artist}</b> include: " + ", ".join([f"<i>{a}</i>" for a in safe_albums])
        if len(albums) > 5:
            text += f" and {len(albums) - 5} more."
        return Reply(text)

    elif question == "genres":
        all_tags = []
        for t in tracks:
            all_tags.extend(t.tags)
        
        if not all_tags:
            return Reply(f"I don't have genre or tag information for <b>{main_artist}</b>.")

        # Rank tags by frequency
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        top_tags = [html.escape(t[0], quote=False) for t in sorted_tags[:5]]
        return Reply(f"Popular tags/genres for <b>{main_artist}</b> include: <b>" + ", ".join(top_tags) + "</b>.")

    # Fallback response for the artist
    count = len(tracks)
    top_t = max(tracks, key=lambda x: x.popularity)
    t_name = html.escape(top_t.name, quote=False)
    return Reply(
        f"<b>{main_artist}</b> has {count} track(s) in the catalog. Top track: <b>{t_name}</b>."
    )