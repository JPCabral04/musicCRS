"""Shared experiment harness: validation folds (T1) and experiment runner (T3).

The course only gives `train` and `test`. Our "validation set" is three
disjoint folds of 1,000 `train` sessions (seed 42), the same size as `test`,
because catalog diversity is not normalized by the number of turns. `val0` is
used for every experiment, `val0-2` to confirm final choices. The rest of
`train` (free pool) is for statistics only, never for scoring.

The runner scores any registered method with the official `evaluate()`, prints
ms/query, and caches predictions and top-200 lists (for fusion) in `cache/runs/`.
By default played tracks are removed (SessionPolicy defaults); `--keep_played`
reproduces the starter-kit baseline, which keeps them.

Usage:
    python -m retrieval.run_experiment --make_val_folds
    python -m retrieval.run_experiment --method bm25_baseline --split test --keep_played   # 0.1446
    python -m retrieval.run_experiment --method bm25_baseline --split val
    python -m retrieval.run_experiment --method bm25_baseline --split val --limit 200     # nDCG only
    python -m retrieval.run_experiment --method bm25_baseline --split val_all             # mean + spread
"""
import argparse
import json
import os
import pickle
import random
import time
from collections.abc import Callable

from datasets import load_dataset

from .bm25 import BM25Retriever
from .bm25_plus import BM25PlusRetriever
from .context import (Scorer, SessionPolicy, TurnContext, finalize_top_k,
                      iter_turn_contexts, load_sessions)
from .data_loader import MusicCatalogLoader
from .evaluation.evaluate import evaluate
from .evaluation.make_ground_truth import make_ground_truth
from .session_cf import SameArtistScorer
from .dense import DenseScorer
from .session_cf import SameArtistScorer, BPRSimilarityScorer

DATASET = "talkpl-ai/TalkPlayData-Challenge-Dataset"
VAL_FOLDS_PATH = "data/val_folds.json"
RUNS_DIR = "cache/runs"
CATALOG_SIZE = 47071
FOLDS = ["val0", "val1", "val2"]
REPORT_METRICS = ["ndcg@20", "catalog_diversity", "final_score"]


def make_val_folds(n: int = 1000, n_folds: int = 3, seed: int = 42,
                   output: str = VAL_FOLDS_PATH) -> dict[str, list[str]]:
    """Draws n_folds disjoint folds of n train session IDs and writes them to JSON.

    IDs are sorted before sampling so the result does not depend on dataset order.
    Returns {"val0": [...], "val1": [...], ...}.
    """
    ids = sorted(load_dataset(DATASET, split="train")["session_id"])
    assert len(ids) == len(set(ids)), "train session IDs are not unique"
    sample = random.Random(seed).sample(ids, n * n_folds)
    folds = {f"val{i}": sample[i * n:(i + 1) * n] for i in range(n_folds)}

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(folds, f, indent=2)
    print(f"Wrote {output}: {({k: len(v) for k, v in folds.items()})}, "
          f"free pool: {len(ids) - n * n_folds} of {len(ids)} train sessions, "
          f"val0[:2] = {folds['val0'][:2]}")
    return folds


def load_val_folds(path: str = VAL_FOLDS_PATH) -> dict[str, list[str]]:
    """Reads the folds written by make_val_folds."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class BM25BaselineScorer:
    """The starter-kit baseline as a Scorer: BM25 on the whole history (baseline_query)."""
    name = "bm25_baseline"

    def __init__(self) -> None:
        self.retriever = BM25Retriever()
        # reused by the runner (load it once)
        self.catalog = self.retriever.catalog

    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        track_ids = self.retriever.text_to_item_retrieval(
            ctx.baseline_query, k)
        # text_to_item_retrieval returns IDs only; -rank keeps the order (fusion uses ranks).
        return [(track_id, -rank) for rank, track_id in enumerate(track_ids)]


# Each factory builds a ready Scorer. New methods are registered here.
METHODS: dict[str, Callable[[], Scorer]] = {
    "bm25_baseline": BM25BaselineScorer,
    "bm25_plus": BM25PlusRetriever,
    "same_artist": lambda: SameArtistScorer(MusicCatalogLoader()),
    "dense": DenseScorer,
    "bpr_sim": lambda: BPRSimilarityScorer(MusicCatalogLoader()),
}


def underlying_split(split: str) -> str:
    """The dataset split behind our split name: val folds come from train."""
    return "test" if split == "test" else "train"


def sessions_for(split: str, limit: int | None = None) -> list[dict]:
    """Loads the sessions of "test", "val" (= val0), "val0", "val1" or "val2"; first `limit` only."""
    if split == "test":
        return load_sessions("test")[:limit]
    fold = "val0" if split == "val" else split
    return load_sessions("train", load_val_folds()[fold][:limit])


def ground_truth_for(split: str, session_ids: set[str]) -> list[dict]:
    """make_ground_truth on the underlying split, kept to the evaluated sessions.

    evaluate() looks up a prediction for every ground-truth turn, so an
    unfiltered ground truth raises KeyError.
    """
    return [gt for gt in make_ground_truth(split=underlying_split(split))
            if gt["session_id"] in session_ids]


def run(scorer: Scorer, catalog: MusicCatalogLoader, sessions: list[dict],
        policy: SessionPolicy, topk: int = 20, k: int = 200
        ) -> tuple[list[dict], dict, list[TurnContext], float]:
    """Runs one scorer on every (session, turn).

    Returns the predictions (challenge format), the raw top-k lists keyed by
    (session_id, turn_number) for fusion tuning, the contexts, and the seconds
    spent inside scorer.score (context building is not timed).
    """
    predictions, top_lists, contexts = [], {}, []
    score_seconds = 0.0
    for ctx in iter_turn_contexts(sessions, catalog):
        start = time.perf_counter()
        ranked = scorer.score(ctx, k)
        score_seconds += time.perf_counter() - start

        contexts.append(ctx)
        top_lists[(ctx.session_id, ctx.turn_number)] = ranked
        predictions.append({
            "session_id": ctx.session_id,
            "turn_number": ctx.turn_number,
            "predicted_track_ids": finalize_top_k(
                ranked, ctx.played_track_ids, topk, policy.exclude_played),
            "predicted_response": "",
        })
    return predictions, top_lists, contexts, score_seconds


def check_predictions(predictions: list[dict], contexts: list[TurnContext],
                      catalog_ids: set[str], exclude_played: bool, topk: int = 20) -> None:
    """Asserts the predictions are safe to score.

    evaluate() would not catch these: it counts every ID for diversity, so a
    list longer than 20 inflates it. Empty lists are allowed (a session scorer
    has nothing at turn 1) but counted.
    """
    keys = [(p["session_id"], p["turn_number"]) for p in predictions]
    assert len(keys) == len(
        set(keys)), "more than one prediction for a (session, turn)"
    assert keys == [(c.session_id, c.turn_number)
                    for c in contexts], "predictions/contexts mismatch"
    n_empty = 0
    for pred, ctx in zip(predictions, contexts):
        ids, key = pred["predicted_track_ids"], (
            ctx.session_id, ctx.turn_number)
        assert len(ids) <= topk, (key, len(ids))
        assert len(ids) == len(set(ids)), (key, "duplicate IDs")
        assert set(ids) <= catalog_ids, (key, set(ids) - catalog_ids)
        if exclude_played:
            assert not set(ids) & set(
                ctx.played_track_ids), (key, "played track predicted")
        n_empty += not ids
    if n_empty:
        print(
            f"warning: {n_empty} of {len(predictions)} prediction lists are empty")


def evaluate_split(scorer: Scorer, catalog: MusicCatalogLoader, method: str, split: str,
                   limit: int | None, policy: SessionPolicy, topk: int, run_name: str) -> dict:
    """Runs, checks, scores and caches one split. Returns the evaluate() dict."""
    sessions = sessions_for(split, limit)
    predictions, top_lists, contexts, score_seconds = run(
        scorer, catalog, sessions, policy, topk)
    check_predictions(predictions, contexts, set(catalog.metadata_dict),
                      policy.exclude_played, topk)

    ground_truth = ground_truth_for(split, {s["session_id"] for s in sessions})
    results = evaluate(predictions, ground_truth, CATALOG_SIZE)

    os.makedirs(RUNS_DIR, exist_ok=True)
    base = os.path.join(RUNS_DIR, f"{run_name}_{split}")
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump(predictions, f)
    with open(f"{base}_top200.pkl", "wb") as f:
        pickle.dump(top_lists, f)

    print(
        f"\n[{method} | {split} | {len(sessions)} sessions, {len(predictions)} turns]")
    print(json.dumps(results, indent=2))
    print(f"ms/query: {1000 * score_seconds / len(predictions):.1f} "
          f"(scorer only, {score_seconds:.0f} s total); saved {base}.json and _top200.pkl")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="MusicCRS experiment harness")
    parser.add_argument("--make_val_folds", action="store_true",
                        help="Write the validation folds and exit.")
    parser.add_argument("--n_val", type=int, default=1000,
                        help="Sessions per fold.")
    parser.add_argument("--n_folds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=VAL_FOLDS_PATH)
    parser.add_argument("--method", choices=sorted(METHODS))
    parser.add_argument("--split", default="val",
                        choices=["val", *FOLDS, "val_all", "test"])
    parser.add_argument("--limit", type=int, default=None,
                        help="First N sessions only (quick check: compare nDCG only).")
    parser.add_argument("--topk", type=int, default=20)
    parser.add_argument("--keep_played", action="store_true",
                        help="Do not remove played tracks (reproduces the starter-kit baseline).")
    args = parser.parse_args()

    if args.make_val_folds:
        make_val_folds(args.n_val, args.n_folds, args.seed, args.output)
        return
    if args.method is None:
        parser.error("--method is required (or use --make_val_folds)")

    policy = SessionPolicy(exclude_played=not args.keep_played)
    run_name = args.method + ("_keep_played" if args.keep_played else "")
    # never overwrite a full run's cache
    run_name += f"_limit{args.limit}" if args.limit else ""
    scorer = METHODS[args.method]()
    catalog = getattr(scorer, "catalog", None) or MusicCatalogLoader()
    if args.limit:
        print(f"note: --limit {args.limit}: catalog_diversity and final_score "
              f"are not comparable with full runs")

    if args.split != "val_all":
        evaluate_split(scorer, catalog, args.method, args.split, args.limit,
                       policy, args.topk, run_name)
        return

    per_fold = {fold: evaluate_split(scorer, catalog, args.method, fold, args.limit,
                                     policy, args.topk, run_name)
                for fold in FOLDS}
    print(
        f"\n[{args.method} | val_all] mean and spread (max - min) over {', '.join(FOLDS)}")
    for metric in REPORT_METRICS:
        values = [results[metric] for results in per_fold.values()]
        print(f"  {metric:18s} mean {sum(values) / len(values):.4f}   "
              f"spread {max(values) - min(values):.4f}   "
              f"({', '.join(f'{v:.4f}' for v in values)})")


if __name__ == "__main__":
    main()
