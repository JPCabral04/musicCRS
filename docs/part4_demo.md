# MusicCRS Part 4: how to test the advanced features

How to try each Part 4 feature in the chat and from the command line: the lines to type, the
expected reply, and the check scripts. A feature is added here when its task is done
(see `part4_plan_simple.md`). Setup, the LLM key and the Part 2 demo are in `part2_demo.md`.

All commands are for **Git Bash**, from the **repo root**.

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

Lyrics has fewer: 322 placeholder vectors (instrumentals) are left out (T8).

The first start downloads the audio and lyrics vectors (~290 MB into `cache/embeddings/`).

---

## 2. Features

(Each finished task adds a subsection here: what to type, what should come back, which check to run.)

### Base (T1): the Part 4 commands

Every Part 4 feature has a slash command (no LLM) and a natural-language form (one LLM call,
the parser). Until a feature's task is done, its command replies "… is not built yet. I
understood: {...}", which shows the slots the parser found.

| Feature | Slash command | In words |
| --- | --- | --- |
| Example critique (F1.1) | `/like 2`, `/dislike bon jovi` | "more like the second one", "less like the one by Bon Jovi" |
| Attribute critique (F1.2) | `/critique year less`, `/critique popularity more`, `/critique tag more acoustic` | "older", "more popular", "more acoustic", "no rap" |
| Sounds like (F2.1) | `/sounds nirvana: smells like teen spirit` | "songs that sound like Smells Like Teen Spirit" |
| Lyrics theme (F2.2) | `/about leaving home` | "songs about leaving home" |
| Why this song? (F3) | `/why 2` | "why the second one?", "why did you pick Yellow?" |

"Songs like Numb" is still a Part 2 recommendation (R6); only "songs that *sound* like Numb"
uses the audio vectors.

Expected replies until the features are built (the slots are what the parser understood):

| Type | Expected reply |
| --- | --- |
| `/like 2` | Built in T3, see below. Before any recommendation: "Ask me for recommendations first, …" |
| `/critique tag more acoustic` | Built in T5, see below. |
| `/sounds nirvana: smells like teen spirit` | Built in T6, see below. |
| `/about leaving home` | Built in T8, see below. |
| "why did you pick the third one?" (with the key) | Built in T7, see below. Before any recommendation: "There is no list of recommended songs to explain yet. …" |

### Example critiques (T3, F1.1): "more like the second one"

The list on screen is one vector (the mean of its songs' **audio** vectors). "More like #2"
pulls it toward #2, "less like #4" pushes it away from #4 (Rocchio), and the 5 closest songs
never shown before come back. Critiques add up until a new list starts (a new
recommendation, "sounds like" or lyrics search). No LLM besides the parser; about 10 ms.

Try it on a rock playlist:

| Type | Natural language (needs the key) | Expected reply |
| --- | --- | --- |
| `/add nirvana: smells like teen spirit`, `/add eagles: hotel california`, `/add bon jovi: its my life` | "add It's My Life by Bon Jovi" | The songs are added (pick a version if asked). |
| `/recommend` | "recommend me something" | Based on your playlist, you might like: 5 songs, for example Come As You Are (Nirvana), **Bad Medicine (Bon Jovi)**, Yellow (Coldplay), Have A Nice Day (Bon Jovi), Sex on Fire (Kings of Leon). |
| `/like 2` | "more like the second one" | **More like Bad Medicine by Bon Jovi:** 5 new songs that sound like it: Glorified G (Pearl Jam), Way Cool Jr. (Ratt), One Wild Night (Bon Jovi), Nobody Listens (Bad Religion), Say It Isn't So (Bon Jovi). |
| `/dislike 4` | "less like the fourth one" | **More like Bad Medicine by Bon Jovi, less like Nobody Listens by Bad Religion:** 5 new songs, the punk one gone: Wild Is The Wind (Bon Jovi), Slaughter ×2, Thunderstruck (AC/DC), Mama I'm Coming Home (Ozzy Osbourne). |
| `/dislike ratt` | "less like the one by Ratt" | A name works too, but only for a song **on screen now**: Ratt was in the previous list, so "I could not find 'ratt' in the last list. …" |
| `/like 7` | "more like the seventh one" | I could not find '7' in the last list. Use its number … or its artist. (Nothing changes.) |
| `/critique year less` | "older" | Built in T5, see below; it adds up with the like and dislike above. |

The exact songs depend on the versions picked and on the playlist; the rows above are the
lists `check_critique` prints for its rock playlist. A song shown once never comes back, and
"add the first two" works on every critique list.

### Attribute critiques (T5, F1.2): "older", "more popular", "more acoustic"

Each critique becomes a filter with a fixed limit, taken from the list **on screen** when it
is said: "older" keeps songs released before the median year of that list, "more popular"
songs above its median popularity, "more acoustic" songs tagged *acoustic*, "no rap" songs
not tagged *rap*. Filters add up (with each other and with likes / dislikes) until a new list
starts. The songs are the closest ones to the critique vector of T3 that pass every filter
(searched among the 1,000 closest). No LLM besides the parser; about 12 ms.

On the same rock playlist, after a fresh `/recommend` (Come As You Are, Bad Medicine, Yellow,
Have A Nice Day, Sex on Fire):

| Type | Natural language (needs the key) | Expected reply |
| --- | --- | --- |
| `/critique year less` | "something older" | **Older than 2000:** Glorified G (Pearl Jam), God Smack (Alice In Chains), Down In A Hole (Alice In Chains), Slide (Goo Goo Dolls), All Eyes On Me (Goo Goo Dolls), all from 1992–1998. |
| `/critique popularity more` | "more popular ones" | **Older than 2000, popularity above 54:** Learn to Fly (Foo Fighters), Black Balloon (Goo Goo Dolls), Only In Dreams (Weezer), I Just Want You (Ozzy Osbourne), You Get What You Give (New Radicals). Still older than 2000: the filters add up. |
| `/critique tag more polka` | "more polka" | Sorry, no new songs near this list are older than 2000 and popularity above 54 and tagged polka. The list stays as it was: … (the filter is dropped, nothing changes). |
| `/critique year less` | "even older" | **Older than 2000, popularity above 54, older than 1998:** the new limit comes from the list on screen: Mama, I'm Coming Home and Hellraiser (Ozzy Osbourne), Pretty Noose (Soundgarden), De Música Ligera (Soda Stereo), Corduroy (Pearl Jam). |
| `/critique colour more` | — | I can change the songs by year ('older', 'newer'), by popularity ('more popular', 'less known') or by style ('more acoustic', 'no rap'). |
| `/recommend`, then `/critique tag more hard rock` | "more hard rock" | A new list forgets the filters; then 5 new songs, all tagged *hard rock*. |
| — (after a fresh `/recommend`) | "like number 2 but older" | Both at once: **More like Bad Medicine by Bon Jovi, older than 2000:** Glorified G (Pearl Jam), Way Cool Jr. (Ratt), Nobody Listens (Bad Religion), Wild Is The Wind (Bon Jovi), Mama, I'm Coming Home (Ozzy Osbourne), all from 1988–1996. |

`check_critique` runs the same steps on the rock, jazz and pop playlists (jazz: older than
1987, then popularity above 40, then older than 1959).

### Covers and previews (T2, T4): album art and 30-second clips

Every song in the playlist panel and in every list of options in the chat (choices,
recommendations, critiques, sounds like, lyrics) shows its album cover and a play button.
They come from the Deezer search API (no key), looked up one song after the other and kept
in memory by track ID. A new list of 5 costs about 1 s; the same songs again cost a few ms.
If Deezer is slow, lookups stop after 2 s and the remaining songs get no card in that reply
(the reply stays within 3-5 s; they are looked up again next time).

| Do | Expected |
| --- | --- |
| `/add nirvana: smells like teen spirit` | The panel shows the song with its Nevermind cover and a play button. |
| `/add eagles: hotel california` | The choice buttons, plus a card per version with cover and preview. |
| Play one preview, then another | The first one stops (one preview at a time in the panel). |
| `/recommend` | The 5 songs as buttons, and below the text a card per song (cover, name, artist, player). |

### Sounds like (T6, F2.1): "songs that sound like Smells Like Teen Spirit"

The named song is the seed. Its **audio** vector (CLAP, made from the sound) is compared with
every other track's, and the 5 closest never shown before come back, leaving out other
versions of the seed. A new list starts, so critiques work on it. No LLM besides the parser.

| Type | Natural language (needs the key) | Expected reply |
| --- | --- | --- |
| `/sounds nirvana: smells like teen spirit` | "songs that sound like Smells Like Teen Spirit" | **Songs that sound like Smells Like Teen Spirit by Nirvana:** I Stand Alone (Godsmack), Stay Away (Nirvana), One Weak (Deftones), In Bloom - Nevermind Version (Nirvana), Another Brick in the Wall, Pt. 1, 2, 3 (Korn). |
| `/like 3` | "more like the third one" | **More like One Weak by Deftones:** Heroin Girl (Everclear), Stress (Godsmack), Victims (Lacuna Coil), P.S. New York Is Burning (Jawbreaker), Gonna Be A Blackout Tonight (Dropkick Murphys). The seed never comes back. |
| `/sounds xqzvwk` | — | I could not find 'xqzvwk' in the catalog. |

"Songs **like** Numb" is still R6 (the Part 1 retriever); only "sound like" uses the audio.

### Lyrics search (T8, F2.2): "songs about leaving home"

The theme is encoded by the same Qwen3 model as the lyrics vectors, and the 5 tracks whose
lyrics vectors are closest come back. Placeholder lyrics vectors (322 instrumentals sharing
one vector) are left out. A new list starts. No LLM besides the parser.

| Type | Natural language (needs the key) | Expected reply |
| --- | --- | --- |
| `/about leaving home` | "songs about leaving home" | **Songs whose lyrics are about leaving home:** Leaving Home (Jebediah), Can We Go Wrong (Hesta Prynn), In The Wild (Alpine), Mickey Mouse (Wavves), Stay Home (American Football). |
| `/about heartbreak` | "songs about heartbreak" | Bringin' On The Heartbreak (Mariah Carey), Break My Heart (Hey Violet), This Is How A Heart Breaks (Rob Thomas), … |
| `/about partying all night` | "songs about partying all night" | Party All Night (Quiet Riot), Party All the Time (Eddie Murphy), Party In Your Bedroom (Cash Cash), No Sleep (Wiz Khalifa), … |

(Lists for a fresh conversation; songs shown before are skipped.)

### Why this song? (T7, F3): "why the second one?"

Up to four sentences, each built with a template from one fact: how the song was found (stored
when it was shown), which Part 1 retrievers ranked it and where (recommendations only), the
tags it shares with the songs it came from, and an artist already in the playlist (both
checked in the database). No LLM writes the reasons, so they cannot be invented. Only songs
of the last list can be asked about. About 2 ms.

On the same rock playlist:

| Type | Natural language (needs the key) | Expected reply |
| --- | --- | --- |
| `/recommend`, then `/why 2` | "why the second one?" | **Why I showed you Bad Medicine by Bon Jovi:** I recommended it for Smells Like Teen Spirit, Hotel California, It's My Life. It was found by matching the words of your songs (#116), being by an artist of your songs (#1). It shares the tags *hard rock*, *jon bon jovi*, *favorite* with those songs. Its artist Bon Jovi is already in your playlist. |
| `/why come as you are` | "why did you pick Come As You Are?" | Same form for #1, found by three retrievers: words (#10), same artist (#59), listening patterns of other users (#2). |
| `/recommend`, `/like 2`, `/critique year less`, then `/why 1` | "why the first one?" | **Why I showed you Wild Is The Wind by Bon Jovi:** It came from your critique "More like Bad Medicine by Bon Jovi, older than 1996", as one of the songs closest in sound to it (audio similarity 0.91). It shares the tags *hard rock*, *melodic hard rock*, *jon bon jovi* with Bad Medicine. Its artist Bon Jovi is already in your playlist. |
| `/why 7` | "why the seventh one?" | I could not find '7' in the last list I showed you. Say a number from 1 to 5, or part of a title or an artist. |
| `/why` | — | Which song? For example: 'why the second one?' or '/why 2'. |
| `/sounds nirvana: smells like teen spirit`, then `/why 1` | "why the first one?" | **Why I showed you I Stand Alone by Godsmack:** It sounds close to Smells Like Teen Spirit by Nirvana (audio similarity 0.93). It shares the tags *alternative*, *rock*, *grunge* with Smells Like Teen Spirit by Nirvana. |
| `/about leaving home`, then `/why 1` | "why the first one?" | **Why I showed you Leaving Home by Jebediah:** Its lyrics are close to the theme 'leaving home' (lyrics similarity 0.55). |

The "why" options stay pending, so "add the second one" still works afterwards.

---

## 3. Command-line checks

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
