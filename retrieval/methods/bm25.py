"""BM25 baseline retrieval over track metadata.

Builds a BM25 index from selected metadata fields (e.g., `track_name`,
`artist_name`, `album_name`) and provides text-to-item retrieval. The
index is cached to disk for subsequent reuse.
"""
import os
import json
import bm25s

from ..base import RetrievalModule
from ..data_loader import MusicCatalogLoader, DEFAULT_DATASET_NAME, DEFAULT_SPLIT_TYPES

DEFAULT_CORPUS_TYPES = ["track_name", "artist_name", "album_name"]


class BM25Retriever(RetrievalModule):
    """BM25 retriever over track metadata."""

    def __init__(
        self,
        dataset_name: str = DEFAULT_DATASET_NAME,
        split_types: list[str] = DEFAULT_SPLIT_TYPES,
        corpus_types: list[str] = DEFAULT_CORPUS_TYPES,
        cache_dir: str = "./cache",
    ) -> None:
        """Initialize the BM25 retriever, building or loading the index.

        Args:
            dataset_name: Hugging Face dataset name containing track metadata.
            split_types: Dataset splits to load and concatenate.
            corpus_types: Metadata fields to include in the text corpus.
            cache_dir: Directory to cache the BM25 index and artifacts.
        """
        self.corpus_types = corpus_types
        self.corpus_name = "_".join(corpus_types)
        self.cache_dir = cache_dir
        self.catalog = MusicCatalogLoader(dataset_name, split_types)

        index_dir = os.path.join(self.cache_dir, "bm25", self.corpus_name)
        if not os.path.exists(index_dir):
            self._build_index(index_dir)
        self.bm25_model, self.track_ids = self._load_index(index_dir)

    def _stringify_metadata(self, metadata: dict) -> str:
        """Convert a metadata dict into a single string for indexing."""
        parts = []
        for corpus_type in self.corpus_types:
            value = metadata[corpus_type]
            if isinstance(value, list):
                value = ", ".join(value)
            parts.append(f"{corpus_type}: {value}")
        return "\n".join(parts)

    def _build_index(self, index_dir: str) -> None:
        """Build and persist a BM25 index over the loaded corpus."""
        track_ids = list(self.catalog.metadata_dict.keys())
        corpus = [
            self._stringify_metadata(self.catalog.metadata_dict[track_id])
            for track_id in track_ids
        ]
        corpus_tokens = bm25s.tokenize(corpus)
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        os.makedirs(index_dir, exist_ok=True)
        retriever.save(index_dir, corpus=corpus)
        with open(os.path.join(index_dir, "track_ids.json"), "w") as f:
            json.dump(track_ids, f, indent=2)

    def _load_index(self, index_dir: str) -> tuple[bm25s.BM25, list[str]]:
        """Load a cached BM25 index and its track id list."""
        bm25_model = bm25s.BM25.load(index_dir, load_corpus=True)
        track_ids = json.load(open(os.path.join(index_dir, "track_ids.json")))
        return bm25_model, track_ids

    def text_to_item_retrieval(self, query: str, topk: int) -> list[str]:
        query_tokens = bm25s.tokenize([query.lower()])
        results = self.bm25_model.retrieve(query_tokens, k=topk, return_as="tuple")
        return [self.track_ids[item["id"]] for item in results.documents[0]]

    def batch_text_to_item_retrieval(
        self, queries: list[str], topk: int
    ) -> list[list[str]]:
        query_tokens = bm25s.tokenize([q.lower() for q in queries])
        results = self.bm25_model.retrieve(query_tokens, k=topk, return_as="tuple")
        return [
            [self.track_ids[item["id"]] for item in results.documents[i]]
            for i in range(len(queries))
        ]
