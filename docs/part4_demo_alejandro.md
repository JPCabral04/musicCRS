# MusicCRS Part 4 demo: Alejandro's tasks (T2, T4, T6, T8, T10)

Alejandro's Part 4 tasks only: T2 / T4 covers and previews, T6 sounds like, T8 lyrics search, T10 audio evaluation. The demo with every feature, in order, is `part4_demo.md`; this file is the same text cut down to these tasks.

How to show each Part 4 feature live: the lines to type, the reply that comes back, and where
it happens in the code. Each feature has a slash command (rules, no LLM) and a
natural-language form (one LLM call, the parser); both end in the same intent and the same
handler. Setup, the LLM key and the Part 2 demo are in `part2_demo.md`.

All commands are for **Git Bash**, from the **repo root**. Every reply below was checked on
Nov 2 by running the slash commands from a fresh conversation.

---

## 1. Start the system

```bash
conda activate musiccrs
python -m musiccrs.musiccrs            # backend on :5000; wait for the startup messages
cd frontend && npm start               # frontend on :3000 (second terminal)
```

Open <http://localhost:3000>. Slash commands work without the LLM key; natural language needs
`LLM_API_KEY` (see `part2_demo.md` §1).

After the retriever, the backend loads the track vectors and prints:

```
Track vectors loaded in 0.4 s:
  metadata: 47071 x 1024, 46579 tracks with a vector
  audio: 47071 x 512, 46579 tracks with a vector
  lyrics: 47071 x 1024, 46257 tracks with a vector
```

Lyrics has fewer: 322 placeholder vectors (instrumentals) are left out (T8). The first start
downloads the audio and lyrics vectors (~290 MB into `cache/embeddings/`).

---

## 2. How to run a demo

**One conversation per section.** A song shown once is never shown again in the same
conversation, so the lists below only come back in a fresh conversation. Reload the page (F5)
before each section: the browser opens a new connection, and the backend creates a new agent
with an empty state (the database and the vectors stay loaded).

**The rock playlist.** Most sections start from the same three songs:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/add nirvana: smells like teen spirit` | "add Smells Like Teen Spirit by Nirvana" | Added Smells Like Teen Spirit by Nirvana to your playlist. |
| `/add eagles: hotel california` | "add Hotel California by Eagles" | Two versions: **click the first one** (2013 Remaster), or `/select 1` / "the first one". |
| `/add bon jovi: its my life` | "add It's My Life by Bon Jovi" | Added It's My Life by Bon Jovi to your playlist. |

**Both forms.** Run a section once with the slash commands (the lists match this file
exactly), then reload and run it again in words: the parser gives the same slots, so the same
lists come back. The backend terminal prints one line per turn with the intent, the ms and the
LLM calls, for example `[CRITIQUE] 467 ms, 1 LLM call` in words and `0 LLM calls` as a slash
command.

**The path every turn takes** (the same for every feature; each section names its handler):

1. The frontend sends the text over the socket.
2. `MusicCRS.receive_utterance` ([musiccrs.py:194](../musiccrs/musiccrs.py#L194)) starts the clock and the LLM-call count.
3. `parse` ([parser.py:337](../musiccrs/nlu/parser.py#L337)): a slash command goes to `parse_command` ([parser.py:108](../musiccrs/nlu/parser.py#L108)) by rules; other text goes to the LLM with the prompt, and the answer is checked by `clean_slot_value` ([parser.py:240](../musiccrs/nlu/parser.py#L240)).
4. The result is a `ParsedIntent(name, slots)`, for example `ParsedIntent("CRITIQUE", {"like": "2"})`.
5. `HANDLERS[parsed.name]` ([musiccrs.py:52](../musiccrs/musiccrs.py#L52)) picks the handler; it reads and changes `state` and returns a `Reply(text, dialogue_acts)`.
6. `receive_utterance` adds a `PLAYLIST` act if the playlist changed, and a `MEDIA` act (covers, previews) if the reply has `OPTIONS` buttons, then sends it all back.
7. The frontend shows the text, the option buttons, the cards and the playlist panel.

---

## 3. Features

### Covers and previews (T2, T4): album art and 30-second clips

**What it shows.** Every song in the playlist panel and in every list of options in the chat
(choices, recommendations, critiques, sounds like, lyrics) shows its album cover and a play
button. They come from the Deezer search API (no key), looked up one song after the other and
kept in memory by track ID. A new list of 5 costs about 1 s; the same songs again cost a few
ms. If Deezer is slow, lookups stop after 2 s and the remaining songs get no card in that
reply (the reply stays within 3-5 s; they are looked up again next time).

| Do | Expected |
| --- | --- |
| `/add nirvana: smells like teen spirit` | The panel shows the song with its Nevermind cover and a play button. |
| `/add eagles: hotel california` | The choice buttons, plus a card per version with cover and preview. |
| Play one preview, then another | The first one stops (one preview at a time in the panel). |
| `/recommend` | The 5 songs as buttons, and below the text a card per song (cover, name, artist, player). |

**In the code:** `get_media` ([media.py:49](../musiccrs/data/media.py#L49)) asks `search_deezer` once per track and caches the answer; `media_act` ([media.py:78](../musiccrs/data/media.py#L78)) is added by `receive_utterance` when the reply has `OPTIONS` (step 6 in §2).

### Sounds like (T6, F2.1): "songs that sound like Smells Like Teen Spirit"

**What it shows.** The named song is the seed. Its **audio** vector (CLAP, made from the
sound) is compared with every other track's, and the 5 closest never shown before come back,
leaving out other versions of the seed. A new list starts, so critiques work on it. No LLM
besides the parser.

Reload (the playlist may stay empty), then:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/sounds nirvana: smells like teen spirit` | "songs that sound like Smells Like Teen Spirit" | **Songs that sound like Smells Like Teen Spirit by Nirvana:** I Stand Alone (Godsmack), Stay Away (Nirvana), One Weak (Deftones), In Bloom - Nevermind Version (Nirvana), Another Brick in the Wall, Pt. 1, 2, 3 (Korn). |
| `/like 3` | "more like the third one" | **More like One Weak by Deftones:** Heroin Girl (Everclear), Stress (Godsmack), Victims (Lacuna Coil), P.S. New York Is Burning (Jawbreaker), Gonna Be A Blackout Tonight (Dropkick Murphys). The seed never comes back. |
| `/sounds xqzvwk` | — | I could not find 'xqzvwk' in the catalog. |

**In the code:** `handle_sounds_like` ([similar.py:27](../musiccrs/handlers/similar.py#L27)) → the resolver finds the seed → `vectors.vector("audio", seed_id)` → `nearest("audio", …)` skipping `state.shown` and the seed's versions → `show_tracks`, which starts a new critique session.

Check: `python -m musiccrs.checks.check_similar` (§4).

### Lyrics search (T8, F2.2): "songs about leaving home"

**What it shows.** The theme is encoded by the same Qwen3 model as the lyrics vectors, and
the 5 tracks whose lyrics vectors are closest come back. Placeholder lyrics vectors (322
instrumentals sharing one vector) are left out. A new list starts. No LLM besides the parser;
about 140 ms.

Reload, then:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/about leaving home` | "songs about leaving home" | **Songs whose lyrics are about leaving home:** Leaving Home (Jebediah), Can We Go Wrong (Hesta Prynn), In The Wild (Alpine), Mickey Mouse (Wavves), Stay Home (American Football). |
| `/about heartbreak` | "songs about heartbreak" | All Fucked Up (The Amity Affliction), Bringin' On The Heartbreak (Mariah Carey), Break My Heart (Hey Violet), This Is How A Heart Breaks (Rob Thomas), Heartbreak On The 101 (Band of Horses). |
| `/about partying all night` | "songs about partying all night" | Party All Night (Quiet Riot), Party All the Time (Eddie Murphy), Party In Your Bedroom (Cash Cash), No Sleep (Wiz Khalifa), … |

**In the code:** `handle_lyrics_search` ([similar.py:101](../musiccrs/handlers/similar.py#L101)) → the dense scorer's model turns the theme into a vector → `nearest("lyrics", …)` (placeholder rows are not usable) → `show_tracks`.

Check: `python -m musiccrs.checks.check_similar` and `check_lyrics` (§4).

---

## 4. Command-line checks

```bash
python -m musiccrs.data.media           # T2: Deezer cover and preview of Smells Like Teen Spirit (network)
python -m musiccrs.checks.check_similar  # T6 + T8: 27 checks of sounds like and lyrics search (no key, ~1 min)
python -m musiccrs.checks.check_lyrics   # T8: missing and placeholder lyrics vectors (~10 s)
python -m musiccrs.checks.eval_audio     # T10 F5b: tags shared with 1,000 seeds, audio vs metadata vs random (~25 s)
```

Expected output (Oct 29):

- `musiccrs.data.media` (Oct 30): `Smells Like Teen Spirit by Nirvana (288 ms)`, then a
  `Cover:` URL (`cdn-images.dzcdn.net/...jpg`) and a `Preview:` URL (`...mp3`).
- `check_similar` (Oct 30): the Numb list, the three theme lists above, `ok` lines and
  `OK: every check passed.`
- `check_lyrics` (Oct 30):
  ```
  Without a lyrics vector:    492 (1.05%)
  Placeholder rows:           322 (0.68%)  (a vector shared by more than 10 tracks)
  Usable for lyrics search: 46257 (98.27%)
  ```
  then the biggest placeholder groups (30 tracks, e.g. Nefeli by Ludovico Einaudi; 29, e.g.
  The Spiders by John Williams; ...).
- `eval_audio` (Oct 30, seed 42): mean tags shared with the seed, the seed's artist left out:
  ```
  audio    3.61
  metadata 2.311
  random   1.491
  ```
  Songs that sound alike share more tags than songs with similar metadata text, and both
  far more than random songs.
