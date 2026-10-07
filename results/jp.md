# JP's Experiment Log

| What I changed | Split | nDCG@20 | diversity | final | ms/query | Keep? |
|---|---|---|---|---|---|---|
| T8: fusion (RRF k=10; bm25_plus 1, same_artist 2, bpr_sim 2, dense 1) | val0 | 0.1925 | 0.5867 | 0.2713 | 9.9 (dense cached) | Yes |
| T8: same fusion | val_all (mean) | 0.1976 | 0.5860 | **0.2753** (spread 0.0106) | 10.0 (dense cached) | Yes |
| T9: `FinalRetriever` (= T8 fusion) | **test** | 0.1522 | 0.6489 | **0.2516** | 10.4 (dense pre-embedded) | Submit |

Best single component for comparison: `bm25_plus` val_all final 0.2214 (spread 0.0071).

## Task T8: Fusion (`fusion.py`, `tune_fusion.py`)

Weighted Reciprocal Rank Fusion: `score(track) = sum of weight / (k_rrf + rank)` over the
component lists. Played tracks are removed from every list before RRF (SessionPolicy). The
weights are tuned on the cached top-200 lists of each component (`cache/runs/<method>_<fold>_top200.pkl`),
through the same `fuse()` that `FusionScorer` uses.

### Check: each component alone (weight 1) reproduces its standalone val0 score

| Component | nDCG@20 | diversity | final |
| --- | ---: | ---: | ---: |
| `bm25_plus` | 0.1628 | 0.4387 | 0.2180 |
| `same_artist` | 0.1507 | 0.3464 | 0.1898 |
| `bpr_sim` | 0.1037 | 0.5359 | 0.1901 |
| `dense` | 0.0694 | 0.6067 | 0.1769 |
| `dense_last_turn` | 0.0771 | 0.5663 | 0.1750 |

All five equal the logged standalone runs, so `fuse` and the cached lists are correct.

### Grid on val0 (`python -m retrieval.tune_fusion --grid`)

`bm25_plus = 1` (RRF only depends on weight ratios); `same_artist`, `bpr_sim`, dense ∈ {0, 0.5, 1, 2, 4};
dense = `dense` or `dense_last_turn`; 225 sets at k_rrf 60 (504 s), then k_rrf 10 / 30 / 100 on the top 3.

| # | k_rrf | Weights (bm25_plus 1) | nDCG@20 | diversity | final |
| --- | ---: | --- | ---: | ---: | ---: |
| 1 | 10 | same_artist 2, bpr_sim 2, dense_last_turn 1 | 0.1932 | 0.5847 | 0.2715 |
| 2 | 10 | same_artist 2, bpr_sim 2, dense 1 | 0.1925 | 0.5867 | 0.2713 |
| 3 | 30 | same_artist 2, bpr_sim 2, dense 1 | 0.1939 | 0.5774 | 0.2706 |
| 4 | 30 | same_artist 2, bpr_sim 2, dense_last_turn 1 | 0.1941 | 0.5753 | 0.2703 |
| 5 | 30 | same_artist 4, bpr_sim 2, dense 1 | 0.1921 | 0.5681 | 0.2673 |
| 6 | 60 | same_artist 2, bpr_sim 2, dense 1 | 0.1916 | 0.5676 | 0.2668 |

k_rrf 10 was the lowest value of the sweep, so lower values were checked by hand on the same weights
(val0 final): `dense` k=3 / 5 / 10 = 0.2671 / 0.2697 / 0.2713; `dense_last_turn` = 0.2672 / 0.2702 / 0.2715.
k=10 is a peak, not the edge of a trend.

### Confirmation on val0-2 (`python -m retrieval.tune_fusion --confirm 5`)

| # | k_rrf | dense | nDCG@20 mean | diversity mean | final mean (val0 / val1 / val2) | spread |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| 1 | 10 | `dense_last_turn` | 0.1978 | 0.5834 | 0.2749 (0.2715 / 0.2805 / 0.2727) | 0.0090 |
| **2** | **10** | **`dense`** | 0.1976 | 0.5860 | **0.2753** (0.2713 / 0.2820 / 0.2725) | 0.0106 |
| 3 | 30 | `dense` | 0.1993 | 0.5750 | 0.2745 (0.2706 / 0.2814 / 0.2714) | 0.0108 |
| 4 | 30 | `dense_last_turn` | 0.1991 | 0.5724 | 0.2738 (0.2703 / 0.2802 / 0.2708) | 0.0099 |
| 5 | 30 | `dense`, same_artist 4 | 0.1957 | 0.5661 | 0.2698 (0.2673 / 0.2767 / 0.2653) | 0.0114 |

- **Decision:** #2, `bm25_plus 1, same_artist 2, bpr_sim 2, dense 1`, k_rrf 10. The top 4 are within
  0.0015 of each other (below the spread); #2 has the best mean and uses the simpler dense query
  (current message only).
- **vs the best single component:** +0.054 final over `bm25_plus` on val_all (0.2753 vs 0.2214), about
  5× the spread. Both metrics rise: nDCG 0.166 → 0.198, diversity 0.44 → 0.59.
- Every component has a non-zero weight in the top 10: all four lists help.

### End to end (`python -m retrieval.run_experiment --method fusion --split val_all`)

- Same numbers as `--confirm` #2 on every fold (0.2713 / 0.2820 / 0.2725): the tuning path and
  `FusionScorer` agree. `check_predictions` passed, no empty list (turn 1 is filled by bm25_plus + dense).
- 10 ms/query with dense queries read from the cache. Live (Part 2) latency ≈ dense's 76 ms GPU /
  394 ms CPU encoding + ~10 ms for the rest.

## Task T9: Final retriever (`final_retriever.py`)

`FinalRetriever(RetrievalModule)` wraps `build_fusion()`. Predictions come from `retrieve(ctx)`
(full pipeline); `text_to_item_retrieval(query)` treats the string as a first-turn current message
(no history, no played tracks), so only bm25_plus and dense contribute through it.

- **Same as T8 on val0:** `--split val0` gives 8,000 lists identical to `cache/runs/fusion_val0.json`.
- **Interface smoke test:** `text_to_item_retrieval("upbeat pop song", 5)` → 5 IDs (top: "Popular Song" by MIKA);
  `batch_text_to_item_retrieval` with 2 queries → 2 lists, the first equal to the single call.
- **Test (milestone check 2 of 2, nothing tuned on it):** 8,000 predictions, 20 unique IDs each, no played track.
  Official evaluator: ndcg@1 0.0536, ndcg@10 0.1313, **ndcg@20 0.1522**, **catalog_diversity 0.6489**,
  **final_score 0.2516**. Points: 10 × (0.2516 − 0.1444) / (0.2235 − 0.1444) = 13.6 → capped at **10**.
- Test vs val: nDCG lower (0.152 vs 0.198; test is harder, as for the baseline: 0.166 vs 0.207 with played
  tracks removed), diversity higher (0.649 vs 0.586).
