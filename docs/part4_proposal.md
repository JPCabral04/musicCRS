# MusicCRS — Part 4 proposal: advanced functionality

**Group:** JP Cabral, Alejandro · **Course:** DAT640, 2026

**Status:** first version submitted on Canvas on Oct 13, 2026. Feedback from Petra Galuscakova
on Oct 16: "looks fine, please start with the implementations", with small comments on F2.2, F4
and F5. The revised version below answers them and is the one to resubmit. The implementation
(15 points) is graded on the approved version and presented in person on Nov 4 or Nov 11.

Canvas rules: proposal text of ~300 words, a rubric table (features and points), and a short
description and citation for each method.

## Lecturer feedback (Oct 16)

- **F2.2:** unclear how lyrics are searched. A database we build may be worth more points; an
  API is fine as it is.
- **F4:** cover art plus music preview may be worth 3 points. Optional: generate a cover image
  for the song or playlist for 1 extra point.
- **F5:** if it means unit tests, that is testing, not evaluation.

## Resubmission text (Oct 16)

The rubric in this text is what we will be graded on once approved. Do not change it here
without a new approval.

```
Response to feedback

F2.2: We do not use an API. We build our own local lyrics index: the dataset's lyrics embeddings for all 47,071 tracks, keyed by track ID in our track database. A theme query is embedded locally with the same model and matched by cosine similarity. Raised to 2 points.
F4: Cover art and 30-second preview kept, raised to 3 points as suggested.
F5: Not unit tests. It is now an offline evaluation with simulated users and reported metrics.
To keep 15 points, F1.3 is merged into F1.2 and F3.1 into F3.2.

MusicCRS Part 4: Steerable and explainable recommendations (revised)

In Part 2 users can only accept or reject suggestions. We let them steer results, search by sound and lyrics theme, and see why a track was suggested, reusing our Part 1 retrieval and unused dataset embeddings (audio, lyrics).

F1 Critiquing. The user critiques a recommendation [2]: "more like the second one", "older". An LLM structures the critique. Example critiques move the query embedding toward liked tracks and away from rejected ones (Rocchio relevance feedback [1]); attribute critiques re-rank by year, popularity or tags.

F2 Sounds like. Nearest neighbours in the CLAP audio embedding space [3] answer "songs that sound like X". For lyrics we build a local index, with no external API: the dataset's lyrics embeddings (Qwen3-Embedding) for the 47,071 tracks, keyed by track ID in our track database; tracks without lyrics are left out. "Songs about leaving home" is embedded locally with the same model and matched by cosine similarity.

F3 Why this song? Each result keeps the signals that produced it (retriever ranks, shared tags, same artist, audio similarity). The explanation states only these, so the LLM cannot invent reasons [2].

F4 Previews. Cover art and a 30-second preview for each track in the UI.

F5 Evaluation. An offline evaluation with simulated users on 1,000 held-out training conversations. The simulated user knows which track the real user chose next and critiques toward it ("more like" the closest shown track, "older" if it is older). We report nDCG@20 before and after each critique. Audio neighbours are scored by tags shared with the seed track, against random tracks and text-embedding neighbours. Latency and LLM calls are logged per turn.

Grading rubric (15 points)
F1.1 Example critiques update the list via relevance feedback: 2
F1.2 Attribute critiques (year, popularity, tags) that stack across turns, no repeated tracks: 2
F2.1 Audio "sounds like" returns 3-5 tracks: 2
F2.2 Lyrics-theme search over our local lyrics index returns 3-5 tracks: 2
F3 "Why this song?" for any recommended track, grounded in the signals actually used: 2
F4 Cover art and 30-second preview in the UI: 3
F5 Offline evaluation with simulated users, plus latency/LLM-call log: 2

References
[1] Rocchio (1971). Relevance feedback in information retrieval.
[2] Balog (2026). Recommender Systems, DAT640 lecture.
[3] Wu et al. (2023). Large-scale contrastive language-audio pretraining. ICASSP.
```

## Grading rubric (15 points, revised Oct 16)

| ID | Requirement | Points |
| --- | --- | --- |
| F1.1 | Example critiques ("more/less like #k") update the list via relevance feedback | 2 |
| F1.2 | Attribute critiques for year, popularity and tags; critiques stack across turns; tracks already shown are not repeated | 2 |
| F2.1 | "Sounds like <track>" returns 3–5 tracks by audio similarity | 2 |
| F2.2 | Lyrics-theme search over our local lyrics index returns 3–5 tracks | 2 |
| F3 | "Why this song?" works for any recommended track and states only the signals actually used | 2 |
| F4 | Cover art and 30-second preview in the UI | 3 |
| F5 | Offline evaluation with simulated users, plus per-turn latency/LLM-call log | 2 |
| | **Total** | **15** |

Changes from Oct 13: F2.2 1→2, F4 2→3, F1.3 merged into F1.2 (−1), F3.1 merged into F3 (−1).
Cover image generation (the optional extra point) is not included.

## References (full)

1. J. J. Rocchio (1971). Relevance feedback in information retrieval. In G. Salton (ed.),
   *The SMART Retrieval System*. Prentice-Hall.
2. K. Balog (2026). Recommender Systems, DAT640 lecture (M12a), University of Stavanger.
   Critiquing: slide 55 ("Conversational recommenders"). Explainability as a recommender
   challenge: slide 13. LLMs can hallucinate items or reasons: slide 56.
3. Y. Wu, K. Chen, T. Zhang, Y. Hui, T. Berg-Kirkpatrick, S. Dubnov (2023). Large-scale
   contrastive language-audio pretraining with feature fusion and keyword-to-caption
   augmentation. *ICASSP 2023*.

The bibliographic details of [1] and [3] were written from memory. Check them before they go
into slides or a report.

## Implementation notes (not in the submitted text)

- **Embeddings.** F1 relevance feedback uses the Qwen3 metadata vectors from Part 1. F2 uses
  the dataset's LAION-CLAP audio vectors and Qwen3 lyrics vectors. Part 1 retrieval stays as
  it is: BM25, Qwen3 dense, BPR, weighted RRF fusion.
- **F2.2 lyrics index.** We only have the lyrics *vectors* (1024-d, not normalized, norm ~110),
  not the lyrics text. The index is the lyrics matrix, L2-normalized, with rows in the same
  `track_ids` order as the track database. Query side: `Qwen/Qwen3-Embedding-0.6B` in query
  mode, as `retrieval/methods/dense.py` already does for metadata. How many tracks have an empty or
  meaningless lyrics vector (instrumentals) is **still to check**; those rows are left out.
- **Critique examples to support.** "More/less like #k", "less like the one by X", "older",
  "newer", "more popular", "more acoustic". F1.2 needs year, popularity and tags.
- **LLM budget.** At most 2 LLM calls per turn for these features (the course limit is 5–10),
  and replies within 3–5 s.
- **F4 source.** Cover and preview come from the public Deezer API.
- **F5 data.** Only `train` conversations (the validation folds), never the test split. The
  simulated user may use the next chosen track because it acts as the ground truth of an
  offline evaluation; the system being evaluated never sees it.
- **F5 metrics.** Critiquing: nDCG@20 of the next chosen track before vs after one simulated
  critique, and the share of critiques that move it up. Audio: mean number of tags shared by
  the top-5 neighbours with the seed track, against 5 random tracks and the top-5 text-embedding
  neighbours. Efficiency: median and 95th-percentile latency and LLM calls per turn.

## Links to the evaluation lecture (M12b)

- **No LLM judge for F3.** Grading our explanations with the same LLM that wrote them is the
  "circularity trap" (M12b, slide 23). F5 uses measures that need no LLM.
- **If the lecturers ask for user evaluation.** A small study with 5 participants and the
  System Usability Scale (SUS; Brooke, 1996; M12b, slides 13–14) is the fallback. It is not
  in the rubric now, because Part 3 is already a user study.

## First submission (Oct 13, superseded)

```
MusicCRS Part 4: Steerable and explainable recommendations

In Part 2 users can only accept or reject suggestions. We let them steer results, search by sound and see why a track was suggested, reusing our Part 1 retrieval and unused dataset embeddings (audio, lyrics).

F1 Critiquing. The user critiques a recommendation [2]: "more like the second one", "older". An LLM structures the critique. Example critiques move the query embedding toward liked tracks and away from rejected ones (Rocchio relevance feedback [1]); attribute critiques re-rank by year, popularity or tags.

F2 Sounds like. Nearest neighbours in the CLAP audio embedding space [3] answer "songs that sound like X"; lyrics embeddings answer "songs about leaving home".

F3 Why this song? Each result keeps the signals that produced it (retriever ranks, shared tags, same artist, audio similarity). The explanation states only these, so the LLM cannot invent reasons [2].

F4 Previews. Cover art and a 30-second preview in the UI.

F5 Evaluation. An offline script on training data checks that critiques move the list the right way and audio neighbours share more tags than random tracks. Latency and LLM calls are logged per turn.

Grading rubric (15 points)
F1.1 Example critiques update the list via relevance feedback: 2
F1.2 Attribute critiques (year, popularity, tags): 2
F1.3 Critiques stack across turns, no repeated tracks: 1
F2.1 Audio "sounds like" returns 3-5 tracks: 2
F2.2 Lyrics-theme search returns 3-5 tracks: 1
F3.1 "Why this song?" works for any recommended track: 1
F3.2 Explanations grounded in the signals actually used: 2
F4 Cover and preview in the UI: 2
F5 Evaluation script and latency/LLM-call log: 2

References
[1] Rocchio (1971). Relevance feedback in information retrieval.
[2] Balog (2026). Recommender Systems, DAT640 lecture.
[3] Wu et al. (2023). Large-scale contrastive language-audio pretraining. ICASSP.
```
