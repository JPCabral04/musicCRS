# Part 1 Work Plan — Detailed Version (tied to the real code)

> **Names and dates:** `part1_plan_simple.md` is the source of truth. There, **Worker 1 = Alejandro** and **Worker 2 = JP**, with these exceptions: JP does T0 (the harness) and `final_retriever.py`; Alejandro does the diversity analysis, the submission push and assembling the report. The dates also moved: harness on Wed Sep 30, the first recommenders on Oct 1–2, sync on Sat Oct 3. Always use the dates in the simple plan.

This is the concrete version of `docs/part1_plan.md`. Same split (Worker 1 / Worker 2), same dates.
The difference: every task now points to real files, functions, line numbers, data fields and commands.

- Line numbers refer to commit `3842f58` of this repo.
- **A VERIFICAR** = not confirmed in the code or the data. Check it before relying on it.
- The facts in Section 2 were checked with small read-only scripts on Sep 28. They are not guesses.
- Signatures below are proposals. Only signatures and docstrings, no implementation.

---

## 1. How the current code works

### 1.1 Data flow of the baseline

```
 Hugging Face (cached in C:\hf)
 ├─ talkpl-ai/TalkPlayData-Challenge-Track-Metadata  (47,071 tracks)
 │     │
 │     ▼
 │  MusicCatalogLoader            data_loader.py L13-33
 │  metadata_dict: track_id -> {track_name, artist_name, album_name, tag_list, ...}
 │     │
 │     ▼
 │  BM25Retriever.__init__        bm25.py L20-43
 │  one text document per track: "track_name: ...\nartist_name: ...\nalbum_name: ..."
 │  index saved to cache/bm25/track_name_artist_name_album_name/   (built once)
 │
 └─ talkpl-ai/TalkPlayData-Challenge-Dataset  (train 15,199 / test 1,000 sessions)
       │  for each session, for turn 1..8
       ▼
    _build_retrieval_input        run_bm25_baseline.py L21-50
    query = every message up to and including this turn's user message,
            as "role: content" lines; earlier `music` messages are replaced
            by the played track's metadata (as "assistant: track_id: ..., track_name: ...")
       │
       ▼
    BM25Retriever.text_to_item_retrieval(query, 20)     bm25.py L77-80
       │
       ▼
    predictions.json   [{session_id, turn_number, predicted_track_ids[20], predicted_response: ""}]
       │
       │      make_ground_truth (evaluation/make_ground_truth.py L29-58)
       │      gold = the `music` message of each turn
       │             │
       ▼             ▼
    evaluate(predictions, ground_truth, 47071)      evaluation/evaluate.py L20-65
       │
       ▼
    nDCG@1/10/20, catalog_diversity, final_score = 0.8 * nDCG@20 + 0.2 * diversity
```

### 1.2 File map (starter kit, never edited)

| File | What it does | Key lines |
| --- | --- | --- |
| `retrieval/base.py` | `RetrievalModule` abstract class: `text_to_item_retrieval(query, topk)` and `batch_text_to_item_retrieval(queries, topk)` | L9-39 |
| `retrieval/data_loader.py` | Loads the catalog. `id_to_metadata(track_id)` returns the dict. `id_to_metadata_str` formats it as one string, starting with `track_id: <uuid>` | L31-33, L39-59 |
| `retrieval/bm25.py` | Builds, caches and queries the BM25 index | L14 (default fields), L36-43 (cache), L45-53 (doc text), L77-80 (query) |
| `retrieval/run_bm25_baseline.py` | Builds one query per (session, turn), runs BM25, writes predictions | L21-50 (query), L53-91 (loop), L94-111 (CLI) |
| `retrieval/evaluation/evaluate.py` | Official scoring function, also a CLI | L20-65 |
| `retrieval/evaluation/metrics.py` | nDCG; **raises an error on duplicate predictions** | L9-29, L43-44 |
| `retrieval/evaluation/diversity.py` | unique recommended IDs / catalog size | L5-11 |
| `retrieval/evaluation/make_ground_truth.py` | Extracts the gold track per turn (works for `train` too) | L21-26, L29-58 |

### 1.3 Glossary

| Term | Plain meaning |
| --- | --- |
| **BM25** | Classic keyword search. A track scores high if it shares rare words with the query. Word counts are saturated and long documents are penalized a little. |
| **Embedding** | A list of numbers (a vector) that represents a text, song or user. Similar things get vectors that point in similar directions. |
| **Cosine similarity** | How much two vectors point the same way (from -1 to 1). You get it as a dot product after scaling both vectors to length 1 ("L2-normalize"). |
| **Dense retrieval** | Embed the query with a neural model and return the tracks whose precomputed vectors are closest. It finds matches by meaning, not just exact words. |
| **nDCG@20** | 1.0 if the gold track is at rank 1, 1/log2(r+1) if it is at rank r ≤ 20, and 0 if it is missing. Averaged over all turns. |
| **Catalog diversity** | Number of different tracks we recommend across all turns, divided by 47,071. |
| **RRF (Reciprocal Rank Fusion)** | Merges several ranked lists: each track gets Σ weight / (60 + rank) over the lists it appears in. It uses only ranks, so the lists' score scales don't matter. |
| **BPR** | Bayesian Personalized Ranking. A collaborative filtering method trained on listening data. Tracks that are played by the same people get similar 128-d vectors. |
| **Validation set** | Fixed samples of *train* sessions that we use to compare and tune methods: three disjoint folds of 1,000 sessions (`val0` default, `val0–2` to confirm). The *test* split is only used at milestones, so we never tune on it. |
| **Leakage** | Using information that won't exist at prediction time (for example the gold track itself). It gives fake high scores and breaks the rules. |

---

## 2. Facts we verified in the data

### 2.1 Conversation dataset (`talkpl-ai/TalkPlayData-Challenge-Dataset`)

- Splits: `train` 15,199 sessions, `test` 1,000 sessions. There are no shared session IDs.
- Session fields: `session_id`, `user_id`, `session_date`, `user_profile`, `conversation_goal`, `conversations`, `goal_progress_assessments`.
  - `user_profile`: `age, age_group, country_code, country_name, gender, preferred_language, preferred_musical_culture, user_id, user_split`.
  - `conversation_goal`: `category` (A–K), `listener_goal` (text), `specificity` (LL/LH/HL/HH).
- Message fields (inside `conversations`): `role`, `content`, `thought`, `turn_number`.
  - `turn_number` is an **int** (1–8).
  - Every session has exactly **24 messages**, always in the order `user → music → assistant`, 8 times.
  - For `music` messages, `content` is the track ID of the gold track for that turn.
  - `thought` is the simulator's hidden reasoning. For the `music` message it names the gold track. **Never use it** (see Section 3).
- Test users: 1,000 sessions from 500 users. 800 sessions are `test_warm` and 200 are `test_cold`. 371 of the 500 test users also appear in train. All train sessions are `train_warm`.
- **The gold track is never a track that was already played earlier in the same session.** This was checked on all train and test turns: 0 repeats. *Dataset pattern, see 6.3.*
- **Same-artist signal** (2,000 train sessions, turns 2–8; *dataset pattern, see 6.3*):
  - 65% of gold tracks share an artist with a track played earlier in the session (61% with the *last* played track).
  - That "same-artist pool" is small: median 60 tracks, 90th percentile 162.
  - The gold artist's name appears in the current user message 27–41% of the time. The gold title appears only 1–3% of the time.
- User messages are long: median 44 words, max 1,141.

### 2.2 Track catalog (`talkpl-ai/TalkPlayData-Challenge-Track-Metadata`, split `all_tracks`)

- 47,071 tracks. Fields: `track_id, ISRC, track_name, artist_name, album_name, tag_list, popularity, release_date, duration, artist_id, album_id`.
- **The tags field is called `tag_list`** (not `tags`). It is a list of noisy user tags, for example `'relaxing', 'goeiepoep', 'via pandora', 'body parts'`. It has a mean of 33 tags and a max of 105. 87 tracks have no tags.
- `track_name`, `artist_name`, `album_name`, `artist_id`, `album_id` are **lists** (up to 4 artists). 10,638 distinct artists; the median artist has 1 track.
- `popularity`: 0–93, median 38.

### 2.3 Precomputed embeddings

**Tracks:** `talkpl-ai/TalkPlayData-Challenge-Track-Embeddings`

| Column | Dim | Notes |
| --- | ---: | --- |
| `track_id` | – | the key; join on it, **don't rely on row order** |
| `audio-laion_clap` | 512 | norm = 1.0 |
| `image-siglip2` | 768 | cover art |
| `cf-bpr` | 128 | **616 tracks have an empty list** (no CF data). Tiny norms (~0.03). |
| `attributes-qwen3_embedding_0.6b` | 1024 | **not normalized** (norm ~85) |
| `lyrics-qwen3_embedding_0.6b` | 1024 | **not normalized** (norm ~110) |
| `metadata-qwen3_embedding_0.6b` | 1024 | **not normalized** (norm ~97) |

- The text model is **Qwen3-Embedding-0.6B** (from the column names and the top-level `README.md` L68).
- Storage: 5 parquet files (~800 MB download), values stored as float64 lists.
- Split `all_tracks` = 47,071 rows, **exactly the catalog's IDs**.
- Split `test_tracks` = 7,405 rows, and it **contains all 6,761 test gold tracks**. Using it as a candidate filter would leak the answers. **We never load it.**
- The dataset card does not say how the text was built (template, instruction, pooling). → **A VERIFICAR** in task W2-1.

**Users:** `talkpl-ai/TalkPlayData-Challenge-User-Embeddings`: `user_id` + `cf-bpr` (128). Rows: train 8,591, test_warm 371, test_cold 129 (104 of these are empty).

### 2.4 What score we need

`final = 0.8 * nDCG@20 + 0.2 * diversity`. Full marks = 0.2235.

| nDCG@20 | diversity | final |
| ---: | ---: | ---: |
| 0.083 (baseline) | 0.39 | 0.145 |
| 0.18 | 0.40 | 0.224 |
| 0.155 | 0.50 | 0.224 |

- +0.0125 nDCG@20 is worth +0.01 final.
- +0.05 diversity is also worth +0.01 final. **Diversity is a real lever, not a side metric.**

---

## 3. Data-use rules (what we may use)

| Use? | Data | Why |
| --- | --- | --- |
| ✅ | Current user message, earlier user/assistant messages | This is the conversation. The baseline uses it too. |
| ✅ | Track IDs of earlier `music` messages ("played tracks") | The baseline uses them (`run_bm25_baseline.py` L46-48). In Part 2 we know what we played. |
| ✅ | Catalog metadata, `all_tracks` embeddings | Explicitly allowed (`retrieval/README.md` L38-44). |
| ✅ | `train` sessions for validation, statistics, tuning | Allowed (`make_ground_truth.py` L8-9 says train is for dev-tuning). Evaluate only on the val folds; compute statistics only on the free pool (T0.1). |
| ❌ | `thought` fields | Hidden simulator reasoning. The `music` thought names the gold track. It does not exist in Part 2. |
| ❌ | `music` / `assistant` messages **of the target turn** | They contain the gold track and its name. The baseline correctly stops before them (L41-44). |
| ❌ | `goal_progress_assessments` | Judged after the turn, so it's future information. |
| ❌ | Embedding split `test_tracks` | It contains every test gold track. |
| ❌ | Test ground truth for tuning | Rule in `retrieval/README.md` L186-189. Only for final scoring. |
| ❌ | LLM calls | Our own rule for Part 1 (speed, reliability, Part 2 budget). |
| ⚠️ out of scope | `conversation_goal`, `user_profile`, user BPR embeddings | Allowed by the README, but the Part 2 chatbot won't have them. **Decided: not used in Part 1.** Mention as future work (Part 4 idea). |

**Leak alarm:** if a method suddenly scores nDCG@20 > 0.4 on validation, assume a leak and check the context builder first.

---

## 4. Terminal setup (Git Bash on Windows)

Run this once per terminal, from the repo root:

```bash
conda activate musiccrs            # if this fails in Git Bash: run `conda init bash` once, reopen the terminal
export HF_HOME="C:/hf"             # use the cached datasets; otherwise they download again into ~/.cache
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
export PYTHONUTF8=1                # avoids cp1252 errors when reading/writing JSON with non-ASCII text
python -c "import retrieval; print('ok')"
```

- `HF_HOME` is **not** set by default in Git Bash (checked). Without it, the 90 MB + 18 MB datasets download again.
- Optional, for faster loading when offline: `export HF_DATASETS_OFFLINE=1`.
- Dense retrieval (W2-1) needs new packages that are **not** installed now: `torch`, `sentence-transformers`, `transformers`. The exact versions that support Qwen3-Embedding are **A VERIFICAR** (the model card says `transformers>=4.51`, `sentence-transformers>=2.7`).
- **Proposed default (confirm in the Day 1 pair session):** Worker 2 opens one small PR that only changes `requirements.txt` (the versions that worked in the W2-1 sanity check). Worker 1 reviews it by installing into a fresh env. Until it's merged, each person installs locally.

---

## 5. Ownership (unchanged) and new files

| Area | Owner | Files |
| --- | --- | --- |
| Shared harness | **Both** (pair session) | `retrieval/context.py`, `retrieval/run_experiment.py`, `data/val_folds.json` |
| Improved BM25 | **Worker 1** | `retrieval/bm25_plus.py` |
| Session signal (same artist + BPR) | **Worker 1** | `retrieval/session_cf.py` |
| Dense retrieval (Qwen3) | **Worker 2** | `retrieval/dense.py` |
| Fusion (RRF) + weight tuning | **Worker 2** | `retrieval/fusion.py` |
| Final `RetrievalModule` + test run | **Worker 1** | `retrieval/final_retriever.py` |
| Diversity analysis | **Worker 2** | `results/diversity_analysis.md` |
| Experiment logs | each their own | `results/worker1.md`, `results/worker2.md` |
| Report | each their own sections; Worker 1 assembles | `G1/report.md` |
| Submission | **Worker 1** | `G1/predictions.json`, `G1/report.md` |

Generated files (never committed) go under `cache/`, which is already in `.gitignore`:

```
cache/bm25/<fields>/          BM25 indexes (made by BM25Retriever)
cache/embeddings/*.npy        track embedding matrices (made by dense.py / session_cf.py)
cache/dense/*.npy             cached query embeddings
cache/runs/*.json|*.pkl       predictions and component top-200 lists per run
```

---

## 6. Shared interface (Day 1, then frozen)

### 6.1 `retrieval/context.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TurnContext:
    """Everything a scorer may know when predicting one turn.

    Built only from messages *before* the target turn's music/assistant messages.
    Contains no dataset-only fields, so the Part 2 chatbot can build one too.
    """
    session_id: str
    turn_number: int                      # 1..8
    current_message: str                  # this turn's user message
    history: tuple[tuple[str, str], ...]  # earlier (role, text); roles "user"/"assistant"/"music" (text = track_id)
    played_track_ids: tuple[str, ...]     # earlier `music` contents, oldest first
    baseline_query: str                   # exactly what _build_retrieval_input returns


@dataclass(frozen=True)
class SessionPolicy:
    """Dataset-pattern rules (Section 6.3). Part 1: the defaults. Part 2: the agent sets them per turn."""
    exclude_played: bool = True    # gold is never a played track (dataset pattern)
    use_same_artist: bool = True   # 65% of golds share an artist with a played track


def load_sessions(split: str, session_ids: list[str] | None = None) -> list[dict]:
    """Loads `train` or `test` sessions from the dialogue dataset, optionally only the given IDs (in that order)."""


def build_turn_context(session: dict, turn_number: int, catalog: MusicCatalogLoader) -> TurnContext:
    """Builds the TurnContext for one (session, turn). Uses _build_retrieval_input for baseline_query."""


def iter_turn_contexts(sessions: list[dict], catalog: MusicCatalogLoader) -> Iterator[TurnContext]:
    """Yields the 8 TurnContexts of every session, in order."""


def finalize_top_k(ranked: list[tuple[str, float]], played: tuple[str, ...], topk: int = 20,
                   exclude_played: bool = True) -> list[str]:
    """Drops duplicates (and played tracks if `exclude_played`), keeps order, returns at most `topk` IDs."""
```

- `TurnContext` is **what we know**; `SessionPolicy` is **how we use it**. They stay separate.

### 6.2 Scorer contract (every component)

```python
class Scorer(Protocol):
    name: str
    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        """Top-k (track_id, score), best first, unique IDs. Played tracks are NOT removed here
        (that happens once, via SessionPolicy, see 6.3).
        May return fewer than k items, or an empty list (e.g. session scorers at turn 1)."""
```

- Scores are only compared **within** one list. Fusion uses ranks, not raw scores.
- `finalize_top_k` is the **only** place that cuts to 20. Keeping it in one place guarantees no duplicates and at most 20 IDs everywhere.
- Scorers fetch a few extra candidates (k = 200 ≫ 20 + 7 played), so removing played tracks later never leaves the top-20 short.

### 6.3 Session rules: dataset patterns, switchable for Part 2

Two of our strongest ideas come from **patterns of this dataset**, not from how every real user behaves:

| | Remove played tracks | Same-artist signal |
| --- | --- | --- |
| Kind of pattern | **Hard rule**: 0 exceptions (Section 2.1) | **Tendency**: 65% of golds |
| Where it comes from | Probably how the data was generated (the system always plays something new) | A plausible real taste (people who hear an artist often want more of them) |
| How it's used | Remove items (yes/no) | A separate list in fusion (a weight) |
| How it fails in Part 2 | User says "play that again" | User says "something different", "another artist" |

- **Part 1:** both are legitimate. We are scored on this dataset, and both use only information from before the target turn. We keep them on (the `SessionPolicy` defaults).
- **Part 2:** the same code is reused by the chatbot, so both must be **switchable per turn**. The agent reads the user's intent (this can be its own LLM call, within the 5–10 per turn limit) and builds the policy:
  - "play that again" → `SessionPolicy(exclude_played=False)`;
  - "something different", "another artist" → `SessionPolicy(use_same_artist=False)`;
  - anything else → the defaults.
  - A request for a **named** track goes through the agent's track lookup (Part 2 R2), not through retrieval.
- **One place only.** The policy is applied in exactly two spots, both reading the same flags:
  1. `FusionScorer.score(ctx, k, policy)` (W2-2): drops played tracks from every component list **before** RRF (so they don't steal ranks), and uses weight 0 for `same_artist` when `use_same_artist=False`.
  2. `finalize_top_k(..., exclude_played=policy.exclude_played)`: the final safety net.
- **No scorer removes played tracks itself.** Otherwise the switch would have to be passed to every scorer, and forgetting one would silently break Part 2.
- **Code status (Oct 1):** `BM25PlusRetriever.score_from_parts` (`bm25_plus.py`) and `SameArtistScorer.score` (`session_cf.py`) still remove played tracks internally. Remove that when the shared harness (T2) lands. Agree on it at the sync first (Worker 1's files).

---

## 7. Tasks

### T0 — Shared harness (pair session, Mon Sep 28) — **Both**

#### T0.1 Validation folds → `data/val_folds.json`

- **Objective.** Fix three disjoint sets of train sessions. Both of us tune on them, so our numbers are comparable and we never tune on test.
- **Why, in plain words.** The course only gives `train` and `test`. "Validation" is not a new split. It's just `train` sessions that we set aside to compare our variants. If we tried 20 variants on `test` and kept the best, we would be fitting to the test set, which the README forbids. None of our methods learn from `train` (BM25, the embeddings and BPR come ready-made), so measuring on train sessions is safe. `test` is used only twice, at the milestones.
- **Why exactly 1,000 sessions per fold (not 300, not all of train).** Catalog diversity is `unique recommended tracks / 47,071` (`evaluation/diversity.py`), and it is **not normalized by the number of turns**. Test = 1,000 sessions × 8 turns × 20 = 160k slots. A fold of the same size gives a diversity (and so a `final_score`) comparable to test. With 300 sessions diversity would be too low; with all 15,199 train sessions (2.4M slots) almost any method covers most of the catalog, and the fusion grid would tune for the wrong trade-off. nDCG@20 is a mean, so it is fine at any size.
- **Why three folds.** One fold gives ~8,000 turns, so a gain below ~0.003–0.005 final can be noise. Three independent folds show the noise directly (the spread between them), with no statistics library.
- **Decision (seed 42):**

  | Part | Size | Use |
  | --- | --- | --- |
  | `val0` | 1,000 sessions | **Default** for every experiment (`--split val`). |
  | `val1`, `val2` | 1,000 each, disjoint | **Confirmation** of important decisions only: final fusion weights, keep/drop a component, any gain < ~0.005 final (`--split val_all`). |
  | free pool (~12,199) | the rest of train | Statistics (like the 65% same-artist number) and anything ever *learned* from train (popularity priors, co-occurrence). **Never evaluate on it.** |

- For fast iteration, use `--limit 200` (the first 200 sessions of `val0`). With `--limit`, only compare nDCG, not diversity.
- **Existing code to reuse.** `datasets.load_dataset(..., split="train")` as in `make_ground_truth.py` L42.
- **New code.** A `make_val_folds` function inside `run_experiment.py` (no extra file):
  ```python
  def make_val_folds(n: int = 1000, n_folds: int = 3, seed: int = 42,
                     output: str = "data/val_folds.json") -> dict[str, list[str]]:
      """Sorts all train session IDs, draws n * n_folds with random.Random(seed).sample, cuts them into
      {"val0": [...], "val1": [...], "val2": [...]}. Writes JSON. The free pool = every other train ID."""
  ```
- **How to test.**
  ```bash
  python -m retrieval.run_experiment --make_val_folds --n_val 1000 --n_folds 3 --seed 42
  python -c "import json; f=json.load(open('data/val_folds.json')); ids=[i for v in f.values() for i in v]; print({k: len(v) for k, v in f.items()}, len(ids) == len(set(ids)), f['val0'][:2])"
  ```
- **Done when.** The file has 3 × 1,000 unique IDs with no overlap, it is committed, and both of us get the same first two IDs of `val0` when we run it.
- **Pitfalls.**
  - Sort the IDs before sampling. Otherwise the result depends on dataset order.
  - If we ever compute statistics from train (for example popularity), use **only the free pool**, or val scores will be too optimistic.
  - Dense is slow on CPU: run it on `val0`, and on `val_all` only for the final check.

#### T0.2 `retrieval/context.py`

- **Objective.** Turn a raw session into one `TurnContext` per turn, so each component gets the current message and the played tracks separately, not just one long string.
- **Existing code to reuse.**
  - `_build_retrieval_input` (`run_bm25_baseline.py` L21-50). **Import it, don't copy it**: `from .run_bm25_baseline import _build_retrieval_input`. Store its output in `baseline_query`. Then the baseline through our harness is byte-for-byte the official baseline.
  - Its cut-off rule (L41-44) is the leak-safe boundary: stop at the first message with `turn_number > target`, or with `turn_number == target` and `role != "user"`. Use **the same rule** to fill `history`, `current_message` and `played_track_ids`.
  - Pass `corpus_types=DEFAULT_CORPUS_TYPES` (`bm25.py` L14) to keep the baseline query identical.
- **New file.** `retrieval/context.py` with the signatures in 6.1.
- **How to test.**
  ```bash
  python -c "
  from retrieval.context import load_sessions, build_turn_context
  from retrieval.data_loader import MusicCatalogLoader
  s = load_sessions('test')[0]; cat = MusicCatalogLoader()
  for t in (1, 2, 8):
      c = build_turn_context(s, t, cat)
      print(t, len(c.history), c.played_track_ids, c.current_message[:60])
  "
  ```
  Look for: turn 1 → 0 history and 0 played tracks; turn 2 → 3 history messages and 1 played track; turn 8 → 21 history messages and 7 played tracks. The gold of turn t (`s['conversations'][3*(t-1)+1]['content']`) must **not** be in `played_track_ids` of turn t.
- **Done when.** The checks above pass for 3 sessions, and T0.3 reproduces the baseline.
- **Pitfalls.**
  - `_build_retrieval_input` starts with `_`, so it is "private". Importing it is fine. Just don't change it.
  - A played `music` message holds a track ID. Convert it to text only where text is needed (BM25, dense), not inside `TurnContext`.

#### T0.3 `retrieval/run_experiment.py`

- **Objective.** One command runs any method on validation or test and prints the official score and the time per query. Every decision we log comes from this command.
- **Existing code to reuse.**
  - Loop structure: `run_baseline` (`run_bm25_baseline.py` L75-91): one prediction dict per (session, turn), `predicted_response: ""`.
  - Ground truth: `make_ground_truth(split=...)` (`evaluation/make_ground_truth.py` L29). It works for `train` too.
  - Scoring: `evaluate(predictions, ground_truth, 47071)` (`evaluation/evaluate.py` L20). This is the grading function.
  - Baseline method: `BM25Retriever()` + `text_to_item_retrieval(ctx.baseline_query, 20)`.
- **New file.**
  ```python
  METHODS: dict[str, Callable[[], Scorer]]   # "bm25_baseline", "bm25_plus", "dense", "same_artist", "bpr_sim", "fusion", "final"

  def run(method: str, split: str, limit: int | None = None, topk: int = 20) -> tuple[list[dict], list[list[tuple[str, float]]]]:
      """split is "val" (= val0), "val1", "val2" (train sessions from data/val_folds.json) or "test".
      ("val_all" is handled in main(): it calls run() once per fold.)
      Returns the predictions (challenge format) and the raw top-200 lists (saved for fusion tuning)."""

  def ground_truth_for(split: str, session_ids: set[str]) -> list[dict]:
      """make_ground_truth on the underlying split, filtered to the evaluated sessions."""

  def check_predictions(predictions: list[dict], contexts: list[TurnContext], catalog_ids: set[str]) -> None:
      """Asserts: one entry per (session, turn); 1..20 IDs; no duplicates; all IDs in the catalog; no played track."""

  def main() -> None:
      """CLI: --method --split {val,val1,val2,val_all,test} --limit --make_val_folds --n_val --n_folds --seed.
      Prints the evaluate() dict, ms/query, and writes cache/runs/<method>_<split>.json and
      cache/runs/<method>_<split>_top200.pkl. With val_all: one evaluate() per fold, then the mean and
      the spread (max - min) of nDCG@20, diversity and final."""
  ```
- **How to test.**
  ```bash
  python -m retrieval.run_experiment --method bm25_baseline --split test --keep_played   # the starter kit keeps played tracks
  python -m retrieval.run_experiment --method bm25_baseline --split val           # record this as "baseline on val"
  python -m retrieval.run_experiment --method bm25_baseline --split val --limit 200
  python -m retrieval.run_experiment --method bm25_baseline --split val_all       # record the spread = our noise level
  ```
  Look at `ndcg@20`, `catalog_diversity`, `final_score` and `ms/query`.
- **As built (Oct 2).** The `Scorer` protocol lives in `context.py`. `run()` takes a built scorer (so `val_all` builds it once). Played tracks are removed by default; `--keep_played` turns that off. Results: test 0.1446 (`--keep_played`) / 0.1664 (default); val_all final mean 0.2072, spread 0.0101.
- **Done when.** `--split test --keep_played` prints nDCG@20 = 0.0830, diversity = 0.3908, final = 0.1446 (the numbers you already got). The val and val_all numbers (with the spread) are written at the top of both `results/worker*.md`. Sanity check: each fold's diversity should be close to test's 0.39, since the folds have the same size.
- **Pitfalls.**
  - `evaluate()` iterates over the **ground truth** and does `preds_by_key[key]` (L45). If the GT has turns we didn't predict, you get a `KeyError`. So always filter the GT to the evaluated sessions (`ground_truth_for`).
  - `evaluate()` counts **every** predicted ID for diversity (L52), not just the first 20. A list of 100 would inflate diversity. `check_predictions` must enforce ≤ 20.
  - `compute_ndcg_metrics` raises `ValueError` on duplicate IDs (`metrics.py` L43-44).
  - `run_bm25_baseline.main` loads the catalog twice (L104-105). Reuse `retriever.catalog` instead.
  - `.gitignore` ignores `predictions*.json`, `ground_truth*.json` and `results*.json` **by file name**. A file like `results/val_run.json` would *not* be ignored. Keep run outputs in `cache/runs/`.
  - Always open JSON with `encoding="utf-8"`.
  - `make_ground_truth(split="train")` builds 121,592 entries in memory before we filter. That's fine, it just takes a moment.

---

### W1-1 — Improved BM25 → `retrieval/bm25_plus.py` — **Worker 1** (Tue Sep 29 – Thu Oct 1)

- **Objective.** Keep BM25 (fast and explainable) but fix three weak points: (1) it wastes slots on tracks already played, (2) it ignores tags, so genre/mood words don't match, (3) it treats a 7-turn-old message the same as the current request.
- **Existing code to reuse (inherit from `BM25Retriever`).**
  - `__init__` (L20-43) already builds, caches and loads an index for **any** list of fields. `BM25PlusRetriever(corpus_types=[..., "tag_list"])` gets a new index for free.
  - `_stringify_metadata` (L45-53) already joins list fields with `", "`, so `tag_list` works without new code.
  - `self.bm25_model` (a `bm25s.BM25`), `self.track_ids` (row → track_id), `self.catalog`.
  - `self.bm25_model.get_scores(tokens)` returns the score of **all 47,071 tracks** as a numpy array. We can add two queries' scores with weights, then take the top k with `np.argpartition`.
  - `text_to_item_retrieval` (L77-80) is inherited, so the class stays a drop-in `RetrievalModule`.
- **New file.**
  ```python
  class BM25PlusRetriever(BM25Retriever):
      name = "bm25_plus"

      def __init__(self, corpus_types: list[str] = ["track_name", "artist_name", "album_name", "tag_list"],
                   w_current: float = 1.0, w_history: float = 0.3, cache_dir: str = "./cache") -> None:
          """Builds/loads the index via BM25Retriever and stores the query weights."""

      def _query_scores(self, text: str) -> np.ndarray:
          """BM25 scores of all tracks for one text (zeros if the text has no known tokens)."""

      def history_text(self, ctx: TurnContext) -> str:
          """Earlier user/assistant messages + played tracks' metadata (name, artist, album)."""

      def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
          """w_current * scores(current_message) + w_history * scores(history). Played tracks are kept (6.3)."""
  ```
- **Steps (one change at a time, each logged with its val score).**
  1. Baseline query + `finalize_top_k(exclude_played=True)` (drop played tracks, refill to 20). This is safe, because the gold is **never** a played track (Section 2.1). The removal happens in the shared `finalize_top_k`, not inside the scorer (6.3).
  2. Add `tag_list` to the index.
  3. Split the query into current message vs history, then tune `w_history` over {0, 0.1, 0.3, 0.5, 1.0} on val.
  4. (Optional) BM25 `k1`/`b` or a top-N tag cut. Only if the steps above are done.
- **How to test.**
  ```bash
  python -m retrieval.run_experiment --method bm25_plus --split val --limit 200   # quick nDCG check
  python -m retrieval.run_experiment --method bm25_plus --split val               # the number you log
  ls cache/bm25/                                                                 # a new track_name_artist_name_album_name_tag_list dir
  ```
- **Done when.** Each step has a line in `results/worker1.md` (change, val nDCG@20, diversity, final, keep?), and the kept version beats the baseline's val final score.
- **Pitfalls.**
  - **The index cache key is only the field names** (`corpus_name`, L36). If you change *how* a document is built (for example keep only the first 10 tags) but keep the same field names, the **old index is silently loaded** (L41 only builds if the dir is missing). Use a different `cache_dir` per variant (for example `./cache/tags_top10`), or delete the dir.
  - If the build crashes halfway, the dir exists but is broken. Delete it by hand.
  - `bm25s.tokenize` removes English stopwords. A message like "the one again" becomes `[]`, and `get_scores([])` crashes (it reads `query_tokens_single[0]`). Guard it by returning zeros. Use `bm25s.tokenize(text, return_ids=False, show_progress=False)`, which returns lists of strings.
  - Repeated query words **are** counted (checked). The baseline history repeats artist names for every played track, so they weigh a lot. That's one more reason for separate weights.
  - `id_to_metadata_str` puts `track_id: <uuid>` into the query text (data_loader L53). It's harmless noise for BM25, but leave it out of your own `history_text`.
  - Tags are noisy and long (33 on average). They make documents longer, and BM25's length normalization (`b`) then lowers title/artist matches. Measure it, don't assume it helps.
  - Tag order: whether `tag_list` is sorted by relevance is **A VERIFICAR** (it matters only for a top-N cut).
- **Latency (Part 2).** Two `get_scores` calls over 47k docs plus `argpartition`: expected to take a few ms. **A VERIFICAR** with `ms/query`.

---

### W2-1 — Dense retrieval → `retrieval/dense.py` — **Worker 2** (Tue Sep 29 – Thu Oct 1)

- **Objective.** Match by meaning ("chill rainy-day indie" ↔ a track tagged mellow/indie folk), which BM25 misses. Embed the query with Qwen3-Embedding-0.6B, the model that made the track vectors, and rank tracks by cosine similarity.
- **Existing code to reuse.**
  - `MusicCatalogLoader().metadata_dict` key order = the order of `BM25Retriever.track_ids`. Use the **same `track_ids` list** for the embedding matrix rows, so all components share one row index.
  - `datasets.load_dataset` (as in `data_loader.py` L27) with `split="all_tracks"`.
- **New file.**
  ```python
  EMB_DATASET = "talkpl-ai/TalkPlayData-Challenge-Track-Embeddings"
  TEXT_FIELDS = ("metadata-qwen3_embedding_0.6b", "attributes-qwen3_embedding_0.6b", "lyrics-qwen3_embedding_0.6b")

  def load_track_matrix(field: str, track_ids: list[str], cache_dir: str = "./cache/embeddings",
                        normalize: bool = True) -> tuple[np.ndarray, np.ndarray]:
      """Returns (matrix float32 [47071, d], has_vector bool [47071]). Row i = track_ids[i].
      Built from split all_tracks by joining on track_id; saved as .npy on first call. Empty vectors -> zero row."""

  class DenseScorer:
      name = "dense"

      def __init__(self, field: str = "metadata-qwen3_embedding_0.6b",
                   model_name: str = "Qwen/Qwen3-Embedding-0.6B",
                   query_mode: str = "current",   # "current" | "current+last_turn" | "history"
                   device: str = "cpu", query_cache: str | None = None) -> None:
          """Loads the track matrix and the query encoder."""

      def query_text(self, ctx: TurnContext) -> str:
          """Builds the text to embed, according to query_mode."""

      def embed_queries(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
          """L2-normalized float32 query vectors (uses the Qwen3 query prompt, see sanity check)."""

      def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
          """Cosine = matrix @ query; top k. Played tracks are kept (6.3)."""

  def sanity_check(n: int = 50, seed: int = 0) -> None:
      """Embeds n tracks' own metadata text and prints the rank of the track itself among 47,071."""
  ```
- **Steps.**
  1. **Load and convert once.** Download `all_tracks` (~700 MB), keep one column, convert float64 → float32, L2-normalize, save `cache/embeddings/<field>.npy` (~190 MB per text field).
  2. **Sanity check (most important, do it first).** We don't know the text template, instruction or pooling behind the track vectors. Embed `"track_name: X\nartist_name: Y\nalbum_name: Z"` (plus 1–2 other templates) for 50 tracks, and check the rank of each track in its own cosine search against `metadata-qwen3...`. Median rank ≈ 1 → our encoder matches theirs. Random ranks → pooling or format mismatch, so stop and investigate before tuning anything.
  3. **Query side.** Qwen3-Embedding uses an instruction for queries (`prompt_name="query"` in sentence-transformers) and none for documents. Compare with and without it on val `--limit 200`.
  4. **Compare the 3 text fields** and the 3 `query_mode`s on val.
  5. **Cache query vectors** per split (`cache/dense/<split>_<query_mode>.npy`) so val/test runs and fusion tuning don't re-embed.
- **How to test.**
  ```bash
  pip install torch sentence-transformers              # after agreeing on versions (A VERIFICAR)
  python -c "from retrieval.dense import sanity_check; sanity_check()"
  python -m retrieval.run_experiment --method dense --split val --limit 200
  python -m retrieval.run_experiment --method dense --split val
  ```
  Look at the median self-rank in the sanity check, and nDCG@20 + `ms/query` in the runs.
- **Done when.** The sanity check shows a matching setup (or we have written down why it doesn't match), one field/mode is chosen on val and logged in `results/worker2.md`, and `ms/query` is recorded **without** the query cache.
- **Pitfalls.**
  - **Never load split `test_tracks`.** It contains all test gold tracks.
  - Qwen3 vectors are **not normalized** (norms 85–116). Without L2-normalizing, dot product favors long vectors, not similar ones.
  - Don't rely on row order. Join on `track_id`. Assert that the matrix has 47,071 rows and that every catalog ID was found.
  - `lyrics-...` may be empty or meaningless for instrumentals. Checking how many rows are empty or zero is **A VERIFICAR**.
  - Long queries: user messages go up to 1,141 words. The "history" mode can be thousands of tokens → slow on CPU. Set `max_seq_length` (for example 512).
  - The model download (~1.2 GB) goes to `HF_HOME`. It needs `SSL_CERT_FILE` set.
- **Latency (Part 2) ⚠️.** This is the **main risk** for the 3–5 s budget. Model loading happens at startup (seconds, once), and the 47k × 1024 matrix product takes ~10–20 ms. But encoding one query on CPU can take from ~0.1 s to over 1 s depending on length. **A VERIFICAR** with real timing. If it's too slow, embed only the current message.

---

### Fri Oct 2 — Sync meeting (both)

- Each person runs the *other's* method on their own machine with `--split val`. The numbers must match.
- **Milestone test check (1 of 2):** run the best single method on `--split test` once. Log it, but **don't tune on it**.
- Merge `worker1/bm25-plus` and `worker2/dense`.

---

### W1-2 — Session signal → `retrieval/session_cf.py` — **Worker 1** (W1-2a Tue Sep 29 – Thu Oct 1, W1-2b Sat Oct 3 – Sun Oct 4)

- **Why it's split in two.** `same_artist` looks like the biggest single gain, and it needs no embeddings. So a simple version (W1-2a) is built early, next to `bm25_plus.py`. Its lists then exist before fusion starts. W1-2b adds the BPR parts once `dense.py`'s `load_track_matrix` is merged (Oct 2).
- **W1-2a (early):** `SameArtistScorer` ordered by recency of the matching played track, then `popularity`. It only needs the catalog.
- **W1-2b (later):** `BPRSimilarityScorer`, and BPR cosine as the tie-breaker inside `SameArtistScorer`. Compare both orderings on val.

- **Objective.** Use what was already played. The data shows this is the strongest signal we have: in turns 2–8, **65% of gold tracks share an artist with a played track**, and that pool is only ~60 tracks (Section 2.1). BPR similarity also adds "people who play these also play…".
- **Existing code to reuse.**
  - `ctx.played_track_ids` from `context.py`.
  - `catalog.metadata_dict[tid]["artist_id"]` (a list) and `["popularity"]`.
  - `load_track_matrix("cf-bpr", track_ids, normalize=True)` from `dense.py` (merged on Oct 2). It returns `has_vector` for the 616 empty ones.
- **New file** (two scorers, so fusion can weight them separately):
  ```python
  class SameArtistScorer:
      name = "same_artist"

      def __init__(self, catalog: MusicCatalogLoader, track_ids: list[str], bpr: np.ndarray, has_bpr: np.ndarray,
                   recency_decay: float = 0.7) -> None:
          """Builds artist_id -> track rows once."""

      def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
          """Tracks sharing an artist_id with a played track (played ones kept, see 6.3). Ordered by recency of the matching
          played track, then BPR cosine to the played centroid, then popularity. Empty at turn 1."""

  class BPRSimilarityScorer:
      name = "bpr_sim"

      def __init__(self, track_ids: list[str], bpr: np.ndarray, has_bpr: np.ndarray, recency_decay: float = 0.7) -> None:
          """Stores the normalized BPR matrix."""

      def centroid(self, played: tuple[str, ...]) -> np.ndarray | None:
          """Recency-weighted mean of the played tracks' BPR vectors (skips empty ones); None if none left."""

      def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
          """Cosine(centroid, all tracks with a vector); played tracks kept (6.3). Empty at turn 1."""
  ```
- **How to test.**
  ```bash
  python -m retrieval.run_experiment --method same_artist --split val --limit 200
  python -m retrieval.run_experiment --method bpr_sim --split val
  ```
  Also print, per turn number, the fraction of turns where the gold is in the same-artist list. It should come out near 0.65 for turns 2–8 (a check that the code matches the statistic).
- **Done when.** Both scorers are logged in `results/worker1.md`, with the per-turn "gold in pool" fraction for `same_artist`.
- **Pitfalls.**
  - The played tracks themselves share an artist (and are closest to the centroid), so they top the raw lists. That's expected: fusion and `finalize_top_k` drop them when `policy.exclude_played` is on (6.3). Don't filter them here.
  - Turn 1 has no played tracks, so both scorers return `[]`. Standalone runs will look bad on turn 1. That's expected, fusion fills it.
  - 616 tracks have no BPR vector. Skip them in the centroid, and give them no BPR score (they can still come from BM25/dense).
  - Use `artist_id`, not `artist_name` (names can collide or be spelled differently). Our 65% statistic used names, so re-measure it with IDs.
  - Standalone `same_artist` may return < 20 tracks. That's fine for fusion. For a standalone run, `finalize_top_k` gives fewer IDs, which is allowed.
  - BPR tends to favor popular tracks. Watch the diversity numbers.
  - The recency weight is a tuning knob. Tune it on val only.
- **Latency (Part 2).** A dictionary lookup plus a 47k × 128 product: about 1 ms.

---

### W2-2 — Fusion → `retrieval/fusion.py` — **Worker 2** (Sat Oct 3 – Sun Oct 4)

- **Objective.** Each signal is right on different turns: BM25 when the artist is named, dense for moods, session signals from turn 2 on. RRF combines ranked lists without calibrating scores, and it has only a few knobs to tune.
- **Existing code to reuse.** The `Scorer` contract (6.2). `finalize_top_k` (6.1). The top-200 lists that `run_experiment.py` saved to `cache/runs/<method>_val_top200.pkl`.
- **New file.**
  ```python
  def rrf(lists: dict[str, list[tuple[str, float]]], weights: dict[str, float], k_rrf: int = 60,
          depth: int = 200) -> list[tuple[str, float]]:
      """score(t) = sum_i weights[i] / (k_rrf + rank_i(t)) over lists containing t; returns sorted, unique."""

  class FusionScorer:
      name = "fusion"

      def __init__(self, scorers: dict[str, Scorer], weights: dict[str, float], k_rrf: int = 60, depth: int = 200) -> None:
          """Holds the component scorers."""

      def score(self, ctx: TurnContext, k: int = 200, policy: SessionPolicy = SessionPolicy()) -> list[tuple[str, float]]:
          """Runs every scorer, applies the policy (6.3), then rrf(). Empty component lists are simply ignored.
          exclude_played: drop played tracks from every list before rrf. use_same_artist=False: weight 0 for same_artist."""

  def grid_search(cached: dict[str, list[list[tuple[str, float]]]], contexts: list[TurnContext],
                  ground_truth: list[dict], grid: dict[str, list[float]]) -> list[dict]:
      """Tries every weight combination on the cached val lists (no re-retrieval); returns results sorted by final_score."""
  ```
- **How to test.**
  ```bash
  python -m retrieval.run_experiment --method bm25_plus   --split val   # these save the top-200 caches
  python -m retrieval.run_experiment --method dense       --split val
  python -m retrieval.run_experiment --method same_artist --split val
  python -m retrieval.run_experiment --method bpr_sim     --split val
  python -c "from retrieval.fusion import main_grid; main_grid()"       # prints the top 10 weight sets
  python -m retrieval.run_experiment --method fusion --split val
  ```
- **Done when.** The best weights and their val final score are logged. The fused val score beats the best single component, **confirmed on `val_all`** (the gain is larger than the spread between folds). The chosen weights are stored as constants in `fusion.py`.
- **Pitfalls.**
  - Tune on **val only**, never on test.
  - Use a coarse grid (for example weights in {0, 0.5, 1, 2}): 4 components → 256 combos, each run in pure Python on the cached lists. That's fast. Don't re-run dense per combo.
  - Optimize **final_score**, not only nDCG. The grid computes diversity on the full 1,000 val sessions.
  - Signals behave differently at turn 1 (no session). Per-turn weights (turn 1 vs 2–8) are a simple, defensible extension, but only if the gain on val is clear.
  - Overfitting risk: too many knobs on 8,000 turns. Prefer the simplest weights within ~0.002 of the best.

---

### W1-3 — Final retriever → `retrieval/final_retriever.py` — **Worker 1** (Mon Oct 5)

- **Objective.** Wrap the tuned pipeline as the `RetrievalModule` subclass the assignment asks for (`retrieval/README.md` L28-36), and produce the test `predictions.json`.
- **Existing code to reuse.** `RetrievalModule` (`base.py` L9-39); `FusionScorer` with frozen weights; `context.load_sessions/iter_turn_contexts/finalize_top_k`; the output format of `run_baseline` (L84-90) and the `json.dump` of `main` (L109-110).
- **New file.**
  ```python
  class FinalRetriever(RetrievalModule):
      def __init__(self, cache_dir: str = "./cache") -> None:
          """Loads the catalog once and builds all component scorers + FusionScorer with the tuned weights."""

      def retrieve(self, ctx: TurnContext, topk: int = 20, policy: SessionPolicy = SessionPolicy()) -> list[str]:
          """Full pipeline for one turn (used by our runner and by the Part 2 chatbot).
          Part 1 always uses the default policy; the Part 2 agent passes its own (6.3)."""

      def text_to_item_retrieval(self, query: str, topk: int) -> list[str]:
          """Interface method: treats `query` as the current message, with no history or played tracks."""

      def batch_text_to_item_retrieval(self, queries: list[str], topk: int) -> list[list[str]]:
          """Calls text_to_item_retrieval for each query."""

  def main() -> None:
      """CLI: --split test --output predictions.json. Runs retrieve() for every turn, then check_predictions."""
  ```
- **How to test.**
  ```bash
  python -m retrieval.final_retriever --split test --output predictions.json
  python -m retrieval.evaluation.make_ground_truth --split test --output ground_truth.json
  python -m retrieval.evaluation.evaluate --predictions predictions.json --ground_truth ground_truth.json --catalog_size 47071
  ```
- **Done when.** There are 8,000 entries, all with exactly 20 unique catalog IDs and no played tracks. `evaluate` runs without errors. The test score is logged (**milestone test check 2 of 2**) and it beats 0.1444.
- **Pitfalls.**
  - `text_to_item_retrieval(query: str)` only gets a string, so session signals can't work through it. We keep it working (the class stays a valid drop-in), but predictions go through `retrieve(ctx)`. Say this openly in the report.
  - Whether QuickFeed/the TAs require predictions to be produced through `text_to_item_retrieval` is **A VERIFICAR** (the README says "or your own runner", L96). Ask a TA before the Oct 2 sync.
  - **Plan B if they do require it:** make `text_to_item_retrieval` parse the baseline query string (the output of `_build_retrieval_input`) back into a `TurnContext`. The last `user:` line is the current message, and the `track_id: <uuid>` inside the expanded `assistant:` lines gives the played tracks (`data_loader.py` L53 adds that prefix). Signature: `parse_baseline_query(query: str) -> TurnContext` in `context.py`. Pitfall: a user message can contain line breaks, so don't split naively on `\n`. Anchor on the `user: ` / `assistant: ` prefixes and test it against `build_turn_context` on 100 val turns. The two must agree.
  - Submission path in the group repo: `G1/predictions.json` and `G1/report.md` (confirmed).

---

### W2-3 — Diversity analysis → `results/diversity_analysis.md` — **Worker 2** (Mon Oct 5)

- **Objective.** Diversity is 20% of the grade (+0.05 diversity = +0.01 final). Check that fusion doesn't collapse onto popular tracks, and find a cheap, defensible way to raise coverage.
- **Existing code to reuse.** `compute_catalog_diversity` (`evaluation/diversity.py` L5-11); the saved `cache/runs/*_val.json`; `catalog.metadata_dict[tid]["popularity"]`.
- **What to report** (per component and for fusion, on the full val set):
  - diversity, and the median `popularity` of recommended tracks;
  - overlap between components (how many top-20 tracks are shared);
  - how often the same track appears across turns (the top-10 most recommended tracks).
- **Possible tweak (only if val says so).** Keep positions 1–10 as they are. In positions 11–20, add a small popularity penalty, or prefer candidates not yet shown in this session. Tune on val. Keep it only if final_score goes up.
- **How to test.** `python -m retrieval.run_experiment --method fusion --split val` before/after the tweak, and compare `catalog_diversity` and `final_score`.
- **Done when.** The analysis file has a table per component and a decision (keep the tweak or not) backed by val numbers.
- **Pitfalls.** Diversity is only comparable at the same number of turns. Always use the full val set (no `--limit`) when comparing diversity.

---

### Tue Oct 6 — Report, logs, mock exam

- Each person writes their own sections in `G1/report.md`. Worker 1 assembles it.
- Every claim in the report comes from a line in `results/worker*.md` (val) or one of the two test milestones.
- Mock exam: each person explains the **other's** file using this document's "Objective" and "Pitfalls" lines as a checklist.

---

## 8. Timeline (same dates, concrete outputs)

| Date | Worker 1 | Worker 2 |
| --- | --- | --- |
| **Sun Sep 27** | Baseline reproduced ✅ (0.1446). Create the private repo, invite W2. | Clone, run Section 4 setup, reproduce the baseline. |
| **Mon Sep 28** | **Pair:** T0.1 val set, T0.2 `context.py`, T0.3 `run_experiment.py`. Done = `bm25_baseline --split test` → 0.1446, and the baseline val score is logged. | *(same session)* |
| **Tue Sep 29 – Thu Oct 1** | W1-1 `bm25_plus.py`, steps 1→3, one val run per step. **Plus W1-2a:** a first `SameArtistScorer` (ordered by recency, then popularity; no BPR yet) and its val score. | W2-1 `dense.py`: convert embeddings, **sanity check first**, then query modes/fields, timing. |
| **Fri Oct 2** | **Sync:** cross-run each other's method, test milestone 1, merge (including the `same_artist` prototype, so fusion can use it). | *(same)* |
| **Sat Oct 3 – Sun Oct 4** | W1-2b `session_cf.py`: `bpr_sim`, BPR ordering inside `same_artist`, and the per-turn pool check. | W2-2 `fusion.py`: save caches, grid search on val, freeze weights. |
| **Mon Oct 5** | W1-3 `final_retriever.py`, test milestone 2, test push to QuickFeed. | W2-3 diversity analysis + optional tail tweak. |
| **Tue Oct 6** | Report sections (BM25+, session signals, final); assemble. | Report sections (dense, fusion, diversity). |
| **Tue Oct 6 (evening)** | Mock exam. | *(same)* |
| **Wed Oct 7** | Buffer. Final push well before 23:59. | Buffer. |

---

## 9. Git workflow (concrete)

Current state: `origin` = `JPCabral04/musicCRS` (private copy), `upstream` = `iai-group/dat640-2026-MusicCRS`. There is one local branch, `main`.

```bash
git checkout main && git pull origin main
git checkout -b worker1/bm25-plus          # or worker2/dense, worker1/session-cf, worker2/fusion
# ... work, then:
git add retrieval/bm25_plus.py results/worker1.md
git commit -m "bm25_plus: add tag_list field"
git pull origin main                        # resolve conflicts on your own branch
git push -u origin worker1/bm25-plus        # then open a PR on GitHub; the other person reviews and runs it
```

- **`docs/` is ignored on purpose** (`.gitignore`). The plans are **not** in the repo. Share `docs/part1_plan.md` and this file outside Git, and re-send them when they change. Don't put anything the code needs in `docs/`.
- `cache/`, `predictions*.json`, `ground_truth*.json`, `results*.json`, `.env` are ignored. `data/` and `results/*.md` are **not** ignored, which is what we want: commit `data/val_folds.json` and the logs.
- If the group repo uses this same `.gitignore`, `G1/predictions.json` will be ignored. Add it with `git add -f G1/predictions.json`.
- Never commit anything from `cache/` (the embedding `.npy` files are hundreds of MB).

---

## 10. Latency budget for Part 2 (3–5 s per response)

| Step | When | Expected cost | Risk |
| --- | --- | --- | --- |
| Load catalog + BM25 index | chatbot startup | seconds | none (once) |
| Load embedding `.npy` (~190 MB text + ~25 MB BPR) | startup | ~1 s | memory only |
| Load Qwen3-Embedding-0.6B | startup | several seconds | none (once) |
| BM25+ (2 × `get_scores`) | per turn | ms | low |
| Same-artist + BPR | per turn | ~1 ms | low |
| **Qwen3 query encoding on CPU** | per turn | 0.1 – 1+ s, depends on length | **⚠️ main risk** |
| Cosine over 47k × 1024 | per turn | ~10–20 ms | low |
| RRF | per turn | ms | low |

- Everything must be loaded **once** at startup. Never call `load_dataset` or reload a model inside a request.
- The agent's LLM calls in Part 2 (up to 5–10 per turn) also take time. Retrieval should stay well under 1 s.
- All numbers above are **A VERIFICAR**. Record real `ms/query` in every log line.

---

## 11. Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Dense sanity check fails (vectors don't match our encoder) by **Thu Oct 1** | Worker 2 uses the precomputed Qwen3 vectors only for **track-to-track** similarity (centroid of played tracks, like `bpr_sim`), which needs no query encoder. Worker 1 helps on Friday. |
| Dense too slow on CPU | Embed only `current_message`, cap `max_seq_length`, or drop dense from the chatbot and keep it offline only. |
| `torch` install problems on Windows | Try the CPU-only wheel first. Decide together before editing `requirements.txt`. |
| A gain on val disappears on test | Keep the simpler version and report it honestly. No tuning on test. |
| Fusion lowers diversity | W2-3 decides the positions 11–20 tweak, on val only. |
| One person falls behind | Raise it at the Oct 2 sync. Reassign **whole files**. |
| Suspiciously high val score (nDCG@20 > 0.4) | Assume a leak. Check `context.py` against the rules in Section 3. |

---

## 12. Open items — A VERIFICAR

1. **Qwen3 track vectors:** the text template, instruction and pooling used to create them are unknown. The W2-1 sanity check decides.
2. **Package versions** for Qwen3-Embedding (`torch`, `sentence-transformers`, `transformers`). They're not installed now.
3. **Real latencies** of every component (Section 10).
4. Whether `lyrics-qwen3...` vectors are empty or meaningless for many tracks.
5. Whether `tag_list` is ordered by relevance (it matters only for a "top-N tags" variant).
6. The same-artist hit rate using `artist_id` instead of `artist_name` (measured: 65% with names).
7. Whether grading requires predictions to come from `text_to_item_retrieval`, or whether our own runner with `retrieve(ctx)` is fine. Ask a TA. Plan B is in W1-3.
8. Whether QuickFeed checks the ≤ 20 IDs rule. (The path is confirmed: `G1/predictions.json` + `G1/report.md`.) Our `check_predictions` enforces it anyway.
9. Whether `conda activate` works in your Git Bash without running `conda init bash` first.
10. **Part 2:** how the agent detects "play that again" / "something different" to set the `SessionPolicy` (its own LLM call vs keyword rules). See 6.3.
10. **Hardware:** does either of us have an NVIDIA GPU? The plan assumes **CPU only**. With a GPU, embedding the ~16k val+test queries gets much faster, but Part 2 latency must still be measured on the machine that runs the chatbot.
