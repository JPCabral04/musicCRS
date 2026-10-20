# Part 2 — Simple Plan (JP & Alejandro)

Presentation: **Wed Oct 28** (target; rescheduled on Oct 15 because T1 had not started — dates are flexible, finishing everything is what matters). In person, **one attempt only**, 10 points. For details (signatures, data fields, design notes), see `part2_plan_detailed.md`. Start here.

---

## 0. Who does what (short version)

Effort scale: easy = 1, medium = 2, hard = 3.

| | **JP** (base + recommendations) | | **Alejandro** (frontend + lookup) | |
| --- | --- | --- | --- | --- |
| Foundation | T1 **Database** (SQLite built from the catalog) | 2 | T5 **R1 playlist panel** in the React UI | 3 |
| | T2 **Agent skeleton**: state, handler table, slash commands, `PLAYLIST` message | 2 | T6 **Track resolver**: finds a track from a loose name ("its my life" → "It's My Life") | 3 |
| | T3 **Intent parser**: one LLM call turns the message into an intent + slots | 3 | T7 **R2** add / remove / view / clear | 2 |
| Features | T4 **R6 recommend** 3–5 songs from the playlist | 1 | T8 **R4 disambiguation** ("Love" → pick one), ranked | 2 |
| | T9 **R8 playlist from a description** ("sad love songs") | 2 | T10 **R5 questions** about tracks and artists | 2 |
| | T11 **R7 selection** ("add the first two", "all except the Metallica one") | 3 | T12 **R3 help** ("what can you do?") | 1 |
| Delivery | T13 simulator config + latency check | 1 | T14 demo script + README section | 1 |
| **Total** | | **14** | | **14** |

- **Why it's fair:** each person has one hard foundation piece (JP: the intent parser; Alejandro: the playlist panel and the track resolver), one hard NL feature (JP: R7; Alejandro: the resolver behind R2/R4), and the same total effort.
- **JP** builds the shared base first (T1–T3), because everything depends on it. Then JP does everything that uses retrieval (R6, R8) and the selection that follows a recommendation (R7). This reuses JP's `FinalRetriever` from Part 1.
- **Alejandro** owns everything the user sees (the UI panel) and everything that turns a name into a track (resolver, R2, R4, R5). Alejandro starts on the UI on day 1, so there is no waiting for the base.
- **Both of us must explain the whole system** at the presentation, not only our own half (mock exam on Oct 20).

---

## 1. What we have to build

A web chat where a user manages a playlist and gets recommendations, **in natural language**:

| ID | What the user can do | Points | Task |
| --- | --- | --- | --- |
| R1 | See the playlist next to the chat; remove/clear/add from the UI too | 1 | T5 |
| R2 | "add Smells Like Teen Spirit", "remove the Queen song", "show my playlist", "clear it". Only songs from our database. By name, or name + artist | 3 | T1, T6, T7 |
| R3 | "what can you do?" → explanation of the features | 1 | T12 |
| R4 | "add Love" → a short, well-ranked list to choose from | 1 | T8 |
| R5 | "who sings X?", "when was X released?", "how many songs does Y have?" (4 types for tracks or artists) | 1 | T10 |
| R6 | "recommend something" → 3–5 songs **related to the playlist** | 1 | T4 |
| R7 | "add the first two", "add all of them", "none", "all except the one by Metallica" (≥ 3 ways) | 1 | T11 |
| R8 | "make me a playlist for the gym" → a full playlist, its **length chosen by us** | 1 | T9 |

Names and artists must match **loosely**: ignore case, punctuation and accents.

---

## 2. How it fits together

```
user message
   │
   ├─ starts with "/" ? ──► slash command (no LLM)      ← simulator + UI buttons
   │
   └─ else ──► intent parser (1 LLM call) ──► {intent, slots}
                                                 │
                                          handler for that intent
                                (playlist / questions / recommend / ...)
                                                 │
                       reply text  +  PLAYLIST message (the whole playlist)
                                                 │
                                    UI redraws the playlist panel
```

- **One source of truth:** the playlist lives in the agent. The UI never touches the database. Its buttons just send chat messages such as `/remove <id>` or `/clear`.
- **One agent per browser tab:** DialogueKit creates a new `MusicCRS` for every connection, so each user has their own playlist. The database and retriever are therefore loaded **once**, at module level, not in `__init__`.

---

## 3. Rules

1. **At most 5–10 LLM calls per turn** (we aim for ≤ 3) and a **reply within 3–5 s**.
2. **Only catalog songs** can be added or recommended (47,071 tracks).
3. **Load everything once** at startup (catalog, DB, retriever). Never load inside a reply.
4. **Session rules from Part 1 are switches** (`SessionPolicy`): R6 never re-recommends songs already in the playlist; "something different" turns the same-artist signal off.
5. **Never commit** the Open WebUI API key or the simulator upload token.
6. **Everything ends up in `main`** (the spec requires one branch).

---

## 4. Tasks, day by day

Each task: **what** → **file** → **done when**.

### Tue Oct 13 (done)

- **JP:** send this plan to Alejandro.
- **Alejandro:** run the backend (`python musiccrs/musiccrs.py`) and the frontend (`npm start`), and read `musiccrs/musiccrs.py` and `frontend/src/components/ChatBox/ChatBox.tsx`.

### Thu Oct 15 (today)

**JP — T1. Database.** Build an SQLite file from the catalog: tracks, artists, normalized names, plus a full-text index. Add one shared `normalize()` function.
→ `musiccrs/data/db.py`, `musiccrs/data/build_db.py` → done when `python -m musiccrs.data.build_db` passes its self-check: `find_by_name("smells like teen spirit")` returns the Nirvana track first, and `find_by_name("hotel california")` finds "Hotel California - 2013 Remaster" (Eagles). ("Bohemian Rhapsody" and "Don't Stop Me Now" are **not** in the catalog.) **Open the PR first thing:** Alejandro needs it on Friday.

**Alejandro — T5. Playlist panel (start).** Add a side panel that shows the playlist from a `PLAYLIST` message. Until T2 exists, test with a fake message.
→ `frontend/src/components/Playlist/` → done when a fake playlist renders next to the chat.

### Fri Oct 16

**JP — T2. Agent skeleton.** Per-user state (playlist, pending options), a table from intent → handler function, slash commands (`/add artist: track`, `/del ...`, `/list`, `/clear`, `/recommend`, `/remove <id>`), and a `PLAYLIST` message after every change.
→ `musiccrs/musiccrs.py`, `musiccrs/state.py` → done when `/add nirvana: smells like teen spirit` then `/list` works. **Done Oct 17** (also `musiccrs/nlu/parser.py` with the slash rules, and simple exact-match handlers in `musiccrs/handlers/playlist.py` that Alejandro takes over in T7).

**JP — T3. Intent parser.** One LLM call returns JSON: the intent plus its slots (track, artist, question type, description, selection). Slash commands skip the LLM.
→ `musiccrs/nlu/parser.py` → done when 20 example sentences (≥ 2 per intent) parse correctly. **After T3, the interfaces are frozen.** **Done Oct 19:** 37/37 sentences correct, 0.45 s per LLM call on average (`python -m musiccrs.checks.check_nlu`). Also `musiccrs/llm.py` (LLM client, key from the `LLM_API_KEY` environment variable) and `musiccrs/nlu/prompt.py`. Slot names and the 8 question types: detailed plan §3.3.

**Alejandro — T6. Track resolver.** Given a name (and maybe an artist), return the matching tracks: exact normalized match first, then fuzzy.
→ `musiccrs/data/resolver.py` → done when "its my life", "IT'S MY LIFE!" and "it's my life by bon jovi" all find the Bon Jovi track.

### Sat Oct 17 – Tue Oct 20

Suggested order (JP's updated Oct 19, after T3 took until Mon): JP **T4 (Mon) → T11 (Tue) → T9 (Wed, before the sync; Thu buffer) → T13 at the sync** (T4 and T11 done Oct 19, T9 done Oct 20). T11 moves before T9 because Alejandro's T8 ("the second one") uses T11's `select_indices`, and T11 is tested on T4's recommendations. Alejandro T7 (Sat), T8 (Sun), T10 (Mon–Tue), T12 and T5 finish (Tue).

**JP — T4. R6 recommend.** Pass the playlist to `FinalRetriever` as the "played tracks" and return 5 songs that are not in the playlist. Save them as pending options for T11.
→ `musiccrs/handlers/recs.py` → done when a playlist of 3 rock songs gives 5 related songs, not just popular ones. **Done Oct 19:** rock, jazz and pop playlists each get 5 related songs, none already in the playlist, in 10 ms per call (`python -m musiccrs.checks.check_recs`). "Something different" leaves out the playlist's artists. Startup now takes 45–51 s (retriever loaded once). Also on Oct 19: `musiccrs/` was reorganized into `data/`, `nlu/`, `handlers/` and `checks/` (layout in the detailed plan §3).

**JP — T9. R8 playlist from a description.** The LLM turns the description into a search query and a length hint (gym session ≈ 60 min). Length = minutes ÷ average song length, kept between 8 and 25.
→ `musiccrs/handlers/recs.py` → done when "sad love songs" and "energetic gym music" give different playlists of sensible lengths. **Done Oct 20:** sad love songs → 11 songs (45 min), gym session → 15 (60), short coffee break → 8 (15), long road trip → 25 (120) (`python -m musiccrs.checks.check_playlist`); 2 LLM calls per turn, 1–3 s. The new playlist replaces the old one and the reply says so. The query prompt keeps activity words like "gym" out, because they match song titles and artist names (Gym Class Heroes).

**JP — T11. R7 selection.** After a recommendation: "all", "none", "the first two", "1 and 3", "all except the one by X". Simple rules first, and the LLM only for the hard cases (exclusions by artist or title).
→ `musiccrs/handlers/selection.py` → done when ≥ 3 formulations work, including an "except" one. **Done Oct 19:** all, none, ordinals ("the first two", "1 and 3", "the last one") by rules with no LLM call; "all except the one by Bon Jovi", "everything but Toxic" and "the Coldplay one" by one LLM call (344 ms mean). 16/16 rule and 6/6 LLM cases pass (`python -m musiccrs.checks.check_select`). A whole SELECT turn (parser + selection) takes 0.4–1.1 s. Also works for R4 same-name choices (exactly one is added), so T8 only has to set `pending_kind="disambiguation"`. The catalog has only one Metallica track, so demos use Bon Jovi.

**Alejandro — T7. R2 handlers.** Add / remove / view / clear, using T6. Refuse songs that are not in the database, with a clear message.
→ `musiccrs/handlers/playlist.py` → done when all 4 actions work in natural language and the panel updates.

**Alejandro — T8. R4 disambiguation.** If T6 returns several tracks, show the top 5 as clickable options. Rank them by popularity plus similarity to the playlist (same artist, BPR vectors from Part 1).
→ `musiccrs/handlers/playlist.py` → done when "add Love" shows 5 options and clicking or typing "the second one" adds it.

**Alejandro — T10. R5 questions.** 4 question types for tracks (artist, album, release year, length) and 4 for artists (number of songs, most popular song, albums, genres/tags). Answers come from the database, not the LLM.
→ `musiccrs/handlers/qa.py` → done when all 8 types answer correctly in natural language.

**Alejandro — T12. R3 help.** "What can you do?", "help", "how do I remove a song?" → a short explanation with examples.
→ `musiccrs/handlers/playlist.py` → done when 3 different phrasings get a useful answer.

**Alejandro — T5. Playlist panel (finish).** Connect it to the real `PLAYLIST` message: remove and clear buttons, plus an add box.

### Wed Oct 21 — sync meeting

- Each person runs the *other's* code from a fresh `git pull`.
- **JP — T13:** set `COMMANDS` in `simulation/config.py` to our real slash commands; run `python simulation/simulator.py --no-upload`; write down the time per intent.
- Fix whatever breaks. Merge everything into `main`.

### Thu Oct 22 – Fri Oct 23

- **Alejandro — T14:** a demo script with one example line per requirement (R1–R8), plus a short README section.
- Buffer for whatever is still failing (these two days exist so that nothing is cut).

### Sat Oct 24 – Mon Oct 26

- Rehearse the demo end to end with the script.
- Mock exam: each person explains the **other's** code.
- Final simulator run **with upload** (only the last upload counts).

### Tue Oct 27 — go / no-go

If a requirement still fails, fix it today. We get one attempt, so a full demo beats a partial one.

### Wed Oct 28 — present

---

## 5. How we work together

- Each person only edits **their own files**. JP's base files (`data/db.py`, `state.py`, `nlu/parser.py`, `musiccrs.py`) change only if both agree once they are frozen (after T3).
- Handlers live in separate files (`handlers/playlist.py` / `handlers/qa.py` for Alejandro, `handlers/recs.py` / `handlers/selection.py` for JP), so we never edit the same file.
- One branch per task (for example `jp/db`, `ale/playlist-panel`) → pull request → the other person reviews and runs it → merge.
- Never commit `cache/`, the database file, API keys or the upload token.

---

## 6. Commands (Git Bash)

```bash
conda activate musiccrs
python -m musiccrs.data.build_db                      # once: builds cache/musiccrs.db
python -m musiccrs.musiccrs                      # backend on :5000 (as a module, from the repo root)
cd frontend && npm start                         # frontend on :3000
python simulation/simulator.py --no-upload       # needs the backend running
python simulation/simulator.py                   # final run, uploads
```

---

## 7. Still to find out

- **The presentation date:** book an Oct 28 slot early (few slots, no rebooking). Part 3 is also due Oct 28, so check that both fit.
- **LLM key:** does the Open WebUI key work at `https://openwebui.ux.uis.no` (Gemma 4 31B), and how long does one call take?
- **Startup and dense:** does loading `FinalRetriever` (Qwen3 model) at startup work on the demo laptop, and is R6/R8 still under 3–5 s? If not, R6/R8 run without dense. (On JP's GPU laptop: 45–51 s startup, R6 in 10 ms.)
- **Simulator:** which slash commands does it really send? Check its first `--no-upload` run before Oct 21.
