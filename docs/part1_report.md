# MusicCRS Part 1: Item Ranking

## Summary

Our ranker merges four retrievers with weighted Reciprocal Rank Fusion (RRF): an improved BM25, a
same-artist list, dense retrieval with Qwen3 embeddings, and a list of tracks close to the session
in BPR space. On the test split it scores 0.2516 (nDCG@20 0.1522, catalog diversity 0.6489). The
provided BM25 baseline scores 0.1446 when we run it.

## Validation

Nothing was tuned on test. We drew three disjoint folds of 1,000 sessions from `train` with seed 42
(val0, val1, val2), ran every experiment on val0 and checked final choices on all three. The folds
match test in size because catalog diversity is the share of the catalog that appears anywhere in
the predictions, so a larger set would score higher for free. On the baseline the folds differ by
0.010 in final score, and we treated smaller gains as noise. Hidden fields such as `thought` and
the `test_tracks` embedding split are never read.

## Two patterns in the data

The correct track is never one that was already played in the session, so a played track in the
top 20 is a wasted slot. Removing them lifts the baseline on test from 0.1446 to 0.1664 with no
other change. And in turns 2–8, 65% of the correct tracks share an artist with a track played
earlier in the same session.

Both are properties of this dataset, and a real user may well ask to hear a song again. So the
retrievers never remove played tracks themselves; one policy object in the fusion and the final
top-20 cut does it, and can switch both rules off.

## Retrievers

BM25+ is the baseline BM25 with two changes. The index also covers `tag_list`, so genre and mood
words in a request can match. The current message and the earlier conversation are scored as two
separate queries, combined as `1.0 × BM25(current) + 3.0 × BM25(history)`, where each played track
in the history is replaced by its name, artist and album. We expected the current message to need
the larger weight, but on val0 it was the other way around: the current message alone reached only
0.067 nDCG@20, against 0.163 with the weights above. Most of BM25+'s gain over the baseline
(+0.014 final score on val0–2) comes from diversity, not nDCG.

The same-artist list holds every track whose `artist_id` matches a played track, with the most
recently played artist first and popularity as the tie-breaker. It is empty on turn 1.

The dense retriever embeds the current message with Qwen3-Embedding-0.6B, the model that produced
the dataset's track embeddings, and ranks tracks by cosine similarity with their metadata
embeddings. We first checked that our encoder agrees with the precomputed vectors: 50 sampled
tracks, each encoded from its own metadata, all ranked themselves first. One query at a time on a
CPU, a fold would have taken about five hours, so queries are encoded in batches and cached.

The BPR retriever averages the collaborative-filtering (BPR) vectors of the played tracks and ranks
the catalog by cosine similarity to that average. Unlike the same-artist list, it can reach other
artists. It is also empty on turn 1.

## Fusion

Played tracks are removed from each list, then the lists are merged:

    score(track) = sum over lists of  weight / (k + rank of the track in the list)

RRF only uses ranks, so BM25 scores and cosine similarities never had to be put on one scale. For
tuning we cached each retriever's top-200 list for every validation turn and re-ran only the
fusion. The grid on val0 had 225 weight settings at k = 60 (BM25+ fixed at 1, the others from
{0, 0.5, 1, 2, 4}) and took about 8 minutes. We then tried k = 10, 30 and 100 on the best three and
checked the best five on all folds.

The final setting is BM25+ 1, same artist 2, BPR 2, dense 1, with k = 10. The four best settings
were within 0.0015 of each other, less than the variation between folds, so we kept the one with
the simpler dense query. All ten best settings used every retriever.

## Results

Validation rows are means over val0–2. Played tracks are removed everywhere except in the first
row.

| Method | Split | nDCG@20 | Diversity | Final score |
| --- | --- | ---: | ---: | ---: |
| BM25 baseline (as provided) | test | 0.0830 | 0.3908 | 0.1446 |
| BM25 baseline, played removed | val | 0.1628 | 0.3845 | 0.2072 |
| BM25+ | val | 0.1664 | 0.4414 | 0.2214 |
| Same artist | val | 0.1506 | 0.3448 | 0.1894 |
| BPR | val | 0.1103 | 0.5427 | 0.1968 |
| Dense | val | 0.0672 | 0.6038 | 0.1745 |
| Fusion (final) | val | 0.1976 | 0.5860 | 0.2753 |
| Fusion (final) | test | 0.1522 | 0.6489 | 0.2516 |

Fusion beats BM25+, the best single retriever, by 0.054 on validation, about five times the
variation between folds, and it raises both nDCG@20 (0.166 to 0.198) and diversity (0.44 to 0.59).
The test score is lower than on validation, but so is the baseline's (0.207 against 0.166 with
played tracks removed), and the baseline has nothing tuned, so test looks harder in general.

## Speed

The project allows 3–5 seconds per response. With the query vector cached, the four retrievers and
the fusion take about 10 ms per query. Encoding a new message with Qwen3 adds a median of 76 ms on
our GPU or 394 ms on a CPU.

## Limitations

The played-track and same-artist rules suit this dataset but would work against a user who asks
for a repeat or for something new. Dense retrieval is weak alone (nDCG@20 0.067), though it has
the highest diversity of the four retrievers. We never ran the fusion without it, so we cannot say
how much of the gain it carries.
