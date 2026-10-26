"""QA handlers (T10, R5): questions about tracks and artists, answered from the database.

Written by Alejandro (Oct 19). Adapted by JP (Oct 21): the artist lookup also tries the
name with or without "the" ("the eagles" -> Eagles), and the shortcuts were written out.
No LLM is used for the answer; the parser (one LLM call) only gives the question type:
- track (ASK_TRACK):   artist, album, release_year, duration
- artist (ASK_ARTIST): track_count, top_track, albums, genres
"""
import html

from ..data.db import normalize
from ..data.resolver import artist_key, resolve, resolve_artist
from ..state import Reply

# How many albums and tags an answer lists at most.
MAX_LISTED = 5

# Whole words (after normalize) that mark a compilation or best-of album. The catalog
# often has a song only on such an album ("Viva La Vida" -> "DDB Hitzone Best Of 2008"),
# so the album answer says so. 507 of the 17,438 album names match (Oct 26).
COMPILATION_WORDS = ("best of", "hits", "hitzone", "greatest", "collection", "anthology",
                     "essential", "essentials", "compilation", "the 70s", "the 80s", "the 90s")


def looks_like_compilation(album):
    """True if the album name has one of COMPILATION_WORDS as whole words.

    "DDB Hitzone Best Of 2008" -> True   ("best of")
    "Love In The 80's"         -> True   ("love in the 80s" contains "the 80s")
    "Parachutes"               -> False
    "Hitchhiker"               -> False  ("hits" must be a whole word)
    """
    # Spaces around both sides, so only whole words match.
    padded_album = " " + normalize(album) + " "
    for words in COMPILATION_WORDS:
        if " " + words + " " in padded_album:
            return True
    return False


def _format_duration(duration_ms):
    """Milliseconds as "M:SS": 301920 -> "5:01". 0 (unknown) -> "unknown duration"."""
    if not duration_ms or duration_ms <= 0:
        return "unknown duration"
    total_seconds = int(duration_ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    seconds_text = str(seconds)
    if seconds < 10:
        seconds_text = "0" + seconds_text
    return str(minutes) + ":" + seconds_text


def _release_year(track):
    """"1991-09-10" -> "1991"; an unknown date ("") -> None."""
    if len(track.release_date) >= 4:
        return track.release_date[:4]
    return None


def handle_ask_track(parsed, state, services):
    """ASK_TRACK (R5): who sings it, which album, which year, how long.

    "who sings Hotel California?" -> "Hotel California - 2013 Remaster is performed by Eagles."
    """
    track_name = parsed.slots.get("track")
    artist = parsed.slots.get("artist")
    question = parsed.slots.get("question")

    if track_name is None:
        return Reply("Which song are you asking about?")

    candidates = resolve(services.db, track_name, artist)
    if len(candidates) == 0:
        safe_name = html.escape(track_name, quote=False)
        return Reply("I couldn't find '" + safe_name + "' in the catalog.")

    # The resolver gives the most popular exact match first.
    track = candidates[0]
    name = html.escape(track.name, quote=False)
    main_artist = html.escape(track.artists[0], quote=False)

    if question == "artist":
        safe_artists = []
        for artist_name in track.artists:
            safe_artists.append(html.escape(artist_name, quote=False))
        return Reply("<b>" + name + "</b> is performed by <b>" + ", ".join(safe_artists) + "</b>.")

    if question == "album":
        if track.album == "":
            return Reply("I don't know the album of <b>" + name + "</b> by " + main_artist + ".")
        album = html.escape(track.album, quote=False)
        if looks_like_compilation(track.album):
            return Reply("In our catalog, <b>" + name + "</b> by " + main_artist
                         + " is on <b>" + album + "</b>. That looks like a compilation or "
                         "best-of album, so the song's original album may have another name.")
        return Reply("<b>" + name + "</b> by " + main_artist + " is on the album <b>"
                     + album + "</b>.")

    if question == "release_year":
        year = _release_year(track)
        if year is None:
            return Reply("I don't have the release year of <b>" + name + "</b> by "
                         + main_artist + ".")
        return Reply("<b>" + name + "</b> by " + main_artist + " was released in <b>"
                     + year + "</b>.")

    if question == "duration":
        return Reply("<b>" + name + "</b> by " + main_artist + " is <b>"
                     + _format_duration(track.duration_ms) + "</b> long.")

    # No question type: a short summary of the song.
    year = _release_year(track)
    if year is None:
        year = "unknown"
    album = html.escape(track.album, quote=False)
    if album == "":
        album = "unknown"
    return Reply("<b>" + name + "</b> by <b>" + main_artist + "</b> (album: <i>" + album
                 + "</i>, year: " + year + ", duration: " + _format_duration(track.duration_ms)
                 + ").")


def handle_ask_artist(parsed, state, services):
    """ASK_ARTIST (R5): how many songs, most popular song, albums, genres.

    "how many songs does Bon Jovi have?" -> "We have 32 tracks by Bon Jovi in the catalog."
    """
    artist = parsed.slots.get("artist")
    question = parsed.slots.get("question")

    # The parser sometimes puts the artist's name in the track slot.
    if artist is None and "track" in parsed.slots:
        artist = parsed.slots["track"]
    if artist is None:
        return Reply("Which artist are you asking about?")

    # Most popular first; also tries the name with or without "the".
    tracks = resolve_artist(services.db, artist)
    if len(tracks) == 0:
        safe_artist = html.escape(artist, quote=False)
        return Reply("I couldn't find any tracks by '" + safe_artist + "' in the catalog.")

    # The artist's name as the catalog writes it ("the eagles" -> "Eagles").
    main_artist = html.escape(artist, quote=False)
    for name in tracks[0].artists:
        if artist_key(name) == artist_key(artist):
            main_artist = html.escape(name, quote=False)

    count = len(tracks)
    top_name = html.escape(tracks[0].name, quote=False)

    if question == "track_count":
        if count == 1:
            return Reply("We have <b>1</b> track by <b>" + main_artist + "</b> in the catalog.")
        return Reply("We have <b>" + str(count) + "</b> tracks by <b>" + main_artist
                     + "</b> in the catalog.")

    if question == "top_track":
        return Reply("The most popular track by <b>" + main_artist + "</b> in our catalog is <b>"
                     + top_name + "</b>.")

    if question == "albums":
        # Album names in order of the artist's most popular tracks, each once.
        albums = []
        for track in tracks:
            if track.album != "" and track.album not in albums:
                albums.append(track.album)
        if len(albums) == 0:
            return Reply("I couldn't find album information for <b>" + main_artist + "</b>.")

        safe_albums = []
        for album in albums[:MAX_LISTED]:
            safe_albums.append("<i>" + html.escape(album, quote=False) + "</i>")
        text = "Albums by <b>" + main_artist + "</b> include: " + ", ".join(safe_albums)
        if len(albums) > MAX_LISTED:
            text = text + " and " + str(len(albums) - MAX_LISTED) + " more"
        return Reply(text + ".")

    if question == "genres":
        # Count how many of the artist's tracks carry each tag. "Rock" and "rock" are the
        # same tag: count them together and show the first spelling seen.
        tag_counts = {}
        tag_spelling = {}
        for track in tracks:
            for tag in track.tags:
                key = tag.lower()
                if key not in tag_counts:
                    tag_counts[key] = 0
                    tag_spelling[key] = tag
                tag_counts[key] = tag_counts[key] + 1
        if len(tag_counts) == 0:
            return Reply("I don't have genre or tag information for <b>" + main_artist + "</b>.")

        # (count, tag) pairs: sorting them puts the most frequent tag first.
        pairs = []
        for key in tag_counts:
            pairs.append((tag_counts[key], tag_spelling[key]))
        pairs.sort(reverse=True)

        top_tags = []
        for tag_count, tag in pairs[:MAX_LISTED]:
            top_tags.append(html.escape(tag, quote=False))
        return Reply("Popular tags/genres for <b>" + main_artist + "</b> include: <b>"
                     + ", ".join(top_tags) + "</b>.")

    # No question type: a short summary of the artist.
    return Reply("<b>" + main_artist + "</b> has " + str(count) + " track(s) in the catalog. "
                 "Top track: <b>" + top_name + "</b>.")
