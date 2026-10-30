"""Offline evaluation of the audio vectors (Part 4, T10 F5b): do songs that sound alike share tags?

Run from the repo root (no API key, no retriever; about 1 min):
    python -m musiccrs.checks.eval_audio

For 1,000 random tracks with an audio vector (seed 42), take three groups of 5 tracks:
- audio:    the 5 nearest in the CLAP audio space;
- metadata: the 5 nearest in the metadata (Qwen3 text) space, the F5b baseline;
- random:   5 random tracks.
Every group leaves out the seed's own artist: same-artist tracks share tags trivially,
and the metadata text contains the artist name, which would favour the metadata space.
Prints the mean number of tags (lower case) a neighbour shares with its seed.
Expected: random < audio. Audio vs metadata tells whether sound agrees with tags.
"""
import random

from retrieval.data_loader import MusicCatalogLoader
from retrieval.methods.dense import DEFAULT_FIELD, load_track_matrix

from ..data.db import TrackDB
from ..data.vectors import TrackVectors
from ..handlers.critique import lower_tags

NUM_SEEDS = 1000
NUM_NEIGHBOURS = 5
SEED = 42


def shared_tags(seed_track, track_ids, db):
    """The number of tags each track shares with the seed, added up.

    seed tags {"grunge", "rock", "90s"}, one track with {"rock", "90s", "pop"} -> 2
    """
    seed_tags = lower_tags(seed_track)
    total = 0
    for track_id in track_ids:
        tags = lower_tags(db.get(track_id))
        total = total + len(seed_tags & tags)
    return total


def random_tracks(rng, track_ids, exclude, count):
    """count random track IDs, none of them in exclude."""
    picked = []
    while len(picked) < count:
        track_id = rng.choice(track_ids)
        if track_id not in exclude and track_id not in picked:
            picked.append(track_id)
    return picked


def ids_of(results):
    """[(track_id, score), ...] -> [track_id, ...]"""
    track_ids = []
    for track_id, score in results:
        track_ids.append(track_id)
    return track_ids


def main():
    # The same track order and metadata matrix the dense scorer uses.
    track_ids = list(MusicCatalogLoader().metadata_dict)
    metadata_matrix, metadata_has_vector = load_track_matrix(DEFAULT_FIELD, track_ids)
    vectors = TrackVectors(track_ids, metadata_matrix, metadata_has_vector)
    db = TrackDB()

    # Seeds: tracks with both an audio and a metadata vector, so the groups compare fairly.
    candidates = []
    for row in range(len(track_ids)):
        if vectors.usable["audio"][row] and vectors.usable["metadata"][row]:
            candidates.append(track_ids[row])
    rng = random.Random(SEED)
    seeds = rng.sample(candidates, NUM_SEEDS)

    totals = {"audio": 0, "metadata": 0, "random": 0}
    for seed_id in seeds:
        seed_track = db.get(seed_id)

        # Leave out the seed and every track by its main artist.
        exclude = {seed_id}
        for track in db.artist_tracks(seed_track.artists[0]):
            exclude.add(track.track_id)

        audio = vectors.nearest("audio", vectors.vector("audio", seed_id),
                                NUM_NEIGHBOURS, exclude)
        metadata = vectors.nearest("metadata", vectors.vector("metadata", seed_id),
                                   NUM_NEIGHBOURS, exclude)
        others = random_tracks(rng, candidates, exclude, NUM_NEIGHBOURS)

        totals["audio"] = totals["audio"] + shared_tags(seed_track, ids_of(audio), db)
        totals["metadata"] = totals["metadata"] + shared_tags(seed_track, ids_of(metadata), db)
        totals["random"] = totals["random"] + shared_tags(seed_track, others, db)

    pairs = NUM_SEEDS * NUM_NEIGHBOURS
    print("Mean tags shared with the seed (" + str(NUM_SEEDS) + " seeds x "
          + str(NUM_NEIGHBOURS) + " tracks, seed's artist left out):")
    for group in ["audio", "metadata", "random"]:
        mean = totals[group] / pairs
        print("  " + group.ljust(9) + str(round(mean, 3)))


if __name__ == "__main__":
    main()
