"""Session signals (T5): tracks by artists already played in the session.

In the dataset 65% of the gold tracks (turns 2-8) share an artist with a played
track, and that pool is small (~60 tracks). Played tracks are NOT removed here:
SessionPolicy does that once, in fusion and finalize_top_k.

Usage:
    python -m retrieval.run_experiment --method same_artist --split val
"""
from .context import TurnContext
from .data_loader import MusicCatalogLoader


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
