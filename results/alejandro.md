# Alejandro's Experiment Log

## Task T6: Dense Recommender (`dense.py`)
- **Sanity Check:** Passed (Median Rank <= 5 between local Qwen3 encoder and HuggingFace vectors).
- **Latency (CPU):** ~2293.5 ms/query.
- **Validation Run (`--limit 10`):**
  - `ndcg@20`: 0.0907
  - `ms/query`: 2293.5
- **Decision:** `DenseScorer` is implemented, verified, and integrated into `METHODS`. Query embeddings/top-200 candidates are available for fusion (T8).