# Alejandro's Experiment Log

## Task T6: Dense Recommender (`dense.py`)

### First version (Oct 4, `63ec099`)
- **Sanity Check:** Passed (Median Rank <= 5 between local Qwen3 encoder and HuggingFace vectors).
- **Latency (CPU):** ~2293.5 ms/query, one query at a time → a full val0 run (8,000 turns) would take ~5 h, so only `--limit 10` (80 turns) finished.
- **Validation Run (`--limit 10`):** `ndcg@20` 0.0907 (80 turns: too few to compare).

### Speed fix (Oct 4, JP)
- Queries are embedded in batches by `DenseScorer.prepare` (called by the runner) and cached by text in `cache/dense/`; GPU float16 when available; `max_seq_length = 512`.
- Track matrix loaded column-wise; every catalog ID is asserted present. **492 tracks have empty text/audio vectors** (zero row, never retrieved by dense).
- **Sanity check:** self-rank 1 for 50/50 tracks (GPU, float16).
- **Live latency** (`python -m retrieval.dense --time 100`, no cache): median **76 ms/query** on GPU (RTX 3060), **394 ms** on CPU (16 threads).
- A full val0 run takes ~2 min on the GPU (~1 min embedding, then 5.7 ms/query from the cache).

### Results (played tracks removed, full folds)

| Method | Field | Prompt | Query | Split | nDCG@20 | Diversity | Final |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| `dense` | metadata | yes | current | val0 | 0.0694 | 0.6067 | 0.1769 |
| `dense_noprompt` | metadata | no | current | val0 | 0.0625 | 0.5538 | 0.1607 |
| `dense_last_turn` | metadata | yes | current + last user msg | val0 | 0.0771 | 0.5663 | 0.1750 |
| `dense_attributes` | attributes | yes | current | val0 | 0.0274 | 0.4373 | 0.1094 |
| `dense` | metadata | yes | current | val_all | 0.0672 (0.0694 / 0.0664 / 0.0657) | 0.6038 | **0.1745** (spread 0.0054) |
| `dense_last_turn` | metadata | yes | current + last user msg | val_all | **0.0718** (0.0771 / 0.0700 / 0.0683) | 0.5660 | 0.1706 (spread 0.0087) |

- **Decision:** metadata field with the query prompt (both clear wins). `current+last_turn` has the higher nDCG on every fold but less diversity; both top-200 lists are cached (`cache/runs/dense[_last_turn]_val{0,1,2}_top200.pkl`) and T8 fusion picks the one that fuses better.
- Standalone, dense is below BM25 (nDCG 0.07 vs 0.16) but brings much more diversity (0.60 vs 0.39): a fusion component, not a ranker on its own.
