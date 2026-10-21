# Part 2 Work Plan — Detailed Version (tied to the real code)

> **Names and dates:** `part2_plan_simple.md` is the source of truth for who does what and when. This file adds the concrete interfaces, data fields and design notes. If the two disagree, the simple plan wins.

- Line numbers refer to commit `642687b` of this repo.
- **A VERIFICAR** = not confirmed in the code or the data yet. Check it before relying on it.
- Signatures below are **proposals**: signatures and docstrings only, no implementation. The owner may change them before the freeze (end of T3, Fri Oct 16). After that, changes need both people.

---

## 1. How the current code works

### 1.1 The starter agent ([musiccrs/musiccrs.py](../musiccrs/musiccrs.py))

- `MusicCRS(Agent)`: `__init__(use_llm=True)` creates an `openai.OpenAI` client (base URL `https://openwebui.ux.uis.no/api`, model `gorina10.gemma-4-31b`, key placeholder `LLM_API_KEY`) and `self._playlist = []`.
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
- The JSON key names of an annotation are `slot` and `value` (checked in T2 in `dialoguekit/platforms/flask_socket_platform.py`, `Message.from_utterance`).
- Run the agent from the repo root as a module: `python -m musiccrs.musiccrs` (since T2 it imports `.data.db`, `.state`, ...). DialogueKit saves every finished chat to `dialogue_export/` (gitignored).

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
- It runs scripted dialogues and persona-based NL dialogues. **The uploaded dialogues are graded. Only the last upload counts.** It needs `GROUP_ID`, `UPLOAD_TOKEN` (by email) and our Open WebUI key (`LLM_API_KEY`). **Never commit the real token or key.**

### 1.6 Part 1 code the agent reuses

| What | Where | Used by |
| --- | --- | --- |
| `MusicCatalogLoader().metadata_dict` (track_id → metadata) | [retrieval/data_loader.py](../retrieval/data_loader.py) | T1 (build the DB) |
| `FinalRetriever.retrieve(ctx, topk, policy)` | [retrieval/final_retriever.py](../retrieval/final_retriever.py) | T4 (R6) |
| `FinalRetriever.text_to_item_retrieval(query, topk)` | same | T9 (R8) |
| `TurnContext`, `SessionPolicy`, `finalize_top_k` | [retrieval/context.py](../retrieval/context.py) | T4, T9 |
| BPR vectors `cf-bpr` (47,071 × 128) | [retrieval/methods/session_cf.py](../retrieval/methods/session_cf.py) | T8 (rank options by similarity to the playlist) |

---

## 2. Data facts for Part 2

Catalog: `talkpl-ai/TalkPlayData-Challenge-Track-Metadata`, split `all_tracks`, 47,071 tracks (Part 1 plan §2.2).

- Fields: `track_id, ISRC, track_name, artist_name, album_name, tag_list, popularity, release_date, duration, artist_id, album_id`.
- `track_name`, `artist_name`, `album_name`, `artist_id`, `album_id` are **lists**. Matching must check **every** name and **every** artist, not only the first.
- 10,638 distinct artists (10,500 after `normalize()`); the median artist has 1 track.
- `popularity` 0–93 (median 38) → the R4 ranking signal.
- `tag_list`: noisy user tags (mean 33 per track) → R5 "genres of an artist", and R8 matching.
- `release_date` → R5 "release year". `duration` → R5 "how long" and the R8 length.
- **Name, artist and duration facts** (counted on Oct 15 by `python -m musiccrs.data.build_db`):

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

File layout of `musiccrs/` (folders by role since Oct 19):

```
musiccrs/
  musiccrs.py     agent + HANDLERS table (python -m musiccrs.musiccrs)
  state.py        shared types: DialogueState, ParsedIntent, Reply, Services
  llm.py          LLM client and ask_json (used by the parser, T9, T11)
  data/           db.py, build_db.py (python -m musiccrs.data.build_db), resolver.py (T6)
  nlu/            parser.py (parse), prompt.py
  handlers/       playlist.py (T2/T7/T8/T12), recs.py (T4/T9), qa.py (T10), selection.py (T11)
  checks/         check_nlu.py, check_recs.py, nlu_examples.json (python -m musiccrs.checks.<name>)
```

Inside a folder, imports go one package up with `..` (for example `from ..state import Reply` in `handlers/playlist.py`).

### 3.1 `musiccrs/data/db.py` — T1

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
- `musiccrs/data/build_db.py`: `python -m musiccrs.data.build_db` reads `MusicCatalogLoader().metadata_dict` and writes `cache/musiccrs.db` (`cache/` is gitignored). It is idempotent: it deletes the file and rebuilds.
- Why SQLite: it is in the Python stdlib, it is one file, it does exact lookups by index in ms, and FTS5 handles partial names. The spec allows any database.

### 3.2 `musiccrs/state.py` — T2 (done)

All shared types live here, so handlers, `nlu/parser.py` and `musiccrs.py` import them from one place (no circular imports).

```python
@dataclass
class DialogueState:
    playlist: list[str] = field(default_factory=list)          # track IDs, in order
    pending_options: list[str] = field(default_factory=list)   # last shown list (R4 or R6/R8)
    pending_kind: str | None = None                            # "disambiguation" | "recommendation" | None

@dataclass
class ParsedIntent:
    name: str                      # one of INTENTS (see §3.3)
    slots: dict[str, str]          # track, artist, track_id, question, description, selection, ...
```

`Reply` and `Services` (§3.4) are in the same file.

### 3.3 `musiccrs/nlu/parser.py` — T2 rules, T3 LLM (frozen Oct 19)

T2 added `split_artist_track(text)` (cut at the first `": "`) and `parse_command(text) -> ParsedIntent | None` (slash commands by rules; `None` when the text is not a slash command). T3 adds:

```python
INTENTS = ("ADD", "REMOVE", "SHOW", "CLEAR", "HELP", "ASK_TRACK", "ASK_ARTIST",
           "RECOMMEND", "CREATE_PLAYLIST", "SELECT", "GREETING", "QUIT", "UNKNOWN")
SLOT_NAMES = ("track", "artist", "track_id", "question", "description", "selection",
              "different", "topic", "text")
TRACK_QUESTIONS = ("artist", "album", "release_year", "duration")
ARTIST_QUESTIONS = ("track_count", "top_track", "albums", "genres")
HELP_TOPICS = ("add", "remove", "show", "clear", "questions", "recommend",
               "create_playlist", "select")

def parse(text: str, state: DialogueState, llm) -> ParsedIntent:
    """Slash commands → parsed by rules, no LLM. No LLM client → UNKNOWN.
    Otherwise one LLM call (system prompt from build_prompt(state) + the user's text),
    then to_parsed_intent() keeps only allowed intents, slots and values."""
```

- Slots: `track`, `artist` (as the user wrote them; the resolver finds the real track), `question` (one of the 8 R5 types above, checked against *its* intent), `description` (R8), `selection` (the raw selection text for R7), `different` (only present when true), `topic` (R3, one of `HELP_TOPICS`; absent for general help). Set **only by our code**, dropped if the LLM sends them: `track_id` (from `/remove <id>`) and `text` (the user's message, on `UNKNOWN`).
- `ASK_TRACK` / `ASK_ARTIST` with a question outside the list keep the intent but lose the `question` slot: the T10 handler must handle a missing question.
- The prompt lives in `musiccrs/nlu/prompt.py` (intents, slot rules, a `Pending options:` line, 8 scope rules against off-topic requests and prompt injection, 18 few-shot examples). Its lists must match the tuples above.
- LLM helpers in `musiccrs/llm.py`, reusable by T9 and T11: `create_client()` (key from the `LLM_API_KEY` environment variable, `None` without it, `max_retries=0`), `extract_json(text)`, `ask_json(llm, messages)` (temperature 0, 5 s timeout; no valid JSON → the model sees its answer and is asked once more, so 2 calls at most; API error → `None`).

### 3.4 Handler contract and registry — T2 (done)

```python
# musiccrs/state.py
@dataclass
class Reply:
    text: str
    dialogue_acts: list[DialogueAct] = field(default_factory=list)

Handler = Callable[[ParsedIntent, DialogueState, "Services"], Reply]

@dataclass
class Services:                     # created once in main, shared by every agent
    db: TrackDB
    retriever: FinalRetriever
    llm: openai.OpenAI | None
```

- `musiccrs.py` keeps `HANDLERS: dict[str, Handler]` (today: ADD, REMOVE, SHOW, CLEAR). `receive_utterance` = `parse_command` (T3: `parse`) → `QUIT` ends the chat → `HANDLERS[parsed.name](...)`, or a fallback reply listing the commands → send the reply with a **`PLAYLIST` act** added when the playlist changed or the intent is `SHOW`.
- `Services` is a module global built by `create_services()` in `__main__` before `platform.start()`; since T4 it also loads `FinalRetriever` (≈ 45–50 s, once). The agent constructor is `MusicCRS(agent_id="MusicCRS")`.
- T2 put simple exact-match versions of ADD / REMOVE / SHOW / CLEAR in `handlers/playlist.py` (most popular match, no resolver, no disambiguation); Alejandro replaces their bodies in T7/T8 and keeps the signatures. Text replies are HTML (the chat renders them), so names are passed through `html.escape(..., quote=False)`.
- Each owner registers handlers from their own file: `handlers/playlist.py` (ADD, REMOVE, SHOW, CLEAR, HELP), `handlers/qa.py` (ASK_TRACK, ASK_ARTIST), `handlers/recs.py` (RECOMMEND, CREATE_PLAYLIST), `handlers/selection.py` (SELECT).

### 3.5 Dialogue acts (the UI and the simulator contract)

| Intent | Annotations | Sent when |
| --- | --- | --- |
| `PLAYLIST` | one `SlotValueAnnotation("track", json.dumps({"id", "name", "artist", "duration_ms"}))` per track, in order (`artist` = main artist); empty playlist → no annotations. Names are **not** HTML-escaped: the panel must render them as plain text, not with `dangerouslySetInnerHTML` | after any change, and on `SHOW` (`playlist_act()` in `musiccrs.py`) |
| `OPTIONS` (existing) | `SlotValueAnnotation("option", "<n>. <name> — <artist>")` | R4 choices, R6 recommendations |

### 3.6 Slash commands (T2, matched in `simulation/config.py` by T13)

| Command | Meaning |
| --- | --- |
| `/add [artist]: [track]` | add (artist optional: `/add [track]`) |
| `/del [artist]: [track]` | remove by name |
| `/remove <track_id>` | remove by ID (UI button) |
| `/select <choice>` | choose from the pending options (the option buttons send `/select <n>`; added Oct 21) |
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
| R6 recommend | `recommend_context(playlist)` = `TurnContext(played_track_ids=tuple(playlist), history=(("music", id), ...) one per playlist track, current_message="", turn_number=len(playlist)+1)`, `SessionPolicy()` → songs already in the playlist are never recommended. The `history` entries let bm25_plus search the playlist's names, artists and albums (with `history=()` it would get two empty queries). The message is empty because "recommend me something" is not a music query (and dense then returns nothing) |
| R6 + "something different" / "other artists" (`different` slot) | `SessionPolicy(use_same_artist=False)`, 50 candidates, then every track sharing an artist with the playlist is dropped (BPR and BM25 still favour the playlist's artists, so the policy alone is not enough) |
| R8 from scratch | `plan_playlist(description)` → LLM query + minutes, then `text_to_item_retrieval(query, playlist_length(minutes))` → no played tracks, so only bm25_plus and dense contribute; the result replaces the playlist |

---

## 5. Tasks

Each task: owner · files · interface · design notes · LLM calls · done when.

### T1 — Database · **JP** · Thu Oct 15

- Files: `musiccrs/data/db.py`, `musiccrs/data/build_db.py`.
- Notes: §3.1. Store **all** artists of a track. Keep `name_norm` for exact lookups and FTS5 for partial ones.
- LLM calls: 0.
- Done when: `python -m musiccrs.data.build_db` builds the DB in under a minute and its self-check passes: `find_by_name("smells like teen spirit")` returns Nirvana first; `find_by_name("SMELLS LIKE TEEN SPIRIT!", artist="nirvana")` returns only Nirvana; `find_by_name("hotel california")` finds the Eagles remaster; `fuzzy_candidates("teen spirit nirvana")` contains it; `artist_tracks("queen")` returns 13 tracks; `get()` on 3 random IDs matches `metadata_dict`.
- Result (Oct 15): build 2.5 s (+ 6 s catalog load); exact lookup 0.2 ms, fuzzy 7 ms.

### T2 — Agent skeleton · **JP** · Fri Oct 16

- Files: `musiccrs/musiccrs.py`, `musiccrs/state.py`.
- Notes: §1.2 (singletons in `main`), §3.2, §3.4, §3.6. Remove the double `platform.start()`. Keep `/quit` and the welcome message. The welcome message mentions "type help".
- LLM calls: 0 (slash path).
- Done when: `/add nirvana: smells like teen spirit`, `/list`, `/del nirvana: smells like teen spirit`, `/clear` work in the browser and each sends a `PLAYLIST` act.
- Result (Oct 17): done, checked with a socket.io client (the browser's channel). Each command replies with a `PLAYLIST` act (empty after `/clear`); a failed `/add` sends none; `/recommend` and free text get a fallback that lists the commands; two clients at once keep separate playlists. Files: `state.py`, `nlu.py` (`parse_command`), `handlers/playlist.py` (simple versions), `musiccrs.py`.
- Known limits, left to T6/T7: exact names only (`/add bohemian rhapsody by queen` is not found, "by" is not parsed); several matches → the most popular is added (`/add bohemian rhapsody` adds Queen's "Operatic Section / 2011 A Cappella Mix").

### T3 — Intent parser · **JP** · Fri Oct 16

- Files: `musiccrs/llm.py`, `musiccrs/nlu/prompt.py`, `musiccrs/nlu/parser.py`, `musiccrs/musiccrs.py`, `musiccrs/checks/nlu_examples.json` (37 sentences, ≥ 2 per intent, with the expected parse), `musiccrs/checks/check_nlu.py`.
- Notes: §3.3. Low temperature (0). Ask for JSON only. Include `pending_kind` in the prompt.
- LLM calls: 1 (2 with a retry).
- Done when: `python -m musiccrs.checks.check_nlu` parses ≥ 90% of `nlu_examples.json` correctly and prints the ms per call. **Then the interfaces are frozen.**
- Result (Oct 19): **37/37 (100%)**, ms per parse mean 447, max 895 (Gemma 4 31B on Open WebUI). Interfaces frozen. The check compares `track`/`artist` after `normalize`, `description`/`selection` by presence only, other slots exactly, and counts an extra slot as a failure. The sentences were written by us, so 100% here does not promise 100% on real users; the simulator run (T13) is the next test.

### T4 — R6 recommend · **JP** · Sat Oct 17

- File: `musiccrs/handlers/recs.py`.
- Notes: §4. `retriever.retrieve(ctx, topk=5, policy)`. Empty playlist → ask the user to add songs first, or offer R8. Store the 5 IDs in `pending_options` with `pending_kind="recommendation"` and send them as `OPTIONS`.
- LLM calls: 0 beyond the parser.
- Done when: 3 different playlists (rock / jazz / pop) give 5 clearly related songs, none already in the playlist; latency written down.
- Result (Oct 19): **done**. `python -m musiccrs.checks.check_recs` passes. Each playlist gets 5 new songs, and "different" gives no playlist artist. **10 ms per call** (max 16, GPU laptop). The retriever loads in 45–51 s at startup. Rock → Nirvana, Bon Jovi ×3, Coldplay; jazz → Armstrong, Brubeck ×2, Coltrane, Elliott Smith; pop → Miley Cyrus, Britney ×2, Future, Nelly. Known limit: "different" on the jazz playlist gives non-jazz songs (Elliott Smith, Night Ranger, ...). Putting the playlist's most common tags in `current_message` was tried and changed almost nothing (same_artist and BPR, weight 2 each, outweigh BM25 and dense, weight 1 each), so it was not added.
- Files: `musiccrs/handlers/recs.py` (`recommend_context`, `options_act`, `playlist_artists`, `drop_playlist_artists`, `handle_recommend`), `musiccrs/musiccrs.py` (`FinalRetriever` in `create_services`, `RECOMMEND` in `HANDLERS`), `musiccrs/checks/check_recs.py`.

### T5 — R1 playlist panel · **Alejandro** · Thu Oct 15 → Tue Oct 20

- Files: `frontend/src/components/Playlist/Playlist.tsx`, `Playlist.css`; small edits to `ChatWidget.tsx` / `ChatBox.tsx` to subscribe to `PLAYLIST` acts.
- Notes: render the **last** `PLAYLIST` act (the agent is the source of truth). A remove button per track sends `/remove <id>`, a clear button sends `/clear`, and an add box sends `add <text>` as a normal chat message (so R4 disambiguation still works). Hide `PLAYLIST` acts from the chat bubbles. Show the track count and total duration.
- LLM calls: 0.
- Done when: add, remove and clear from both the chat and the panel keep the two in sync. `npm test` still passes.
- Result (Oct 21, Alejandro, PR #14): `frontend/src/components/Playlist/PlaylistPanel.tsx` + `.css`, mounted beside the chat in `ChatBox.tsx`; it reads the last `PLAYLIST` act of the raw messages, renders names as plain text, × sends `/remove <id>`, "Clear Playlist" sends `/clear`, the add box sends `add <text>`, and the header shows the count and total minutes. Adapted by JP (Oct 21): his `tsconfig.json` change was dropped (`moduleResolution: "bundler"` fails on TypeScript 4.9.5: TS6046); `npx tsc --noEmit` passes. The chat now also shows the `OPTIONS` act as buttons (DialogueKit sends no `attachments`, so the starter kit's buttons never appeared); a click sends `/select <n>`. `npm test` cannot run on this machine (a Babel version clash in `node_modules`, unrelated to our code).

### T6 — Track resolver · **Alejandro** · Fri Oct 16

- File: `musiccrs/data/resolver.py`.

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
- Result (Oct 19, Alejandro; adapted Oct 21, JP): `difflib.SequenceMatcher` instead of rapidfuzz (no new dependency). Order: only an artist → `resolve_artist`; exact match of the whole name first (so "Stand By Me" is not split at "by"); then "song by artist" split; then fuzzy over 50 FTS5 candidates, title score ≥ 0.6, and **with an artist, the candidate's artist must score ≥ 0.8** (JP's fix: "Always" by Bon Jovi gave 45 songs by other artists, "Goodbye" by Chris Young gave Chris Brown). `artist_key` drops a leading "the" ("the eagles" → Eagles). 11 resolver cases in `check_handlers`.

### T7 — R2 handlers · **Alejandro** · Sat Oct 17

- File: `musiccrs/handlers/playlist.py` (ADD, REMOVE, SHOW, CLEAR).
- Notes: 1 match → add/remove. Several → T8. 0 → "I couldn't find X in the database". A duplicate add → say so, don't add twice. REMOVE resolves against the **playlist first** ("remove the Queen song").
- LLM calls: 0 beyond the parser.
- Done when: all 4 actions work in natural language with 2+ phrasings each, and the panel updates.
- Result (Oct 19–21, Alejandro; adapted Oct 21, JP): REMOVE rewritten. It crashed when there was no `track` slot (`parsed.raw_text` does not exist), so "remove the Queen song" (`{"artist": "queen"}`) and `/remove <unknown id>` broke the turn. Now it goes by ID, then by title (`normalize` / `base_name` equal, or part of the title) and/or artist (`artist_key`); 1 match → removed, several → listed, the user asked for the title. The handlers no longer add their own `PLAYLIST` act (the agent sends it once). "1 song" / "1 song removed".

### T8 — R4 disambiguation · **Alejandro** · Sun Oct 18

- File: `musiccrs/handlers/playlist.py`.
- Ranking: `score = popularity/93 + same_artist_as_playlist + cosine(BPR(track), mean BPR(playlist))`. With an empty playlist, popularity only. Show the top 5 as `OPTIONS` and store them in `pending_options` (`pending_kind="disambiguation"`).
- The choice: a click (quick reply), or "the second one" / "the one by X" → SELECT, using T11's `select_indices` (shared, owned by JP).
- LLM calls: 0 beyond the parser.
- Done when: "add Love" shows 5 sensible options; with a rock playlist, rock versions rank higher.
- Result (Oct 19, Alejandro; adapted Oct 21, JP): `rank_options` = popularity/93 + 1.5 × same artist + BPR cosine. The BPR part looked for `services.bpr_matrix`, which does not exist, so it was never used; it now reads the Part 1 `bpr_sim` scorer inside the retriever (`services.retriever.fusion.scorers["bpr_sim"]`, unit rows). Measured: with an R&B playlist (TLC, ...), "Love?" by Strapping Young Lad (metal) drops from 3rd to 5th. `options_act` moved from `recs.py` to `playlist.py` (shared by R4 and R6/R8; `recs.py` already imported `playlist.py`).

### T9 — R8 playlist from a description · **JP** · Mon Oct 19 – Tue Oct 20

- File: `musiccrs/handlers/recs.py` (CREATE_PLAYLIST).
- Notes: one LLM call returns `{"query": "...", "minutes": N}`. If no duration is implied, `minutes` comes from the activity (gym ≈ 60, a party is longer, "a few songs" is short). Length = `round(minutes * 60 / mean_duration)`, clamped 8–25 (mean duration in §2). Then `text_to_item_retrieval(query, topk=length)`.
- LLM calls: 1 (2 with a retry), plus the parser.
- Done when: 3 descriptions give relevant playlists of different lengths, and the length rule is written in the code comment.
- Result (Oct 20): **done**. `python -m musiccrs.checks.check_playlist`: "sad love songs" → 11 songs (45 min), "energetic music for a gym session" → 15 (60), "a few songs for a short coffee break" → 8 (15), "music for a long road trip" → 25 (120); **0.8 s** mean per handler call (plan LLM call + retrieval, max 1.5 s); whole turn with the parser ≈ 1.5–3.4 s (the first dense encode after startup is the slowest).
- Decision (open item 7): the new playlist **replaces** the current one, and the reply says "It replaced your previous playlist of N songs". The songs are not shown as options (the spec asks for a playlist created automatically), and the old pending options are cleared.
- `plan_playlist`: the query and the minutes are checked separately; an empty query → the description; minutes not a number, a bool, or outside 5–300 → 45 (`DEFAULT_MINUTES`, 11 songs). No LLM client → the description and 45 min, so R8 still works without the key (always 11 songs).
- Prompt rule added after the first run: no place or activity word in the query. "gym" is a tag of only 30 tracks but is in 17 names and artists, so "the gym" gave Gym Class Heroes ×4; mood words ("energetic" 1,624 tags, 0 names) do not have that problem. Known limit: bm25_plus searches titles and artists together with tags, so words like "coffee" or "road" still pull matching titles (6 "Coffee" titles for the coffee break). A tag-only search would fix it but changes the Part 1 retriever.
- No per-artist cap: at most 2 songs by one artist in every checked playlist.
- Files: `musiccrs/handlers/recs.py` (`MEAN_TRACK_SECONDS`, `MIN_LENGTH`, `MAX_LENGTH`, `DEFAULT_MINUTES`, `PLAYLIST_PROMPT`, `playlist_length`, `plan_playlist`, `handle_create_playlist`), `musiccrs/musiccrs.py` (`CREATE_PLAYLIST` in `HANDLERS`), `musiccrs/checks/check_playlist.py`.
- Parser limit seen (T3): "now give me sad love songs instead" → RECOMMEND `{"different": true}`, not CREATE_PLAYLIST. "make me a playlist of ..." / "make me a playlist for ..." work.

### T10 — R5 questions · **Alejandro** · Mon Oct 19 – Tue Oct 20

- File: `musiccrs/handlers/qa.py` (ASK_TRACK, ASK_ARTIST).
- Question types (the `question` slot): track → `artist`, `album`, `release_year`, `duration` (popularity as a fifth if time allows); artist → `track_count`, `top_track`, `albums`, `genres` (top tags across the artist's tracks).
- The answers come **from the DB with templates**. The LLM only fills the slots (in the T3 call), so it cannot invent facts. If the track is ambiguous, answer for the most popular match and say which one.
- LLM calls: 0 beyond the parser.
- Done when: all 8 types answer correctly, with 2 phrasings each.
- Result (Oct 19, Alejandro; adapted Oct 21, JP): all 8 types from the DB, checked in `check_handlers` (e.g. It's My Life → 2000, Bad Medicine → 5:16, Bon Jovi → 32 tracks, Nirvana's top → Heart-Shaped Box). ASK_ARTIST now uses `resolve_artist` ("the eagles"), and the shortcuts were written out.

### T11 — R7 selection · **JP** · Mon Oct 19 – Tue Oct 20

- File: `musiccrs/handlers/selection.py` (SELECT).

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
- Result (Oct 19): **done**. `python -m musiccrs.checks.check_select`: 16/16 rule cases, 6/6 LLM cases, **344 ms** mean per LLM case (max 759). Through the parser (`parse` → `HANDLERS["SELECT"]`), "add the first two", "all of them please", "none, thanks", "add all except the one by Bon Jovi", "just the Coldplay one" and "the second one" all leave the right playlist, in 0.4–1.1 s per turn.
- Rules (`rule_indices`): every word must be known (all / none words, ordinals, digits, "first N" / "last N", filler words); one unknown word ("except", "by", an artist) → `None`, so "the first one by X" is never read as "the first one". "both" only with 2 options; "none" or "all" mixed with a position → `None`.
- LLM fallback (`llm_indices`): the options as numbered lines with every artist, answer `{"indices": [1-based numbers]}` or `{"indices": null}`. Anything but a list of whole numbers in 1..count → `None`, so a bad answer never adds a wrong song.
- `handle_select`: not understood or no `selection` slot → ask again and **keep** the options; `[]` → nothing added, options cleared; `"disambiguation"` with more than one choice → "pick only one", options kept; songs already in the playlist are not added twice and are named in the reply. The `PLAYLIST` act comes from `receive_utterance` as usual.
- Files: `musiccrs/handlers/selection.py` (`rule_indices`, `options_text`, `llm_indices`, `select_indices`, `clear_pending`, `track_list_html`, `handle_select`), `musiccrs/musiccrs.py` (`SELECT` in `HANDLERS`), `musiccrs/checks/check_select.py`.
- Data fact: the catalog has **one** Metallica track (a medley), so demo and test lines use Bon Jovi, Nirvana or Coldplay.

### T12 — R3 help · **Alejandro** · Tue Oct 20

- File: `musiccrs/handlers/playlist.py` (HELP).
- Notes: a fixed, well-written text with one example per feature. If the parser fills a `topic` slot ("how do I remove?"), show only that part.
- LLM calls: 0 beyond the parser.
- Done when: "help", "what can you do?" and "how do I make a playlist?" all give a useful answer.
- Result (Oct 19, Alejandro; Oct 21, JP): one explanation per `HELP_TOPICS` value; the full help lists all of them (JP added R8 and question examples). A GREETING handler (`handle_greeting` in `musiccrs.py`, T13) replies with the features too.

### T13 — Latency check (was: simulator config) · **JP** · Oct 20–21

- Changed Oct 20: the course simulator is from the 2025 course (upstream commits Oct 30 – Nov 12, 2025), the 2026 Part 2 spec does not mention it, and it needs an upload token we did not get (it checks the token and calls the course server even with `--no-upload`). Its default `COMMANDS` already match ours; `simulation/config.py` is not changed.
- Built: `handle_greeting` (GREETING had no handler: "Hello!" got "cannot do that yet"); `print_turn_time` (`[ADD] 812 ms` per turn in the backend terminal); a warm-up search in `create_services` (the first `text_to_item_retrieval` after startup took 894 ms, then 147 / 170 ms; after the warm-up the first real one takes 119 ms); `musiccrs/checks/check_latency.py`, a 25-turn scripted conversation with the simulator's hard catalog cases, checking the intent, the playlist length after each turn and ≤ 3 s per turn.
- Result: §7.

### T14 — Demo script + README · **JP** (was Alejandro) · Oct 21

- Files: `docs/part2_demo.md` (setup, start, a 30-line demo script for R1–R8, the checks, the acts, problems; it replaces `docs/how_to_run.md`) and "Part 2: how to run and demo" in `README.md`.
- Done when: both people run the full script without a failure.

---

## 6. Timeline

| Day | JP | Alejandro | Output |
| --- | --- | --- | --- |
| Tue Oct 13 | send the plan | run backend + frontend, read the code | — |
| Thu Oct 15 | T1 database → PR | T5 panel with a fake `PLAYLIST` | `cache/musiccrs.db` |
| Fri Oct 16 | T2 skeleton, T3 parser → PR, **freeze** | review T1, T6 resolver | slash commands work |
| Sat Oct 17 | T3 parser (took until Mon) | T7 R2 | NL add/remove/view/clear |
| Sun Oct 18 | T3 parser | T8 R4 | |
| Mon Oct 19 | T3 → PR #10; T4 R6 | T10 R5 (start) | |
| Tue Oct 20 | T11 R7 (before T9: T8 uses `select_indices`) | T10 R5, T12 R3, finish T5 | all R1–R8 in branches except R8 |
| Wed Oct 21 | T9 R8 (morning); **sync**: run each other's code; T13 simulator `--no-upload` | **sync** | everything in `main` |
| Thu Oct 22 – Fri Oct 23 | fix what the simulator found | T14 demo script + README | buffer |
| Sat Oct 24 – Mon Oct 26 | rehearse, mock exam, final upload | rehearse, mock exam | |
| Tue Oct 27 | go / no-go | go / no-go | |
| Wed Oct 28 | present | present | |

---

## 7. Latency and LLM budget per intent

Limits: 3–5 s per turn (our aim: ≤ 3 s, ≤ 3 LLM calls). Measured by T13 with `check_latency`
(Oct 20, run 2, after the warm-up, before the merge; JP's laptop, Gemma 4 31B), whole turn = parser + handler:

| Intent | LLM calls | Other cost | Measured per turn (mean / max) |
| --- | --- | --- | --- |
| slash command | 0 | SQLite | 0–4 ms |
| GREETING / HELP | 1 (parser) | none | 625 ms (GREETING) |
| ADD | 1 | SQLite + fuzzy | 651 / 749 ms (7 turns) |
| REMOVE / SHOW / CLEAR | 1 | SQLite | 480 / 311 / 306 ms |
| ASK_TRACK / ASK_ARTIST | 1 | SQLite | 564 / 647 ms |
| RECOMMEND | 1 | `FinalRetriever` 7–10 ms (empty message, no dense encode) | 465 ms |
| SELECT | 1 (rules, or a button: 0) or 2 (LLM fallback) | — | 481 ms |
| CREATE_PLAYLIST | 2 (parser + plan) | retrieval with a live dense encode (~120–170 ms after the warm-up) | 1218 ms (was 3094 before the warm-up) |
| QUIT | 1 | — | 311 ms |

- Every turn under 3 s. Run-to-run noise from the LLM is large (SHOW 828 ms in run 1, 311 ms in run 2, same code), so one run is only a rough guide.
- Run 3 (Oct 21, after the merge, 25 turns with HELP, ASK_*, R4 options and `/select`): **OK**, every turn under 3 s. Mean ms: GREETING 700, HELP 316, ADD 576 (max 649, 10 turns), SELECT 493 (4), REMOVE 442 (2), SHOW 309, ASK_TRACK 564, ASK_ARTIST 647, RECOMMEND 344, CREATE_PLAYLIST **1676** (the slowest), CLEAR 311, QUIT 412. Same day: `check_nlu` 37/37 (mean 515 ms, max 925), `check_select` 16/16 rules + 6/6 LLM (mean 690 ms, max 1244).

- Startup: catalog + BM25 index + embeddings + the Qwen3 model take **45–51 s** (measured in T4 on JP's GPU laptop), **once**. This is fine. Part of it is the catalog loaded twice (`BM25PlusRetriever` and `DenseScorer` each create a `MusicCatalogLoader`).
- If one Gemma 4 31B call already takes > 2 s, add rule-based shortcuts for the common phrasings ("show my playlist", "clear it") before the LLM.

---

## 8. Git workflow

- Branches: `jp/db`, `jp/agent-skeleton`, `jp/nlu`, `jp/recommend`, `jp/selection`, `jp/create-playlist`, `ale/playlist-panel`, `ale/resolver`, `ale/playlist-handlers`, `ale/qa`.
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
6. R6 "recommend me something" → R7 "add all except the one by X" (X = an artist actually in the list; not Metallica, which has one catalog track)
7. R2 "remove the Eagles song", "clear my playlist"
8. R8 "make me a playlist of sad love songs", then "energetic music for a gym session" (different lengths, the second replaces the first; avoid descriptions whose key word is common in titles, like "run" or "night")

---

## 11. Open items — A VERIFICAR

1. The presentation slot on Oct 28 (Part 3 is also due that day). Book early: few slots, no rebooking.
2. The exact JSON key names of a dialogue-act annotation in the socket message (§1.3).
3. ~~The unit of `duration` and its mean~~ — resolved Oct 15: milliseconds, mean 239.7 s (§2).
4. Open WebUI key works; the latency of one Gemma 4 31B call from our network.
5. Whether `rapidfuzz` is worth a new dependency, or FTS5 + `difflib` is enough.
6. ~~Which phrasings the simulator's persona dialogues actually use~~ — resolved Oct 20: the simulator is not used (2025 tool, no upload token); its scripted hard cases are in `check_latency`.
7. ~~R8: replace the current playlist, or propose and ask?~~ — resolved Oct 20 (T9): replace, and say so in the reply.
8. Memory and startup time of `FinalRetriever` on the laptop used for the demo (JP's GPU laptop: 45–51 s startup, 10 ms per R6 call; not yet measured on a CPU-only laptop).
