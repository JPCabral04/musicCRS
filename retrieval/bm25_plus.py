"""Improved BM25 (T4): tags in the index, current message and history scored apart.

Three changes over the baseline: `tag_list` is indexed (so genre/mood words can
match), and the current user message and the earlier conversation are scored
as two separate queries with their own weights. On val0 the current message
alone is weak; w_history=3.0 was best (nDCG flat from 1.5 on). nDCG@20 stays
at the baseline's level: the gain over the baseline is catalog diversity,
mostly from the tags. Played tracks are NOT removed here: SessionPolicy does
that once, in fusion and finalize_top_k.

Usage:
    python -m retrieval.run_experiment --method bm25_plus --split val
"""
import bm25s
import numpy as np

from .bm25 import BM25Retriever
from .context import TurnContext

DEFAULT_CORPUS_TYPES_PLUS = ["track_name", "artist_name", "album_name", "tag_list"]
# Fields of a played track added to the history query (no track_id: a UUID is noise).
PLAYED_FIELDS = ["track_name", "artist_name", "album_name"]


class BM25PlusRetriever(BM25Retriever):
    """BM25 over name/artist/album/tags with a weighted current-vs-history query."""
    name = "bm25_plus"

    def __init__(self, corpus_types: list[str] = DEFAULT_CORPUS_TYPES_PLUS,
                 w_current: float = 1.0, w_history: float = 3.0,
                 cache_dir: str = "./cache") -> None:
        """Builds/loads the index via BM25Retriever and stores the query weights."""
        super().__init__(corpus_types=corpus_types, cache_dir=cache_dir)
        self.w_current = w_current
        self.w_history = w_history

    def _query_scores(self, text: str) -> np.ndarray:
        """BM25 scores of all tracks for one text (zeros if it has no known tokens)."""
        tokens = bm25s.tokenize([text], return_ids=False, show_progress=False)[0]
        # get_scores crashes on [] (e.g. "the one again" is all stopwords).
        tokens = [t for t in tokens if t in self.bm25_model.vocab_dict]
        if not tokens:
            return np.zeros(len(self.track_ids))
        return self.bm25_model.get_scores(tokens)

    def history_text(self, ctx: TurnContext) -> str:
        """Earlier user/assistant messages plus the played tracks' name, artist and album."""
        parts = []
        for role, content in ctx.history:
            if role == "music":
                metadata = self.catalog.metadata_dict.get(content, {})
                for field in PLAYED_FIELDS:
                    parts.extend(metadata.get(field, []))
            else:
                parts.append(content)
        return "\n".join(parts)

    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        """w_current * scores(current message) + w_history * scores(history). Played tracks kept."""
        scores = self.w_current * self._query_scores(ctx.current_message)
        if self.w_history:
            scores = scores + self.w_history * self._query_scores(self.history_text(ctx))
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]        # the k best rows, unordered
        top = top[np.argsort(-scores[top])]              # ordered best first
        return [(self.track_ids[row], float(scores[row])) for row in top]
