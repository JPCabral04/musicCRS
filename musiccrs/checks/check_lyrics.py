import os
from pathlib import Path
import numpy as np
from collections import Counter

from retrieval import MusicCatalogLoader
from retrieval.methods.dense import load_track_matrix
from musiccrs.data.db import TrackDB


def check_lyrics_vectors(db_path=None):
    """Analyzes lyrics embeddings to filter out missing, zero, or repeated placeholder vectors

    (e.g., instrumentals or tracks sharing identical placeholder embeddings).

    Returns:
        track_ids (list): List of track IDs matching catalog order.
        lyrics_ok (np.ndarray): Boolean mask where True indicates a valid, meaningful lyrics vector.
    """
    print("=== Checking Lyrics Vectors (T8) ===")

    # 1. Load catalog tracks in exact dataset order using MusicCatalogLoader
    print("Loading catalog...")
    catalog_loader = MusicCatalogLoader()
    # Handle catalog format (dictionary vs list)
    if hasattr(catalog_loader, "all_tracks"):
        tracks_data = catalog_loader.all_tracks
        if isinstance(tracks_data, dict):
            track_ids = list(tracks_data.keys())
        else:
            track_ids = [t["track_id"] if isinstance(t, dict) else getattr(t, "track_id") for t in tracks_data]
    elif hasattr(catalog_loader, "metadata_dict"):
        track_ids = list(catalog_loader.metadata_dict.keys())
    else:
        # Fallback inspection of catalog_loader
        raw = getattr(catalog_loader, "tracks", getattr(catalog_loader, "data", []))
        track_ids = [t["track_id"] if isinstance(t, dict) else getattr(t, "track_id", t) for t in raw]

    total_tracks = len(track_ids)
    print(f"Catalog loaded: {total_tracks} tracks.")

    # 2. Locate SQLite DB for metadata lookups
    if db_path is None:
        base_dir = Path(__file__).resolve().parent.parent.parent
        possible_paths = [
            base_dir / "cache" / "musiccrs.db",
            base_dir / "data" / "talkplay.db",
            base_dir / "musiccrs" / "data" / "talkplay.db",
            Path("cache/musiccrs.db").resolve(),
            Path("data/talkplay.db").resolve(),
        ]
        for path in possible_paths:
            if path.exists():
                db_path = str(path)
                break

    db = TrackDB(db_path if db_path and os.path.exists(db_path) else "cache/musiccrs.db")

    # 3. Load normalized lyrics matrix
    print(f"Loading lyrics matrix for {total_tracks} tracks...")
    matrix, has_vector = load_track_matrix("lyrics-qwen3_embedding_0.6b", track_ids)

    # 4. Identify zero / missing vectors
    zero_vector_mask = ~has_vector
    num_missing = np.sum(zero_vector_mask)

    # 5. Round vectors to detect identical/near-identical placeholder embeddings (e.g. instrumentals)
    rounded_matrix = np.round(matrix, decimals=3)

    # Convert rows to bytes to count duplicates efficiently
    row_bytes = [row.tobytes() for row in rounded_matrix]
    counts = Counter(row_bytes)

    # Find row signatures that appear more than 10 times (placeholder/instrumental vectors)
    frequent_signatures = {sig for sig, cnt in counts.items() if cnt > 10}

    repeated_mask = np.array([sig in frequent_signatures for sig in row_bytes])
    repeated_mask = repeated_mask & has_vector
    num_repeated = np.sum(repeated_mask)

    # 6. Construct the clean mask: must have a vector and must not be a frequent placeholder
    lyrics_ok = has_vector & (~repeated_mask)
    num_valid = np.sum(lyrics_ok)

    # Print summary facts for Part 4 documentation
    print("\n--- Summary Data Facts for Lyrics Vectors ---")
    print(f"Total catalog tracks:      {total_tracks:6d}")
    print(f"Tracks without vector:     {num_missing:6d} ({num_missing / total_tracks * 100:.2f}%)")
    print(f"Repeated/Placeholder rows: {num_repeated:6d} ({num_repeated / total_tracks * 100:.2f}%)")
    print(f"Valid lyrics_ok tracks:    {num_valid:6d} ({num_valid / total_tracks * 100:.2f}%)")
    print("---------------------------------------------\n")

    # Display top placeholder vector clusters
    print("Top placeholder vector clusters:")
    for sig, cnt in counts.most_common(5):
        if cnt <= 1:
            break
        sample_idx = row_bytes.index(sig)
        sample_id = track_ids[sample_idx]
        sample_track = db.get(sample_id)
        t_name = sample_track.name if sample_track else "Unknown"
        t_artist = sample_track.artists[0] if sample_track and sample_track.artists else "Unknown"
        print(f"  - Count: {cnt:5d} tracks | Sample: '{t_name}' by {t_artist} (ID: {sample_id})")

    return track_ids, lyrics_ok


if __name__ == "__main__":
    check_lyrics_vectors()