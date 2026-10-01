"""Check that gold tracks are never already played, and count played tracks in predictions.

1. On every `train` session and turn from 2 to 8, counts how often the gold
   track was already played in an earlier turn of the same session (expected: 0).
2. Optionally, for a predictions file, counts how many predicted slots are
   tracks already played in the session. Since the gold is never a played
   track, those slots are wasted; removing them can only help. Only the
   played tracks (system input) are read here, never the gold.

Usage:
    python -m retrieval.analysis.played_tracks_stats
    python -m retrieval.analysis.played_tracks_stats --predictions predictions.json --split test
"""
import argparse
import json

from datasets import load_dataset

from .same_artist_stats import _played_tracks_by_turn

DATASET = "talkpl-ai/TalkPlayData-Challenge-Dataset"


def count_gold_repeats(split: str = "train") -> tuple[int, int]:
    """Returns (turns checked, turns whose gold was played earlier) for turns 2-8."""
    n_turns = n_repeats = 0
    for session in load_dataset(DATASET, split=split):
        tracks = _played_tracks_by_turn(session)
        for t in range(1, len(tracks)):  # index 1..7 = turns 2..8
            n_turns += 1
            n_repeats += tracks[t] in tracks[:t]
    return n_turns, n_repeats


def count_played_in_predictions(predictions: list[dict], split: str) -> tuple[int, int, int]:
    """Returns (rows with >= 1 played track, played slots, total slots)."""
    played = {s["session_id"]: _played_tracks_by_turn(s)
              for s in load_dataset(DATASET, split=split)}
    rows_with_played = played_slots = total_slots = 0
    for row in predictions:
        before = set(played[row["session_id"]][: row["turn_number"] - 1])
        n = sum(track_id in before for track_id in row["predicted_track_ids"])
        rows_with_played += n > 0
        played_slots += n
        total_slots += len(row["predicted_track_ids"])
    return rows_with_played, played_slots, total_slots


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--predictions", default=None,
                        help="Optional predictions JSON to check for played tracks.")
    parser.add_argument("--split", default="test",
                        help="Split the predictions were made on.")
    args = parser.parse_args()

    n_turns, n_repeats = count_gold_repeats("train")
    print(f"[train] turns 2-8 checked: {n_turns}, gold already played: {n_repeats}")

    if args.predictions:
        with open(args.predictions, encoding="utf-8") as f:
            predictions = json.load(f)
        rows, slots, total = count_played_in_predictions(predictions, args.split)
        print(f"[{args.predictions}] rows: {len(predictions)}, "
              f"rows with >= 1 played track: {rows} ({rows / len(predictions):.1%}), "
              f"played slots: {slots}/{total} ({slots / total:.1%})")


if __name__ == "__main__":
    main()
