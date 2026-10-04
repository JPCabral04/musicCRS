# Alejandro's Experiment Log

| What I changed | Split | nDCG@20 | diversity | final | ms/query | Keep? |
|---|---|---|---|---|---|---|
| T6: Dense retrieval (Qwen3-Embedding-0.6B) | val (limit 10) | 0.0907 | 0.0212 | 0.0768 | 2293.5 | Yes |
| T7: BPR similarity scorer (cf-bpr centroid) | val | 0.1037 | 0.5359 | 0.1901 | 1.0 | Yes |

## Task T6: Dense Recommender (`dense.py`)
- **Sanity Check:** Passed (Median Rank <= 5 between local Qwen3 encoder and HuggingFace vectors).
- **Latency (CPU):** ~2293.5 ms/query.
- **Validation Run (`--limit 10`):**
  - `ndcg@20`: 0.0907
  - `ms/query`: 2293.5
- **Decision:** `DenseScorer` is implemented, verified, and integrated into `METHODS`. Query embeddings/top-200 candidates are available for fusion (T8).


## Task T7: BPR Similarity Scorer (`session_cf.py`)
- **Implementation:** `BPRSimilarityScorer` (`bpr_sim`). Computes centroid of played tracks' BPR vectors and ranks catalog by cosine similarity. Returns empty list on turn 1.
- **Latency:** 1.0 ms/query.
- **Validation Results (`val`):**
  - `ndcg@20`: 0.1037
  - `catalog_diversity`: 0.5359
  - `final_score`: 0.1901
- **Status:** Complete and verified.