# How to run and test MusicCRS

Steps to start the agent and the chat UI, and to check in the browser that the agent works.
State: after T2 (slash commands only). Natural language (T3) and recommendations (T4) come later.

All commands are for **Git Bash**, from the **repo root**.

---

## 1. One-time setup

```bash
conda activate musiccrs                # Python 3.11 env
pip install -r requirements.txt
python -m musiccrs.data.build_db            # builds cache/musiccrs.db (~10 s), ends with "OK 1" ... "OK 6"
cd frontend && npm install && cd ..    # needs Node.js (tested with v24); only the first time
```

- `build_db` downloads the catalog from Hugging Face the first time (internet needed once).
- Run `build_db` again only if `musiccrs/data/db.py` or `musiccrs/data/build_db.py` changes.
- **LLM key (needed from T3 on; slash commands work without it).** The course LLM is Gemma 4 31B on
  Open WebUI. Register at <https://openwebui.ux.uis.no> with your student number, then go to
  Settings -> Account and generate an API key. The agent reads it from the `LLM_API_KEY`
  environment variable, set in the backend terminal before starting it:
  `export LLM_API_KEY="sk-..."` (Git Bash) or `$env:LLM_API_KEY = "sk-..."` (PowerShell).
  Without it, the agent prints a warning and runs with slash commands only. The simulator still
  needs the key in `simulation/config.py` **only on your machine, never commit it**.

---

## 2. Start (two terminals)

**Terminal 1 — backend (agent):**

```bash
conda activate musiccrs
python -m musiccrs.musiccrs
```

Wait for `Running on http://127.0.0.1:5000`. Leave it open.

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

Type these messages in order. Each line shows the expected reply and whether a `PLAYLIST` act is
sent (see section 4 for how to see it).

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
| 9 | `/recommend` | Sorry, I cannot do that yet. You can use: ... | no |
| 10 | `hello` | Sorry, I did not understand that. You can use: ... | no |
| 11 | `/quit` | It was nice talking to you. Bye | no |

**The T2 "done when"** is rows 2, 5, 7 and 8: each must work and send a `PLAYLIST` act.

### Commands available now

| Command | What it does |
| --- | --- |
| `/add [artist]: [track]` | Add a song. The artist is optional: `/add hotel california` |
| `/del [artist]: [track]` | Remove a song by name |
| `/remove <track_id>` | Remove a song by ID (for the playlist panel buttons) |
| `/list` | Show the playlist |
| `/clear` | Empty the playlist |
| `/quit` | End the conversation |

- Names match loosely: case, punctuation and accents are ignored (`IT'S MY LIFE!` = `its my life`).
- Only **exact** names work for now (`/add bohemian rhapsody by queen` is not found). Partial names and typos come with the track resolver (T6/T7).
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

---

## 5. One playlist per tab

Open a second tab at http://localhost:3000 and type `/list`: it says the playlist is empty, even if
the first tab has songs. Each tab (socket connection) gets its own agent. Reloading a tab also
starts a new, empty playlist.

---

## 6. Problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| `'musiccrs' is not a package` | started with `python musiccrs/musiccrs.py` | `python -m musiccrs.musiccrs` from the repo root |
| `cache/musiccrs.db not found` | the DB was never built | `python -m musiccrs.data.build_db` |
| `RuntimeError: Services are not loaded` | `MusicCRS` was created without starting `__main__` | start the agent with `python -m musiccrs.musiccrs` |
| The chat shows no welcome message | backend not running, or started after the page | start terminal 1, then reload the page |
| `Address already in use` / port 5000 busy | an old backend is still running | close it (`Ctrl+C` in its terminal) and start again |
| `ModuleNotFoundError: dialoguekit` | wrong Python | `conda activate musiccrs` |

- Every finished chat is saved to `dialogue_export/` by DialogueKit. The folder is gitignored; delete it whenever you like.
