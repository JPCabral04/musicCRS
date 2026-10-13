# MusicCRS — Part 4 proposal: advanced functionality

**Group:** JP Cabral, Alejandro · **Course:** DAT640, 2026

**Status:** submitted on Canvas on Oct 13, 2026 (deadline Oct 14). Waiting for the lecturers'
feedback: approval (5 points) or a request for changes. The implementation (15 points) is
graded on the approved version and presented in person on Nov 4 or Nov 11.

Canvas rules: proposal text of ~300 words, a rubric table (features and points), and a short
description and citation for each method.

## Submitted text (as sent, ~296 words)

The approved rubric below is what we will be graded on. Do not change it here without a new
approval.

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

## Grading rubric (15 points)

| ID | Requirement | Points |
| --- | --- | --- |
| F1.1 | Example critiques ("more/less like #k") update the list via relevance feedback | 2 |
| F1.2 | Attribute critiques for year, popularity and tags | 2 |
| F1.3 | Critiques stack across turns; tracks already shown are not repeated | 1 |
| F2.1 | "Sounds like <track>" returns 3–5 tracks by audio similarity | 2 |
| F2.2 | Lyrics-theme search returns 3–5 tracks by lyrics similarity | 1 |
| F3.1 | "Why this song?" works for any recommended track | 1 |
| F3.2 | Explanations are grounded in the signals actually used | 2 |
| F4 | Cover and 30-second preview in the UI | 2 |
| F5 | Evaluation script and per-turn latency/LLM-call log | 2 |
| | **Total** | **15** |

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
- **Critique examples to support.** "More/less like #k", "less like the one by X", "older",
  "newer", "more popular", "more acoustic". F1.2 needs year, popularity and tags.
- **LLM budget.** At most 2 LLM calls per turn for these features (the course limit is 5–10),
  and replies within 3–5 s.
- **F4 source.** Cover and preview come from the public Deezer API.
- **F5 data.** Only `train` conversations (the validation folds), never the test split.
  Example check: after "older", the mean release year of the list must go down.

## Links to the evaluation lecture (M12b)

- **No LLM judge for F3.** Grading our explanations with the same Llama that wrote them is the
  "circularity trap" (M12b, slide 23). F5 uses checks that need no LLM.
- **If the lecturers ask for user evaluation.** A small study with 5 participants and the
  System Usability Scale (SUS; Brooke, 1996; M12b, slides 13–14) is the fallback. It is not
  in the rubric now, because Part 3 is already a user study.
