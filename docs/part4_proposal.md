# MusicCRS — Part 4 proposal: advanced functionality

**Group:** JP Cabral, Alejandro · **Course:** DAT640, 2026

## Goal

In Part 2 the user can only accept or reject a recommendation. We propose features that let the
user **steer** recommendations, **find music by how it sounds**, and **understand why** a track
was suggested. They build on our Part 1 retrieval (BM25, Qwen3 dense, BPR, RRF fusion) and on
dataset embeddings we have not used yet (LAION-CLAP audio, Qwen3 lyrics). At most 2 LLM calls
per turn; responses within 3–5 s.

## Features

- **F1. Critiquing.** After a recommendation or generated playlist, the user can say "more like
  the second one", "less like the one by Metallica", "older", "more popular", "more acoustic".
  The LLM parses the critique into a structured form. Example critiques move the query vector
  toward the tracks the user liked and away from those they rejected, in the Qwen3 embedding
  space (relevance feedback).
  Attribute critiques filter or re-rank by year, popularity and tags.
- **F2. "Sounds like".** "Songs that sound like <track>" returns nearest neighbours by **CLAP
  audio embeddings**. "Songs about leaving home" ranks tracks by **lyrics embeddings**.
- **F3. "Why this song?"** Each recommended track keeps the signals that produced it (retriever
  ranks in the fusion, shared tags, same artist, audio similarity). The explanation states only
  these facts.
- **F4. Previews.** Cover and 30-second preview for recommended tracks in the UI, via the public
  Deezer API.
- **F5. Evaluation.** An offline script on conversations from the training data (never the test
  split) checks that critiques move the list the right
  way (e.g. "older" lowers the mean release year) and that audio neighbours share more tags than
  random tracks. The agent logs latency and LLM calls per turn.

## Grading rubric (15 points)

| ID | Requirement | Points |
| --- | --- | --- |
| F1.1 | Example critiques ("more/less like #k", "less like the one by X") update the list via relevance feedback | 2 |
| F1.2 | Attribute critiques for year, popularity and tags (≥ 4 kinds, ≥ 3 phrasings each) | 2 |
| F1.3 | Critiques stack over turns; tracks already shown are not repeated | 1 |
| F2.1 | "Sounds like <track>" returns 3–5 tracks by audio similarity | 2 |
| F2.2 | Lyrics-theme search returns 3–5 tracks by lyrics similarity | 1 |
| F3.1 | "Why this song?" works for any recommended track, by position or name | 1 |
| F3.2 | Explanations are grounded in the signals actually used | 2 |
| F4 | Cover and 30-second preview in the UI | 2 |
| F5 | Evaluation script and per-turn latency/LLM-call log, results shown in the presentation | 2 |
| | **Total** | **15** |
