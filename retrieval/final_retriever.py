"""Final retriever (T9): the tuned fusion wrapped as the course's RetrievalModule.

Two entry points:
- `retrieve(ctx)`: the full pipeline for one turn (bm25_plus + same_artist +
  bpr_sim + dense, fused with the T8 weights). Our predictions come from here,
  and the Part 2 agent calls it with its own SessionPolicy.
- `text_to_item_retrieval(query)`: the interface method. A plain string has no
  history and no played tracks, so it is treated as the current message of a
  first turn: only bm25_plus and dense contribute.

Usage:
    python -m retrieval.final_retriever --split test --output predictions.json
    python -m retrieval.final_retriever --split val0 --output cache/runs/final_val0.json
"""
import argparse
import json
import time

from .base import RetrievalModule
from .context import SessionPolicy, TurnContext, finalize_top_k, iter_turn_contexts
from .fusion import build_fusion
from .run_experiment import FOLDS, check_predictions, sessions_for


class FinalRetriever(RetrievalModule):
    """Weighted RRF of bm25_plus, same_artist, bpr_sim and dense (weights in fusion.py)."""

    def __init__(self) -> None:
        self.fusion = build_fusion()
        self.catalog = self.fusion.catalog

    def retrieve(self, ctx: TurnContext, topk: int = 20,
                 policy: SessionPolicy = SessionPolicy()) -> list[str]:
        """Top-k track IDs for one turn. Part 1 uses the default policy; the Part 2 agent passes its own."""
        ranked = self.fusion.score(ctx, policy=policy)
        return finalize_top_k(ranked, ctx.played_track_ids, topk, policy.exclude_played)

    def text_to_item_retrieval(self, query: str, topk: int) -> list[str]:
        """Treats `query` as the current message of a first turn (no history, no played tracks)."""
        ctx = TurnContext(session_id="", turn_number=1, current_message=query,
                          history=(), played_track_ids=(), baseline_query=query)
        return self.retrieve(ctx, topk)

    def batch_text_to_item_retrieval(self, queries: list[str], topk: int) -> list[list[str]]:
        return [self.text_to_item_retrieval(query, topk) for query in queries]


def main() -> None:
    parser = argparse.ArgumentParser(description="Final retriever: writes predictions JSON")
    parser.add_argument("--split", default="test", choices=["test", *FOLDS])
    parser.add_argument("--output", required=True, help="Path to write predictions JSON")
    parser.add_argument("--topk", type=int, default=20)
    args = parser.parse_args()

    retriever = FinalRetriever()
    contexts = list(iter_turn_contexts(sessions_for(args.split), retriever.catalog))
    retriever.fusion.prepare(contexts)  # dense embeds every query of the split in batches

    predictions, start = [], time.perf_counter()
    for ctx in contexts:
        predictions.append({
            "session_id": ctx.session_id,
            "turn_number": ctx.turn_number,
            "predicted_track_ids": retriever.retrieve(ctx, args.topk),
            "predicted_response": "",
        })
    seconds = time.perf_counter() - start

    check_predictions(predictions, contexts, set(retriever.catalog.metadata_dict),
                      exclude_played=True, topk=args.topk)
    # Stricter than check_predictions: the submission must be full lists.
    assert all(len(p["predicted_track_ids"]) == args.topk for p in predictions), "short list"

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)
    print(f"Wrote {len(predictions)} predictions ({args.topk} IDs each) to {args.output}; "
          f"{1000 * seconds / len(predictions):.1f} ms/query (dense queries pre-embedded)")


if __name__ == "__main__":
    main()
