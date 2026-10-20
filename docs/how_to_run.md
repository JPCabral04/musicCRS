# How to run and test MusicCRS

Steps to start the agent and the chat UI, and to check in the browser that the agent works.
State: after T9 (Oct 20). Done: slash commands (T2), natural language (T3), recommendations (T4,
R6), choosing among recommendations (T11, R7), playlist from a description (T9, R8). Not yet: the
playlist panel (T5), loose names and choosing among same-name songs (T6–T8), questions (T10), help (T12).

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

- The key is saved inside the env folder (`envs/musiccrs/conda-meta/state`), not in the repo.
- `conda env config vars list` and `conda env export` print it: never commit an exported env file.
- To remove it: `conda env config vars unset LLM_API_KEY`, then reactivate.
- For one terminal only: `export LLM_API_KEY="sk-..."` (Git Bash) or `$env:LLM_API_KEY = "sk-..."` (PowerShell).
- Without the key, the backend prints `LLM_API_KEY is not set: the agent runs with slash commands only.`
- The simulator needs the key in `simulation/config.py` **only on your machine, never commit it**.

---

## 2. Start (two terminals)

**Terminal 1 — backend (agent):**

```bash
conda activate musiccrs
python -m musiccrs.musiccrs
```

It prints `Loading the retriever...`, then `Retriever loaded in ~50 s` (the Part 1 retriever, loaded
once), then `Running on http://127.0.0.1:5000`. Wait for that last line. Leave it open.

> Use `python -m musiccrs.musiccrs`, not `python musiccrs/musiccrs.py`. The second one fails with
> `'musiccrs' is not a package`.

**Terminal 2 — frontend (chat UI):**

```bash
cd frontend
npm start
```

The browser opens http://localhost:3000. The welcome message should say
*"Hello, I'm MusicCRS. I can build a playlist with you and recommend songs. Type /help to see what I can do."*

Stop either one with `Ctrl+C`.

---

## 3. Test in the browser

Type the messages of each part in order, in **one tab** (each tab has its own playlist). Each row
shows the expected reply and whether a `PLAYLIST` act is sent (see section 4 for how to see it).
The replies below come from a full run on Oct 19 (same messages over socket.io, the browser's channel).

### 3.1 Slash commands (T2, no LLM)

| # | Type | Expected reply | `PLAYLIST` act |
| --- | --- | --- | --- |
| 1 | `/list` | Your playlist is empty. | yes, empty |
| 2 | `/add nirvana: smells like teen spirit` | Added Smells Like Teen Spirit by Nirvana to your playlist. | yes, 1 track |
| 3 | `/add hotel california` | Added Hotel California - 2013 Remaster by Eagles to your playlist. | yes, 2 tracks |
| 4 | `/add Nirvana: Smells Like Teen Spirit!` | ... is already in your playlist. | no |
| 5 | `/list` | Numbered list with the 2 songs | yes, 2 tracks |
| 6 | `/add queen: hotel california` | Sorry, I could not find 'hotel california' by 'queen' in the catalog. | no |
| 7 | `/del nirvana: smells like teen spirit` | Removed Smells Like Teen Spirit by Nirvana from your playlist. | yes, 1 track |
| 8 | `/clear` | Cleared your playlist (1 songs removed). | yes, empty |
| 9 | `/recommend` | Your playlist is empty, so I have nothing to base recommendations on. Add a few songs first, ... | no |

**The T2 "done when"** is rows 2, 5, 7 and 8: each must work and send a `PLAYLIST` act.

### 3.2 Natural language (T3, needs the key)

Each message costs one LLM call: replies take about 0.3–0.8 s.

| # | Type | Expected reply | `PLAYLIST` act |
| --- | --- | --- | --- |
| 10 | `hello` | Sorry, I cannot do that yet. You can use: ... (GREETING has no handler yet) | no |
| 11 | `put smells like teen spirit by nirvana on my list` | Added Smells Like Teen Spirit by Nirvana to your playlist. | yes, 1 track |
| 12 | `add its my life by bon jovi` | Added It's My Life by Bon Jovi to your playlist. | yes, 2 tracks |
| 13 | `what is on my playlist?` | Numbered list with the 2 songs | yes, 2 tracks |
| 14 | `what is the weather in Oslo?` | Sorry, I did not understand that. You can use: ... | no |
| 15 | `the first one` | Sorry, I did not understand that. ... (nothing to choose from yet) | no |

- `add hotel california by the eagles` is **not found**: the catalog artist is "Eagles", and names
  must still match exactly ("the" is not ignored). Loose names come with the track resolver (T6/T7).

### 3.3 Recommend (T4, R6) and choose (T11, R7)

Continue in the same tab, with the 2 songs of rows 11–12 in the playlist. The recommended songs
depend on the playlist, so yours may differ; pick the artist to exclude from the list you get.

| # | Type | Expected reply | `PLAYLIST` act |
| --- | --- | --- | --- |
| 16 | `recommend me something` | 5 numbered songs (Oct 19: Come As You Are, Bad Medicine, Have A Nice Day, Misunderstood, Lithium — Nirvana and Bon Jovi) + "Say 'add the first two', ..." | no (an `OPTIONS` act instead) |
| 17 | `add all except the ones by Bon Jovi` | Added to your playlist: Come As You Are, Lithium (the 2 non-Bon Jovi songs) | yes, 4 tracks |
| 18 | `add the first one` | Sorry, I did not understand that. ... (the options were used up) | no |
| 19 | `recommend me something` | 5 new songs, none already in the playlist | no |
| 20 | `the first two` | Added to your playlist: the first two of row 19 | yes, 6 tracks |
| 21 | `recommend me some songs by other artists` | "Something different from the artists in your playlist:" 5 songs, no Nirvana or Bon Jovi (Oct 19: Red Hot Chili Peppers ×4, Foo Fighters) | no |
| 22 | `none, thanks` | OK, I did not add any of them. | no |
| 23 | `recommend me something` | 5 new songs | no |
| 24 | `just the last one` | Added to your playlist: the 5th song of row 23 | yes, 7 tracks |
| 25 | `/quit` | It was nice talking to you. Bye | no |

- **The T4 "done when"**: rows 16, 19, 21 give 5 songs each, none already in the playlist.
- **The T11 "done when"**: rows 17 (exclusion), 20 (ordinal subset), 22 (none) and 24 all work, and
  row 18 shows the options are cleared after use. "all except ..." costs a second LLM call (≈ 1 s in total).
- Choices other than all / none / ordinals ("the Coldplay one", "everything but Toxic") go to the LLM.
- Don't use Metallica in an "except" test: the catalog has only one Metallica track.

### 3.4 Playlist from a description (T9, R8)

Open a **new tab** (empty playlist). The songs come from the LLM's query, so yours may differ.

| # | Type | Expected reply | `PLAYLIST` act |
| --- | --- | --- | --- |
| 26 | `make me a playlist of sad love songs` | "Here is a playlist for 'sad love songs': 11 songs, about 41 minutes (I aimed for about 45 minutes)." + the songs (Oct 20: Frank Ocean, Neil Young, Lana Del Rey, Khalid, ...) | yes, 11 tracks |
| 27 | `now make me one with energetic music for a gym session` | 15 songs, about 62 minutes (aimed 60) + "It replaced your previous playlist of 11 songs." | yes, 15 tracks |
| 28 | `recommend me something` | 5 songs based on the new playlist | no (`OPTIONS`) |
| 29 | `add the first one` | Added to your playlist: the first song of row 28 | yes, 16 tracks |
| 30 | `create a playlist for a dinner party` | 23 songs, about 97 minutes (aimed 90) + "It replaced your previous playlist of 16 songs." | yes, 23 tracks |

- **The T9 "done when"**: rows 26, 27 and 30 give playlists of different lengths (11, 15, 23), chosen from
  the description without asking. Each costs 2 LLM calls (parser + plan): 1–3 s per turn, the first the slowest.
- The new playlist always **replaces** the old one, and the reply says so.
- Without the key, R8 cannot be reached (it needs the parser); the handler itself falls back to the
  description as the query and 45 minutes (11 songs).
- Phrase it as "make me a playlist of / for ...": "now give me sad love songs instead" is parsed as RECOMMEND.

### 3.5 Command-line checks (no browser)

```bash
python -m musiccrs.checks.check_nlu        # T3: 37/37 sentences, ms per parse (needs the key)
python -m musiccrs.checks.check_recs       # T4: rock / jazz / pop playlists, 5 new songs each (~50 s load)
python -m musiccrs.checks.check_select     # T11: 16 rule cases; 6 LLM cases with the key
python -m musiccrs.checks.check_playlist   # T9: length rule + 4 descriptions (~50 s load; lengths differ only with the key)
```

Each ends with `OK ...` and exits with code 1 if a case fails.

### Commands available now

| Command | What it does |
| --- | --- |
| `/add [artist]: [track]` | Add a song. The artist is optional: `/add hotel california` |
| `/del [artist]: [track]` | Remove a song by name |
| `/remove <track_id>` | Remove a song by ID (for the playlist panel buttons) |
| `/list` | Show the playlist |
| `/clear` | Empty the playlist |
| `/recommend` | 5 songs related to the playlist |
| `/quit` | End the conversation |

- `/help` is parsed, but HELP has no handler until T12 ("Sorry, I cannot do that yet").
- Names match loosely: case, punctuation and accents are ignored (`IT'S MY LIFE!` = `its my life`).
- Only **exact** names work for now (`/add bohemian rhapsody by queen` and `the eagles` are not found). Partial names and typos come with the track resolver (T6/T7).
- If several songs share a name, the most popular one is added (choosing comes in T8).

---

## 4. See the `PLAYLIST` act

The chat window does not show dialogue acts (the playlist panel of T5 will). To see them:

1. Open DevTools (`F12`) → **Network** tab → filter **WS**.
2. Reload the page (`F5`) so the socket connection shows up, then click it.
3. Open the **Messages** tab. Each agent reply is a frame like:

```text
42["message",{"sender":"MusicCRS","message":{"text":"Added ...","dialogue_acts":[
  {"intent":"PLAYLIST","annotations":[
    {"slot":"track","value":"{\"id\": \"e9383e0c-...\", \"name\": \"Smells Like Teen Spirit\", \"artist\": \"Nirvana\", \"duration_ms\": 301920}"}]}]}}]
```

- One `track` annotation per song, in playlist order. `value` is JSON text: read it with `JSON.parse`.
- An empty playlist gives `"annotations": []`.
- A recommendation sends an `OPTIONS` act instead, one `option` annotation per song:
  `{"slot":"option","value":"1. Come As You Are — Nirvana"}`. The chat does not show these as
  buttons yet.

---

## 5. One playlist per tab

Open a second tab at http://localhost:3000 and type `/list`: it says the playlist is empty, even if
the first tab has songs. Each tab (socket connection) gets its own agent. Reloading a tab also
starts a new, empty playlist (and forgets any pending recommendations).

---

## 6. Problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| `'musiccrs' is not a package` | started with `python musiccrs/musiccrs.py` | `python -m musiccrs.musiccrs` from the repo root |
| `cache/musiccrs.db not found` | the DB was never built | `python -m musiccrs.data.build_db` |
| `RuntimeError: Services are not loaded` | `MusicCRS` was created without starting `__main__` | start the agent with `python -m musiccrs.musiccrs` |
| The chat shows no welcome message | backend not running (or still loading the retriever), or started after the page | wait for `Running on ...`, then reload the page |
| Every free-text message gets "Sorry, I did not understand that" | `LLM_API_KEY` not set (the backend printed a warning at startup) | set the key (section 1), restart the backend |
| `Address already in use` / port 5000 busy | an old backend is still running | close it (`Ctrl+C` in its terminal) and start again |
| `ModuleNotFoundError: dialoguekit` | wrong Python | `conda activate musiccrs` |

- Every finished chat is saved to `dialogue_export/` by DialogueKit. The folder is gitignored; delete it whenever you like.
