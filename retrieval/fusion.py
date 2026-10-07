"""Fusion (T8): merges the component lists with weighted Reciprocal Rank Fusion.

Each component is right on different turns: BM25 when an artist is named,
dense for moods, the session lists (same artist, BPR) from turn 2 on. RRF
uses only ranks, so the components' score scales never have to be calibrated:

    score(track) = sum over lists of  weight_list / (k_rrf + rank_in_list)

SessionPolicy is applied here, once: played tracks leave every list before RRF
(so they do not take rank positions), and `use_same_artist=False` gives
`same_artist` weight 0. Components are named as in `run_experiment.METHODS`,
so weights tuned on the cached lists (`tune_fusion.py`) are copied here as is.

Usage:
    python -m retrieval.run_experiment --method fusion --split val
"""
from .bm25_plus import BM25PlusRetriever
from .context import Scorer, SessionPolicy, TurnContext
from .data_loader import MusicCatalogLoader
from .dense import DenseScorer
from .session_cf import BPRSimilarityScorer, SameArtistScorer

# Tuned by tune_fusion.py on val0, confirmed on val0-2 (final mean 0.2753, spread 0.0106;
# bm25_plus alone 0.2214). k_rrf 10 beat 3, 5, 30, 60 and 100; dense (current message)
# tied dense_last_turn, so the simpler query was kept.
K_RRF = 10     # rank damping: higher = flatter (the top of a list counts less)
DEPTH = 200    # how many candidates each component returns (the cached lists' size)
WEIGHTS = {"bm25_plus": 1.0, "same_artist": 2.0, "bpr_sim": 2.0, "dense": 1.0}


def rrf(lists: dict[str, list[tuple[str, float]]], weights: dict[str, float],
        k_rrf: int = K_RRF) -> list[tuple[str, float]]:
    """Weighted RRF of ranked lists (rank 1 = best); lists with weight 0 or missing are ignored.

    Ties are broken by track ID, so the result does not depend on the order of `lists`.
    """
    fused: dict[str, float] = {}
    for name, ranked in lists.items():
        weight = weights.get(name, 0.0)
        if not weight:
            continue
        for rank, (track_id, _) in enumerate(ranked, start=1):
            fused[track_id] = fused.get(track_id, 0.0) + weight / (k_rrf + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def fuse(lists: dict[str, list[tuple[str, float]]], played: tuple[str, ...],
         weights: dict[str, float], k_rrf: int = K_RRF,
         policy: SessionPolicy = SessionPolicy()) -> list[tuple[str, float]]:
    """Applies the SessionPolicy to every list, then RRF. Shared by FusionScorer and the tuning."""
    skip = set(played) if policy.exclude_played else set()
    if not policy.use_same_artist:
        weights = {**weights, "same_artist": 0.0}
    kept = {name: [(t, s) for t, s in ranked if t not in skip]
            for name, ranked in lists.items()}
    return rrf(kept, weights, k_rrf)


class FusionScorer:
    """Runs every component scorer and fuses their lists with weighted RRF."""
    name = "fusion"

    def __init__(self, scorers: dict[str, Scorer], weights: dict[str, float],
                 k_rrf: int, catalog: MusicCatalogLoader) -> None:
        self.scorers = scorers
        self.weights = weights
        self.k_rrf = k_rrf
        self.catalog = catalog  # reused by the runner (load it once)

    def prepare(self, contexts: list[TurnContext]) -> None:
        """Forwards the runner's optional prepare hook (dense embeds its queries in batches)."""
        for scorer in self.scorers.values():
            if hasattr(scorer, "prepare"):
                scorer.prepare(contexts)

    def score(self, ctx: TurnContext, k: int = 200,
              policy: SessionPolicy = SessionPolicy()) -> list[tuple[str, float]]:
        """Top-k fused (track_id, rrf score). Played tracks removed unless the policy keeps them."""
        lists = {name: scorer.score(ctx, DEPTH) for name, scorer in self.scorers.items()}
        return fuse(lists, ctx.played_track_ids, self.weights, self.k_rrf, policy)[:k]


def build_fusion(weights: dict[str, float] = WEIGHTS, k_rrf: int = K_RRF) -> FusionScorer:
    """Builds only the components with a non-zero weight; all share one catalog."""
    bm25 = BM25PlusRetriever()
    factories = {
        "bm25_plus": lambda: bm25,
        "same_artist": lambda: SameArtistScorer(bm25.catalog),
        "bpr_sim": lambda: BPRSimilarityScorer(bm25.catalog),
        "dense": lambda: DenseScorer(),
        "dense_last_turn": lambda: DenseScorer(query_mode="current+last_turn"),
    }
    scorers = {name: factories[name]() for name, weight in weights.items() if weight}
    return FusionScorer(scorers, weights, k_rrf, bm25.catalog)
