"""Dense retrieval module using Qwen3 embeddings (T6).

Loads precomputed track embeddings from HuggingFace, L2-normalizes them,
and ranks tracks by cosine similarity with the user's message, embedded by
Qwen/Qwen3-Embedding-0.6B (the model that made the track vectors).

Encoding a query is the slow part (~2.3 s on a laptop CPU, one at a time), so
query vectors are cached by text in cache/dense/, and `prepare` embeds all of
a run's queries in batches (on the GPU if there is one) before scoring.

Usage:
    # Sanity check: does our encoder match the precomputed vectors?
    python -m retrieval.dense

    # Live latency of one query (no cache), on val0 messages
    python -m retrieval.dense --time 100

    # Run experiment via harness
    python -m retrieval.run_experiment --method dense --split val
"""

import argparse
import os
import pickle
import time
import numpy as np
from typing import Tuple, List, Optional
from datasets import load_dataset

from .context import TurnContext
from .data_loader import MusicCatalogLoader

EMB_DATASET = "talkpl-ai/TalkPlayData-Challenge-Track-Embeddings"
DEFAULT_FIELD = "metadata-qwen3_embedding_0.6b"
MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
CATALOG_SIZE = 47071
# Qwen3's default is 32k tokens; user messages go up to ~1,100 words.
MAX_SEQ_LENGTH = 512


def load_track_matrix(
    field: str = DEFAULT_FIELD,
    track_ids: Optional[List[str]] = None,
    cache_dir: str = "./cache/embeddings",
    normalize: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """Loads precomputed embeddings for all tracks from HuggingFace,
    aligns rows to track_ids, L2-normalizes them, and saves to cache_dir.

    Row i of the matrix is track_ids[i] (the catalog order, same as BM25).
    Tracks with an empty vector (616 in cf-bpr) get a zero row.

    Returns:
        matrix: float32 array of shape (N, dim)
        has_vector: bool array indicating tracks with non-empty embeddings
    """

    if track_ids is None:
        track_ids = list(MusicCatalogLoader().metadata_dict)

    os.makedirs(cache_dir, exist_ok=True)
    suffix = "" if normalize else "_raw"
    cache_path = os.path.join(cache_dir, f"{field}{suffix}.npy")
    mask_path = os.path.join(cache_dir, f"{field}{suffix}_mask.npy")

    # Load from local cache if exists
    if os.path.exists(cache_path) and os.path.exists(mask_path):
        matrix = np.load(cache_path)
        has_vector = np.load(mask_path)
        assert len(matrix) == len(track_ids), (cache_path, len(matrix))
        return matrix, has_vector

    print(f"Downloading and processing precomputed embeddings for '{field}'...")
    ds = load_dataset(EMB_DATASET, split="all_tracks")  # never "test_tracks": it holds the test golds
    # Only the two columns we need; pandas turns each vector into a numpy array at once.
    table = ds.select_columns(["track_id", field]).to_pandas()
    vectors = dict(zip(table["track_id"], table[field]))

    missing = [tid for tid in track_ids if tid not in vectors]
    assert not missing, f"{len(missing)} catalog tracks have no row in {EMB_DATASET}"

    # Find vector dimension
    dim = max(len(vec) for vec in vectors.values())
    matrix = np.zeros((len(track_ids), dim), dtype=np.float32)
    has_vector = np.zeros(len(track_ids), dtype=bool)

    for i, tid in enumerate(track_ids):
        vec = vectors[tid]
        if len(vec) == dim:
            matrix[i] = vec
            has_vector[i] = True

    if normalize:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # Prevent division by zero
        matrix = matrix / norms

    np.save(cache_path, matrix)
    np.save(mask_path, has_vector)

    print(f"Saved {field} matrix {matrix.shape} to {cache_path} "
          f"({(~has_vector).sum()} tracks without a vector)")
    return matrix, has_vector


def load_encoder(model_name: str = MODEL_NAME, device: Optional[str] = None):
    """Loads the Qwen3 encoder: on the GPU in float16 if there is one, else on the CPU."""
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for DenseScorer. Run: pip install sentence-transformers torch"
        )
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"Loading query encoder model '{model_name}' on {device} ({dtype})...")
    model = SentenceTransformer(model_name, device=device, model_kwargs={"torch_dtype": dtype})
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


class DenseScorer:
    """
    Embeds the user's message with Qwen/Qwen3-Embedding-0.6B and scores all
    catalog tracks by cosine similarity against precomputed embeddings.
    """

    name = "dense"

    def __init__(
        self,
        field: str = DEFAULT_FIELD,
        query_mode: str = "current",   # "current" | "current+last_turn"
        use_prompt: bool = True,
        model_name: str = MODEL_NAME,
        cache_dir: str = "./cache",
        device: Optional[str] = None,
    ) -> None:
        assert query_mode in ("current", "current+last_turn"), query_mode
        self.query_mode = query_mode
        # Qwen3 embeds queries with an instruction ("query" prompt) and documents without.
        self.prompt_name = "query" if use_prompt else None

        self.catalog = MusicCatalogLoader()
        self.track_ids = list(self.catalog.metadata_dict)

        # Load precomputed track embeddings (L2-normalized)
        self.matrix, self.has_vector = load_track_matrix(
            field=field, track_ids=self.track_ids,
            cache_dir=os.path.join(cache_dir, "embeddings"), normalize=True
        )
        self.model = load_encoder(model_name, device)

        # Query vectors by text: shared by every split and query mode.
        prompt_tag = "prompt" if use_prompt else "noprompt"
        self.query_cache_path = os.path.join(cache_dir, "dense", f"queries_{prompt_tag}.pkl")
        self.query_cache: dict[str, np.ndarray] = {}
        # Our own local file (like the runner's _top200.pkl), never downloaded.
        if os.path.exists(self.query_cache_path):
            with open(self.query_cache_path, "rb") as f:
                self.query_cache = pickle.load(f)

    def query_text(self, ctx: TurnContext) -> str:
        """The text to embed: the current message, optionally after the previous user message."""
        if self.query_mode == "current":
            return ctx.current_message
        earlier_user = [content for role, content in ctx.history if role == "user"]
        return "\n".join(earlier_user[-1:] + [ctx.current_message])

    def encode_queries(self, texts: List[str], batch_size: int = 32,
                       show_progress_bar: bool = False) -> np.ndarray:
        """
        Embeds query texts (with the query prompt if use_prompt) and L2-normalizes.
        """
        vecs = self.model.encode(
            texts,
            prompt_name=self.prompt_name,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress_bar,
        )
        return vecs.astype(np.float32)

    def prepare(self, contexts: List[TurnContext]) -> None:
        """Embeds every query of a run that is not cached yet, in batches, and saves the cache.

        Called once by the experiment runner before scoring. Texts are sorted by
        length so each batch holds similar lengths (less padding).
        """
        texts = {self.query_text(ctx) for ctx in contexts}
        missing = sorted((t for t in texts if t.strip() and t not in self.query_cache), key=len)
        print(f"dense: {len(texts) - len(missing)} of {len(texts)} queries cached, "
              f"embedding {len(missing)}")
        if not missing:
            return
        vecs = self.encode_queries(missing, show_progress_bar=True)
        self.query_cache.update(zip(missing, vecs))
        os.makedirs(os.path.dirname(self.query_cache_path), exist_ok=True)
        with open(self.query_cache_path, "wb") as f:
            pickle.dump(self.query_cache, f)

    def score(self, ctx: TurnContext, k: int = 200) -> List[Tuple[str, float]]:
        """
        Scores tracks based on cosine similarity with the query text. Played tracks are kept.
        """
        query_text = self.query_text(ctx)
        if not query_text.strip():
            return []

        q_vec = self.query_cache.get(query_text)
        if q_vec is None:  # not prepared (e.g. a live turn): encode now
            q_vec = self.encode_queries([query_text])[0]
            self.query_cache[query_text] = q_vec

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
    print("\n=================== Dense Sanity Check ===================")
    cat = MusicCatalogLoader()
    track_ids = list(cat.metadata_dict)

    # Load precomputed embeddings
    matrix, has_vector = load_track_matrix(DEFAULT_FIELD, track_ids=track_ids)
    assert matrix.shape[0] == CATALOG_SIZE, matrix.shape

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

    # Same encoder setup as DenseScorer (device, dtype, max_seq_length)
    model = load_encoder()

    # Document encoding without prompt
    t0 = time.time()
    doc_vecs = model.encode(sample_texts, normalize_embeddings=True, show_progress_bar=True)
    t_elapsed = time.time() - t0

    ranks = []
    for i, idx in enumerate(sample_indices):
        d_vec = doc_vecs[i].astype(np.float32)
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


def time_live_queries(n: int = 100) -> None:
    """Times one live query (encode + cosine + top 200, no cache) on the first n val0 turns.

    This is the latency the Part 2 agent pays per turn; the runner's ms/query
    only measures cache lookups once `prepare` has run.
    """
    from .context import iter_turn_contexts
    from .run_experiment import sessions_for  # local import: run_experiment imports this module

    scorer = DenseScorer()
    contexts = list(iter_turn_contexts(sessions_for("val", n // 8 + 1), scorer.catalog))[:n]
    scorer.score(contexts[0])  # warm-up (first call allocates GPU memory)
    times = []
    for ctx in contexts:
        scorer.query_cache.pop(scorer.query_text(ctx), None)  # force a real encode
        start = time.perf_counter()
        scorer.score(ctx)
        times.append(1000 * (time.perf_counter() - start))
    print(f"live dense query over {len(times)} val0 turns: median {np.median(times):.1f} ms, "
          f"mean {np.mean(times):.1f} ms, max {np.max(times):.1f} ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dense retrieval checks")
    parser.add_argument("--time", type=int, default=None, metavar="N",
                        help="Time N live queries instead of running the sanity check.")
    args = parser.parse_args()
    if args.time:
        time_live_queries(args.time)
    else:
        sanity_check()
