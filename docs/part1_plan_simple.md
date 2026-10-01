# Part 1 — Simple Plan (JP & Alejandro)

Deadline: **Wed Oct 7, 23:59**. For details (line numbers, function signatures), see `part1_plan_detailed.md`. Start here.

---

## 0. Who does what (short version)

| | **JP** | **Alejandro** |
| --- | --- | --- |
| Shared base | T1–T3: validation set, context builder, experiment runner (Wed Sep 30) | Reviews and runs the T1–T3 pull request |
| Recommenders | T6 **Dense (Qwen3)** — search by meaning | T4 **Better BM25** — keyword search, improved |
| | | T5 **Same artist** — songs by artists already played |
| | | T7 **BPR similar** — songs similar to the ones already played |
| Combine | T8 **Merge (RRF)** — combine all lists, tune weights | T10 **Diversity check** |
| Final | T9 **Final retriever** + the run on test | T11 **Submission push** to the group repo + assemble the report |
| Report | Sections: harness, dense, fusion, final | Sections: BM25+, same artist, BPR, diversity |

- **JP** has the more complex part: the neural model, the fusion, and the final class.
- **Alejandro** has the parts that are simpler to code, but T5 (same artist) is probably **the biggest score gain** of all (see Section 3).

---

## 1. What we have to build

A user chats with a music bot. At each turn, the user asks for something, for example:

> "Nice! Now play something more upbeat by the same band."

Our program reads the conversation so far and must return **the 20 songs** (out of 47,071) most likely to be the one the bot really played next.

- The dataset has 1,000 **test** conversations × 8 turns = 8,000 predictions.
- For each turn we know the correct song (the "gold" song), so we can score ourselves.

**The grade:**

```
final_score = 0.8 × nDCG@20 + 0.2 × diversity
```

- **nDCG@20** = "did we put the correct song high in our list?" Rank 1 = 1.0, rank 20 ≈ 0.23, not in the list = 0.
- **diversity** = "how many *different* songs did we recommend overall?" Recommending the same popular songs to everyone is penalized.
- Baseline = **0.1444** (0 points). **0.2235** = full marks. We have 0.1446 locally.

---

## 2. How the existing code works (the baseline)

Only 3 files matter:

| File | What it does |
| --- | --- |
| `retrieval/bm25.py` | A search engine over song **name + artist + album**. |
| `retrieval/run_bm25_baseline.py` | For every turn, glues the **whole conversation** into one text and searches with it. Writes `predictions.json`. |
| `retrieval/evaluation/evaluate.py` | Compares `predictions.json` with the correct songs and prints the score. |

**BM25** = keyword search. A song scores high if its name/artist/album shares rare words with the query (for example "Nirvana").

**Why the baseline is weak:**
1. It searches with the *whole* conversation, so an old message counts as much as the current request.
2. It ignores tags ("chill", "rock", "90s"), so mood/genre requests don't match.
3. It often recommends songs that were **already played**. In the data, the correct song is **never** one that was already played. Those are wasted slots.
4. It doesn't use the most useful fact we found (next section).

---

## 3. What we found in the data

- **65% of the time** (turns 2–8), the correct song is **by an artist who was already played** in this conversation. That's usually only ~60 candidate songs. This is our biggest opportunity.
- The correct song is **never** a song already played.
- These two facts are **patterns of this dataset**, not rules about real users (see Section 4b).
- The dataset also gives **embeddings** (lists of numbers that represent each song's meaning) made with a model called **Qwen3**. With them we can match "chill rainy-day music" to songs even when no words match.
- It also gives **BPR vectors**: songs that the same people listen to get similar vectors ("people who like X also like Y").

---

## 4. Our approach in one paragraph

We build **4 simple "recommenders"**. Each one gives a ranked list of songs for the current turn. Then we **merge** the 4 lists into one top-20:

| # | Recommender | Idea | Owner |
| --- | --- | --- | --- |
| 1 | **Better BM25** | Keyword search, but: add tags, count the current message more | Alejandro |
| 2 | **Same artist** | Songs by artists already played in this conversation | Alejandro |
| 3 | **Dense (Qwen3)** | Search by meaning using the song embeddings | JP |
| 4 | **BPR similar** | Songs similar to the ones already played | Alejandro |
| → | **Merge (RRF)** | A song high in several lists goes to the top | JP |

**RRF (Reciprocal Rank Fusion)** = for each song, add `weight / (60 + its rank)` over all lists. Simple, and easy to explain.

---

## 4b. Two dataset tricks we can switch off

- **Trick 1: remove songs already played.** In this dataset the correct song is never one already played, so those slots are always wasted.
- **Trick 2: same artist.** In this dataset the correct song is often by an artist already played.
- In Part 1 both are fine: we are scored on this dataset, and both use only what happened before the current turn.
- In Part 2 a real user may say "play that again" (trick 1 must be off) or "something different" (trick 2 must be off).
- So both are **switches**, set in **one shared place** (the merge step and the final top-20 cut), never inside a single recommender. Part 1 keeps them on. In Part 2 the chatbot turns them off when the user asks.

---

## 5. Three rules

1. **Never tune on the test set.** We compare our ideas on 1,000 conversations taken from `train` (our "validation set"). We only look at the test score twice: Oct 3 and Oct 5.
2. **Never use hidden information:** the `thought` fields, `goal_progress_assessments`, the embedding split `test_tracks` (it contains the test answers!), or anything from the current turn after the user message.
3. **No LLM calls.** And keep everything fast: the same code must answer in under 3–5 s in the Part 2 chatbot.

---

## 6. Tasks, day by day

Each task: **what** → **file** → **done when**.

### Tue Sep 29 (today)

- **JP:** send this plan to Alejandro.
- **Alejandro:** set up the conda env, reproduce the baseline (≈ 0.1446), and read `bm25.py` and `run_bm25_baseline.py`.

### Wed Sep 30

**JP — T1. Validation set.** Pick 1,000 random `train` conversations (fixed seed 42) and save their IDs.
→ `data/val_session_ids.json` → done when running it twice gives the same file.

**JP — T2. Context builder.** For each turn, extract 4 things: the current message, the earlier messages, the songs already played, and the baseline query text.
→ `retrieval/context.py` → done when turn 1 has 0 played songs and turn 8 has 7.

**JP — T3. Experiment runner.** One command that runs any recommender on validation or test and prints the score and the time per query.
→ `retrieval/run_experiment.py` → done when running the baseline on test gives **0.1446** again.

JP opens a pull request. **Alejandro** reviews it and runs the baseline command himself. He must get the same 0.1446.

**Alejandro — start T4** (see below). Until T3 is merged, test with the baseline scripts.

### Thu Oct 1 – Fri Oct 2

**Alejandro — T4. Better BM25.** Do one change at a time and write down the score after each:
1. measure the gain of removing already-played songs (the removal itself is done by the shared final step, not inside BM25, see Section 4b);
2. add `tag_list` to the search index;
3. score the current message and the old history separately, and give the current message more weight.

→ `retrieval/bm25_plus.py` → done when it beats the baseline on validation.

**Alejandro — T5. Same-artist recommender (simple version).** Return the songs by already-played artists, the most recent artist first, then by popularity. Empty on turn 1.
→ `retrieval/session_cf.py` → done when its validation score is written down.

**JP — T6. Dense recommender.**
1. Download the song embeddings once and save them locally.
2. **Check first** that our Qwen3 model produces the same kind of vectors: embed a song's own name/artist and see if that song comes out at rank 1.
3. Embed the user's message and return the closest songs.
4. Measure the time per query.

→ `retrieval/dense.py` → done when the check passes and the validation score is written down.

### Sat Oct 3 — sync meeting

Each person runs the *other's* code and gets the same numbers. Check on test once. Merge everything into `main`.

### Sat Oct 3 – Sun Oct 4

**Alejandro — T7. BPR recommender.** Average the BPR vectors of the played songs, return the most similar songs. Also use it to order the same-artist list. (It uses the embedding loader from JP's `dense.py`, merged on Oct 3.)
→ `retrieval/session_cf.py`.

**JP — T8. Merge (RRF).** Combine the 4 lists. Try a few weights per list **on validation** and keep the best.
→ `retrieval/fusion.py` → done when the merge beats every single recommender.

### Mon Oct 5

**JP — T9. Final version.** Wrap everything in one class (required by the assignment), run on test, write `predictions.json`, and check it (8,000 rows, exactly 20 different songs each, no played songs).
→ `retrieval/final_retriever.py`.

**Alejandro — T10. Diversity check.** Are we recommending too many popular songs? If yes, try a small fix on positions 11–20, and keep it only if the validation score goes up.
→ `results/diversity_analysis.md`.

**Alejandro — T11. Test push.** Copy `predictions.json` to `G1/predictions.json` in the group repo and push once to see that QuickFeed accepts it.

### Tue Oct 6 – Wed Oct 7

- Each person writes the report sections for their own parts (Section 0).
- Alejandro assembles `G1/report.md`.
- Mock exam (Tue evening): each person explains the **other's** code.
- Final push well before 23:59 on Wed.

---

## 7. How we work together

- Each person only edits **their own files**. The shared files (T1–T3) change only if both agree.
- One branch per task (for example `alejandro/bm25-plus`, `jp/dense`) → pull request → the other person reviews and runs it → merge.
- Each person keeps a log: `results/jp.md`, `results/alejandro.md`. One line per experiment:

  | What I changed | nDCG@20 | diversity | final | Keep? |
  | --- | --- | --- | --- | --- |

- Never commit `cache/` or big data files.

---

## 8. Commands (Git Bash)

Once per terminal:

```bash
conda activate musiccrs
```

Run something (after T3 exists):

```bash
python -m retrieval.run_experiment --method bm25_plus --split val --limit 200   # quick check (only compare nDCG)
python -m retrieval.run_experiment --method bm25_plus --split val               # the number you write in your log
```

The final test check (T9):

```bash
python -m retrieval.final_retriever --split test --output predictions.json
python -m retrieval.evaluation.make_ground_truth --split test --output ground_truth.json
python -m retrieval.evaluation.evaluate --predictions predictions.json --ground_truth ground_truth.json --catalog_size 47071
```

---

## 9. Still to find out

- Does either of us have an NVIDIA GPU? (Dense is slow on CPU.)
- Ask a TA: must predictions come from `text_to_item_retrieval(query)`, or can we use our own runner?
- JP adds `torch` + `sentence-transformers` to `requirements.txt` in a small PR (needed for T6).
