# MusicCRS Part 2: how to run, demo script and checks

How to start the agent and the chat UI, the demo script with one tested line per requirement
(R1–R8), and the command-line checks. Replaces the old `how_to_run.md`.
State: Oct 21, everything of Part 2 merged (both members' tasks T1–T14).

All commands are for **Git Bash**, from the **repo root**.

---

## 1. One-time setup

```bash
conda activate musiccrs                # Python 3.11 env
pip install -r requirements.txt
python -m musiccrs.data.build_db       # builds cache/musiccrs.db (~10 s), ends with "OK 1" ... "OK 6"
cd frontend && npm install && cd ..    # needs Node.js (tested with v24); only the first time
```

- `build_db` downloads the catalog from Hugging Face the first time (internet needed once).
- Run `build_db` again only if `musiccrs/data/db.py` or `musiccrs/data/build_db.py` changes.

### LLM key (needed for natural language; slash commands work without it)

The course LLM is Gemma 4 31B on Open WebUI. Register at <https://openwebui.ux.uis.no> with your
student number, then go to Settings -> Account and generate an API key. The agent reads it from
the `LLM_API_KEY` environment variable.

Store it once in the conda env, so it is set every time the env is activated:

```bash
conda activate musiccrs
conda env config vars set LLM_API_KEY=sk-...
conda deactivate && conda activate musiccrs        # reactivate to load it
python -c "import os; print('ok' if os.environ.get('LLM_API_KEY') else 'missing')"
```

- The key is saved inside the env folder (`envs/musiccrs/conda-meta/state`), not in the repo. It is
  only set in a terminal where `conda activate musiccrs` was run.
- `conda env config vars list` and `conda env export` print it: never commit an exported env file.
- For one terminal only: `export LLM_API_KEY="sk-..."` (Git Bash) or `$env:LLM_API_KEY = "sk-..."` (PowerShell).
- Without the key, the backend prints `LLM_API_KEY is not set: the agent runs with slash commands only.`

---

## 2. Start (two terminals)

**Terminal 1 — backend (agent):**

```bash
conda activate musiccrs
python -m musiccrs.musiccrs
```

It prints `Loading the retriever...`, then `Retriever loaded in ~30–60 s` (the Part 1 retriever,
loaded once, including one warm-up search), then `Running on http://127.0.0.1:5000`. Wait for that
last line. Every turn then prints its intent and time, for example `[ADD] 650 ms`.

> Use `python -m musiccrs.musiccrs`, not `python musiccrs/musiccrs.py` (`'musiccrs' is not a package`).

**Terminal 2 — frontend (chat UI):**

```bash
cd frontend
npm start
```

The browser opens http://localhost:3000: the chat on the left, the playlist panel on the right.
The welcome message says *"Hello, I'm MusicCRS. I can build a playlist with you and recommend
songs. Type /help to see what I can do."* Stop either one with `Ctrl+C`.

---

## 3. Demo script (R1–R8)

Type the lines in order, in **one tab** (each tab has its own playlist). The replies below come
from the scripted runs of Oct 20–21 (`check_latency`, `check_handlers`); recommended and generated
songs depend on the playlist and the LLM, so yours may differ. Times are per turn on JP's laptop:
about 0.3–0.9 s for one LLM call, 1–3 s for R8 (two calls).

| # | Req | Type / do | Expected |
| --- | --- | --- | --- |
| 1 | R3 | `Hello!` | "Hi! I can add and remove songs in your playlist, answer questions ..." |
| 2 | R3 | `what can you do?` | Every feature with examples: add, remove, show, clear, questions, recommend, create a playlist, choose from a list |
| 3 | R3 | `how do I remove a song?` | Only the remove help |
| 4 | R2 | `add Smells Like Teen Spirit by Nirvana` | Added ...; the panel shows 1 song |
| 5 | R2 | `put its my life by bon jovi on my list` | Added It's My Life by Bon Jovi (loose name: no apostrophe, lower case) |
| 6 | R2 | `add Hotel California by the Eagles` | Two versions (the catalog writes "Eagles"): buttons "1. Hotel California - 2013 Remaster — Eagles", "2. ... Live ..." |
| 7 | R4 | click the first button | "Added to your playlist: Hotel California - 2013 Remaster by Eagles"; 3 songs |
| 8 | R2 | `add Always by Bon Jovi` | "Sorry, I could not find 'Always' by 'Bon Jovi' in the catalog." (only catalog songs) |
| 9 | R4 | `add Love` | "I found several songs called 'Love'." 5 options as buttons, most popular first (Keyshia Cole, Musiq Soulchild, ...), songs like the playlist's moved up (same artist, BPR similarity) |
| 10 | R4 | `the second one` | Added the 2nd option; 4 songs |
| 11 | R5 | `who sings Hotel California?` | "Hotel California - 2013 Remaster is performed by Eagles." |
| 12 | R5 | `when was It's My Life released?` | "... was released in 2000." |
| 13 | R5 | `what album is Smells Like Teen Spirit on?` | "... is on the album Nevermind (30th Anniversary Edition Super Deluxe)." |
| 14 | R5 | `how long is Bad Medicine?` | "... is 5:16 long." |
| 15 | R5 | `how many songs does Bon Jovi have?` | "We have 32 tracks by Bon Jovi in the catalog." |
| 16 | R5 | `what is Nirvana's most popular song?` | "... is Heart-Shaped Box." |
| 17 | R5 | `which albums does Queen have?` | "Albums by Queen include: ..." (up to 5) |
| 17b | R5 | `what genre are the Eagles?` | The most frequent tags, each once, any case ("rock, Pop, Hard Rock, classic rock, country rock") |
| 18 | R2 | `show me my playlist` | Numbered list of the 4 songs |
| 19 | R2 | `remove the Bon Jovi song` | Removed It's My Life by Bon Jovi (by artist only); 3 songs |
| 20 | R6 | `recommend me something` | 5 songs related to the playlist (same artists, similar listeners), none already in it, as buttons |
| 21 | R7 | `add all except the one by <an artist in the list>` | Adds the other 4 (one extra LLM call) |
| 22 | R6 | `recommend me something different` | 5 songs by artists not in the playlist |
| 23 | R7 | `the first two` / `none` / click one button | Adds the first two / nothing / that one |
| 24 | R8 | `make me a playlist of sad love songs` | "Here is a playlist for 'sad love songs': 11 songs, about 41 minutes (I aimed for about 45 minutes)." It replaces the old playlist and says so |
| 25 | R8 | `now make me one with energetic music for a gym session` | 15 songs, about 60 minutes (a gym session ≈ 60 min) |
| 26 | R2 | `clear my playlist` | "Cleared your playlist (15 songs removed)." The panel is empty |
| 27 | R1 | Panel: type `toxic` in "Add a track..." and press + | The same as typing "add toxic" in the chat: options or added |
| 28 | R1 | Panel: click × next to a song | Removed ...; the panel updates |
| 29 | R1 | Panel: "Clear Playlist" | Cleared ...; the panel is empty |
| 30 | — | `goodbye` | "It was nice talking to you. Bye" |

Notes for the demo:
- **Layout:** the chat takes the free width (at least 420 px), the panel sits beside it (300–460 px) and drops below the chat on narrow screens.
- **R1:** the panel always shows the agent's playlist (one `PLAYLIST` act after every change).
  Its buttons only send chat commands (`/remove <id>`, `/clear`, `add ...`): the playlist lives in
  the agent, the UI never touches the database.
- **R4 ranking:** popularity / 93 + 1.5 if the song shares an artist with the playlist + the BPR
  cosine with the playlist (Part 1 vectors). With an empty playlist it is popularity only.
- **R7:** "all", "none", ordinals ("the first two", "1 and 3", "the last one") and the buttons are
  read by rules (no LLM); "all except the one by X" and "the Coldplay one" use one LLM call.
  Don't use Metallica in an "except" test: the catalog has only one Metallica track.
- **R8 length:** the LLM estimates the minutes from the description; songs = minutes × 60 / 239.7 s
  (the catalog's mean song length), kept between 8 and 25.
- Songs **not** in the catalog (handy to show R2's "only catalog songs"): "Always" by Bon Jovi,
  "Money, Money, Money" by ABBA (no ABBA at all), "We Believe" by Good Charlotte, "Goodbye" by Chris
  Young. "Bohemian Rhapsody" exists only as an a cappella mix, so it is added under that name.

---

## 4. Command-line checks (no browser)

```bash
python -m musiccrs.checks.check_handlers   # T6-T8, T10, T12: resolver, add/remove/show/clear, R4, help, 8 questions (no key, ~1 s)
python -m musiccrs.checks.check_nlu        # T3: 37/37 sentences, ms per parse (needs the key)
python -m musiccrs.checks.check_recs       # T4: rock / jazz / pop playlists, 5 new songs each (~50 s load)
python -m musiccrs.checks.check_select     # T11: 16 rule cases; 6 LLM cases with the key
python -m musiccrs.checks.check_playlist   # T9: length rule + 4 descriptions (~50 s load; lengths differ only with the key)
python -m musiccrs.checks.check_latency    # T13: a 25-turn conversation, intent + playlist length + < 3 s per turn (needs the key)
```

Each ends with `OK ...` and exits with code 1 if a case fails.

### Slash commands

| Command | What it does |
| --- | --- |
| `/add [artist]: [track]` | Add a song. The artist is optional: `/add hotel california` |
| `/del [artist]: [track]` | Remove a song by name |
| `/remove <track_id>` | Remove a song by ID (the panel's × button) |
| `/select <choice>` | Choose from the last options: `/select 2` (the option buttons) |
| `/list` | Show the playlist |
| `/clear` | Empty the playlist |
| `/recommend` | 5 songs related to the playlist |
| `/help` | What the agent can do |
| `/quit` | End the conversation |

Slash commands skip the LLM. Everything else goes through one LLM call (the intent parser).

---

## 5. Under the hood

### The `PLAYLIST` and `OPTIONS` acts

To see them: DevTools (`F12`) → **Network** → filter **WS** → reload the page → click the socket →
**Messages**. Each agent reply is a frame like:

```text
42["message",{"sender":"MusicCRS","message":{"text":"Added ...","dialogue_acts":[
  {"intent":"PLAYLIST","annotations":[
    {"slot":"track","value":"{\"id\": \"e9383e0c-...\", \"name\": \"Smells Like Teen Spirit\", \"artist\": \"Nirvana\", \"duration_ms\": 301920}"}]}]}}]
```

- `PLAYLIST`: one `track` annotation per song, in playlist order; `value` is JSON text. An empty
  playlist gives `"annotations": []`. Sent once, by the agent, whenever the playlist changed or on SHOW.
- `OPTIONS`: one `option` annotation per choice, `{"slot":"option","value":"1. Come As You Are — Nirvana"}`.
  The chat shows one button per option; a click sends `/select <n>`.

### One playlist per tab

Each tab (socket connection) gets its own agent, so a second tab starts with an empty playlist.
Reloading a tab also starts a new, empty playlist.

### Problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| `'musiccrs' is not a package` | started with `python musiccrs/musiccrs.py` | `python -m musiccrs.musiccrs` from the repo root |
| `cache/musiccrs.db not found` | the DB was never built | `python -m musiccrs.data.build_db` |
| `RuntimeError: Services are not loaded` | `MusicCRS` was created without starting `__main__` | start the agent with `python -m musiccrs.musiccrs` |
| The chat shows no welcome message | backend not running (or still loading the retriever), or started after the page | wait for `Running on ...`, then reload the page |
| Every free-text message gets "Sorry, I did not understand that" | `LLM_API_KEY` not set in that terminal | `conda activate musiccrs` (section 1), restart the backend |
| `Address already in use` / port 5000 busy | an old backend is still running | close it (`Ctrl+C` in its terminal) and start again |
| `ModuleNotFoundError: dialoguekit` | wrong Python | `conda activate musiccrs` |
| `npm test` fails with "Requires Babel ^7.22.0" | a Babel version clash inside `node_modules` (starter kit, not our code) | not needed for the demo; `npx tsc --noEmit` type-checks the UI |

- Every finished chat is saved to `dialogue_export/` by DialogueKit. The folder is gitignored.
- The course's user simulator (`simulation/`) is from the 2025 course and needs an upload token we
  did not get, so it is not used; `check_latency` replays its hard cases instead.
