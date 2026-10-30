"""T10 F5b: Offline evaluation of audio representations.

Compares audio neighbours against text neighbours and random baselines
using metadata properties (artist overlap).
"""

import random
from retrieval.final_retriever import FinalRetriever
from ..data.db import TrackDB
from ..data.vectors import TrackVectors


def run_eval(sample_size=50, top_k=5):
    """Runs T10 evaluation comparing audio, text, and random neighbours."""
    print("=== T10 Evaluation: Audio vs Text vs Random Neighbours ===")

    db = TrackDB()

    print("Loading retriever and track vectors...")
    retriever = FinalRetriever()
    scorers = retriever.fusion.scorers
    dense = scorers["dense"]

    # Instanciamos TrackVectors
    vectors = TrackVectors(dense.track_ids, dense.matrix, dense.has_vector)

    num_tracks = len(vectors.track_ids)

    # v.usable["audio"] contiene la máscara booleana por fila
    audio_usable_mask = vectors.usable.get("audio", [])

    # Filtrar filas (índices) que tengan vector de audio disponible
    valid_rows = [
        row for row in range(num_tracks) if row < len(audio_usable_mask) and audio_usable_mask[row]
    ]

    if not valid_rows:
        print("[Error] No valid audio vectors found in vectors.usable['audio'].")
        return

    random.seed(42)
    eval_rows = random.sample(valid_rows, min(sample_size, len(valid_rows)))

    audio_artist_matches = 0
    metadata_artist_matches = 0
    random_artist_matches = 0
    total_comparisons = len(eval_rows) * top_k

    for row in eval_rows:
        query_tid = vectors.track_ids[row]
        query_track = db.get(query_tid)
        if not query_track or not query_track.artists:
            continue

        query_artist = query_track.artists[0].lower()
        exclude_set = {query_tid}

        # 1. Audio Neighbours (CLAP)
        try:
            query_audio_vec = vectors.matrices["audio"][row]
            audio_nearest = vectors.nearest("audio", query_audio_vec, top_k, exclude_set)
            for n_tid, _ in audio_nearest:
                n_track = db.get(n_tid)
                if n_track and n_track.artists and n_track.artists[0].lower() == query_artist:
                    audio_artist_matches += 1
        except Exception as e:
            print(f"[Warning] Error evaluating audio nearest for row {row}: {e}")

        # 2. Metadata / Dense Text Neighbours
        try:
            query_meta_vec = vectors.matrices["metadata"][row]
            metadata_nearest = vectors.nearest("metadata", query_meta_vec, top_k, exclude_set)
            for n_tid, _ in metadata_nearest:
                n_track = db.get(n_tid)
                if n_track and n_track.artists and n_track.artists[0].lower() == query_artist:
                    metadata_artist_matches += 1
        except Exception as e:
            print(f"[Warning] Error evaluating metadata nearest for row {row}: {e}")

        # 3. Random Baseline
        rand_rows = random.sample([r for r in range(num_tracks) if r != row], top_k)
        for n_row in rand_rows:
            n_tid = vectors.track_ids[n_row]
            n_track = db.get(n_tid)
            if n_track and n_track.artists and n_track.artists[0].lower() == query_artist:
                random_artist_matches += 1

    # Resultados T10
    print(f"\nResults over {len(eval_rows)} query tracks (Top-{top_k} neighbours):")
    print(f"  • Same-Artist Overlap (Audio / CLAP):   {audio_artist_matches / total_comparisons * 100:.2f}%")
    print(f"  • Same-Artist Overlap (Text/Metadata): {metadata_artist_matches / total_comparisons * 100:.2f}%")
    print(f"  • Same-Artist Overlap (Random):        {random_artist_matches / total_comparisons * 100:.2f}%\n")


if __name__ == "__main__":
    run_eval()