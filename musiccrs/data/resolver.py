"""Track resolver (T6): turns a loose track name, and maybe an artist, into catalog tracks.

Written by Alejandro (Oct 19); artist checks added by JP (Oct 21), so that a song by the
wrong artist is never offered when the user named the artist.

"its my life", "IT'S MY LIFE!" and "it's my life by bon jovi" all find the Bon Jovi track.
"always" by "bon jovi" finds nothing (the catalog has no such song), instead of blink-182.
"""
import re
from difflib import SequenceMatcher

from .db import base_name, normalize

# A fuzzy candidate must be at least this close to the asked title (0 = nothing alike, 1 = same).
MIN_TITLE_SCORE = 0.6

# When the user names an artist, a fuzzy candidate's artist must be at least this close
# (lets "bon jovy" through, not "chris brown" for "chris young").
MIN_ARTIST_SCORE = 0.8

# How much the title and the artist count in the score of a fuzzy candidate.
TITLE_WEIGHT = 0.6
ARTIST_WEIGHT = 0.4

# How many tracks the full-text index returns as fuzzy candidates.
NUM_FUZZY_CANDIDATES = 50


def _extract_artist_from_track_string(track_str):
    """Split "song by artist" (or "song - artist") when the parser left both in the track slot.

    "its my life by bon jovi" -> ("its my life", "bon jovi")
    "toxic"                   -> ("toxic", None)
    """
    if not track_str:
        return "", None

    patterns = [
        r"^(.*?)\s+(?:by|de)\s+(.*)$",
        r"^(.*?)\s+-\s+(.*)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, track_str, re.IGNORECASE)
        if match:
            title_part = match.group(1).strip()
            artist_part = match.group(2).strip()
            if title_part and artist_part:
                return title_part, artist_part

    return track_str, None


def artist_key(name):
    """The artist name for comparing: normalized, without a leading "the".

    "The Eagles" -> "eagles"
    "Beyoncé"    -> "beyonce"
    """
    key = normalize(name)
    if key.startswith("the "):
        key = key[4:]
    return key


def artist_variants(artist):
    """The artist as typed, plus the same name with or without "the", for exact lookups.

    "the eagles" -> ["the eagles", "eagles"]
    "beatles"    -> ["beatles", "the beatles"]
    """
    typed = normalize(artist)
    key = artist_key(artist)
    variants = [typed]
    if key != typed:
        variants.append(key)
    else:
        variants.append("the " + key)
    return variants


def similarity(text_a, text_b):
    """How alike two already-normalized strings are, from 0.0 to 1.0.

    ("bon jovi", "bon jovy") -> 0.875
    """
    if text_a == "" or text_b == "":
        return 0.0
    return SequenceMatcher(None, text_a, text_b).ratio()


def title_score(title, track):
    """How close the asked title is to the track's full name or its base name.

    ("smells like teen sprit", "Smells Like Teen Spirit") -> about 0.98
    """
    wanted = normalize(title)
    full_score = similarity(wanted, normalize(track.name))
    base_score = similarity(wanted, base_name(track.name))
    if base_score > full_score:
        return base_score
    return full_score


def best_artist_score(artist, track):
    """How close the asked artist is to the closest of the track's artists."""
    wanted = artist_key(artist)
    best = 0.0
    for name in track.artists:
        score = similarity(wanted, artist_key(name))
        if score > best:
            best = score
    return best


def resolve_artist(db, artist):
    """All tracks by the artist, most popular first, also trying with or without "the".

    "the eagles" -> the Eagles tracks (the catalog writes "Eagles")
    """
    for variant in artist_variants(artist):
        tracks = db.artist_tracks(variant)
        if len(tracks) > 0:
            return tracks
    return []


def find_exact(db, track, artist):
    """Exact normalized matches of the name (with the artist, if given), most popular first."""
    if artist is None:
        return db.find_by_name(track)

    for variant in artist_variants(artist):
        matches = db.find_by_name(track, variant)
        if len(matches) > 0:
            return matches
    return []


def find_fuzzy(db, track, artist):
    """Close matches when the exact lookup found nothing, best first.

    With an artist, a candidate must be by that artist (MIN_ARTIST_SCORE), so
    "goodbye" by "chris young" does not return "Say Goodbye" by Chris Brown.
    """
    query_text = track
    if artist is not None:
        query_text = track + " " + artist
    candidates = db.fuzzy_candidates(query_text, limit=NUM_FUZZY_CANDIDATES)

    # (score, position) pairs: sorting them never compares two Track objects.
    scored = []
    position = 0
    for candidate in candidates:
        score = title_score(track, candidate)
        keep = score >= MIN_TITLE_SCORE
        if keep and artist is not None:
            artist_score = best_artist_score(artist, candidate)
            if artist_score < MIN_ARTIST_SCORE:
                keep = False
            score = TITLE_WEIGHT * score + ARTIST_WEIGHT * artist_score
        if keep:
            scored.append((score, position))
        position = position + 1

    # Highest score first.
    scored.sort(reverse=True)

    result = []
    seen_ids = []
    for score, position in scored:
        candidate = candidates[position]
        if candidate.track_id not in seen_ids:
            seen_ids.append(candidate.track_id)
            result.append(candidate)
    return result


def resolve(db, track, artist=None):
    """Resolve a loose track reference into a ranked list of catalog tracks.

    Strategy:
    1. Only an artist -> the artist's tracks.
    2. Exact normalized match of the whole name (with the artist, if given).
    3. "song by artist" in the track slot -> split it and try the exact match again.
    4. Fuzzy match (typos), which must keep the artist when one is given.

    "its my life"             -> [It's My Life (Bon Jovi), It's My Life (Talk Talk), ...]
    "its my life by bon jovi" -> [It's My Life (Bon Jovi)]
    "always", "bon jovi"      -> []  (not in the catalog)
    """
    if track is None:
        track = ""
    track = track.strip()
    if artist is not None and artist.strip() == "":
        artist = None

    if track == "" and artist is None:
        return []

    # 1. Only an artist was given: "add something by Nirvana".
    if track == "":
        return resolve_artist(db, artist)

    # 2. Exact match of the whole name first, so "Stand By Me" is never split at "by".
    exact = find_exact(db, track, artist)
    if len(exact) > 0:
        return exact

    # 3. The parser left "song by artist" in the track slot.
    if artist is None:
        title, found_artist = _extract_artist_from_track_string(track)
        if found_artist is not None:
            track = title
            artist = found_artist
            exact = find_exact(db, track, artist)
            if len(exact) > 0:
                return exact

    # 4. Typos and small differences.
    return find_fuzzy(db, track, artist)
