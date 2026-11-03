# MusicCRS Part 4: how to test the advanced features

How to show each Part 4 feature live: the lines to type, the reply that comes back, and where
it happens in the code. Each feature has a slash command (rules, no LLM) and a
natural-language form (one LLM call, the parser); both end in the same intent and the same
handler. Setup, the LLM key and the Part 2 demo are in `part2_demo.md`. The same text cut down to
one person's tasks: `part4_demo_jp.md` (T1, T3, T5, T7, T9) and `part4_demo_alejandro.md`
(T2, T4, T6, T8, T10).

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

### Base (T1): the Part 4 commands and the shown-tracks memory

**What it shows.** T1 is the base the other features call: four new intents in the parser,
one shared nearest-neighbour search over the track vectors, and `show_tracks`, the one place
that remembers the list on screen, the songs already shown and why each was shown.

Reload. **Before any recommendation** (empty state):

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/like 2` | "more like the second one" | Ask me for recommendations first, then tell me what to change, for example 'more like the second one', 'older' or 'more popular'. |
| `/why 2` | "why the second one?" | There is no list of recommended songs to explain yet. Ask me for recommendations first. |
| `/recommend` | "recommend me some songs" | Your playlist is empty, so I have nothing to base recommendations on. Add a few songs first, … |

Then build the rock playlist (§2) and:

| Slash command | Natural language | Backend line | Reply |
| --- | --- | --- | --- |
| `/recommend` | "recommend me something" | `[RECOMMEND]` | Based on your playlist, you might like: Come As You Are (Nirvana), Bad Medicine (Bon Jovi), Yellow (Coldplay), Have A Nice Day (Bon Jovi), Sex on Fire (Kings of Leon). |
| `/like 2` | "more like the second one" | `[CRITIQUE]` | More like **Bad Medicine by Bon Jovi**: 5 new songs (T3). |
| `/critique tag more hard rock` | "more hard rock" | `[CRITIQUE]` | 5 songs tagged hard rock (T5). |
| `/sounds nirvana: smells like teen spirit` | "songs that sound like Smells Like Teen Spirit" | `[SOUNDS_LIKE]` | Songs that sound like … (T6). |
| `/about leaving home` | "songs about leaving home" | `[LYRICS_SEARCH]` | Songs whose lyrics are about leaving home (T8). |
| `/why 2` | "why the second one?" | `[EXPLAIN]` | Why I showed you … (T7), about #2 of the **last** list (the lyrics list). |

"Songs **like** Numb" is still a Part 2 recommendation (R6); only "songs that **sound** like
Numb" uses the audio vectors.

**In the code:**

- Startup: `create_services` loads the vectors once ([musiccrs.py:99-110](../musiccrs/musiccrs.py#L99-L110)). The metadata matrix is the dense scorer's own (no copy); audio and lyrics come from `cache/embeddings/`. Stored as `Services.vectors` ([state.py:64](../musiccrs/state.py#L64)).
- The one search: `TrackVectors.nearest(space, query_vector, k, exclude_ids)` ([vectors.py:121](../musiccrs/data/vectors.py#L121)): one matrix product scores every track (rows have length 1, so it is a cosine), `argsort` ranks them, a loop keeps the first k that have a vector and are not excluded.
- New slash commands: `/like`, `/dislike`, `/critique`, `/sounds`, `/about`, `/why` in `parse_command` ([parser.py:173-209](../musiccrs/nlu/parser.py#L173-L209)); the four new intents in `HANDLERS` ([musiccrs.py:65-68](../musiccrs/musiccrs.py#L65-L68)).
- The memory: `last_shown`, `shown`, `signals`, `critique` in `DialogueState` ([state.py:19-35](../musiccrs/state.py#L19-L35)). R6 calls `show_tracks` ([recs.py:294](../musiccrs/handlers/recs.py#L294)); `show_tracks` ([shown.py:42](../musiccrs/handlers/shown.py#L42)) saves the list in `pending_options` and `last_shown`, adds it to `shown` and stores the signals; R8 calls only `remember_tracks` ([recs.py:406](../musiccrs/handlers/recs.py#L406)).
- "the second one" or "bon jovi" → a track ID: `pick_shown` ([shown.py:67](../musiccrs/handlers/shown.py#L67)) reads `last_shown`, which "add the first two" does not empty.

Check: `python -m musiccrs.checks.check_base` (§4).

### Example critiques (T3, F1.1): "more like the second one"

**What it shows.** The list on screen is one vector (the mean of its songs' **audio**
vectors). "More like #2" pulls it toward #2, "less like #4" pushes it away from #4 (Rocchio),
and the 5 closest songs never shown before come back. Critiques add up until a new list
starts (a new recommendation, "sounds like" or lyrics search). No LLM besides the parser;
about 15 ms.

Reload, build the rock playlist (§2), then:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/recommend` | "recommend me something" | Come As You Are (Nirvana), **Bad Medicine (Bon Jovi)**, Yellow (Coldplay), Have A Nice Day (Bon Jovi), Sex on Fire (Kings of Leon). |
| `/like 2` | "more like the second one" | More like **Bad Medicine by Bon Jovi**: Glorified G (Pearl Jam), Way Cool Jr. (Ratt), One Wild Night (Bon Jovi), Nobody Listens (Bad Religion), Say It Isn't So (Bon Jovi). |
| `/dislike 4` | "less like the fourth one" | More like **Bad Medicine by Bon Jovi**, less like **Nobody Listens by Bad Religion**: Wild Is The Wind (Bon Jovi), You Are The One (Slaughter), Thunderstruck - Live (AC/DC), Mama, I'm Coming Home (Ozzy Osbourne), That's Not Enough (Slaughter). The punk song is gone. |
| `/dislike ratt` | "less like the one by Ratt" | I could not find 'ratt' in the last list. … A name works only for a song **on screen now**; Ratt was in the previous list. |
| `/like 7` | "more like the seventh one" | I could not find '7' in the last list. Use its number … or its artist. (Nothing changes.) |
| `/select 1` | "add the first one" | Added to your playlist: Wild Is The Wind by Bon Jovi. Every critique list can be added from. |

**In the code:** `handle_critique` ([critique.py:251](../musiccrs/handlers/critique.py#L251)) → `pick_shown` turns "2" into Bad Medicine's ID and adds it to `state.critique["liked"]` → `critique_query` ([critique.py:58](../musiccrs/handlers/critique.py#L58)): mean audio vector of the base list, plus liked, minus disliked → `critique_ranking` ([critique.py:230](../musiccrs/handlers/critique.py#L230)) calls `nearest("audio", query, …, state.shown)` → `show_tracks` with `new_list=False`, so the critique session goes on.

Check: `python -m musiccrs.checks.check_critique` (§4).

### Attribute critiques (T5, F1.2): "older", "more popular", "more acoustic"

**What it shows.** Each critique becomes a filter with a fixed limit, taken from the list
**on screen** when it is said: "older" keeps songs released before the median year of that
list, "more popular" songs above its median popularity, "more acoustic" songs tagged
*acoustic*, "no rap" songs not tagged *rap*. Filters add up (with each other and with likes /
dislikes) until a new list starts. The songs are the closest ones to the critique vector of
T3 that pass every filter (searched among the 1,000 closest). No LLM besides the parser;
about 25 ms.

Reload, build the rock playlist (§2), `/recommend`, then:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/critique year less` | "something older" | **Older than 2000:** Glorified G (Pearl Jam), God Smack (Alice In Chains), Down In A Hole (Alice In Chains), Slide (Goo Goo Dolls), All Eyes On Me (Goo Goo Dolls). |
| `/critique popularity more` | "more popular ones" | **Older than 2000, popularity above 54:** Learn to Fly (Foo Fighters), Black Balloon (Goo Goo Dolls), Only In Dreams (Weezer), I Just Want You (Ozzy Osbourne), You Get What You Give (New Radicals). Still older than 2000: the filters add up. |
| `/critique tag more polka` | "more polka" | Sorry, no new songs near this list are older than 2000 and popularity above 54 and tagged polka. The list stays as it was: … (the filter is dropped). |
| `/critique year less` | "even older" | **Older than 2000, popularity above 54, older than 1998:** the new limit comes from the list on screen: Mama, I'm Coming Home and Hellraiser (Ozzy Osbourne), Pretty Noose (Soundgarden), De Música Ligera (Soda Stereo), Corduroy (Pearl Jam). |
| `/critique colour more` | — | I can change the songs by year ('older', 'newer'), by popularity ('more popular', 'less known') or by style ('more acoustic', 'no rap'). |

A second run (reload, rock playlist, `/recommend`), for style tags:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/critique tag more hard rock` | "more hard rock" | **Tagged hard rock:** Defy You (The Offspring), Hero (Josey Scott), God Smack (Alice In Chains), Down In A Hole (Alice In Chains), Broken Glass (Three Days Grace). |
| `/critique tag less rap` | "no rap" | **Tagged hard rock, not tagged rap:** Dani California (Red Hot Chili Peppers), Slide (Goo Goo Dolls), All Eyes On Me (Goo Goo Dolls), Learn to Fly (Foo Fighters), Black Balloon (Goo Goo Dolls). |

In words only (needs the key; list from Oct 30), after a fresh `/recommend`: "like number 2 but older" does both at once:
**More like Bad Medicine by Bon Jovi, older than 2000** (Glorified G, Way Cool Jr., Nobody
Listens, Wild Is The Wind, Mama, I'm Coming Home, all from 1988–1996).

**In the code:** `handle_critique` ([critique.py:251](../musiccrs/handlers/critique.py#L251)) → `make_filter` ([critique.py:130](../musiccrs/handlers/critique.py#L130)) computes the limit from the songs on screen (median year or popularity, or the tag) → appended to `state.critique["filters"]` → `critique_ranking` ([critique.py:230](../musiccrs/handlers/critique.py#L230)) takes the 1,000 nearest and keeps those that pass `passes_filters` ([critique.py:199](../musiccrs/handlers/critique.py#L199)). If none pass, the new filter is removed and the list stays.

Check: `python -m musiccrs.checks.check_critique` (§4).

### Why this song? (T7, F3): "why the second one?"

**What it shows.** Up to four sentences, each built with a template from one fact: how the
song was found (stored when it was shown), which Part 1 retrievers ranked it and where
(recommendations only), the tags it shares with the songs it came from, and an artist already
in the playlist (both checked in the database). No LLM writes the reasons, so they cannot be
invented. Only songs of the last list can be asked about. About 2 ms.

Reload, build the rock playlist (§2), then:

| Slash command | Natural language | Reply |
| --- | --- | --- |
| `/recommend`, then `/why 2` | "why the second one?" | **Why I showed you Bad Medicine by Bon Jovi:** I recommended it for Smells Like Teen Spirit by Nirvana; Hotel California - 2013 Remaster by Eagles and It's My Life by Bon Jovi. It was found by matching the words of your songs (lower in its list), being by an artist of your songs (its top pick). It shares the tags *hard rock*, *jon bon jovi*, *favorite* with those songs. Its artist Bon Jovi is already in your playlist. |
| `/why come as you are` | "why did you pick Come As You Are?" | Same form, found by three retrievers: words (in its top ten), same artist (lower in its list), the listening patterns of other users (in its top ten). |
| `/like 2`, `/critique year less`, then `/why 1` | "why the first one?" | **Why I showed you Wild Is The Wind by Bon Jovi:** It came from your critique "More like Bad Medicine by Bon Jovi, older than 1996", as one of the songs closest in sound to it (audio similarity 0.91). It shares the tags *hard rock*, *melodic hard rock*, *jon bon jovi* with Bad Medicine. Its artist Bon Jovi is already in your playlist. |
| `/select 2` | "add the second one" | Added Mama, I'm Coming Home by Ozzy Osbourne: the "why" did not clear the options. |
| `/why 7` | "why the seventh one?" | I could not find '7' in the last list I showed you. Say a number from 1 to 5, or part of a title or an artist. |
| `/why` | — | Which song? For example: 'why the second one?' or '/why 2'. |
| `/sounds nirvana: smells like teen spirit`, then `/why 1` | "why the first one?" | **Why I showed you I Stand Alone by Godsmack:** It sounds close to Smells Like Teen Spirit by Nirvana (audio similarity 0.93). It shares the tags *alternative*, *rock*, *grunge* with Smells Like Teen Spirit by Nirvana. |
| `/about leaving home`, then `/why 1` | "why the first one?" | **Why I showed you Leaving Home by Jebediah:** Its lyrics are close to the theme 'leaving home' (lyrics similarity 0.55). |

**In the code:** `handle_explain` ([explain.py:213](../musiccrs/handlers/explain.py#L213)) → `pick_shown` finds the song in `last_shown` → `explain_track` ([explain.py:180](../musiccrs/handlers/explain.py#L180)) reads `state.signals[track_id]` and builds the sentences: `found_sentence` (source), `retrievers_sentence` (ranks stored by R6, [recs.py:291-293](../musiccrs/handlers/recs.py#L291-L293)), `tags_sentence` and `artist_sentence` (checked in the database).

Check: `python -m musiccrs.checks.check_explain` (§4).

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

**In the code:** `get_media` ([media.py:62](../musiccrs/data/media.py#L62)) asks `search_deezer` once per track and caches the answer for 10 minutes (Deezer preview links expire after about 15); `media_act` ([media.py:92](../musiccrs/data/media.py#L92)) is added by `receive_utterance` when the reply has `OPTIONS` (step 6 in §2).

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

### Evaluation and turn log (T9, F5a)

**What it shows.** Nothing new to type in the chat. Every turn prints its time **and its LLM
calls** in the backend terminal:

| Type in the chat | Backend terminal |
| --- | --- |
| `/recommend` | `[RECOMMEND] ... ms, 0 LLM calls` (slash command: no LLM) |
| "more like the second one" | `[CRITIQUE] ... ms, 1 LLM call` (the parser) |
| "add all except the one by Bon Jovi" | `[SELECT] ... ms, 2 LLM calls` (parser + selection) |

The ms vary; the call counts do not. The critique evaluation (`eval_critique`) and the
latency check (`check_latency`) run from the command line (§4).

**In the code:** `receive_utterance` sets `llm.call_count = 0` ([musiccrs.py:202](../musiccrs/musiccrs.py#L202)); every request to the LLM adds 1 ([llm.py:93](../musiccrs/llm.py#L93)); `print_turn_time` ([musiccrs.py:150](../musiccrs/musiccrs.py#L150)) prints the line at the end of the turn.

---

## 4. Command-line checks

```bash
python -m musiccrs.data.vectors          # T1: matrix sizes + 5 audio neighbours of Smells Like Teen Spirit (~15 s)
python -m musiccrs.checks.check_base     # T1: 68 checks of slash commands, shown tracks, pick_shown, nearest (no key, ~12 s)
python -m musiccrs.checks.check_nlu      # T1: 53 sentences, 14 of them Part 4 (needs the key)
python -m musiccrs.checks.check_critique # T3 + T5: 104 checks, like / dislike / attributes on rock, jazz, pop (no key, ~1 min)
python -m musiccrs.data.media           # T2: Deezer cover and preview of Smells Like Teen Spirit (network)
python -m musiccrs.checks.check_similar  # T6 + T8: 27 checks of sounds like and lyrics search (no key, ~1 min)
python -m musiccrs.checks.check_lyrics   # T8: missing and placeholder lyrics vectors (~10 s)
python -m musiccrs.checks.eval_audio     # T10 F5b: tags shared with 1,000 seeds, audio vs metadata vs random (~25 s)
python -m musiccrs.checks.check_explain  # T7: 41 checks, one song per source, numbers traced to stored values (no key, ~1 min)
python -m musiccrs.checks.eval_critique  # T9 F5a: simulated critiques on 1,000 val0 conversations (no key, ~5 min; --limit 200 for a quicker run)
python -m musiccrs.checks.check_latency  # T9: 30 scripted turns, ms and LLM calls per turn (needs the key)
```

Expected output (Oct 29):

- `musiccrs.data.vectors`: the three size lines above, then
  ```
  Sounds closest to Smells Like Teen Spirit by Nirvana:
    0.932  I Stand Alone by Godsmack
    0.922  Stay Away by Nirvana
    0.915  One Weak by Deftones
    0.914  In Bloom - Nevermind Version by Nirvana
    0.913  Another Brick in the Wall, Pt. 1, 2, 3 by Korn
  ```
- `check_base`: every line `ok`, last line `OK: every check passed.`
- `check_nlu`: `Passed 53/53 (100.0%); T3 needs 90%`, about 470 ms per parse.
- `check_critique` (Oct 30): for each playlist the R6 list, the "more like #2" list and the
  "less like #4" list, each followed by `ok` lines, for example
  ```
  ok    closer to #2: mean cosine 0.601 -> 0.84
  ok    further from the disliked song: mean cosine 0.892 -> 0.837
  ```
  (jazz 0.425 → 0.592 and 0.836 → 0.658; pop 0.75 → 0.902 and 0.906 → 0.905). Then (T5,
  Oct 30) for each playlist the "older", "more popular" and "older again" lists, for example
  ```
  ok    still older than 2000 (0 not)
  ok    all popularity above 54 (0 not)
  ok    the second year limit is not later: 2000 -> 1998
  ```
  then 7 + 7 edge cases, `ms per critique: median 12, max 52` and `OK: every check passed.`
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
- `check_explain` (Oct 30): first the ranks, for example
  ```
  ok    use_same_artist=True: same 100 IDs as retrieve()
  ok    bm25_plus rank 10 (stored 10)
  ok    same_artist is off, not stored
  ```
  then each explanation (lines starting with `|`) followed by `ok` lines such as
  `ok    every number is stored (found ['1996', '0.91'], not stored [])`, then 4 edge cases,
  `ms per explanation: median 1.7, max 2.3` and `OK: every check passed.`
- `eval_critique` (Oct 31, all 1,000 val0 sessions, turn 8):
  ```
  gold already among the 5 shown (accepted, skipped): 180
  gold or shown songs without an audio vector (skipped): 0
  evaluated: 820 (806 with at least one true attribute critique)

  list                                nDCG@20       up     down     same
  no critique (retriever, 6-25)        0.1429
  more like #k                         0.0455    6.3 %   31.2 %   62.4 %
  more like #k + year / popularity     0.0754   12.1 %   29.6 %   58.3 %
  ```
  The critique alone moves the list toward songs that *sound* like #k, but loses the words of
  the conversation that the retriever matches; true attribute critiques win part of it back.
- `check_latency` (Oct 31): each turn as `[CRITIQUE] 467 ms, 1 LLM call, playlist 6: More like ...`
  (the SELECT turns "the first one" take 0-1 ms and 0 LLM calls: rules only), then mean and max
  ms per intent, then:
  ```
  All 30 turns: median 595 ms, 95th percentile 1233 ms, max 1309 ms
  LLM calls: 27 in total, 0.9 per turn, max 2 in one turn
  OK: 30 turns, every one under 3000 ms and at most 3 LLM calls, with the expected intent and playlist length.
  ```
  The slowest turns are LYRICS_SEARCH (1309 ms) and CREATE_PLAYLIST (1233 ms, the only turn
  with 2 LLM calls). The ms vary from run to run; the call counts do not.
