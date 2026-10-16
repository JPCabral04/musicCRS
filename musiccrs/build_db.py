"""Build the track database cache/musiccrs.db from the catalog (Part 2, T1).

Run from the repo root:
    python -m musiccrs.build_db
"""
import json
import sqlite3

from retrieval.data_loader import MusicCatalogLoader

from .db import DEFAULT_DB_PATH, base_name, normalize

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


def build(catalog, db_path):
    """Create a fresh database file at db_path with the tracks table."""
    # Make sure the cache folder exists and the old database is gone.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    connection = sqlite3.connect(db_path)
    connection.execute(CREATE_TRACKS)
    connection.execute(CREATE_NAMES)

    track_rows = []
    name_rows = []
    for track_id in catalog:
        metadata = catalog[track_id]
        track_row = make_track_row(track_id, metadata)
        track_rows.append(track_row)
        name_rows.extend(make_name_rows(track_id, metadata))

    connection.executemany(INSERT_TRACK, track_rows)
    connection.executemany(INSERT_NAME, name_rows)
    connection.executescript(CREATE_NAMES_INDEXES)
    connection.commit()
    connection.close()


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
    connection.close()


if __name__ == "__main__":
    main()
