"""Fusion tuning (T8): grid search over RRF weights on the cached validation lists.

The runner saved every component's raw top-200 lists in
`cache/runs/<method>_<fold>_top200.pkl`, so no scorer is re-run here (dense
would take minutes per run). Each weight set goes through the same `fuse()` as
FusionScorer, then `finalize_top_k` and the official `evaluate()`, so a number
found here must match `run_experiment --method fusion` exactly.

RRF ranks only depend on the weights' ratios (doubling all weights changes
nothing), so `bm25_plus` stays at 1 and only the other weights move.

Usage:
    python -m retrieval.run_experiment --method <each component> --split val_all   # the caches
    python -m retrieval.tune_fusion --check        # each component alone = its standalone val0 score
    python -m retrieval.tune_fusion --grid         # val0 only: all weight sets, saves the ranking
    python -m retrieval.tune_fusion --confirm 5    # top 5 of the grid on val0, val1, val2
"""
import argparse
import itertools
import json
import os
import pickle
import time

from .context import finalize_top_k, iter_turn_contexts
from .data_loader import MusicCatalogLoader
from .evaluation.evaluate import evaluate
from .fusion import K_RRF, fuse
from .run_experiment import (CATALOG_SIZE, FOLDS, REPORT_METRICS, RUNS_DIR,
                             ground_truth_for, sessions_for)

COMPONENTS = ["bm25_plus", "same_artist", "bpr_sim", "dense", "dense_last_turn"]
DENSE_VARIANTS = ["dense", "dense_last_turn"]  # T6 left the choice to fusion: one of the two
GRID = [0, 0.5, 1, 2, 4]                      # weights relative to bm25_plus = 1
GRID_K_RRF = 60                               # k_rrf of the first pass over all weight sets (fusion.K_RRF is the frozen result)
K_RRF_VALUES = [10, 30, 60, 100]              # tried on the best weight sets only
GRID_PATH = os.path.join(RUNS_DIR, "fusion_grid_val0.json")


def load_fold(fold: str, catalog: MusicCatalogLoader) -> dict:
    """Contexts (for the played tracks), ground truth and every component's cached lists of one fold."""
    sessions = sessions_for(fold)
    cached = {}
    for method in COMPONENTS:
        with open(os.path.join(RUNS_DIR, f"{method}_{fold}_top200.pkl"), "rb") as f:
            cached[method] = pickle.load(f)  # our own file, written by run_experiment
    return {
        "contexts": list(iter_turn_contexts(sessions, catalog)),
        "ground_truth": ground_truth_for(fold, {s["session_id"] for s in sessions}),
        "cached": cached,
    }


def score_weights(data: dict, weights: dict[str, float], k_rrf: int = K_RRF) -> dict:
    """Fuses the cached lists of every turn with these weights and returns evaluate()'s dict."""
    predictions = []
    for ctx in data["contexts"]:
        key = (ctx.session_id, ctx.turn_number)
        lists = {name: data["cached"][name][key] for name, w in weights.items() if w}
        ranked = fuse(lists, ctx.played_track_ids, weights, k_rrf)
        predictions.append({
            "session_id": ctx.session_id,
            "turn_number": ctx.turn_number,
            "predicted_track_ids": finalize_top_k(ranked, ctx.played_track_ids),
            "predicted_response": "",
        })
    return evaluate(predictions, data["ground_truth"], CATALOG_SIZE)


def weight_grid() -> list[dict[str, float]]:
    """bm25_plus = 1; same_artist, bpr_sim and one dense variant take every GRID value."""
    sets = []
    for w_artist, w_bpr, w_dense in itertools.product(GRID, repeat=3):
        # with weight 0 the two dense variants are the same set: keep one
        for dense in DENSE_VARIANTS if w_dense else DENSE_VARIANTS[:1]:
            sets.append({"bm25_plus": 1.0, "same_artist": w_artist,
                         "bpr_sim": w_bpr, dense: w_dense})
    return sets


def fmt(weights: dict[str, float]) -> str:
    return ", ".join(f"{name} {w:g}" for name, w in weights.items() if w)


def check(catalog: MusicCatalogLoader) -> None:
    """Each component alone (weight 1) must give back its standalone val0 score."""
    data = load_fold("val0", catalog)
    for method in COMPONENTS:
        results = score_weights(data, {method: 1.0})
        print(f"{method:16s} " + "  ".join(
            f"{m} {results[m]:.4f}" for m in REPORT_METRICS))


def grid(catalog: MusicCatalogLoader) -> None:
    """Scores every weight set on val0 (k_rrf 60), then other k_rrf on the top 3; saves the ranking."""
    data = load_fold("val0", catalog)
    sets = weight_grid()
    start = time.perf_counter()
    rows = [{"weights": w, "k_rrf": GRID_K_RRF, **score_weights(data, w, GRID_K_RRF)} for w in sets]
    print(f"{len(sets)} weight sets in {time.perf_counter() - start:.0f} s")
    rows.sort(key=lambda row: -row["final_score"])
    for row in rows[:3]:
        rows += [{"weights": row["weights"], "k_rrf": k, **score_weights(data, row["weights"], k)}
                 for k in K_RRF_VALUES if k != GRID_K_RRF]
    rows.sort(key=lambda row: -row["final_score"])

    with open(GRID_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print(f"top 10 on val0 (saved all to {GRID_PATH}):")
    for row in rows[:10]:
        print(f"  final {row['final_score']:.4f}  ndcg {row['ndcg@20']:.4f}  "
              f"div {row['catalog_diversity']:.4f}  k_rrf {row['k_rrf']:3d}  {fmt(row['weights'])}")


def confirm(catalog: MusicCatalogLoader, n: int) -> None:
    """Scores the top n sets of the val0 grid on all three folds: mean and spread (max - min)."""
    with open(GRID_PATH, encoding="utf-8") as f:
        rows = json.load(f)[:n]
    per_fold = {}
    for fold in FOLDS:
        data = load_fold(fold, catalog)
        per_fold[fold] = [score_weights(data, row["weights"], row["k_rrf"]) for row in rows]
    for i, row in enumerate(rows):
        print(f"\n#{i + 1}  k_rrf {row['k_rrf']}  {fmt(row['weights'])}")
        for metric in REPORT_METRICS:
            values = [per_fold[fold][i][metric] for fold in FOLDS]
            print(f"  {metric:18s} mean {sum(values) / len(values):.4f}   "
                  f"spread {max(values) - min(values):.4f}   "
                  f"({', '.join(f'{v:.4f}' for v in values)})")


def main() -> None:
    parser = argparse.ArgumentParser(description="RRF weight tuning on cached val lists")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--grid", action="store_true")
    parser.add_argument("--confirm", type=int, metavar="N")
    args = parser.parse_args()

    catalog = MusicCatalogLoader()
    if args.check:
        check(catalog)
    if args.grid:
        grid(catalog)
    if args.confirm:
        confirm(catalog, args.confirm)


if __name__ == "__main__":
    main()
