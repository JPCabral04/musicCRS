# Part 4 Work Plan — Detailed Version (tied to the real code)

> **Names and dates:** `part4_plan_simple.md` is the source of truth for who does what and when. This file adds the concrete interfaces, data fields and design notes. If the two disagree, the simple plan wins. The graded rubric is the revised one in `part4_proposal.md` (Oct 16).

- File references are to `main` at commit `41d71aa` (Oct 28).
- **A VERIFICAR** = not confirmed in the code or the data yet. Check it before relying on it.
- Signatures below are **proposals** (signatures and docstrings only). The owner may change them until T1 is merged. After that, shared interfaces (§3) change only if both agree.
- **Simplicity is a requirement, not a nice-to-have.** Every feature below is "one vector, one dot product, a few `if`s". If a design gets harder to explain than that, simplify it.

---

## 1. What we reuse from Parts 1 and 2

| What | Where | Used by |
| --- | --- | --- |
| `load_track_matrix(field, track_ids)` → `(matrix, has_vector)`, rows in catalog order, L2-normalized, cached in `cache/embeddings/` | [retrieval/methods/dense.py](../retrieval/methods/dense.py) L40 | T1 (audio, lyrics) |
| The dense scorer's metadata matrix (`.matrix`, `.track_ids`) and encoder (`.encode_queries(texts)`, Qwen3 query prompt, L2-normalized) | `services.retriever.fusion.scorers["dense"]` | T1 (metadata vectors, no second copy), T8 (lyrics query) |
| `FusionScorer.score`: builds one list per component (`bm25_plus`, `same_artist`, `bpr_sim`, `dense`), then `fuse` | [retrieval/methods/fusion.py](../retrieval/methods/fusion.py) L76 | T7 (which retrievers found a track) |
| `resolve(db, track, artist)` | [musiccrs/data/resolver.py](../musiccrs/data/resolver.py) L178 | T6 (seed track of "sounds like") |
| `handle_recommend`, `recommend_context`, `options_act`, `describe_track` | [musiccrs/handlers/recs.py](../musiccrs/handlers/recs.py), [musiccrs/handlers/playlist.py](../musiccrs/handlers/playlist.py) | T1 (record shown tracks), T3, T6, T8 (same reply format) |
| `state.pending_options` + `handle_select` | [musiccrs/state.py](../musiccrs/state.py), [musiccrs/handlers/selection.py](../musiccrs/handlers/selection.py) | every new list can be followed by "add the first two" |
| `ask_json(llm, messages)` | [musiccrs/llm.py](../musiccrs/llm.py) L67 | T9 (count calls here) |
| `print_turn_time`, `check_latency` | [musiccrs/musiccrs.py](../musiccrs/musiccrs.py) L113, [musiccrs/checks/check_latency.py](../musiccrs/checks/check_latency.py) | T9 |
| `get_ndcg(gold, preds, k)` | [retrieval/evaluation/metrics.py](../retrieval/evaluation/metrics.py) L9 | T9 |
| `load_sessions`, `build_turn_context`, `data/val_folds.json` | [retrieval/context.py](../retrieval/context.py) | T9 (val0 only) |
| Chat messages render HTML (`dangerouslySetInnerHTML`) | [frontend/src/components/ChatMessage.tsx](../frontend/src/components/ChatMessage.tsx) L55 | T4 |

---

## 2. Data facts for Part 4

From `talkpl-ai/TalkPlayData-Challenge-Track-Embeddings`, split `all_tracks` (Part 1 plan §2.3). Never load `test_tracks`.

| Field | Dim | Notes | Used by |
| --- | ---: | --- | --- |
| `metadata-qwen3_embedding_0.6b` | 1024 | already loaded by the dense scorer (normalized) | F3, F5b baseline (F1 moved to audio, §4.1) |
| `audio-laion_clap` | 512 | norm 1.0 | F1 (critiques), F2.1, F5b |
| `lyrics-qwen3_embedding_0.6b` | 1024 | not normalized (norm ~110); `load_track_matrix` normalizes it | F2.2 |

- 492 tracks have **no** vector in any Qwen3 field nor in CLAP (zero rows, `has_vector = False`). They are never returned by `nearest`.
- **A VERIFICAR (T8, first step):** how many lyrics vectors are "meaningless" (instrumentals). Likely sign: many tracks share (almost) the same vector, the embedding of an empty or placeholder text. Count the most common rounded vectors; leave those rows out with a `lyrics_ok` mask.
- **Lyrics text is not in the dataset**, only the vectors. So F2.2 can show *that* a track matches a theme, never *which line* matches.
- Catalog fields for F1.2: `release_date` (644 empty → no year, filtered out by year critiques), `popularity` 0–93 (median 38), `tag_list` (noisy, mean 33 tags, 87 tracks without tags). Already in `TrackDB` as `Track.release_date`, `Track.popularity`, `Track.tags`.
- **For F4:** the catalog has an `ISRC` field (not stored in our SQLite DB). **A VERIFICAR:** string or list, and how many are empty. It is read from `services.retriever.catalog.metadata_dict[track_id]` (already in memory), so the DB is not rebuilt.
- Memory: CLAP 47,071 × 512 float32 ≈ 96 MB, lyrics ≈ 192 MB. Metadata is shared with the dense scorer (no new copy).

---

## 3. Shared interfaces (owner JP, T1, frozen after T1)

**Built in T1 (Oct 29, branch `jp/p4-base`).** The interfaces below are the code as merged. Three changes from the first proposal, agreed by JP:
1. `TrackVectors(track_ids, metadata_matrix, metadata_has_vector)` instead of `TrackVectors(dense_scorer)`, so a check can build it without loading the Qwen encoder.
2. New `state.last_shown`: `handle_select` empties `pending_options` after "add the first two", so `pick_shown` reads `last_shown` (kept after a selection) instead.
3. R8 does not call `show_tracks` (its songs go straight into the playlist; options would point at songs already there). It calls `remember_tracks` (shown + signals only) and forgets the old list (`last_shown = []`, `critique = None`).

New and changed files:

```
musiccrs/
  state.py              + last_shown, shown, signals, critique on DialogueState; + vectors on Services
  data/vectors.py       TrackVectors: the three matrices + nearest()          (T1, JP)
  data/media.py         cover + preview lookup, MEDIA act                     (T2, Ale)
  handlers/shown.py     show_tracks(), remember_tracks(), same_signals(), pick_shown()  (T1, JP)
  handlers/critique.py  CRITIQUE                                              (T3, T5, JP)
  handlers/explain.py   EXPLAIN                                               (T7, JP)
  handlers/similar.py   SOUNDS_LIKE, LYRICS_SEARCH                            (T6, T8, Ale)
  checks/check_base.py  71 checks of the T1 base, no LLM, no retriever        (T1, JP)
  checks/check_critique.py, eval_critique.py                                  (JP)
  checks/check_similar.py, check_lyrics.py, eval_audio.py                     (Ale)
```

### 3.1 State (`musiccrs/state.py`)

```python
@dataclass
class DialogueState:
    playlist: list = ...           # unchanged
    pending_options: list = ...    # unchanged: the last list shown (for R7)
    pending_kind: str = None       # unchanged; new lists also use "recommendation"

    # The last recommended list shown, in order. Kept after "add the first two"
    # (unlike pending_options), so "more like the second one" / "why the second one?" work.
    last_shown: list = field(default_factory=list)

    # Every track ID shown in this conversation, in any list. F1.2: never shown twice.
    shown: set = field(default_factory=set)

    # track_id -> what produced it (F3 reads only this). Examples in §3.3.
    signals: dict = field(default_factory=dict)

    # The current critique session (F1). Reset when a new list starts.
    # {"base_ids": [...], "liked": [...], "disliked": [...], "filters": [...]}
    critique: dict = None

@dataclass
class Services:
    db, retriever, llm             # unchanged
    vectors: object = None         # TrackVectors (T1); None in checks that need no vectors
```

### 3.2 Vectors (`musiccrs/data/vectors.py`)

```python
class TrackVectors:
    """The track vectors the Part 4 features search in, loaded once at startup.

    Row i of every matrix is track_ids[i] (the catalog order). All rows are L2-normalized,
    so a dot product is a cosine similarity.
    "metadata" -> the dense scorer's matrix (shared, not copied)
    "audio"    -> audio-laion_clap (512)
    "lyrics"   -> lyrics-qwen3_embedding_0.6b (1024); rows without real lyrics masked out (T8)
    """
    def __init__(self, track_ids, metadata_matrix, metadata_has_vector): ...
        # self.matrices[space], self.usable[space] (one bool per row), self.row_of[track_id]
    def size_text(self, space):
        """"audio: 47071 x 512, 46579 tracks with a vector" (printed at startup)."""
    def vector(self, space, track_id):
        """The vector of one track, or None if it has none. space = "metadata" | "audio" | "lyrics"."""
    def nearest(self, space, query_vector, k, exclude_ids):
        """The k track IDs with the highest dot product with query_vector, best first,
        skipping exclude_ids and rows without a vector. Returns [(track_id, score), ...]."""
```

- `nearest` is one `matrix @ query_vector`, then `numpy.argsort(-scores)`, then a plain `for` loop that skips unusable rows and excluded IDs until `k` are kept. Measured: ≈ 7 ms for the 47k × 1024 lyrics matrix (Oct 29).
- `__init__` uses `load_track_matrix("audio-laion_clap", track_ids)` and `load_track_matrix("lyrics-qwen3_embedding_0.6b", track_ids)`; `create_services` passes the dense scorer's `track_ids`, `.matrix`, `.has_vector` (same object, no copy). Loading takes 0.4 s once the `.npy` files are in `cache/embeddings/` (the first run downloads them).
- All three spaces have 46,579 usable rows (the same 492 tracks have no vector). **T8:** replace `self.usable["lyrics"]` with the `lyrics_ok` mask from `check_lyrics.py`.
- `python -m musiccrs.data.vectors` prints the sizes and the 5 audio neighbours of Smells Like Teen Spirit.

### 3.3 Shown tracks and signals (`musiccrs/handlers/shown.py`)

```python
def same_signals(track_ids, signals):
    """{track_id: a copy of signals} for every track of a list (one dict copy each)."""

def remember_tracks(state, track_ids, signals_by_id):
    """Add the IDs to state.shown and store each track's signals in state.signals.
    Used alone by R8 (no options to pick from)."""

def show_tracks(state, track_ids, signals_by_id, new_list=True):
    """Remember a list of recommended tracks that is about to be shown.

    remember_tracks, then pending_options (so R7 "add the first two" works),
    pending_kind = "recommendation", and last_shown.
    new_list=True (R6, sounds like, lyrics) also starts a new critique session:
    state.critique = {"base_ids": track_ids, "liked": [], "disliked": [], "filters": []}.
    The critique handler passes new_list=False, so its likes and filters are kept."""

def pick_shown(value, state, db):
    """The track ID of one track of last_shown, from a number or a loose name.
    "2" -> last_shown[1]; "bon jovi" / "numb" -> the first track whose normalized
    title or artist contains the text. None if out of range, no match, or empty text."""
```

Signals per source (a plain dict, JSON-like, so F3 can read it without knowing who made it):

| Source | Example |
| --- | --- |
| R6 recommend (JP, T7 adds `retrievers`) | `{"source": "recommend", "base_ids": [...], "different": False, "retrievers": {"bm25_plus": 3, "dense": 12}}` |
| R8 playlist (JP) | `{"source": "playlist", "description": "sad love songs", "query": "<the LLM's search words>"}` |
| Critique (JP, T3/T5) | `{"source": "critique", "liked": ["id2"], "disliked": [], "filters": ["older than 1998"], "similarity": 0.82}` |
| Sounds like (Ale, T6) | `{"source": "audio", "seed_id": "...", "similarity": 0.91}` |
| Lyrics (Ale, T8) | `{"source": "lyrics", "theme": "leaving home", "similarity": 0.58}` |

Since T1, R6 calls `show_tracks` and R8 calls `remember_tracks` (in `recs.py`), so every list in the system feeds F1.2 and F3 from day 1.

### 3.4 Intents, slots and slash commands (`musiccrs/nlu/`)

| Intent | Slots | Example sentence → slots | Slash command (no LLM) |
| --- | --- | --- | --- |
| `CRITIQUE` | `like`, `dislike` (a number or a name), `attribute` (`year` / `popularity` / `tag`), `direction` (`more` / `less`), `tag` | "more like the second one" → `{like: "2"}`; "less like the one by Bon Jovi" → `{dislike: "bon jovi"}`; "older" → `{attribute: year, direction: less}`; "more acoustic" → `{attribute: tag, direction: more, tag: acoustic}`; "like #2 but newer" → both | `/like 2`, `/dislike 3`, `/critique year less`, `/critique tag more acoustic` |
| `SOUNDS_LIKE` | `track`, `artist` | "songs that sound like Numb by Linkin Park" | `/sounds linkin park: numb` |
| `LYRICS_SEARCH` | `theme` | "songs about leaving home" → `{theme: "leaving home"}` | `/about leaving home` |
| `EXPLAIN` | `option` (a number or a name) | "why the second one?", "why did you pick Numb?" | `/why 2` |

- Still **one** LLM call for the parser (plus its one retry). The new features add no LLM call: the parser already returns structured slots. That is how "an LLM structures the critique" (proposal F1) is met.
- **Boundary with Part 2 intents** (the prompt must say it, and `nlu_examples.json` must test it): "songs like Numb" stays `RECOMMEND` (Part 2, text + CF retrieval); "songs that *sound* like Numb" is `SOUNDS_LIKE`. "Recommend sad songs" with no list on screen stays `RECOMMEND`/`CREATE_PLAYLIST`; "songs *about* leaving home" is `LYRICS_SEARCH`. The prompt classifies `CRITIQUE` and `EXPLAIN` by the words, whether or not options are pending (after a selection only `last_shown` is left); the handler checks `last_shown` and says so when there is no list.
- Slot values: numbers come as digits (`"2"`, read by `pick_shown`); `attribute` and `direction` only take the allowed values (`CRITIQUE_ATTRIBUTES`, `CRITIQUE_DIRECTIONS` in `parser.py`, checked after `.lower()`); `tag` and `theme` are free text. `/critique` uses `split(maxsplit=2)`, so a tag can have spaces ("hard rock").
- T1 stubs (`handlers/critique.py`, `explain.py`, `similar.py`) reply "… is not built yet. I understood: {slots}"; each task replaces its stub's body.
- **Done (Oct 29):** `check_nlu` 53/53 (39 old + 14 new: 6 CRITIQUE, 2 SOUNDS_LIKE, 2 LYRICS_SEARCH, 2 EXPLAIN, 2 boundary), mean 469 ms per parse; `check_base` 71/71; `check_handlers` and `check_recs` still pass.

---

## 4. Feature design

### 4.1 F1.1 Example critiques — T3, JP (`handlers/critique.py`)

**As built (Oct 30, branch `jp/critique`).** One change from the first plan: the critiques move in the **audio** space (CLAP), not the metadata space. The metadata vectors are text embeddings of title / artist / album, so they match title words: "more like *Bad Medicine* (Bon Jovi)" gave *Bad Seeds*, *Adderall*, *Bad Business* (21 Savage), *Medicine*. In audio it gave Pearl Jam, Ratt, Bon Jovi ×2, Bad Religion; on jazz, Mingus, Sinatra, Mulligan, Chet Baker. The BPR (co-listening) vectors were also tried: good for very popular artists, noisy otherwise (jazz → Enrique Iglesias). One constant, `SPACE = "audio"`.

**Idea (Rocchio relevance feedback):** the list on screen is described by one vector, the average of its tracks' audio vectors. A critique moves that vector:

```
new_query = α · base  +  β · mean(liked vectors)  −  γ · mean(disliked vectors)
α = 1.0, β = 0.75, γ = 0.15   (the classic SMART values)
```

then L2-normalize and take `vectors.nearest(SPACE, new_query, 5, exclude = state.shown ∪ playlist)`.

```python
def mean_vector(track_ids, vectors):
    """Mean of the tracks' vectors in SPACE (tracks without one left out), or None."""

def critique_query(critique, vectors):
    """The Rocchio vector of state.critique, L2-normalized, or None if the base has no vectors."""

def handle_critique(parsed, state, services):
    """CRITIQUE: add the like / dislike to state.critique, rank again, show 5 new tracks."""
```

- `base` is fixed when the list first appears (`show_tracks` with `new_list=True`), and liked / disliked **accumulate** across turns. So "more like #2", then "less like #4" applies both.
- The reply says what it did: "More like *Numb* (Linkin Park), less like *Toxic*:" then the 5 tracks, so the user sees the critique was understood.
- Both slots are resolved by `pick_shown` before anything changes, so "more like #7" changes nothing. A liked or disliked song is in `shown`, so it never comes back on screen and cannot be picked twice: likes and dislikes are a plain append.
- Each new track's signals: `{"source": "critique", "liked", "disliked", "filters", "similarity"}` (copies of the lists, the track's own cosine to the query). `show_tracks(new_list=False)` keeps the base and the likes.
- Attribute slots alone ("older") still get the stub reply until T5.
- γ stays 0.15: 0.25 and 0.5 were tried (Oct 30); they pushed jazz out of jazz (Ministry, Led Zeppelin) and, at 0.5, lost the like in pop.
- **Done when:** after a rock recommendation, "more like the second one" gives 5 unseen tracks whose mean cosine to #2 is higher than the first list's (printed by `check_critique`). **Done Oct 30:** `check_critique` 46/46 on rock / jazz / pop; cosine to #2 0.601 → 0.840 (rock), 0.425 → 0.592 (jazz), 0.750 → 0.902 (pop); 9 ms per critique.

### 4.2 F1.2 Attribute critiques, stacking, no repeats — T5, JP

Each attribute critique becomes a **filter with a fixed threshold**, taken from the list on screen when the critique is made:

| Critique | Filter stored | Kept tracks |
| --- | --- | --- |
| "older" | `{"attribute": "year", "direction": "less", "value": 1998}` (median year of the list on screen) | year < 1998 |
| "newer" | `year`, `more`, median | year > median |
| "more popular" / "less known" | `popularity`, `more` / `less`, median | popularity > / < median |
| "more acoustic" | `tag`, `more`, `"acoustic"` | `"acoustic"` in the normalized tags |
| "no rap" / "less rap" | `tag`, `less`, `"rap"` | `"rap"` not in the tags |

- **Ranking with filters:** take the 1,000 nearest tracks to the Rocchio vector (§4.1), keep those that pass **every** filter, in that order, and show the first 5. Fewer than 5 left → show what is left and say which critique is too strict.
- **Stacking:** filters are a list in `state.critique`; a new critique appends. "older" twice works: the second median is taken from the already older list.
- **No repeats:** `exclude = state.shown ∪ playlist`, for every list in the conversation (not only the critique session).
- **Reset:** a new `RECOMMEND`, `CREATE_PLAYLIST`, `SOUNDS_LIKE` or `LYRICS_SEARCH` starts a new critique session. `shown` is never reset (one conversation).
- Tracks without a year are dropped by year filters (644 tracks).
- **Done when:** "older" then "more popular" gives tracks older *and* more popular than the first list's medians, none shown before.

### 4.3 F2.1 Sounds like — T6, Alejandro (`handlers/similar.py`)

```python
def handle_sounds_like(parsed, state, services):
    """SOUNDS_LIKE: resolve the seed track, show the 5 nearest tracks in CLAP audio space."""
```

1. `resolve(db, track, artist)` → several matches → take the most popular (no disambiguation round, to keep it one turn). None → "I could not find ...".
2. `seed = vectors.vector("audio", seed_id)`; no audio vector → say so.
3. `vectors.nearest("audio", seed, 20, exclude = state.shown ∪ playlist ∪ {seed_id})`.
4. Drop other versions of the seed (same `base_name` and same main artist: remasters, live versions), keep 5.
5. `show_tracks(state, ids, {"source": "audio", "seed_id": ..., "similarity": score})`, reply with `options_act`.

- **Why audio finds what text misses:** CLAP vectors are computed from the sound itself, so two songs with no shared words, tags or listeners can still be close.
- **Done when:** Smells Like Teen Spirit, Hotel California and It's My Life each get 5 tracks, no version of the seed among them.

### 4.4 F2.2 Lyrics theme search — T8, Alejandro

1. **First, a check script** (`checks/check_lyrics.py`): count empty lyrics rows and rows that share a near-identical vector with many others (instrumentals). Record the counts in the README and this plan. Build the `lyrics_ok` mask from it (used by `TrackVectors`).
2. `handle_lyrics_search`: `query = dense_scorer.encode_queries([theme])[0]` (same Qwen3 model and query prompt the dataset's vectors were made with; already loaded, ~76 ms on GPU, ~400 ms on CPU).
3. `vectors.nearest("lyrics", query, 5, exclude = shown ∪ playlist)` → `show_tracks(... {"source": "lyrics", "theme": ..., "similarity": ...})`.

- **"Our own local index"** = the lyrics matrix in memory, rows aligned with our track IDs, minus the masked rows. No external API.
- **A VERIFICAR:** Qwen3 asymmetric use: query with the query prompt vs the stored document vectors (made without a prompt, as for metadata). Try both on the 3 themes; keep the one that looks right and write down why.
- **Done when:** "leaving home", "heartbreak" and "partying all night" give 3 different, plausible lists.

### 4.5 F3 Why this song? — T7, JP (`handlers/explain.py`)

```python
def explain_track(track_id, state, db, vectors):
    """2-4 sentences, each built from one stored or checked fact. No LLM."""

def handle_explain(parsed, state, services):
    """EXPLAIN: pick_shown(option) -> explain_track. Not shown in this conversation -> say so."""
```

Sentences, one per available fact (template, in this order):

| Fact | Where it comes from | Sentence |
| --- | --- | --- |
| How it was found | `signals[id]["source"]` + its fields | "It sounds close to *Numb* (audio similarity 0.91)." / "Its lyrics match 'leaving home'." / "You asked for older songs (before 1998)." |
| Which retrievers ranked it | `signals[id]["retrievers"]` (R6 only) | "Found by keyword match (#3) and by meaning (#12)." |
| Shared tags | computed now: tags shared with the base tracks | "It shares the tags *grunge*, *90s* with your playlist." |
| Same artist | computed now | "It is by Nirvana, who is already in your playlist." |

- **T7 also adds** `FinalRetriever.retrieve_with_sources(ctx, topk, policy)` → `(track_ids, {track_id: {component: rank}})`. It calls each scorer once, as `FusionScorer.score` does, keeps the per-component lists, and fuses them. `handle_recommend` switches to it and stores `retrievers` in the signals. Part 1 results do not change (same fusion).
- **Why no LLM:** the reasons can only come from data we stored, so they cannot be invented (lecture M12a: LLMs can hallucinate reasons). And grading the explanations with the same LLM would be circular (M12b).
- **Done when:** one track from each source gets an explanation, and every number in it can be found in `state.signals` or the DB.

### 4.6 F4 Covers and previews — T2 + T4, Alejandro

**Backend (T2, `data/media.py`):**

```python
def get_media(track, catalog):
    """{"cover": url or None, "preview": url or None} for one track, cached in memory.
    1. GET https://api.deezer.com/track/isrc:<ISRC>      (timeout 1.5 s)
    2. if not found: GET https://api.deezer.com/search?q=artist:"<artist>" track:"<name>"  (first hit)
    Uses album.cover_medium and preview from Deezer's JSON. Any error -> both None."""

def media_act(track_ids, db, catalog):
    """A MEDIA dialogue act, one annotation per track:
    SlotValueAnnotation("track", '{"id": ..., "name": ..., "artist": ..., "cover": ..., "preview": ...}')"""
```

- Two call sites in `musiccrs.py` (the only edit to JP's file, reviewed by JP): (1) after a handler, if the reply has an `OPTIONS` act, append `media_act(state.pending_options, ...)`; (2) `playlist_act` adds `cover` and `preview` to each track's JSON.
- **Cache** in a module-level dict (track_id → media), filled on first use. In memory only, because Deezer preview links are signed and expire (**A VERIFICAR** how long); a restart refreshes them.
- **Latency:** 5 uncached lookups one after another ≈ 0.5–1.5 s (**A VERIFICAR**). If too slow: warm the cache at startup for the demo tracks. No threads.
- **Done when:** `python -m musiccrs.data.media` prints a cover and a preview URL for Smells Like Teen Spirit, Hotel California and It's My Life, and the hit rate on 100 random catalog tracks.

**Frontend (T4):**

- `ChatBox`: when an agent message has a `MEDIA` act, render a row of small cards under the text: cover (64 px), title, artist, and `<audio controls preload="none" src={preview}>`. No preview → the card has no player.
- `PlaylistPanel`: read `cover` / `preview` from the `PLAYLIST` JSON; a 40 px cover and a play / pause button per row (one shared `<audio>` element, so only one song plays at a time).
- **Done when:** a recommendation shows 5 covers whose previews play, and the panel shows covers. `npm test` still passes.

### 4.7 F5 Evaluation — T9 (JP) + T10 (Alejandro)

**F5a critique simulation (T9, `checks/eval_critique.py`, no LLM):**

1. `val0` sessions (1,000, from `data/val_folds.json`). One turn per session: the last turn whose played list is not empty. Context from `build_turn_context`; `gold` = the track the real user chose at that turn.
2. **Before:** `retriever.retrieve(ctx, 20)`. The first 5 are "shown". Gold among them → the user would accept; count it, skip the turn.
3. **Simulated user:** "more like #k", where #k is the shown track whose vector in the critique space (`critique.SPACE`, audio since T3) is closest to the gold's. Second variant: also an attribute critique when it is true for the gold ("older" if the gold's year is below the shown median, else "newer"; same for popularity).
4. **After:** the same `critique.py` functions the agent uses, `exclude = played ∪ shown`, top 20.
5. Report: nDCG@20 before vs after (`get_ndcg`), the share of turns where the gold's rank improved, and the number of skipped turns, for both variants.

- The simulated user knowing the gold is allowed: it **plays the user**, it is not part of the system. The system only receives the critique.
- **What it does not measure:** whether real users phrase critiques this way, or like the result (a user study would; Part 3 is one).

**Latency and LLM-call log (T9):** `ask_json` increments a module-level counter in `llm.py`; `receive_utterance` resets it each turn; `print_turn_time` prints `[CRITIQUE] 412 ms, 1 LLM call`. `check_latency` gets Part 4 turns (critiques, sounds like, lyrics, why) and prints median and 95th-percentile ms and LLM calls.

**F5b audio evaluation (T10, `checks/eval_audio.py`, no LLM):**

- 1,000 random tracks with an audio vector (seed 42). For each: top-5 CLAP neighbours, 5 random tracks, top-5 metadata-Qwen3 neighbours, all excluding the seed's own artist (same-artist tracks share tags trivially).
- Report the mean number of (normalized) tags shared with the seed for each of the three. Expected: random < audio; audio vs text tells whether sound similarity agrees with tags.

**Done when:** both scripts print their tables; the numbers go into the README's Part 4 section.

---

## 5. Latency and LLM budget

| Turn | LLM calls | Expected time |
| --- | ---: | --- |
| Any Part 4 slash command | 0 | < 100 ms + media lookups |
| Critique / sounds like / why in words | 1 (parser) | ~0.5–1 s |
| Lyrics theme in words | 1 | ~0.6–1.4 s (encoder on GPU / CPU) |
| Media lookups, uncached | 0 | +0.5–1.5 s (**A VERIFICAR**) |

All well under the 5–10 calls and 3–5 s limits. T9 measures the real numbers.

---

## 6. What we deliberately do not do (to keep it explainable)

- No LLM for critiques beyond the parser, no LLM for explanations, no LLM judge.
- No vector database or approximate search: one numpy dot product over 47k rows is fast enough.
- No retraining, no fine-tuning, no new embeddings (only the query side of lyrics is embedded, with the model we already load).
- No threads for Deezer; a cache and a timeout instead.
- No cover image generation (the optional extra point; not in the approved rubric).

---

## 7. Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Deezer misses many ISRCs or is slow | Search by artist + title; show the card without cover / preview; warm the cache for demo tracks |
| Most lyrics vectors are meaningless | Report the count honestly, restrict the index to the good rows, pick demo themes that work |
| Critiques often leave < 5 tracks | Widen the candidate pool from 1,000 to 5,000 before giving up |
| Parser confuses `RECOMMEND` with `SOUNDS_LIKE` / `LYRICS_SEARCH` | More boundary examples in the prompt and `nlu_examples.json`; slash commands always work for the demo |
| Memory on the demo laptop | Load lyrics vectors as float16 (half the memory) |
