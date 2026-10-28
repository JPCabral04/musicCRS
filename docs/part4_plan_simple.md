# Part 4 — Simple Plan (JP & Alejandro)

Presentation: **Wed Nov 4** (one week from Oct 28, so about one task per person per day). In person, 15 points for the implementation, graded on the approved rubric in `part4_proposal.md`. For signatures, data fields and design notes, see `part4_plan_detailed.md`. Start here.

---

## 0. Who does what (short version)

Effort scale: easy = 1, medium = 2, hard = 3.

| | **JP** (base + critiquing + explanations) | | **Alejandro** (media + similarity search) | |
| --- | --- | --- | --- | --- |
| Foundation | T1 **Base**: new intents, slash commands, "shown tracks" memory, track vectors loaded once | 2 | T2 **Media lookup**: cover + 30 s preview from Deezer, cached | 2 |
| Features | T3 **F1.1 "more / less like #k"** (relevance feedback) | 2 | T4 **F4 UI**: covers and play buttons in the chat and the playlist panel | 2 |
| | T5 **F1.2 "older", "more popular", "more acoustic"**, stacking, no repeats | 2 | T6 **F2.1 "sounds like X"** (audio vectors) | 2 |
| | T7 **F3 "why this song?"** from the stored signals | 2 | T8 **F2.2 "songs about leaving home"** (lyrics vectors) | 3 |
| Evaluation | T9 **F5a** critique simulation + latency / LLM-call log | 3 | T10 **F5b** audio neighbours vs random vs text neighbours | 1 |
| Delivery | | | T11 demo script + README section | 1 |
| **Total** | | **11** | | **11** |

- **Why this split:** JP owns everything that changes *how the list is ranked* (critiques, and the explanation of that ranking). Alejandro owns everything that *finds tracks by similarity* (audio, lyrics) and everything *the user sees* (covers, previews). Points owned: JP 7 (F1.1, F1.2, F3, half of F5), Alejandro 8 (F2.1, F2.2, F4, half of F5).
- **Why we can work apart:** Alejandro starts with F4 (T2, T4), which needs nothing from JP. By the time he reaches F2 (T6), JP's base (T1) is merged.
- **Both of us must explain the whole system**, not only our own half.

---

## 1. What we have to build (approved rubric, 15 points)

| ID | What the user can do | Points | Task |
| --- | --- | --- | --- |
| F1.1 | "more like the second one", "less like the one by Bon Jovi" → the list changes | 2 | T3 |
| F1.2 | "older", "more popular", "more acoustic"; critiques add up across turns; a song already shown never comes back | 2 | T5 |
| F2.1 | "songs that sound like Smells Like Teen Spirit" → 3–5 tracks | 2 | T6 |
| F2.2 | "songs about leaving home" → 3–5 tracks, from our own lyrics index | 2 | T8 |
| F3 | "why the second one?" → reasons taken only from what was really used | 2 | T7 |
| F4 | Cover art and a 30-second preview in the UI | 3 | T2, T4 |
| F5 | Offline evaluation with simulated users, plus a per-turn latency / LLM-call log | 2 | T9, T10 |

---

## 2. How it fits together

```
user message ──► parser (slash rules, or 1 LLM call) ──► intent + slots
                                                              │
          ┌───────────────┬──────────────┬────────────────────┼───────────────┐
      CRITIQUE        SOUNDS_LIKE    LYRICS_SEARCH        EXPLAIN        (Part 2 intents)
   (T3, T5, JP)      (T6, Ale)       (T8, Ale)          (T7, JP)
          │               │              │                    │
          └──── nearest tracks by vector (one shared function, T1) ──┘
                                     │
           show_tracks(): pending options + "shown" set + why-signals
                                     │
        reply text + OPTIONS act + MEDIA act (covers, previews) ──► UI
```

- **One shared search:** every new feature is "take a vector, find the closest tracks, skip the ones already shown". T1 writes that function once (`nearest`); the features differ only in *which* vectors and *which* query vector.
- **One place that remembers what was shown:** `show_tracks()` (T1) saves the list for "add the first two" (R7), adds it to the "never repeat" set (F1.2) and stores *why* each track is there (F3).

---

## 3. Rules

1. **At most 5–10 LLM calls per turn** (we aim for ≤ 2: the parser, plus its one retry) and a **reply within 3–5 s**.
2. **Only catalog songs.** Vectors come from the dataset (`all_tracks`), loaded **once** at startup.
3. **Evaluation never touches the test split.** F5 uses the `val0` training fold. The simulated user may know the real next track; the system never does.
4. **Explanations never invent.** F3 builds its sentences from stored facts with a template. No LLM writes the reasons.
5. **Keep it simple** (we must explain every line): numpy dot products, no vector database, no new model training, no parallel requests, no LLM inside the features. Plain Python, as in Part 2.
6. **Never commit** API keys, `cache/` or the database file.

---

## 4. Tasks, day by day

Each task: **what** → **file** → **done when**. One week, so each task gets about one day. If a day slips, use the "if we fall behind" rule at the end of this section, not the rehearsal day.

### Wed Oct 28 – Thu Oct 29

- **Both:** check on Canvas that the revised proposal (Oct 16) was resubmitted and approved. Book the Nov 4 slot.
- **JP — T1. Base.** New intents `CRITIQUE`, `SOUNDS_LIKE`, `LYRICS_SEARCH`, `EXPLAIN` in the parser (LLM prompt + slash commands), stub handlers, `show_tracks()` + the "shown" set + why-signals in the state, and the track vectors (metadata, audio, lyrics) loaded once with a shared `nearest()` function.
→ `musiccrs/nlu/`, `musiccrs/state.py`, `musiccrs/data/vectors.py`, `musiccrs/handlers/shown.py` → done when every new slash command reaches its stub, `check_nlu` still passes with ≥ 2 new sentences per new intent, and startup prints the three matrix sizes. **PR merged by Thu Oct 29 evening: after T1 the interfaces are frozen.**
- **Alejandro — T2. Media lookup.** For a track, ask Deezer for its cover and 30 s preview (by ISRC, else by artist + title), cache the answer in memory, and add a `MEDIA` act to every reply that shows tracks.
→ `musiccrs/data/media.py`, two small call sites in `musiccrs/musiccrs.py` → done when `python -m musiccrs.data.media` prints a cover and a preview URL for Smells Like Teen Spirit, Hotel California and It's My Life.

### Fri Oct 30

- **JP — T3. F1.1 example critiques.** "More like #2" / "less like the one by X": move the query vector toward the liked tracks and away from the disliked ones (Rocchio), then show the 5 nearest tracks not shown before.
→ `musiccrs/handlers/critique.py` → done when, after a rock recommendation, "more like the second one" gives 5 new tracks closer to #2 (checked by cosine in `check_critique`).
- **Alejandro — T4. F4 UI.** Under every list in the chat: cover thumbnails and a play button per track. In the playlist panel: a cover and a play button per row.
→ `frontend/src/components/` → done when a recommendation shows 5 covers whose previews play, and the panel shows covers.

### Sat Oct 31

- **JP — T5. F1.2 attribute critiques.** "Older", "newer", "more / less popular", "more X" / "no X" (a tag). Each critique becomes a filter with a threshold taken from the list on screen; filters add up until a new list starts; shown tracks never come back.
→ `musiccrs/handlers/critique.py` → done when "older" then "more popular" gives tracks that are older *and* more popular than the first list, with no repeats.
- **Alejandro — T6. F2.1 sounds like.** Find the named track (Part 2 resolver), take its audio (CLAP) vector, show the 5 nearest tracks (not the same song by the same artist). Also run the lyrics count of T8 step 1 (`check_lyrics`), so Sunday starts with the answer.
→ `musiccrs/handlers/similar.py` → done when 3 seed songs each get 5 tracks, and the reply lists the seed.

### Sun Nov 1 — sync in the evening

- **JP — T7. F3 why this song?** "Why the second one?" / "why Numb?" → 2–4 sentences built from the track's stored signals (which retrievers found it, critiques applied, audio or lyrics similarity) plus facts checked against the database (shared tags, same artist as a playlist song).
→ `musiccrs/handlers/explain.py`, a small addition to `retrieval/final_retriever.py` → done when it works for a track from each source (recommend, critique, sounds like, lyrics) and every sentence can be traced to a stored value.
- **Alejandro — T8. F2.2 lyrics search.** Leave out the tracks with an empty or meaningless lyrics vector (counted on Saturday). Embed the theme with the same Qwen3 model (already loaded by the retriever) and show the 5 nearest lyrics vectors.
→ `musiccrs/handlers/similar.py`, `musiccrs/checks/check_lyrics.py` → done when "songs about leaving home", "heartbreak" and "partying all night" give 3 different, plausible lists.
- **Evening sync:** each person runs the *other's* branch from a fresh `git pull`. Merge everything into `main`. All 7 rubric features should now be demoable.

### Mon Nov 2

- **JP — T9. F5a evaluation + log.** On 1,000 `val0` conversations, a simulated user critiques the list toward the real next track; report nDCG@20 before vs after and the share of turns where it moved up. Count LLM calls per turn and print latency median / 95th percentile.
→ `musiccrs/checks/eval_critique.py`, `musiccrs/llm.py`, `musiccrs/checks/check_latency.py` → done when both scripts print their tables, and the numbers go into the README.
- **Alejandro — T10. F5b audio evaluation.** 1,000 random seed tracks: tags shared with the seed by the top-5 audio neighbours, vs 5 random tracks, vs the top-5 text-embedding neighbours.
→ `musiccrs/checks/eval_audio.py` → done when it prints the 3 numbers.
- **Alejandro — T11.** Demo script (one line per rubric item) + "Part 4" README section. → `docs/part4_demo.md`.

### Tue Nov 3 — go / no-go

- Morning: last merge into `main`, full demo from a fresh start. Fix what fails.
- Afternoon: mock exam, each person explains the **other's** code.

### Wed Nov 4 — present

### If we fall behind

Every feature is worth points, so we keep all of them and make each one smaller, in this order:
1. F5 runs on fewer conversations (200 instead of 1,000) and reports fewer variants.
2. F1.2 keeps only year and popularity (no tags).
3. F4 shows covers and previews in the chat only, not in the playlist panel.
4. F3 drops the "which retrievers found it" sentence (no `retrieve_with_sources`).

---

## 5. How we work together

- Each person edits **only their own files**. After T1, `state.py`, `nlu/`, `data/vectors.py` and `handlers/shown.py` change only if both agree.
- Alejandro's two call sites in `musiccrs.py` (T2) are the one exception, reviewed by JP.
- One branch per task (`jp/p4-base`, `jp/critique`, `jp/explain`, `jp/p4-eval`, `ale/media`, `ale/media-ui`, `ale/sounds-like`, `ale/lyrics`, `ale/p4-eval`) → pull request → the other runs it → merge into `main`.

---

## 6. Commands (Git Bash)

```bash
conda activate musiccrs
python -m musiccrs.musiccrs                      # backend on :5000
cd frontend && npm start                         # frontend on :3000
python -m musiccrs.checks.check_nlu              # parser, now with the Part 4 intents
python -m musiccrs.checks.eval_critique          # F5a (no LLM)
python -m musiccrs.checks.eval_audio             # F5b (no LLM)
python -m musiccrs.checks.check_latency          # latency + LLM calls per turn
```

---

## 7. Still to find out

- **Approval:** is the revised proposal (Oct 16) on Canvas and approved?
- **Deezer:** does `track/isrc:<ISRC>` find most catalog tracks, and how long do preview links stay valid?
- **Lyrics:** how many tracks have an empty or meaningless lyrics vector? (T8, first step.)
- **Memory on the demo laptop:** three more matrices (~0.5 GB in total). Does startup still work?
