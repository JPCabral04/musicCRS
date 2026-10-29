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
| `/like 2` | Critiques are not built yet. I understood: {'like': '2'} |
| `/critique tag more acoustic` | Critiques are not built yet. I understood: {'attribute': 'tag', 'direction': 'more', 'tag': 'acoustic'} |
| `/sounds nirvana: smells like teen spirit` | 'Sounds like' is not built yet. I understood: {'track': 'smells like teen spirit', 'artist': 'nirvana'} |
| `/about leaving home` | Lyrics search is not built yet. I understood: {'theme': 'leaving home'} |
| "why did you pick the third one?" (with the key) | Explanations are not built yet. I understood: {'option': '3'} |

---

## 3. Command-line checks

```bash
python -m musiccrs.data.vectors          # T1: matrix sizes + 5 audio neighbours of Smells Like Teen Spirit (~15 s)
python -m musiccrs.checks.check_base     # T1: 71 checks of slash commands, shown tracks, pick_shown, nearest (no key, ~12 s)
python -m musiccrs.checks.check_nlu      # T1: 53 sentences, 14 of them Part 4 (needs the key)
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
