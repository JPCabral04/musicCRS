"""Session signals (T5, T7): tracks by artists already played in the session
and tracks similar in BPR latent space.

In the dataset 65% of the gold tracks (turns 2-8) share an artist with a played
track, and that pool is small (~60 tracks). Played tracks are NOT removed here:
SessionPolicy does that once, in fusion and finalize_top_k.

Usage:
    python -m retrieval.run_experiment --method same_artist --split val
    python -m retrieval.run_experiment --method bpr_sim --split val
"""
import numpy as np

from .context import TurnContext
from .data_loader import MusicCatalogLoader
from .dense import load_track_matrix


class SameArtistScorer:
    """Tracks sharing an artist_id with a played track: most recent artist first, then popularity."""
    name = "same_artist"

    def __init__(self, catalog: MusicCatalogLoader) -> None:
        """Builds the artist_id -> track IDs index once."""
        self.catalog = catalog  # reused by the runner (load it once)
        self.metadata = catalog.metadata_dict
        self.artist_to_tracks: dict[str, list[str]] = {}
        for track_id, metadata in self.metadata.items():
            for artist_id in metadata.get("artist_id", []):
                self.artist_to_tracks.setdefault(artist_id, []).append(track_id)

    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        """Same-artist candidates ranked by (recency of the matching played track, popularity).

        Played tracks are kept (see SessionPolicy). Empty at turn 1.
        """
        recency: dict[str, int] = {}  # candidate -> 0 if its artist was played last, 1 before that...
        for age, played_id in enumerate(reversed(ctx.played_track_ids)):
            for artist_id in self.metadata.get(played_id, {}).get("artist_id", []):
                for track_id in self.artist_to_tracks.get(artist_id, []):
                    recency.setdefault(track_id, age)  # first seen = most recent
        ranked = sorted(recency, key=lambda track_id: (
            recency[track_id], -(self.metadata[track_id].get("popularity") or 0)))
        # The order is the signal; -rank keeps it (fusion uses ranks).
        return [(track_id, -rank) for rank, track_id in enumerate(ranked[:k])]


class BPRSimilarityScorer:
    """Task T7: Recommends tracks similar to the centroid of played tracks in BPR CF space."""
    name = "bpr_sim"

    def __init__(self, catalog: MusicCatalogLoader, cache_dir: str = "./cache/embeddings") -> None:
        """Loads precomputed cf-bpr matrix and aligns with track_ids."""
        self.catalog = catalog  # reused by the runner (load it once)
        # Catalog order, same as DenseScorer and BM25: row i of the matrix is track_ids[i].
        self.track_ids = list(catalog.metadata_dict)
        self.tid_to_idx = {tid: i for i, tid in enumerate(self.track_ids)}

        self.matrix, self.has_vector = load_track_matrix(
            field="cf-bpr", track_ids=self.track_ids, cache_dir=cache_dir, normalize=True
        )

    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        """
        Cosine similarity to the centroid of played tracks in BPR space.

        Played tracks are kept (SessionPolicy handles removal). Empty at turn 1.
        """
        if not ctx.played_track_ids:
            return []

        vecs = []
        for tid in ctx.played_track_ids:
            idx = self.tid_to_idx.get(tid)
            if idx is not None and self.has_vector[idx]:
                vecs.append(self.matrix[idx])

        if not vecs:
            return []

        centroid = np.mean(vecs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm == 0:
            return []
        centroid = centroid / norm

        sims = self.matrix @ centroid

        k = min(k, len(sims))
        top_indices = np.argpartition(-sims, k - 1)[:k]
        top_indices = top_indices[np.argsort(-sims[top_indices])]

        return [(self.track_ids[idx], float(sims[idx])) for idx in top_indices]
