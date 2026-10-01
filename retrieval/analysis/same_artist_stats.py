"""Measure how often the gold track is by an artist already played in the session.

For a random sample of `train` sessions and every turn from 2 to 8, checks
whether the gold track shares an artist with a track played in an earlier
turn, and how large that "same-artist pool" is (all catalog tracks by the
played artists, minus the played tracks). Only information available before
the target turn is used. This motivates the same-artist recommender (T5).

Usage:
    python -m retrieval.analysis.same_artist_stats --n_sessions 2000 --seed 0
    python -m retrieval.analysis.same_artist_stats --show 3   # print 3 example sessions
"""
import argparse
import random
import statistics
from collections import defaultdict

from datasets import load_dataset

from ..data_loader import MusicCatalogLoader


def _played_tracks_by_turn(session: dict) -> list[str]:
    """Returns the session's `music` track IDs ordered by turn number."""
    music = [m for m in session["conversations"] if m["role"] == "music"]
    music.sort(key=lambda m: m["turn_number"])
    return [m["content"] for m in music]


def _print_example(session: dict, catalog: dict) -> None:
    """Prints, per turn, the gold track and whether its artist was played before."""
    print(f"\nsession {session['session_id']}")
    played_artists = set()
    for turn, track_id in enumerate(_played_tracks_by_turn(session), start=1):
        meta = catalog[track_id]
        artists = set(meta["artist_name"])
        hit = "yes" if artists & played_artists else "no"
        print(f'  turn {turn}: gold = "{meta["track_name"][0]}" by {sorted(artists)}'
              f" | artist played before? {hit}")
        played_artists |= artists


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n_sessions", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--show", type=int, default=0,
                        help="Print this many example sessions turn by turn.")
    args = parser.parse_args()

    catalog = MusicCatalogLoader().metadata_dict
    tracks_by_artist = defaultdict(set)
    for track_id, meta in catalog.items():
        for artist in meta["artist_name"]:
            tracks_by_artist[artist].add(track_id)

    sessions = load_dataset("talkpl-ai/TalkPlayData-Challenge-Dataset", split="train")
    sample = random.Random(args.seed).sample(range(len(sessions)), args.n_sessions)

    for i in sample[:args.show]:
        _print_example(sessions[i], catalog)

    n_turns = hits_any = hits_last = 0
    pool_sizes = []
    for i in sample:
        tracks = _played_tracks_by_turn(sessions[i])
        for t in range(1, len(tracks)):  # index 1..7 = turns 2..8
            played = tracks[:t]
            gold_artists = set(catalog[tracks[t]]["artist_name"])
            played_artists = {a for p in played for a in catalog[p]["artist_name"]}
            last_artists = set(catalog[played[-1]]["artist_name"])

            n_turns += 1
            hits_any += bool(gold_artists & played_artists)
            hits_last += bool(gold_artists & last_artists)
            pool = set().union(*(tracks_by_artist[a] for a in played_artists))
            pool_sizes.append(len(pool - set(played)))

    pool_sizes.sort()
    print(f"\nsessions: {args.n_sessions} (seed {args.seed}), turns 2-8 evaluated: {n_turns}")
    print(f"gold shares an artist with ANY played track:  {hits_any / n_turns:.1%}")
    print(f"gold shares an artist with LAST played track: {hits_last / n_turns:.1%}")
    print(f"same-artist pool size: median {statistics.median(pool_sizes):.0f}, "
          f"p90 {pool_sizes[int(0.9 * len(pool_sizes))]}, max {pool_sizes[-1]}")


if __name__ == "__main__":
    main()
