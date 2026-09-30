from .data_loader import MusicCatalogLoader

class SameArtistScorer:
    """
    Identifies catalog tracks sharing an artist ID with previously played tracks in the session.
    Ranks tracks by played-artist recency and track popularity.
    """

    def __init__(self, catalog: MusicCatalogLoader) -> None:
        self.catalog = catalog
        self.metadata = catalog.metadata_dict

        self.artist_to_tracks: dict[str, list[str]] = {}
        for tid, meta in self.metadata.items():
            artist_ids = meta.get("artist_id", [])
            if isinstance(artist_ids, str):
                artist_ids = [artist_ids]

            for aid in artist_ids:
                if aid not in self.artist_to_tracks:
                    self.artist_to_tracks[aid] = []
                self.artist_to_tracks[aid].append(tid)

    def score(
        self,
        played_track_ids: list[str],
        topk: int = 200,
        recency_decay: float = 0.7,
    ) -> list[tuple[str, float]]:
        """
        Scores candidate tracks sharing artist IDs with played session tracks.
        """
        if not played_track_ids:
            return []

        played_set = set(played_track_ids)
        candidate_scores: dict[str, float] = {}

        for rank_idx, tid in enumerate(reversed(played_track_ids)):
            recency_weight = recency_decay**rank_idx

            meta = self.metadata.get(tid, {})
            artist_ids = meta.get("artist_id", [])
            if isinstance(artist_ids, str):
                artist_ids = [artist_ids]

            for aid in artist_ids:
                matching_tracks = self.artist_to_tracks.get(aid, [])
                for cand_id in matching_tracks:
                    if cand_id in played_set:
                        continue

                    pop = float(self.metadata.get(cand_id, {}).get("popularity", 0) or 0)
                    score = recency_weight * 1000.0 + pop

                    if cand_id not in candidate_scores or score > candidate_scores[cand_id]:
                        candidate_scores[cand_id] = score

        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_candidates[:topk]