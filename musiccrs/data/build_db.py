"""Build the track database cache/musiccrs.db from the catalog (Part 2, T1).

Run from the repo root:
    python -m musiccrs.data.build_db
"""
import json
import random
import sqlite3

from retrieval.data_loader import MusicCatalogLoader

from .db import DEFAULT_DB_PATH, TrackDB, base_name, normalize

CREATE_TRACKS = """
CREATE TABLE tracks (
    track_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    album        TEXT NOT NULL,
    popularity   INTEGER NOT NULL,
    release_date TEXT NOT NULL,
    duration_ms  INTEGER NOT NULL,
    tags_json    TEXT NOT NULL,
    artists_json TEXT NOT NULL
)
"""

INSERT_TRACK = "INSERT INTO tracks VALUES (?, ?, ?, ?, ?, ?, ?, ?)"

# One row per name of a track (some tracks have 2 or 3 names).
CREATE_NAMES = """
CREATE TABLE track_names (
    track_id  TEXT NOT NULL,
    name      TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    base_norm TEXT NOT NULL
)
"""

INSERT_NAME = "INSERT INTO track_names VALUES (?, ?, ?, ?)"

# Indexes make "WHERE name_norm = ?" fast. They are created after the inserts.
CREATE_NAMES_INDEXES = """
CREATE INDEX idx_names_norm ON track_names(name_norm);
CREATE INDEX idx_names_base ON track_names(base_norm);
"""

# One row per artist of a track (some tracks have several artists).
# position 0 is the main artist.
CREATE_ARTISTS = """
CREATE TABLE track_artists (
    track_id    TEXT NOT NULL,
    position    INTEGER NOT NULL,
    artist_name TEXT NOT NULL,
    artist_norm TEXT NOT NULL
)
"""

INSERT_ARTIST = "INSERT INTO track_artists VALUES (?, ?, ?, ?)"

CREATE_ARTISTS_INDEXES = """
CREATE INDEX idx_artists_norm ON track_artists(artist_norm);
"""

# Full-text search table (FTS5): it indexes every word of the names and artists,
# so we can find tracks that share some words with a text.
# track_id is only stored, not searched (UNINDEXED).
CREATE_FTS = """
CREATE VIRTUAL TABLE tracks_fts USING fts5(track_id UNINDEXED, names, artists)
"""

INSERT_FTS = "INSERT INTO tracks_fts VALUES (?, ?, ?)"


def make_track_row(track_id, metadata):
    """Turn the catalog entry of one track into a row of the tracks table."""
    # Some tracks have 2 or 3 names and 2 albums: keep the first one of each.
    name = metadata["track_name"][0]
    album = metadata["album_name"][0]

    # In the catalog popularity is a float (39.0); the table stores an integer.
    popularity = int(metadata["popularity"])

    # 644 tracks have no release date.
    release_date = metadata["release_date"]
    if release_date is None:
        release_date = ""

    duration_ms = int(metadata["duration"])

    # SQLite has no list type, so the lists are stored as JSON text.
    tags_json = json.dumps(metadata["tag_list"])
    artists_json = json.dumps(metadata["artist_name"])

    return (track_id, name, album, popularity, release_date,
            duration_ms, tags_json, artists_json)


def make_name_rows(track_id, metadata):
    """Rows of the track_names table: one for each name of the track."""
    rows = []
    for name in metadata["track_name"]:
        name_norm = normalize(name)
        base_norm = base_name(name)
        row = (track_id, name, name_norm, base_norm)
        rows.append(row)
    return rows


def make_artist_rows(track_id, metadata):
    """Rows of the track_artists table: one for each artist of the track."""
    rows = []
    position = 0
    for artist in metadata["artist_name"]:
        artist_norm = normalize(artist)
        row = (track_id, position, artist, artist_norm)
        rows.append(row)
        position = position + 1
    return rows


def make_fts_row(track_id, metadata):
    """Row of the tracks_fts table: all names and all artists as normalized text."""
    normalized_names = []
    for name in metadata["track_name"]:
        normalized_names.append(normalize(name))

    normalized_artists = []
    for artist in metadata["artist_name"]:
        normalized_artists.append(normalize(artist))

    # " ".join(list) glues the items of a list into one text, with a space between.
    names_text = " ".join(normalized_names)
    artists_text = " ".join(normalized_artists)
    return (track_id, names_text, artists_text)


def build(catalog, db_path):
    """Create a fresh database file at db_path with the tracks table."""
    # Make sure the cache folder exists and the old database is gone.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    connection = sqlite3.connect(db_path)
    connection.execute(CREATE_TRACKS)
    connection.execute(CREATE_NAMES)
    connection.execute(CREATE_ARTISTS)
    connection.execute(CREATE_FTS)

    track_rows = []
    name_rows = []
    artist_rows = []
    fts_rows = []
    for track_id in catalog:
        metadata = catalog[track_id]
        track_row = make_track_row(track_id, metadata)
        track_rows.append(track_row)
        name_rows.extend(make_name_rows(track_id, metadata))
        artist_rows.extend(make_artist_rows(track_id, metadata))
        fts_rows.append(make_fts_row(track_id, metadata))

    connection.executemany(INSERT_TRACK, track_rows)
    connection.executemany(INSERT_NAME, name_rows)
    connection.executemany(INSERT_ARTIST, artist_rows)
    connection.executemany(INSERT_FTS, fts_rows)
    connection.executescript(CREATE_NAMES_INDEXES)
    connection.executescript(CREATE_ARTISTS_INDEXES)
    connection.commit()
    connection.close()


def self_check(catalog, db_path):
    """Check the new database with the T1 "done when" tests.

    `assert condition, message` does nothing if the condition is true. If it
    is false, the script stops with an AssertionError that shows the message.
    """
    db = TrackDB(db_path)

    # 1. Exact name: the most popular track comes first (Nirvana, popularity 82).
    found = db.find_by_name("smells like teen spirit")
    assert len(found) > 0, "teen spirit: nothing found"
    assert found[0].artists == ("Nirvana",), "teen spirit: first is not Nirvana"
    print("OK 1: find_by_name('smells like teen spirit') ->", len(found), "tracks")

    # 2. Capitals, "!" and an artist: only the Nirvana track is left.
    found = db.find_by_name("SMELLS LIKE TEEN SPIRIT!", artist="nirvana")
    assert len(found) == 1, "teen spirit + nirvana: expected 1 track"
    assert found[0].artists == ("Nirvana",), "teen spirit + nirvana: wrong artist"
    print("OK 2: find_by_name with artist -> 1 track")

    # 3. The base name finds a track whose name has a version suffix.
    found = db.find_by_name("hotel california")
    assert len(found) > 0, "hotel california: nothing found"
    assert found[0].artists == ("Eagles",), "hotel california: first is not Eagles"
    print("OK 3: find_by_name('hotel california') ->", found[0].name)

    # 4. The full-text search finds the track from a few words of it.
    found = db.fuzzy_candidates("teen spirit nirvana")
    found_nirvana = False
    for track in found:
        if track.name == "Smells Like Teen Spirit" and track.artists == ("Nirvana",):
            found_nirvana = True
    assert found_nirvana, "fuzzy: Nirvana track not among the candidates"
    print("OK 4: fuzzy_candidates('teen spirit nirvana') ->", len(found), "candidates")

    # 5. All tracks of an artist.
    found = db.artist_tracks("queen")
    assert len(found) == 13, "queen: expected 13 tracks, got " + str(len(found))
    print("OK 5: artist_tracks('queen') -> 13 tracks")

    # 6. get() returns what the catalog has, for 3 random tracks.
    # Seed 0: the same 3 tracks every time.
    all_ids = sorted(catalog)
    generator = random.Random(0)
    sample_ids = generator.sample(all_ids, 3)
    for track_id in sample_ids:
        metadata = catalog[track_id]
        track = db.get(track_id)
        assert track.name == metadata["track_name"][0], track_id + ": name differs"
        assert list(track.artists) == metadata["artist_name"], track_id + ": artists differ"
        assert track.duration_ms == metadata["duration"], track_id + ": duration differs"
        assert track.popularity == int(metadata["popularity"]), track_id + ": popularity differs"
    print("OK 6: get() matches the catalog for 3 random tracks")


def main():
    catalog = MusicCatalogLoader().metadata_dict
    print("catalog loaded:", len(catalog), "tracks")

    build(catalog, DEFAULT_DB_PATH)

    connection = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = connection.execute("SELECT COUNT(*) FROM tracks")
    count = cursor.fetchone()[0]
    print("tracks in", DEFAULT_DB_PATH, ":", count)

    cursor = connection.execute("SELECT COUNT(*) FROM track_names")
    count = cursor.fetchone()[0]
    print("names:", count)

    cursor = connection.execute("SELECT COUNT(*) FROM track_artists")
    count = cursor.fetchone()[0]
    print("artists:", count)
    connection.close()

    self_check(catalog, DEFAULT_DB_PATH)


if __name__ == "__main__":
    main()
