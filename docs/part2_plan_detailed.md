# Part 2 Work Plan — Detailed Version (tied to the real code)

> **Names and dates:** `part2_plan_simple.md` is the source of truth for who does what and when. This file adds the concrete interfaces, data fields and design notes. If the two disagree, the simple plan wins.

- Line numbers refer to commit `642687b` of this repo.
- **A VERIFICAR** = not confirmed in the code or the data yet. Check it before relying on it.
- Signatures below are **proposals**: signatures and docstrings only, no implementation. The owner may change them before the freeze (end of T3, Fri Oct 16). After that, changes need both people.

---

## 1. How the current code works

### 1.1 The starter agent ([musiccrs/musiccrs.py](../musiccrs/musiccrs.py))

- `MusicCRS(Agent)`: `__init__(use_llm=True)` creates an `ollama.Client` (host `https://ollama.ux.uis.no`, model `llama3.3:70b`, key placeholder) and `self._playlist = []`.
- `receive_utterance(utterance)` (line 52) is a chain of `if utterance.text.startswith(...)` for `/info`, `/ask_llm`, `/options`, `/quit`. Every reply goes out through `self._dialogue_connector.register_agent_utterance(AnnotatedUtterance(text, participant=AGENT, dialogue_acts=[...]))`.
- `/options` shows how structured data reaches the UI: a `DialogueAct(intent=Intent("OPTIONS"), annotations=[SlotValueAnnotation("option", ...)])`. The frontend turns these into clickable quick replies.
- `if __name__ == "__main__"` calls `platform.start()` **twice** (lines 137–138). That's harmless but should be cleaned up in T2.

### 1.2 How DialogueKit creates agents (checked in the installed package)

- `FlaskSocketPlatform(MusicCRS)` receives the **class**. On every socket connection, `Platform.connect` calls `get_new_agent()`, which runs `self._agent_class(self._agent_class.__name__)` (`dialoguekit/platforms/platform.py:72`).
- Consequences:
  1. **One agent object per connection** → per-user state (playlist, pending options) lives on `self`. Two browser tabs = two playlists.
  2. The first constructor argument receives the string `"MusicCRS"`. Today that lands in `use_llm` (truthy, so it works by accident). T2 makes the signature explicit.
  3. Heavy resources (DB connection, `FinalRetriever`, LLM client) must be **module-level singletons** created once in `main`. If they are built in `__init__`, they are rebuilt on every connection (seconds per tab, and the Qwen3 model loaded again each time).

### 1.3 The message format (top-level README)

The UI and the simulator receive each agent message as:

```json
{"sender": "MusicCRS",
 "message": {"text": "...",
             "dialogue_acts": [{"intent": "OPTIONS",
                                "annotations": [{"slot": "option", "value": "..."}]}]}}
```

- The **simulator reads only `text` and `dialogue_acts`** (`simulation/README.md`). Anything the UI shows beyond that (the playlist panel, buttons) is invisible to it.
- The exact JSON key names of an annotation (`slot` / `value`) are **A VERIFICAR**. Print one message in the browser console in T5.

### 1.4 The frontend path ([frontend/src/](../frontend/src/))

| File | Role |
| --- | --- |
| `contexts/socket_connector.tsx` | socket.io client: `emit("message", ...)`, `on("message", ...)`, `start_conversation`, `restart`, login/register |
| `contexts/SocketContext.tsx` | exposes `sendMessage`, `quickReply`, `onMessage`, ... to components |
| `components/ChatBox/ChatBox.tsx` | the chat: `handleInput` sends text, `handelMessage` renders agent messages and builds quick-reply buttons from dialogue acts |
| `components/QuickReply.tsx` | one clickable option button |
| `components/Widget/ChatWidget.tsx`, `Embedded/ChatEmbedded.tsx` | layout wrappers |
| `types.tsx` | `ChatMessage`, `AgentMessage` types |

T5 adds the playlist panel **beside** `ChatBox` and reads the same `onMessage` stream.

### 1.5 The simulator ([simulation/](../simulation/))

- Only `simulation/config.py` may be edited (the source is integrity-checked).
- `COMMANDS` maps fixed intent keys to **our** commands. The current values are the defaults: `ADD_TRACK: "/add [artist]: [track]"`, `REMOVE_TRACK: "/del [artist]: [track]"`, `RECOMMEND: "/recommend"`, `SHOW_PLAYLIST: "/list"`, `GREETING: "Hello!"`, `QUIT: "/quit"`.
- It runs scripted dialogues and persona-based NL dialogues. **The uploaded dialogues are graded. Only the last upload counts.** It needs `GROUP_ID`, `UPLOAD_TOKEN` (by email) and our Ollama key. **Never commit the real token or key.**

### 1.6 Part 1 code the agent reuses

| What | Where | Used by |
| --- | --- | --- |
| `MusicCatalogLoader().metadata_dict` (track_id → metadata) | [retrieval/data_loader.py](../retrieval/data_loader.py) | T1 (build the DB) |
| `FinalRetriever.retrieve(ctx, topk, policy)` | [retrieval/final_retriever.py](../retrieval/final_retriever.py) | T4 (R6) |
| `FinalRetriever.text_to_item_retrieval(query, topk)` | same | T9 (R8) |
| `TurnContext`, `SessionPolicy`, `finalize_top_k` | [retrieval/context.py](../retrieval/context.py) | T4, T9 |
| BPR vectors `cf-bpr` (47,071 × 128) | [retrieval/session_cf.py](../retrieval/session_cf.py) | T8 (rank options by similarity to the playlist) |

---

## 2. Data facts for Part 2

Catalog: `talkpl-ai/TalkPlayData-Challenge-Track-Metadata`, split `all_tracks`, 47,071 tracks (Part 1 plan §2.2).

- Fields: `track_id, ISRC, track_name, artist_name, album_name, tag_list, popularity, release_date, duration, artist_id, album_id`.
- `track_name`, `artist_name`, `album_name`, `artist_id`, `album_id` are **lists**. Matching must check **every** name and **every** artist, not only the first.
- 10,638 distinct artists (10,500 after `normalize()`); the median artist has 1 track.
- `popularity` 0–93 (median 38) → the R4 ranking signal.
- `tag_list`: noisy user tags (mean 33 per track) → R5 "genres of an artist", and R8 matching.
- `release_date` → R5 "release year". `duration` → R5 "how long" and the R8 length.
- **Name, artist and duration facts** (counted on Oct 15 by `python -m musiccrs.build_db`):

| Fact | Value | Consequence |
| --- | --- | --- |
| Tracks with 2 or 3 names (aliases, e.g. "Falling Down" + "Falling Down - Explicit Album Version") | 2,224 + 68 (49,431 names) | the DB stores every name (`track_names`) |
| Names with a version suffix `" - ..."` ("Hotel California - 2013 Remaster", most Beatles tracks "- Remastered") | 4,932 (~10%) | the DB also stores `base_norm`, the name without the suffix and brackets |
| Normalized names shared by > 1 track | 3,282 names (9,093 tracks); 4,363 base names (12,264 tracks) | R4 disambiguation is common (`"love"` → 7 tracks) |
| `artist_id` list does not line up with `artist_name` (e.g. 1 name, 3 IDs) | 3,342 tracks | `artist_id` is not used; artists are matched by name |
| Tracks with up to 31 artists; 55 artist entries are empty or "!!!" | — | every artist is stored |
| `duration` unit | **milliseconds** | `Track.duration_ms` |
| `duration` known (> 0) | 46,409 tracks (662 are 0) | mean **239.7 s**, median 227.9 s → the R8 length rule |
| `release_date` empty | 644 tracks | R5 says "unknown" |
| `album_name` with 2 entries | 13,351 tracks | `Track.album` = the first |
| Famous songs **not** in the catalog | "Bohemian Rhapsody" (only an a cappella mix), "Don't Stop Me Now" | use "Smells Like Teen Spirit", "Hotel California", "It's My Life" in tests and the demo |

---

## 3. Shared interfaces (owner JP, frozen after T3)

### 3.1 `musiccrs/db.py` — T1

```python
def normalize(text: str) -> str:
    """Lowercase, strip accents (NFKD), drop apostrophes, "&" -> "and", other punctuation -> spaces.
    "Don't Stop Me Now!" -> "dont stop me now". Used by the DB build and every lookup."""

def base_name(name: str) -> str:
    """normalize() of the name without its " - ..." suffix and (...) / [...] parts.
    "Hotel California - 2013 Remaster" -> "hotel california"."""

@dataclass(frozen=True)
class Track:
    track_id: str
    name: str
    artists: tuple[str, ...]
    album: str
    popularity: int
    release_date: str
    duration_ms: int          # milliseconds, 0 if unknown
    tags: tuple[str, ...]

class TrackDB:
    def __init__(self, path: str = "cache/musiccrs.db") -> None: ...
    def get(self, track_id: str) -> Track | None: ...
    def find_by_name(self, name: str, artist: str | None = None) -> list[Track]:
        """Exact match on any normalized name or base name (and on any normalized artist,
        if given). Most popular first."""
    def fuzzy_candidates(self, text: str, limit: int = 50) -> list[Track]:
        """FTS5 match (words joined by OR) on names + artists, best BM25 first.
        Wide on purpose: T6 re-scores the candidates (typos are T6's job)."""
    def artist_tracks(self, artist: str) -> list[Track]:
        """All tracks where any artist matches `artist` after normalize()."""
```

- Tables: `tracks(track_id PK, name, album, popularity, release_date, duration_ms, tags_json, artists_json)`, `track_names(track_id, name, name_norm, base_norm)` (every alias), `track_artists(track_id, position, artist_name, artist_norm)`, plus `tracks_fts` (FTS5 over the normalized names + artists). Indexes on `name_norm`, `base_norm` and `artist_norm`.
- `musiccrs/build_db.py`: `python -m musiccrs.build_db` reads `MusicCatalogLoader().metadata_dict` and writes `cache/musiccrs.db` (`cache/` is gitignored). It is idempotent: it deletes the file and rebuilds.
- Why SQLite: it is in the Python stdlib, it is one file, it does exact lookups by index in ms, and FTS5 handles partial names. The spec allows any database.

### 3.2 `musiccrs/state.py` — T2

```python
@dataclass
class DialogueState:
    playlist: list[str] = field(default_factory=list)          # track IDs, in order
    pending_options: list[str] = field(default_factory=list)   # last shown list (R4 or R6/R8)
    pending_kind: str | None = None                            # "disambiguation" | "recommendation" | None
```

### 3.3 `musiccrs/nlu.py` — T3

```python
INTENTS = ("ADD", "REMOVE", "SHOW", "CLEAR", "HELP", "ASK_TRACK", "ASK_ARTIST",
           "RECOMMEND", "CREATE_PLAYLIST", "SELECT", "GREETING", "UNKNOWN")

@dataclass
class ParsedIntent:
    name: str                      # one of INTENTS
    slots: dict[str, str]          # track, artist, question, description, selection, ...

def parse(text: str, state: DialogueState, llm) -> ParsedIntent:
    """Slash commands → parsed by rules, no LLM.
    Otherwise one LLM call with a JSON-only prompt (intents, slot names, few-shot examples,
    and whether options are pending, so "the second one" becomes SELECT)."""
```

- The slot names (frozen after T3): `track`, `artist`, `question` (one of the R5 types), `description` (R8), `selection` (the raw selection text for R7), `different` (bool, "something different").
- If the LLM output is not valid JSON, retry once (so 2 calls at most), then return `UNKNOWN`.

### 3.4 Handler contract and registry — T2

```python
@dataclass
class Reply:
    text: str
    dialogue_acts: list[DialogueAct] = field(default_factory=list)

Handler = Callable[[ParsedIntent, DialogueState, "Services"], Reply]

@dataclass
class Services:                     # created once in main, shared by every agent
    db: TrackDB
    retriever: FinalRetriever
    llm: ollama.Client | None
```

- `musiccrs.py` keeps `HANDLERS: dict[str, Handler]`. `receive_utterance` = `parse` → `HANDLERS[parsed.name](...)` → send the reply, then a **`PLAYLIST` act** whenever the playlist changed.
- Each owner registers handlers from their own file: `handlers_playlist.py` (ADD, REMOVE, SHOW, CLEAR, HELP), `handlers_qa.py` (ASK_TRACK, ASK_ARTIST), `handlers_recs.py` (RECOMMEND, CREATE_PLAYLIST), `selection.py` (SELECT).

### 3.5 Dialogue acts (the UI and the simulator contract)

| Intent | Annotations | Sent when |
| --- | --- | --- |
| `PLAYLIST` | one `SlotValueAnnotation("track", json.dumps({"id", "name", "artist"}))` per track, in order | after any change, and on `SHOW` |
| `OPTIONS` (existing) | `SlotValueAnnotation("option", "<n>. <name> — <artist>")` | R4 choices, R6 recommendations |

### 3.6 Slash commands (T2, matched in `simulation/config.py` by T13)

| Command | Meaning |
| --- | --- |
| `/add [artist]: [track]` | add (artist optional: `/add [track]`) |
| `/del [artist]: [track]` | remove by name |
| `/remove <track_id>` | remove by ID (UI button) |
| `/list` | show the playlist |
| `/clear` | clear the playlist |
| `/recommend` | R6 |
| `/help` | R3 |
| `/quit` | end |

---

## 4. Session rules in Part 2 (from Part 1 §6.3)

`SessionPolicy` is set per turn by the agent, never inside a scorer:

| Situation | Policy |
| --- | --- |
| R6 recommend | `TurnContext(played_track_ids=tuple(playlist), current_message=<user text or "">, history=(), turn_number=len(playlist)+1)`, `SessionPolicy()` → songs already in the playlist are never recommended |
| R6 + "something different" / "other artists" (`different` slot) | `SessionPolicy(use_same_artist=False)` |
| R8 from scratch | `text_to_item_retrieval(query)` → no played tracks, so only bm25_plus and dense contribute |

---

## 5. Tasks

Each task: owner · files · interface · design notes · LLM calls · done when.

### T1 — Database · **JP** · Thu Oct 15

- Files: `musiccrs/db.py`, `musiccrs/build_db.py`.
- Notes: §3.1. Store **all** artists of a track. Keep `name_norm` for exact lookups and FTS5 for partial ones.
- LLM calls: 0.
- Done when: `python -m musiccrs.build_db` builds the DB in under a minute and its self-check passes: `find_by_name("smells like teen spirit")` returns Nirvana first; `find_by_name("SMELLS LIKE TEEN SPIRIT!", artist="nirvana")` returns only Nirvana; `find_by_name("hotel california")` finds the Eagles remaster; `fuzzy_candidates("teen spirit nirvana")` contains it; `artist_tracks("queen")` returns 13 tracks; `get()` on 3 random IDs matches `metadata_dict`.
- Result (Oct 15): build 2.5 s (+ 6 s catalog load); exact lookup 0.2 ms, fuzzy 7 ms.

### T2 — Agent skeleton · **JP** · Fri Oct 16

- Files: `musiccrs/musiccrs.py`, `musiccrs/state.py`.
- Notes: §1.2 (singletons in `main`), §3.2, §3.4, §3.6. Remove the double `platform.start()`. Keep `/quit` and the welcome message. The welcome message mentions "type help".
- LLM calls: 0 (slash path).
- Done when: `/add nirvana: smells like teen spirit`, `/list`, `/del nirvana: smells like teen spirit`, `/clear` work in the browser and each sends a `PLAYLIST` act.

### T3 — Intent parser · **JP** · Fri Oct 16

- Files: `musiccrs/nlu.py`, `musiccrs/nlu_examples.json` (≥ 2 sentences per intent, with the expected parse).
- Notes: §3.3. Low temperature (0). Ask for JSON only. Include `pending_kind` in the prompt.
- LLM calls: 1 (2 with a retry).
- Done when: `python -m musiccrs.nlu --check` parses ≥ 90% of `nlu_examples.json` correctly and prints the ms per call. **Then the interfaces are frozen.**

### T4 — R6 recommend · **JP** · Sat Oct 17

- File: `musiccrs/handlers_recs.py`.
- Notes: §4. `retriever.retrieve(ctx, topk=5, policy)`. Empty playlist → ask the user to add songs first, or offer R8. Store the 5 IDs in `pending_options` with `pending_kind="recommendation"` and send them as `OPTIONS`.
- LLM calls: 0 beyond the parser.
- Done when: 3 different playlists (rock / jazz / pop) give 5 clearly related songs, none already in the playlist; latency written down.

### T5 — R1 playlist panel · **Alejandro** · Thu Oct 15 → Tue Oct 20

- Files: `frontend/src/components/Playlist/Playlist.tsx`, `Playlist.css`; small edits to `ChatWidget.tsx` / `ChatBox.tsx` to subscribe to `PLAYLIST` acts.
- Notes: render the **last** `PLAYLIST` act (the agent is the source of truth). A remove button per track sends `/remove <id>`, a clear button sends `/clear`, and an add box sends `add <text>` as a normal chat message (so R4 disambiguation still works). Hide `PLAYLIST` acts from the chat bubbles. Show the track count and total duration.
- LLM calls: 0.
- Done when: add, remove and clear from both the chat and the panel keep the two in sync. `npm test` still passes.

### T6 — Track resolver · **Alejandro** · Fri Oct 16

- File: `musiccrs/resolver.py`.

```python
def resolve(db: TrackDB, track: str | None, artist: str | None) -> list[Track]:
    """Candidates for a loose reference, best first:
    1. exact normalized name (+ artist if given);
    2. if the name is empty: the artist's tracks;
    3. fuzzy: db.fuzzy_candidates() re-scored with rapidfuzz (A VERIFICAR: new dependency);
    Drops weak fuzzy matches below a threshold so "asdfgh" returns []."""
```

- Also handle "X by Y" inside the track slot when the parser misses the artist.
- LLM calls: 0.
- Done when: a test list of ~15 loose references (case, punctuation, accents, "feat.", typos, artist only) resolves as expected.

### T7 — R2 handlers · **Alejandro** · Sat Oct 17

- File: `musiccrs/handlers_playlist.py` (ADD, REMOVE, SHOW, CLEAR).
- Notes: 1 match → add/remove. Several → T8. 0 → "I couldn't find X in the database". A duplicate add → say so, don't add twice. REMOVE resolves against the **playlist first** ("remove the Queen song").
- LLM calls: 0 beyond the parser.
- Done when: all 4 actions work in natural language with 2+ phrasings each, and the panel updates.

### T8 — R4 disambiguation · **Alejandro** · Sun Oct 18

- File: `musiccrs/handlers_playlist.py`.
- Ranking: `score = popularity/93 + same_artist_as_playlist + cosine(BPR(track), mean BPR(playlist))`. With an empty playlist, popularity only. Show the top 5 as `OPTIONS` and store them in `pending_options` (`pending_kind="disambiguation"`).
- The choice: a click (quick reply), or "the second one" / "the one by X" → SELECT, using T11's `select_indices` (shared, owned by JP).
- LLM calls: 0 beyond the parser.
- Done when: "add Love" shows 5 sensible options; with a rock playlist, rock versions rank higher.

### T9 — R8 playlist from a description · **JP** · Sun Oct 18

- File: `musiccrs/handlers_recs.py` (CREATE_PLAYLIST).
- Notes: one LLM call returns `{"query": "...", "minutes": N}`. If no duration is implied, `minutes` comes from the activity (gym ≈ 60, a party is longer, "a few songs" is short). Length = `round(minutes * 60 / mean_duration)`, clamped 8–25 (mean duration in §2). Then `text_to_item_retrieval(query, topk=length)`. Ask before replacing a non-empty playlist, or show the result as a proposal (A VERIFICAR: decide in T9).
- LLM calls: 1.
- Done when: 3 descriptions give relevant playlists of different lengths, and the length rule is written in the code comment.

### T10 — R5 questions · **Alejandro** · Mon Oct 19 – Tue Oct 20

- File: `musiccrs/handlers_qa.py` (ASK_TRACK, ASK_ARTIST).
- Question types (the `question` slot): track → `artist`, `album`, `release_year`, `duration` (popularity as a fifth if time allows); artist → `track_count`, `top_track`, `albums`, `genres` (top tags across the artist's tracks).
- The answers come **from the DB with templates**. The LLM only fills the slots (in the T3 call), so it cannot invent facts. If the track is ambiguous, answer for the most popular match and say which one.
- LLM calls: 0 beyond the parser.
- Done when: all 8 types answer correctly, with 2 phrasings each.

### T11 — R7 selection · **JP** · Mon Oct 19 – Tue Oct 20

- File: `musiccrs/selection.py` (SELECT).

```python
def select_indices(text: str, options: list[Track], llm) -> list[int] | None:
    """0-based indices of the chosen options, [] for none, None if not understood.
    Rules first (no LLM): "all"/"everything", "none"/"no thanks", ordinals ("the first two",
    "1 and 3", "the last one"). LLM fallback (1 call, JSON list of indices) for references by
    artist/title and exclusions ("all except the one by Metallica")."""
```

- Used for both `pending_kind`s: recommendation (add the chosen ones) and disambiguation (add the one chosen).
- LLM calls: 0–1.
- Done when: ≥ 3 formulations work (all / ordinal subset / none / except-by-artist), including one with an exclusion. Clear `pending_options` after use.

### T12 — R3 help · **Alejandro** · Tue Oct 20

- File: `musiccrs/handlers_playlist.py` (HELP).
- Notes: a fixed, well-written text with one example per feature. If the parser fills a `topic` slot ("how do I remove?"), show only that part.
- LLM calls: 0 beyond the parser.
- Done when: "help", "what can you do?" and "how do I make a playlist?" all give a useful answer.

### T13 — Simulator config + latency · **JP** · Wed Oct 21

- File: `simulation/config.py` (only `COMMANDS`, `GROUP_ID`). The token and key are filled in locally and never committed.
- Run `python simulation/simulator.py --no-upload`, read the dialogues, and fix what fails. Record ms per intent (§7).
- Done when: a full `--no-upload` run completes with no crash. Final upload on Mon Oct 26.

### T14 — Demo script + README · **Alejandro** · Thu Oct 22 – Fri Oct 23

- Files: `docs/part2_demo.md` (one or two example lines per R1–R8, in demo order), plus a "Part 2" section in `README.md` (how to build the DB and run).
- Done when: both people run the full script without a failure.

---

## 6. Timeline

| Day | JP | Alejandro | Output |
| --- | --- | --- | --- |
| Tue Oct 13 | send the plan | run backend + frontend, read the code | — |
| Thu Oct 15 | T1 database → PR | T5 panel with a fake `PLAYLIST` | `cache/musiccrs.db` |
| Fri Oct 16 | T2 skeleton, T3 parser → PR, **freeze** | review T1, T6 resolver | slash commands work |
| Sat Oct 17 | T4 R6 | T7 R2 | NL add/remove/view/clear |
| Sun Oct 18 | T9 R8 | T8 R4 | |
| Mon Oct 19 | T11 R7 (start) | T10 R5 (start) | |
| Tue Oct 20 | T11 R7 (finish) | T10 R5, T12 R3, finish T5 | all R1–R8 in branches |
| Wed Oct 21 | **sync**: run each other's code; T13 simulator `--no-upload` | **sync** | everything in `main` |
| Thu Oct 22 – Fri Oct 23 | fix what the simulator found | T14 demo script + README | buffer |
| Sat Oct 24 – Mon Oct 26 | rehearse, mock exam, final upload | rehearse, mock exam | |
| Tue Oct 27 | go / no-go | go / no-go | |
| Wed Oct 28 | present | present | |

---

## 7. Latency and LLM budget per intent

Limits: 5–10 LLM calls and 3–5 s per turn. The numbers below are **A VERIFICAR** (T13 measures them).

| Intent | LLM calls | Other cost | Expected |
| --- | --- | --- | --- |
| slash command | 0 | SQLite ms | < 0.1 s |
| ADD / REMOVE / SHOW / CLEAR / HELP | 1 (parser) | SQLite + fuzzy | ≈ 1 LLM call |
| ASK_TRACK / ASK_ARTIST | 1 | SQLite | ≈ 1 LLM call |
| RECOMMEND | 1 | `FinalRetriever` (dense encode 76 ms GPU / 394 ms CPU in Part 1) | ≈ 1 call + 0.5 s |
| CREATE_PLAYLIST | 2 | retrieval | ≈ 2 calls + 0.5 s |
| SELECT | 1–2 | — | ≈ 2 calls |

- Startup: catalog + BM25 index + embeddings + the Qwen3 model take several seconds, **once**. This is fine.
- If one Llama-3.3-70B call already takes > 2 s, add rule-based shortcuts for the common phrasings ("show my playlist", "clear it") before the LLM.

---

## 8. Git workflow

- Branches: `jp/db`, `jp/agent-skeleton`, `jp/nlu`, `jp/recs`, `jp/selection`, `ale/playlist-panel`, `ale/resolver`, `ale/playlist-handlers`, `ale/qa`.
- PR → the other person pulls, runs, reviews → merge into `main`. Small commits, one logical change each.
- Never commit: `cache/` (the DB), the API key, the upload token.

---

## 9. Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| LLM slow or down at the demo | Slash commands and the rule-based paths (selection rules, help) still work. Show them. |
| A parser JSON error | One retry, then `UNKNOWN` → "Sorry, try rephrasing, or type help". |
| `FinalRetriever` too slow or too heavy on the demo laptop | Build it without dense (bm25_plus + same_artist + bpr_sim). R6 still relates to the playlist through same_artist and BPR. |
| T1–T3 late (critical path) | Alejandro codes against a stub `TrackDB` with 10 hard-coded tracks; the interfaces in §3 are enough. |
| The fuzzy matcher is too eager ("Love" matches 500 tracks) | A threshold + exact matches first. R4 shows only the top 5. |
| One person falls behind | Raise it at the Oct 21 sync and reassign **whole tasks**. |
| A requirement still failing on Oct 27 | Fix it that day; the Oct 22–23 buffer exists for this. The presentation is one attempt only. |

---

## 10. Demo order (draft for T14)

1. R3 "what can you do?"
2. R2 "add smells like teen spirit", "add its my life by bon jovi", "show my playlist"
3. R4 "add Love" → choose "the second one"
4. R1 remove a song from the panel, add one from the panel box
5. R5 "who sings Hotel California?", "how many songs by Queen do you have?" (+ the other types)
6. R6 "recommend me something" → R7 "add all except the one by X"
7. R2 "remove the Eagles song", "clear my playlist"
8. R8 "make me a playlist for a long run"

---

## 11. Open items — A VERIFICAR

1. The presentation slot on Oct 28 (Part 3 is also due that day). Book early: few slots, no rebooking.
2. The exact JSON key names of a dialogue-act annotation in the socket message (§1.3).
3. ~~The unit of `duration` and its mean~~ — resolved Oct 15: milliseconds, mean 239.7 s (§2).
4. Ollama key works; the latency of one Llama-3.3-70B call from our network.
5. Whether `rapidfuzz` is worth a new dependency, or FTS5 + `difflib` is enough.
6. Which phrasings the simulator's persona dialogues actually use (read the first `--no-upload` run).
7. R8: replace the current playlist, or propose and ask? (decide in T9).
8. Memory and startup time of `FinalRetriever` on the laptop used for the demo.
