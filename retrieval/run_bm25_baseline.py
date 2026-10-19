"""Generate BM25 baseline predictions for a dataset split.

For each session and turn, retrieves top-k track IDs using the full
conversation history up to and including that turn's user message as the
query (matching `music-crs-baselines/mcrs/crs_baseline.py`'s retrieval
input: prior turns joined as `role: content` lines, with `music` turns
expanded to track metadata). Produces a predictions JSON file in the
format expected by `retrieval.evaluation.evaluate`.
"""
import argparse
import json

from datasets import load_dataset

from .methods.bm25 import BM25Retriever, DEFAULT_CORPUS_TYPES
from .data_loader import MusicCatalogLoader

NUM_TURNS = 8


def _build_retrieval_input(
    conversations: list[dict],
    target_turn_number: int,
    catalog: MusicCatalogLoader,
    corpus_types: list[str],
) -> str:
    """Builds the BM25 query: conversation history up to `target_turn_number`.

    Args:
        conversations: The session's full list of turn messages.
        target_turn_number: The turn being predicted (inclusive).
        catalog: Catalog used to expand `music` turns to metadata.
        corpus_types: Metadata fields used when expanding `music` turns.

    Returns:
        A "role: content" per line string covering every message up to
        and including the target turn's user message.
    """
    lines = []
    for message in conversations:
        if message["turn_number"] > target_turn_number:
            break
        if message["turn_number"] == target_turn_number and message["role"] != "user":
            break
        role, content = message["role"], message["content"]
        if role == "music":
            role = "assistant"
            content = catalog.id_to_metadata_str(content, corpus_types)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def run_baseline(
    retriever: BM25Retriever,
    catalog: MusicCatalogLoader,
    dataset_name: str,
    split: str,
    topk: int,
    corpus_types: list[str] = DEFAULT_CORPUS_TYPES,
) -> list[dict]:
    """Runs BM25 retrieval for every session x turn in a split.

    Args:
        retriever: A fitted BM25Retriever.
        catalog: Catalog used to expand `music` turns to metadata.
        dataset_name: Hugging Face dataset name for the dialogue dataset.
        split: Dataset split to use (e.g. "test").
        topk: Number of track IDs to retrieve per turn.
        corpus_types: Metadata fields used when expanding `music` turns.

    Returns:
        A list of prediction dicts (session_id, turn_number,
        predicted_track_ids, predicted_response).
    """
    dataset = load_dataset(dataset_name, split=split)
    predictions = []
    for item in dataset:
        for turn_number in range(1, NUM_TURNS + 1):
            query = _build_retrieval_input(
                item["conversations"], turn_number, catalog, corpus_types
            )
            predicted_track_ids = retriever.text_to_item_retrieval(query, topk)
            predictions.append(
                {
                    "session_id": item["session_id"],
                    "turn_number": turn_number,
                    "predicted_track_ids": predicted_track_ids,
                    "predicted_response": "",
                }
            )
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BM25 baseline")
    parser.add_argument(
        "--dialogue_dataset", default="talkpl-ai/TalkPlayData-Challenge-Dataset"
    )
    parser.add_argument("--split", default="test")
    parser.add_argument("--topk", type=int, default=20)
    parser.add_argument("--output", required=True, help="Path to write predictions JSON")
    args = parser.parse_args()

    retriever = BM25Retriever()
    catalog = MusicCatalogLoader()
    predictions = run_baseline(
        retriever, catalog, args.dialogue_dataset, args.split, args.topk
    )
    with open(args.output, "w") as f:
        json.dump(predictions, f, indent=2)
    print(f"Wrote {len(predictions)} predictions to {args.output}")


if __name__ == "__main__":
    main()
