"""Offline evaluation of the critiques (Part 4, F5a): a simulated user critiques the list
toward the song the real user chose, and we measure whether that song moves up.

Run from the repo root (no LLM, about 5 min with the retriever load):
    python -m musiccrs.checks.eval_critique              # the 1,000 val0 sessions
    python -m musiccrs.checks.eval_critique --limit 200  # a quicker run

For each val0 session (a training fold, never the test split), at the last turn (turn 8,
7 songs played before it):
1. The Part 1 retriever ranks 25 songs for the turn. The first 5 are "shown".
   If the gold song (the one the real user chose) is among them, the user would just
   accept it: the turn is counted as accepted and skipped.
2. "Before" = songs 6-25: what the user would see next without a critique.
3. The simulated user says "more like #k", where #k is the shown song whose audio vector
   is closest to the gold's. It knows the gold because it plays the user; the system only
   receives the critique.
4. "After" = the agent's own code (critique_query + critique_ranking): the 20 songs
   nearest to the Rocchio query, never a played or shown song.
5. Second variant: "more like #k" plus "older" / "newer" and "more" / "less popular", each
   only when it is true for the gold (compared with the median of the shown list, as the
   agent does). All said at once, so every threshold comes from the shown list.

Prints nDCG@20 before and after, and the share of turns where the gold moved up or down.
"""
import argparse

import numpy as np

from retrieval.context import build_turn_context
from retrieval.evaluation.metrics import get_ndcg
from retrieval.experiments.run_experiment import sessions_for

from ..handlers.critique import SPACE, critique_query, critique_ranking, make_filter, year_of
from ..musiccrs import create_services

# The turn evaluated in each session: the last one, so 7 songs were played before it.
TURN = 8
# Songs on screen, as in the agent (NUM_RECOMMENDATIONS).
NUM_SHOWN = 5
# Length of the before and after lists, as in Part 1 (nDCG@20).
TOP_K = 20


def gold_of(session, turn_number):
    """The track the real user chose at this turn: the content of its "music" message."""
    for message in session["conversations"]:
        if message["turn_number"] == turn_number and message["role"] == "music":
            return message["content"]
    return None


def closest_shown(gold_vector, shown_ids, vectors):
    """The shown song whose audio vector is closest to the gold's (the one the simulated
    user critiques with "more like #k"), or None if no shown song has a vector.

    gold [1, 0], shown A [0.6, 0.8] and B [0.8, 0.6] -> B (cosine 0.8 > 0.6)
    """
    best_id = None
    best_score = None
    for track_id in shown_ids:
        vector = vectors.vector(SPACE, track_id)
        if vector is None:
            continue
        # Both vectors have length 1, so the dot product is the cosine.
        score = float(np.dot(gold_vector, vector))
        if best_score is None or score > best_score:
            best_id = track_id
            best_score = score
    return best_id


def true_filters(gold_track, shown_ids, db):
    """The attribute critiques that are true for the gold, as the agent's filters.

    shown years [1986, 1988, 1991, 1995, 2000] (median 1991), gold from 1983
        -> year filter "less 1991" ("older")
    gold popularity equal to the shown median -> no popularity filter (neither is true)
    """
    filters = []
    for attribute in ["year", "popularity"]:
        # make_filter takes the median of the shown list; the direction is set below.
        one_filter = make_filter({"attribute": attribute, "direction": "less"}, shown_ids, db)
        if one_filter is None:
            continue

        if attribute == "year":
            gold_value = year_of(gold_track)
        else:
            gold_value = gold_track.popularity
        if gold_value is None:
            continue

        if gold_value < one_filter["value"]:
            one_filter["direction"] = "less"
        elif gold_value > one_filter["value"]:
            one_filter["direction"] = "more"
        else:
            continue
        filters.append(one_filter)
    return filters


def rank_of(track_id, track_ids):
    """The 1-based position of track_id in the list, or None if it is not there."""
    for index in range(len(track_ids)):
        if track_ids[index] == track_id:
            return index + 1
    return None


def moved(before_rank, after_rank):
    """"up", "down" or "same" for the gold's rank (None = not in the top 20).

    (None, 4) -> "up"    (12, 3) -> "up"    (3, None) -> "down"    (None, None) -> "same"
    """
    if after_rank is not None and (before_rank is None or after_rank < before_rank):
        return "up"
    if before_rank is not None and (after_rank is None or after_rank > before_rank):
        return "down"
    return "same"


def after_list(shown_ids, liked_id, filters, exclude_ids, services):
    """The agent's list after the critique: the TOP_K songs nearest to the Rocchio query
    that pass every filter, with the same functions handle_critique uses."""
    critique = {"base_ids": shown_ids, "liked": [liked_id], "disliked": [], "filters": filters}
    query = critique_query(critique, services.vectors)
    if query is None:
        return []
    ranked = critique_ranking(query, filters, exclude_ids, services.vectors, services.db, TOP_K)
    track_ids = []
    for track_id, score in ranked:
        track_ids.append(track_id)
    return track_ids


def new_result():
    """The counters of one variant."""
    return {"ndcg": [], "up": 0, "down": 0, "same": 0}


def add_result(result, gold_id, before_ids, after_ids):
    """Adds one turn to a variant: its nDCG@20 and whether the gold moved up or down."""
    result["ndcg"].append(get_ndcg([gold_id], after_ids, TOP_K))
    direction = moved(rank_of(gold_id, before_ids), rank_of(gold_id, after_ids))
    result[direction] = result[direction] + 1


def percent_text(count, total):
    """12 of 400 -> "3.0 %"."""
    return str(round(100 * count / total, 1)) + " %"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only the first N val0 sessions")
    args = parser.parse_args()

    services = create_services(use_llm=False)
    sessions = sessions_for("val0", args.limit)
    catalog = services.retriever.catalog

    accepted = 0
    no_vector = 0
    with_filters = 0
    before_ndcg = []
    like_only = new_result()
    like_and_filters = new_result()

    for session in sessions:
        ctx = build_turn_context(session, TURN, catalog)
        gold_id = gold_of(session, TURN)

        # 1. The Part 1 retriever (played songs already left out); the first 5 are shown.
        retrieved = services.retriever.retrieve(ctx, NUM_SHOWN + TOP_K)
        shown_ids = retrieved[:NUM_SHOWN]
        if gold_id in shown_ids:
            accepted = accepted + 1
            continue

        # 3. The simulated user needs the gold's audio vector to pick #k.
        gold_vector = services.vectors.vector(SPACE, gold_id)
        liked_id = None
        if gold_vector is not None:
            liked_id = closest_shown(gold_vector, shown_ids, services.vectors)
        if liked_id is None:
            no_vector = no_vector + 1
            continue

        # 2. Before: what comes next without a critique.
        before_ids = retrieved[NUM_SHOWN:]
        before_ndcg.append(get_ndcg([gold_id], before_ids, TOP_K))

        # The agent never shows a played or an already shown song again.
        exclude_ids = set(ctx.played_track_ids)
        for track_id in shown_ids:
            exclude_ids.add(track_id)

        # 4. After "more like #k".
        after_ids = after_list(shown_ids, liked_id, [], exclude_ids, services)
        add_result(like_only, gold_id, before_ids, after_ids)

        # 5. After "more like #k" + the attribute critiques true for the gold.
        filters = true_filters(services.db.get(gold_id), shown_ids, services.db)
        if len(filters) > 0:
            with_filters = with_filters + 1
        after_ids = after_list(shown_ids, liked_id, filters, exclude_ids, services)
        add_result(like_and_filters, gold_id, before_ids, after_ids)

    evaluated = len(before_ndcg)
    print("\nval0, turn " + str(TURN) + ": " + str(len(sessions)) + " sessions")
    print("  gold already among the 5 shown (accepted, skipped): " + str(accepted))
    print("  gold or shown songs without an audio vector (skipped): " + str(no_vector))
    print("  evaluated: " + str(evaluated) + " (" + str(with_filters)
          + " with at least one true attribute critique)")
    if evaluated == 0:
        return

    print("\n" + "list".ljust(34) + "nDCG@20".rjust(9) + "up".rjust(9) + "down".rjust(9)
          + "same".rjust(9))
    print("no critique (retriever, 6-25)".ljust(34)
          + str(round(float(np.mean(before_ndcg)), 4)).rjust(9))
    rows = [("more like #k", like_only), ("more like #k + year / popularity", like_and_filters)]
    for name, result in rows:
        print(name.ljust(34) + str(round(float(np.mean(result["ndcg"])), 4)).rjust(9)
              + percent_text(result["up"], evaluated).rjust(9)
              + percent_text(result["down"], evaluated).rjust(9)
              + percent_text(result["same"], evaluated).rjust(9))
    print("up / down: the gold's rank in the top 20 after the critique vs before "
          "(not in the top 20 counts as below it).")


if __name__ == "__main__":
    main()
