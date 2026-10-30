"""The track vectors the Part 4 features search in (T1), loaded once at startup.

Three spaces, each one matrix with one row per catalog track (row i is track_ids[i]).
Every row is L2-normalized (length 1), so a dot product between two rows is their cosine.
    "metadata" -> metadata-qwen3_embedding_0.6b (1024 numbers): the dense scorer's matrix,
                  shared, not copied. Used by the critiques (F1) and as the F5b baseline.
    "audio"    -> audio-laion_clap (512): made from the sound itself. "Sounds like" (F2.1).
    "lyrics"   -> lyrics-qwen3_embedding_0.6b (1024): made from the lyrics. Themes (F2.2).

Every feature is the same search: take a query vector, find the closest rows, skip the
tracks already shown. That search is nearest(), written once here.

Run from the repo root to print the matrix sizes and the 5 tracks that sound closest
to Smells Like Teen Spirit (no LLM, no retriever):
    python -m musiccrs.data.vectors
"""
import numpy as np

from retrieval.data_loader import MusicCatalogLoader
from retrieval.methods.dense import DEFAULT_FIELD, load_track_matrix

from .db import TrackDB
from .resolver import resolve

AUDIO_FIELD = "audio-laion_clap"
LYRICS_FIELD = "lyrics-qwen3_embedding_0.6b"

# A lyrics vector shared by more than this many tracks is a placeholder, not real lyrics
# (instrumentals and tracks with missing lyrics all got the same embedding).
MAX_COPIES = 10


def lyrics_ok_mask(matrix, has_vector):
    """True for each row with a real lyrics vector: it has one, and it is not a placeholder.

    Rows are rounded to 3 decimals, so near-identical placeholders count as the same.
    Row of an instrumental, shared by 300 tracks  -> False
    Row of "Smells Like Teen Spirit" (unique)     -> True
    """
    rounded = np.round(matrix, decimals=3)

    # 1. Count how many rows have each exact vector (its bytes are the dict key).
    keys = []
    copies = {}
    for row in rounded:
        key = row.tobytes()
        keys.append(key)
        if key in copies:
            copies[key] = copies[key] + 1
        else:
            copies[key] = 1

    # 2. A row is usable when it has a vector that few other rows share.
    ok = np.zeros(len(keys), dtype=bool)
    for index in range(len(keys)):
        if has_vector[index] and copies[keys[index]] <= MAX_COPIES:
            ok[index] = True
    return ok


class TrackVectors:
    """The three matrices, plus which rows may be returned by a search."""

    def __init__(self, track_ids, metadata_matrix, metadata_has_vector):
        """track_ids and the metadata matrix come from the dense scorer, already in memory.

        The audio and lyrics matrices are read from cache/embeddings/ (downloaded from
        Hugging Face and saved there the first time, by load_track_matrix).
        """
        self.track_ids = track_ids

        # Track ID -> its row number, so vector() does not search the list.
        # "e9383e0c-..." (Smells Like Teen Spirit) -> 1234
        self.row_of = {}
        for row in range(len(track_ids)):
            self.row_of[track_ids[row]] = row

        audio_matrix, audio_has_vector = load_track_matrix(AUDIO_FIELD, track_ids)
        lyrics_matrix, lyrics_has_vector = load_track_matrix(LYRICS_FIELD, track_ids)

        self.matrices = {
            "metadata": metadata_matrix,
            "audio": audio_matrix,
            "lyrics": lyrics_matrix,
        }

        # Space -> one True/False per row: True when the row may be returned.
        # A track without a vector has a zero row: it would score 0 against everything.
        # Lyrics also leave out placeholder rows (T8), or a theme search returns instrumentals.
        self.usable = {
            "metadata": metadata_has_vector,
            "audio": audio_has_vector,
            "lyrics": lyrics_ok_mask(lyrics_matrix, lyrics_has_vector),
        }

    def size_text(self, space):
        """One line about a space, for the startup print.

        "audio" -> "audio: 47071 x 512, 46579 tracks with a vector"
        """
        matrix = self.matrices[space]
        rows = matrix.shape[0]
        columns = matrix.shape[1]
        usable_count = int(self.usable[space].sum())
        return (space + ": " + str(rows) + " x " + str(columns) + ", "
                + str(usable_count) + " tracks with a vector")

    def vector(self, space, track_id):
        """The vector of one track in one space, or None if it has none.

        ("audio", id of Smells Like Teen Spirit) -> array of 512 numbers
        ("audio", "not-a-track-id")              -> None
        """
        if track_id not in self.row_of:
            return None
        row = self.row_of[track_id]
        if not self.usable[space][row]:
            return None
        return self.matrices[space][row]

    def nearest(self, space, query_vector, k, exclude_ids):
        """The k tracks whose vectors are closest to query_vector, best first.

        Skips the tracks in exclude_ids (a set or list) and the rows without a vector.
        Returns [(track_id, score), ...], where score is the cosine similarity
        (query_vector should be L2-normalized too).

        ("audio", vector of Smells Like Teen Spirit, 3, {its own ID})
            -> [("id-a", 0.93), ("id-b", 0.92), ("id-c", 0.91)]
        """
        matrix = self.matrices[space]
        usable = self.usable[space]

        # One dot product per row: 47,071 scores in a single numpy operation.
        scores = matrix @ query_vector

        # argsort gives the row numbers from the lowest score to the highest.
        # Sorting the negated scores gives them from the highest to the lowest.
        order = np.argsort(-scores)

        results = []
        for row in order:
            if len(results) == k:
                break
            if not usable[row]:
                continue
            track_id = self.track_ids[row]
            if track_id in exclude_ids:
                continue
            results.append((track_id, float(scores[row])))
        return results


def main():
    """Load the vectors as the agent does (without the encoder) and try one search."""
    # The same track order and metadata matrix the dense scorer uses.
    catalog = MusicCatalogLoader()
    track_ids = list(catalog.metadata_dict)
    metadata_matrix, metadata_has_vector = load_track_matrix(DEFAULT_FIELD, track_ids)

    vectors = TrackVectors(track_ids, metadata_matrix, metadata_has_vector)
    print(vectors.size_text("metadata"))
    print(vectors.size_text("audio"))
    print(vectors.size_text("lyrics"))

    db = TrackDB()
    seed = resolve(db, "smells like teen spirit", "nirvana")[0]
    seed_vector = vectors.vector("audio", seed.track_id)

    print()
    print("Sounds closest to " + seed.name + " by " + seed.artists[0] + ":")
    neighbours = vectors.nearest("audio", seed_vector, 5, {seed.track_id})
    for track_id, score in neighbours:
        track = db.get(track_id)
        print("  " + str(round(score, 3)) + "  " + track.name + " by " + track.artists[0])


if __name__ == "__main__":
    main()
