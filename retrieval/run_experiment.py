"""Shared experiment harness: validation folds (T1).

The course only gives `train` and `test`. Our "validation set" is three
disjoint folds of 1,000 `train` sessions (seed 42), the same size as `test`,
because catalog diversity is not normalized by the number of turns. `val0` is
used for every experiment, `val0-2` to confirm final choices. The rest of
`train` (free pool) is for statistics only, never for scoring.

Usage:
    python -m retrieval.run_experiment --make_val_folds
    python -m retrieval.run_experiment --make_val_folds --n_val 1000 --n_folds 3 --seed 42
"""
import argparse
import json
import os
import random

from datasets import load_dataset

DATASET = "talkpl-ai/TalkPlayData-Challenge-Dataset"
VAL_FOLDS_PATH = "data/val_folds.json"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="MusicCRS experiment harness")
    parser.add_argument("--make_val_folds", action="store_true",
                        help="Write the validation folds and exit.")
    parser.add_argument("--n_val", type=int, default=1000, help="Sessions per fold.")
    parser.add_argument("--n_folds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=VAL_FOLDS_PATH)
    args = parser.parse_args()

    if args.make_val_folds:
        make_val_folds(args.n_val, args.n_folds, args.seed, args.output)
    else:
        parser.error("nothing to do (only --make_val_folds is implemented so far)")


if __name__ == "__main__":
    main()
