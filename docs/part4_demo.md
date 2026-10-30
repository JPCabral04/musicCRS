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
  lyrics: 47071 x 1024, 46579 tracks with a vector
```

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
| `/sounds nirvana: smells like teen spirit` | 'Sounds like' is not built yet. I understood: {'track': 'smells like teen spirit', 'artist': 'nirvana'} |
| `/about leaving home` | Lyrics search is not built yet. I understood: {'theme': 'leaving home'} |
| "why did you pick the third one?" (with the key) | Explanations are not built yet. I understood: {'option': '3'} |

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

---

## 3. Command-line checks

```bash
python -m musiccrs.data.vectors          # T1: matrix sizes + 5 audio neighbours of Smells Like Teen Spirit (~15 s)
python -m musiccrs.checks.check_base     # T1: 71 checks of slash commands, shown tracks, pick_shown, nearest (no key, ~12 s)
python -m musiccrs.checks.check_nlu      # T1: 53 sentences, 14 of them Part 4 (needs the key)
python -m musiccrs.checks.check_critique # T3 + T5: 104 checks, like / dislike / attributes on rock, jazz, pop (no key, ~1 min)
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
