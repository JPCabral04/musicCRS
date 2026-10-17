"""Track database for the Part 2 agent (T1)."""
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Where the database file lives: <repo root>/cache/musiccrs.db
this_file = Path(__file__).resolve()
musiccrs_folder = this_file.parent
repo_root = musiccrs_folder.parent
DEFAULT_DB_PATH = repo_root / "cache" / "musiccrs.db"


def normalize(text: str) -> str:
    """Turn a song or artist name into a simple form for matching.

    "Don't Stop Me Now!" -> "dont stop me now"
    "Beyoncé"            -> "beyonce"
    "Simon & Garfunkel"  -> "simon and garfunkel"
    """
    # Split each accented letter into the letter plus a separate accent mark.
    text = unicodedata.normalize("NFKD", text)

    # Keep every character that is not an accent mark.
    without_accents = ""
    for char in text:
        if not unicodedata.combining(char):
            without_accents = without_accents + char
    text = without_accents

    text = text.lower()

    # Delete apostrophes, so "don't" becomes "dont" (what users type).
    text = text.replace("'", "")
    text = text.replace("’", "")  # the curly apostrophe ’

    text = text.replace("&", " and ")

    # Replace every run of characters that are not letters or digits by one space.
    text = re.sub(r"[\W_]+", " ", text)

    # Remove the spaces at the start and the end.
    text = text.strip()
    return text


def base_name(name: str) -> str:
    """Normalized name without the version suffix and without bracketed parts.

    "Hotel California - 2013 Remaster"  -> "hotel california"
    "Letting Go (feat. Sarah Green)"    -> "letting go"
    """
    # Keep only what comes before the first " - ".
    parts = name.split(" - ")
    base = parts[0]

    # Remove everything inside (...) and [...].
    base = re.sub(r"\(.*?\)", " ", base)
    base = re.sub(r"\[.*?\]", " ", base)

    base = normalize(base)

    # If nothing is left (the whole name was in brackets), use the full name.
    if base == "":
        base = normalize(name)
    return base


@dataclass(frozen=True)
class Track:
    """All the data of one track, as the agent uses it."""
    track_id: str
    name: str                  # first name of the track in the catalog
    artists: tuple             # all artists, main artist first
    album: str
    popularity: int            # 0 to 93
    release_date: str          # "YYYY-MM-DD", or "" if unknown
    duration_ms: int           # 0 if unknown
    tags: tuple


def row_to_track(row):
    """Turn one row of the tracks table into a Track."""
    # The lists were saved as JSON text: turn the text back into a list.
    artists_list = json.loads(row["artists_json"])
    tags_list = json.loads(row["tags_json"])

    return Track(
        track_id=row["track_id"],
        name=row["name"],
        artists=tuple(artists_list),
        album=row["album"],
        popularity=row["popularity"],
        release_date=row["release_date"],
        duration_ms=row["duration_ms"],
        tags=tuple(tags_list),
    )


class TrackDB:
    """Read-only access to cache/musiccrs.db."""

    def __init__(self, path=DEFAULT_DB_PATH):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                str(path) + " not found. Build it first: python -m musiccrs.build_db")

        # mode=ro opens the file read-only. check_same_thread=False lets the
        # chat server use this connection from different threads.
        uri = path.resolve().as_uri() + "?mode=ro"
        self.connection = sqlite3.connect(
            uri, uri=True, check_same_thread=False)

        # With Row we can read a column by its name: row["name"].
        self.connection.row_factory = sqlite3.Row

    def get(self, track_id):
        """Return the Track with this ID, or None if there is none."""
        cursor = self.connection.execute(
            "SELECT * FROM tracks WHERE track_id = ?", (track_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return row_to_track(row)

    def run_query(self, sql, params):
        """Run a SELECT on the tracks table and return a list of Track."""
        cursor = self.connection.execute(sql, params)
        tracks = []
        for row in cursor.fetchall():
            track = row_to_track(row)
            tracks.append(track)
        return tracks

    def find_by_name(self, name, artist=None):
        """Tracks whose name matches `name`, most popular first.

        The match is exact after normalize(): it can be the full name or the
        base name (without the version suffix). "hotel california" finds
        "Hotel California - 2013 Remaster".

        If `artist` is given, one of the artists of the track must match it too.
        """
        name_norm = normalize(name)
        if name_norm == "":
            return []

        sql = """
            SELECT DISTINCT tracks.*
            FROM tracks
            JOIN track_names ON track_names.track_id = tracks.track_id
            WHERE (track_names.name_norm = ? OR track_names.base_norm = ?)
        """
        params = [name_norm, name_norm]

        if artist is not None:
            artist_norm = normalize(artist)
            if artist_norm != "":
                sql = sql + """
                    AND tracks.track_id IN (
                        SELECT track_id FROM track_artists WHERE artist_norm = ?
                    )
                """
                params.append(artist_norm)

        sql = sql + " ORDER BY tracks.popularity DESC"
        return self.run_query(sql, params)

    def artist_tracks(self, artist):
        """All tracks where one of the artists matches `artist`, most popular first."""
        artist_norm = normalize(artist)
        if artist_norm == "":
            return []

        sql = """
            SELECT DISTINCT tracks.*
            FROM tracks
            JOIN track_artists ON track_artists.track_id = tracks.track_id
            WHERE track_artists.artist_norm = ?
            ORDER BY tracks.popularity DESC
        """
        return self.run_query(sql, (artist_norm,))

    def fuzzy_candidates(self, text, limit=50):
        """Tracks that share at least one word with `text`, best match first.

        It is wide on purpose: it returns candidates, and the resolver (T6)
        chooses the right one among them.
        """
        words = normalize(text).split()
        if len(words) == 0:
            return []

        # FTS5 query: "its" OR "my" OR "life". The quotes make each word plain
        # text, so words like "or" or "and" are not read as FTS5 operators.
        quoted_words = []
        for word in words:
            quoted_words.append('"' + word + '"')
        fts_query = " OR ".join(quoted_words)

        sql = """
            SELECT tracks.*
            FROM tracks_fts
            JOIN tracks ON tracks.track_id = tracks_fts.track_id
            WHERE tracks_fts MATCH ?
            ORDER BY tracks_fts.rank
            LIMIT ?
        """
        return self.run_query(sql, (fts_query, limit))
