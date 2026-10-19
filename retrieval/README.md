# Retrieval

Text-to-item retrieval over the track metadata catalog used in the RecSys 2026
MusicCRS challenge, plus evaluation utilities for scoring predictions.
Adapted from [`music-crs-baselines`](https://github.com/nlp4musa/music-crs-baselines)
and [`music-crs-evaluator`](https://github.com/nlp4musa/music-crs-evaluator).

## Task

Given a conversation between a user and a music recommender system, your task is to
**rank the track catalog and return the top tracks the user is most likely looking
for at the current turn**. This is the retrieval component of the MusicCRS pipeline:
given the conversation so far, produce a ranked list of candidate track IDs from the
~47k-track catalog.

You are given a working BM25 baseline (below) as your starting point. Your task is
to build a retrieval method that **outperforms it** on the final score defined
under [Final score](#final-score).

### Input and output

  - **Input:** a conversation turn, consisting of the dialogue history up to and
  including the user's current message (see `experiments/run_bm25_baseline.py` for how the
  baseline builds its query from this history).
  - **Output:** a ranked list of up to 20 track IDs from the catalog
  (`talkpl-ai/TalkPlayData-Challenge-Track-Metadata`), most relevant first.

Implement your method as a subclass of `RetrievalModule` (see `base.py`):

```python
def text_to_item_retrieval(self, query: str, topk: int) -> list[str]: ...
def batch_text_to_item_retrieval(self, queries: list[str], topk: int) -> list[list[str]]: ...
```

This keeps your method a drop-in replacement for `BM25Retriever` everywhere it's
used (prediction generation, evaluation).

### Data available to you

  - Track metadata (name, artist, album, tags, popularity, release date)
  - Track and user embeddings, precomputed with multiple encoders (audio, image,
  collaborative filtering, and text) — see the top-level
  [README's Dataset section](../README.md#dataset) for the full list
  - The conversation dataset itself, including user profiles and conversation goals

You are free to use any combination of these. Some directions to consider:
dense/semantic retrieval using the precomputed embeddings, hybrid ranking
(combining BM25 with dense similarity), query expansion or rewriting,
personalization using user profiles, or reranking with a cross-encoder.

## Structure

```
retrieval/
├── base.py               # RetrievalModule abstract interface
├── data_loader.py        # MusicCatalogLoader — loads track metadata from Hugging Face
├── context.py            # TurnContext, SessionPolicy, finalize_top_k — shared by all methods
├── final_retriever.py    # FinalRetriever — the tuned fusion, used by the Part 2 agent
├── methods/              # one ranker per file (the names used by --method)
│   ├── bm25.py               # BM25Retriever — BM25 baseline
│   ├── bm25_plus.py          # BM25 with tags indexed, current message and history scored apart
│   ├── dense.py              # dense retrieval with Qwen3 embeddings
│   ├── session_cf.py         # same-artist and BPR-similarity scorers
│   └── fusion.py             # weighted reciprocal rank fusion of the above
├── experiments/          # scripts run from the terminal
│   ├── run_bm25_baseline.py  # generates BM25 predictions over a dialogue dataset split
│   ├── run_experiment.py     # runs any method on test / val folds, caches runs
│   └── tune_fusion.py        # grid search for the fusion weights
├── analysis/             # dataset statistics behind design choices
└── evaluation/
    ├── metrics.py             # nDCG
    ├── diversity.py           # item (catalog) diversity
    ├── make_ground_truth.py   # extract ground truth from the challenge dialogue dataset
    └── evaluate.py            # evaluate() + CLI runner — nDCG, diversity, and final_score
```

See the top-level [README's Dataset section](../README.md#dataset) for what
data is available in the RecSys 2026 MusicCRS challenge collection.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Retrieval

`BM25Retriever` builds (and caches to `./cache/bm25/<corpus_name>`) a BM25 index
over selected metadata fields for `talkpl-ai/TalkPlayData-Challenge-Track-Metadata`,
then ranks track IDs for a query.

```python
from retrieval import BM25Retriever

retriever = BM25Retriever()  # downloads + indexes on first run, cached after
retriever.text_to_item_retrieval("upbeat pop song", topk=5)
retriever.batch_text_to_item_retrieval(["upbeat pop song", "sad piano ballad"], topk=5)
```

## Evaluation

Your method will be evaluated on the `test` split (the devset):

```bash
python3 -m retrieval.experiments.run_bm25_baseline --split test --topk 20 --output predictions.json   # or your own runner
python3 -m retrieval.evaluation.evaluate --predictions predictions.json --ground_truth ground_truth.json --catalog_size 47071
```

### Ground truth

`talkpl-ai/TalkPlayData-Challenge-Dataset` has `train` (15,199 sessions) and
`test` (1,000 sessions, used as the devset) splits. Each session has 8 turns;
each turn embeds the gold track ID and gold response directly in its
`conversations` field. Extract these into the format `evaluate.py` expects:

```bash
python3 -m retrieval.evaluation.make_ground_truth --split test --output path/to/ground_truth.json
```

### Generating BM25 predictions

`experiments/run_bm25_baseline.py` retrieves top-k track IDs for every session x turn in a
dialogue dataset split. The query is the full conversation history up to and
including that turn's user message (prior `music` turns are expanded to
track metadata), matching the retrieval input built in
`music-crs-baselines/mcrs/crs_baseline.py`. There is no LLM query rewriting
or response generation — retrieval only, so `predicted_response` is left
empty:

```bash
python3 -m retrieval.experiments.run_bm25_baseline --split test --topk 20 --output path/to/predictions.json
```

### Scoring predictions

`evaluate()` computes macro-averaged nDCG@{1,10,20}, item (catalog)
diversity, and a combined **final score**, given predictions and ground
truth in the challenge format:

  - Predictions: list of `{session_id, turn_number, predicted_track_ids, predicted_response}`
  - Ground truth: list of `{session_id, turn_number, ground_truth_track_id}`

```bash
python3 -m retrieval.evaluation.evaluate \
  --predictions path/to/predictions.json \
  --ground_truth path/to/ground_truth.json \
  --catalog_size 47071 \
  --output path/to/results.json
```

Or from Python:

```python
from retrieval.evaluation import compute_ndcg_metrics, compute_catalog_diversity
```

Use this (or `retrieval.evaluation.evaluate()` from Python) to compute your score
yourself during development — this is the exact function used for grading.

#### Final score

Your ranking is scored on a single combined metric:

```
final_score = 0.8 * nDCG@20 + 0.2 * catalog_diversity
```

  - **nDCG@20** — how highly you rank the ground truth track within your top 20
  predictions, averaged over all turns. This is the primary signal: getting the
  right track ranked highly matters most.
  - **catalog_diversity** — the fraction of the track catalog covered by your
  recommendations across all turns (unique recommended tracks / catalog size).
  This penalizes methods that recommend the same small set of popular tracks to
  everyone, regardless of the query.

### Baseline to beat (test split, 1,000 sessions x 8 turns)

| Metric | BM25 baseline |
| --- | ---: |
| nDCG@1 | 0.0101 |
| nDCG@10 | 0.0644 |
| nDCG@20 | 0.0828 |
| Catalog diversity | 0.3906 |
| **Final score** | **0.1444** |

nDCG is in line with the `music-crs-evaluator` baseline's LLaMA-1B+BM25
numbers (nDCG@10 = 0.0627, nDCG@20 = 0.0815); the small gap is expected
since that baseline additionally uses an LLM for response generation
while ours is retrieval only.

## Notes

  - You do not need to generate a text response for this task — leave
  `predicted_response` empty in your predictions; it isn't scored.
  - Ground truth for the `test` split can be extracted yourself with
  `retrieval.evaluation.make_ground_truth` for local development. Do not
  use it to fit your method (e.g. hard-coding gold tracks); it's for
  evaluation only.
