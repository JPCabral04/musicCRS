"""Dense retrieval module using Qwen3 embeddings.

Loads precomputed track embeddings from HuggingFace, L2-normalizes them,
and ranks tracks by cosine similarity using Qwen/Qwen3-Embedding-0.6B.

Usage:
    # Run sanity check directly
    python -m retrieval.dense

    # Run experiment via harness
    python -m retrieval.run_experiment --method dense --split val
"""

import os
import time
import numpy as np
from typing import Tuple, List, Optional
from datasets import load_dataset

from .bm25 import BM25Retriever
from .context import TurnContext, Scorer
from .data_loader import MusicCatalogLoader

EMB_DATASET = "talkpl-ai/TalkPlayData-Challenge-Track-Embeddings"
DEFAULT_FIELD = "metadata-qwen3_embedding_0.6b"


def load_track_matrix(
    field: str = DEFAULT_FIELD,
    track_ids: Optional[List[str]] = None,
    cache_dir: str = "./cache/embeddings",
    normalize: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """Loads precomputed embeddings for all tracks from HuggingFace, 
    aligns rows to track_ids, L2-normalizes them, and saves to cache_dir.

    Returns:
        matrix: float32 array of shape (N, dim)
        has_vector: bool array indicating tracks with non-empty embeddings
    """

    if track_ids is None:
        bm25_temp = BM25Retriever()
        track_ids = bm25_temp.track_ids

    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{field}.npy")
    mask_path = os.path.join(cache_dir, f"{field}_mask.npy")

    # Load from local cache if exists
    if os.path.exists(cache_path) and os.path.exists(mask_path):
        matrix = np.load(cache_path)
        has_vector = np.load(mask_path)
        return matrix, has_vector

    print(f"Downloading and processing precomputed embeddings for '{field}'...")
    ds = load_dataset(EMB_DATASET, split="all_tracks")

    id_to_row = {row["track_id"]: i for i, row in enumerate(ds)}

    # Find vector dimension
    sample_vec = next(row[field] for row in ds if row[field] and len(row[field]) > 0)
    dim = len(sample_vec)
    num_tracks = len(track_ids)

    matrix = np.zeros((num_tracks, dim), dtype=np.float32)
    has_vector = np.zeros(num_tracks, dtype=bool)

    for i, tid in enumerate(track_ids):
        if tid in id_to_row:
            row_idx = id_to_row[tid]
            vec = ds[row_idx][field]
            if vec and len(vec) == dim:
                matrix[i] = np.array(vec, dtype=np.float32)
                has_vector[i] = True

    if normalize:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # Prevent division by zero
        matrix = matrix / norms

    np.save(cache_path, matrix)
    np.save(mask_path, has_vector)

    print(f"Saved {field} matrix {matrix.shape} to {cache_path}")
    return matrix, has_vector


class DenseScorer:
    """
    Embeds the current user message with Qwen/Qwen3-Embedding-0.6B (using query prompt)
    and scores all catalog tracks by cosine similarity against precomputed embeddings.
    """

    name = "dense"

    def __init__(
        self,
        field: str = DEFAULT_FIELD,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        cache_dir: str = "./cache/embeddings",
        device: str = "cpu",
    ) -> None:
        self.catalog = MusicCatalogLoader()
        bm25_ref = BM25Retriever()
        self.track_ids = bm25_ref.track_ids

        # Load precomputed track embeddings (L2-normalized)
        self.matrix, self.has_vector = load_track_matrix(
            field=field, track_ids=self.track_ids, cache_dir=cache_dir, normalize=True
        )

        print(f"Loading query encoder model '{model_name}'...")
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name, device=device)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for DenseScorer. Run: pip install sentence-transformers torch"
            )

    def encode_query(self, text: str) -> np.ndarray:
        """
        Embeds query text using prompt_name='query' and L2-normalizes.
        """
        if not text or not text.strip():
            return np.zeros(self.matrix.shape[1], dtype=np.float32)

        # Encode using the official query prompt instruction for Qwen3
        vec = self.model.encode(
            [text],
            prompt_name="query",
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return vec.astype(np.float32)

    def score(self, ctx: TurnContext, k: int = 200) -> List[Tuple[str, float]]:
        """
        Scores tracks based on cosine similarity with current user message.
        """
        query_text = ctx.current_message
        if not query_text or not query_text.strip():
            return []

        q_vec = self.encode_query(query_text)
        if np.all(q_vec == 0):
            return []

        # Cosine similarity matrix product (both matrix and q_vec are L2-normalized)
        sims = self.matrix @ q_vec

        k = min(k, len(sims))
        top_indices = np.argpartition(-sims, k - 1)[:k]
        top_indices = top_indices[np.argsort(-sims[top_indices])]

        return [(self.track_ids[idx], float(sims[idx])) for idx in top_indices]


def sanity_check(n_samples: int = 50, seed: int = 42) -> None:
    """
    Embeds n_samples tracks' metadata with Qwen/Qwen3-Embedding-0.6B (document mode)
    and verifies their rank against precomputed metadata embeddings.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers is not installed. Run: pip install sentence-transformers torch")
        return

    print("\n=================== Dense Sanity Check ===================")
    cat = MusicCatalogLoader()
    bm25_ref = BM25Retriever()
    track_ids = bm25_ref.track_ids

    # Load precomputed embeddings
    matrix, has_vector = load_track_matrix(DEFAULT_FIELD, track_ids=track_ids)

    # Sample tracks that have vectors
    rng = np.random.RandomState(seed)
    valid_indices = np.where(has_vector)[0]
    sample_indices = rng.choice(valid_indices, size=min(n_samples, len(valid_indices)), replace=False)

    sample_texts = []
    for idx in sample_indices:
        tid = track_ids[idx]
        meta = cat.metadata_dict[tid]
        name = ", ".join(meta.get("track_name", [])) if isinstance(meta.get("track_name"), list) else meta.get("track_name", "")
        artist = ", ".join(meta.get("artist_name", [])) if isinstance(meta.get("artist_name"), list) else meta.get("artist_name", "")
        album = ", ".join(meta.get("album_name", [])) if isinstance(meta.get("album_name"), list) else meta.get("album_name", "")
        text = f"track_name: {name}\nartist_name: {artist}\nalbum_name: {album}"
        sample_texts.append(text)

    print(f"Loading local encoder Qwen/Qwen3-Embedding-0.6B for {len(sample_texts)} tracks...")
    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")

    # Document encoding without prompt
    t0 = time.time()
    doc_vecs = model.encode(sample_texts, normalize_embeddings=True, show_progress_bar=True)
    t_elapsed = time.time() - t0

    ranks = []
    for i, idx in enumerate(sample_indices):
        d_vec = doc_vecs[i]
        sims = matrix @ d_vec
        rank = int(np.sum(sims > sims[idx])) + 1
        ranks.append(rank)

    median_rank = float(np.median(ranks))
    mean_rank = float(np.mean(ranks))

    print(f"\n--- Sanity Check Summary ---")
    print(f"Sample size: {len(ranks)}")
    print(f"First 10 ranks: {ranks[:10]}")
    print(f"Median Rank: {median_rank}")
    print(f"Mean Rank: {mean_rank:.2f}")
    print(f"Encoding time: {t_elapsed:.2f}s ({1000 * t_elapsed / len(ranks):.1f} ms/track)")

    if median_rank <= 5:
        print("\nSUCCESS: Local Qwen3 encoder matches precomputed HuggingFace embeddings.")
    else:
        print("\nFAIL: Median rank is high!")


if __name__ == "__main__":
    sanity_check()