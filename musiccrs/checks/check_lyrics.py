"""Facts about the lyrics vectors (Part 4, T8): how many are missing or placeholders.

Run from the repo root (no API key, no retriever; about 15 s):
    python -m musiccrs.checks.check_lyrics

It applies lyrics_ok_mask (the mask the agent uses for lyrics search) and prints
how many tracks have no vector, how many share a placeholder vector, and the
biggest placeholder groups with one sample track each.
"""
from retrieval.data_loader import MusicCatalogLoader
from retrieval.methods.dense import load_track_matrix

from ..data.db import TrackDB
from ..data.vectors import LYRICS_FIELD, MAX_COPIES, lyrics_ok_mask


def percent_text(count, total):
    """"  322 (0.68%)" for count=322, total=47071."""
    return str(count).rjust(6) + " (" + str(round(100 * count / total, 2)) + "%)"


def main():
    # The same track order as the agent (the dense scorer's catalog order).
    track_ids = list(MusicCatalogLoader().metadata_dict)
    matrix, has_vector = load_track_matrix(LYRICS_FIELD, track_ids)
    lyrics_ok = lyrics_ok_mask(matrix, has_vector)

    total = len(track_ids)
    missing = int((~has_vector).sum())
    placeholders = int((has_vector & ~lyrics_ok).sum())
    usable = int(lyrics_ok.sum())
    print("Catalog tracks:          " + str(total).rjust(6))
    print("Without a lyrics vector: " + percent_text(missing, total))
    print("Placeholder rows:        " + percent_text(placeholders, total)
          + "  (a vector shared by more than " + str(MAX_COPIES) + " tracks)")
    print("Usable for lyrics search:" + percent_text(usable, total))

    # The placeholder groups: rounded vector -> the rows that have it.
    groups = {}
    for row in range(total):
        if has_vector[row] and not lyrics_ok[row]:
            key = matrix[row].round(3).tobytes()
            if key not in groups:
                groups[key] = []
            groups[key].append(row)

    sizes = []
    for key in groups:
        sizes.append((len(groups[key]), key))
    sizes.sort(reverse=True)

    db = TrackDB()
    print()
    print("Biggest placeholder groups:")
    for size, key in sizes[:5]:
        sample = db.get(track_ids[groups[key][0]])
        print("  " + str(size).rjust(5) + " tracks, e.g. " + sample.name
              + " by " + sample.artists[0])


if __name__ == "__main__":
    main()
