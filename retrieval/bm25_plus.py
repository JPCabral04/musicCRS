from typing import List, Tuple, Dict, Optional
import bm25s
from .bm25 import BM25Retriever, DEFAULT_DATASET_NAME, DEFAULT_SPLIT_TYPES

DEFAULT_CORPUS_TYPES_PLUS = ["track_name", "artist_name", "album_name", "tag_list"]

class BM25PlusRetriever(BM25Retriever):
    """
    Indexes 'tag_list' alongside standard track metadata.
    Allows separate scoring and weighting for current user message and conversation history.
    Excludes previously played tracks from predictions.
    """

    def __init__(
        self,
        dataset_name: str = DEFAULT_DATASET_NAME,
        split_types: list[str] = DEFAULT_SPLIT_TYPES,
        corpus_types: list[str] = DEFAULT_CORPUS_TYPES_PLUS,
        w_current: float = 1.0,
        w_history: float = 0.3,
        cache_dir: str = "./cache",
    ) -> None:
        super().__init__(
            dataset_name=dataset_name,
            split_types=split_types,
            corpus_types=corpus_types,
            cache_dir=cache_dir,
        )
        self.w_current = w_current
        self.w_history = w_history

    def _retrieve_candidates(self, text: str, k: int = 1000) -> Dict[str, float]:
        """Retrieves top-k candidate track IDs and their BM25 scores for a given text."""
        if not text or not text.strip():
            return {}

        query_tokens = bm25s.tokenize([text.lower()], show_progress=False)
        results = self.bm25_model.retrieve(
            query_tokens, k=min(k, len(self.track_ids)), return_as="tuple"
        )

        candidates: Dict[str, float] = {}
        if len(results.documents) > 0:
            for doc, score in zip(results.documents[0], results.scores[0]):
                track_id = self.track_ids[doc["id"]]
                candidates[track_id] = float(score)
        return candidates

    def score_from_parts(
        self,
        current_message: str,
        history_text: str = "",
        played_track_ids: Optional[List[str]] = None,
        topk: int = 200,
    ) -> List[Tuple[str, float]]:
        """
        Computes weighted score: w_current * scores(current) + w_history * scores(history).
        Excludes tracks already played in the session.
        """
        curr_candidates = self._retrieve_candidates(current_message, k=1000)
        hist_candidates = (
            self._retrieve_candidates(history_text, k=1000) if history_text else {}
        )

        combined_scores: Dict[str, float] = {}

        for tid, score in curr_candidates.items():
            combined_scores[tid] = combined_scores.get(tid, 0.0) + (self.w_current * score)

        for tid, score in hist_candidates.items():
            combined_scores[tid] = combined_scores.get(tid, 0.0) + (self.w_history * score)

        played_set = set(played_track_ids) if played_track_ids else set()
        for played_id in played_set:
            combined_scores.pop(played_id, None)

        sorted_results = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_results[:topk]

    def text_to_item_retrieval(self, query: str, topk: int) -> list[str]:
        """Base interface implementation for compatibility with RetrievalModule."""
        query_tokens = bm25s.tokenize([query.lower()], show_progress=False)
        results = self.bm25_model.retrieve(query_tokens, k=topk, return_as="tuple")
        return [self.track_ids[item["id"]] for item in results.documents[0]]