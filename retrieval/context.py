"""Shared experiment harness: per-turn context builder (T2).

Turns a raw session into one `TurnContext` per turn: everything a scorer may
know when predicting that turn. The cut-off is the baseline's own rule
(`_build_retrieval_input`): stop before the target turn's `music` message,
which is the gold track. Every scorer reads the same `TurnContext`, so the
leak-safe boundary lives in one place. It has no dataset-only fields, so the
Part 2 agent can build one from a live conversation.

Usage (self-check on the first sessions of a split):
    python -m retrieval.context --split test --n_sessions 3
    python -m retrieval.context --split train --n_sessions 3
"""
import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from datasets import load_dataset

from .analysis.same_artist_stats import _played_tracks_by_turn
from .bm25 import DEFAULT_CORPUS_TYPES
from .data_loader import MusicCatalogLoader
from .evaluation.make_ground_truth import DEFAULT_DATASET_NAME
from .run_bm25_baseline import NUM_TURNS, _build_retrieval_input


@dataclass(frozen=True)
class TurnContext:
    """Everything a scorer may know when predicting one turn.

    Built only from messages before the target turn's music/assistant messages.
    Tuples (not lists), so no scorer can change the context it shares with the others.
    """
    session_id: str
    turn_number: int                      # 1..8
    current_message: str                  # this turn's user message
    # earlier (role, content); roles "user"/"music"/"assistant"
    history: tuple[tuple[str, str], ...]
    # earlier `music` contents (track IDs), oldest first
    played_track_ids: tuple[str, ...]
    baseline_query: str                   # exactly what _build_retrieval_input returns


@dataclass(frozen=True)
class SessionPolicy:
    """Dataset-pattern rules, kept apart from the facts in TurnContext.

    Part 1 uses the defaults. In Part 2 the agent sets them per turn from the
    user's intent ("play that again" -> exclude_played=False, "something
    different" -> use_same_artist=False). Applied only in fusion and finalize_top_k.
    """
    exclude_played: bool = True   # gold is never a played track (dataset pattern)
    use_same_artist: bool = True  # 65% of golds share an artist with a played track


class Scorer(Protocol):
    """Contract every retrieval component follows, so fusion and the runner can swap them."""
    name: str

    def score(self, ctx: TurnContext, k: int = 200) -> list[tuple[str, float]]:
        """Top-k (track_id, score), best first, unique IDs.

        Played tracks are NOT removed here (SessionPolicy does that once, in
        fusion and finalize_top_k). May return fewer than k items, or none
        (e.g. a session scorer at turn 1).
        """
        ...


def load_sessions(split: str, session_ids: list[str] | None = None) -> list[dict]:
    """Loads `train` or `test` sessions, optionally only the given IDs (in that order)."""
    dataset = load_dataset(DEFAULT_DATASET_NAME, split=split)
    if session_ids is None:
        return list(dataset)
    by_id = {session["session_id"]: session for session in dataset}
    missing = [sid for sid in session_ids if sid not in by_id]
    if missing:
        raise KeyError(
            f"{len(missing)} session IDs not in {split}, e.g. {missing[:3]}")
    return [by_id[sid] for sid in session_ids]


def build_turn_context(session: dict, turn_number: int,
                       catalog: MusicCatalogLoader) -> TurnContext:
    """Builds the TurnContext for one (session, turn)."""
    conversations = session["conversations"]
    history, played, current_message = [], [], None
    for message in conversations:
        # Same cut-off as _build_retrieval_input: nothing after this turn's user message.
        if message["turn_number"] > turn_number:
            break
        if message["turn_number"] == turn_number and message["role"] != "user":
            break
        role, content = message["role"], message["content"]
        if message["turn_number"] == turn_number:
            current_message = content
            continue
        history.append((role, content))
        if role == "music":
            played.append(content)
    if current_message is None:
        raise ValueError(
            f"no user message for turn {turn_number} in {session['session_id']}")
    return TurnContext(
        session_id=session["session_id"],
        turn_number=turn_number,
        current_message=current_message,
        history=tuple(history),
        played_track_ids=tuple(played),
        baseline_query=_build_retrieval_input(
            conversations, turn_number, catalog, DEFAULT_CORPUS_TYPES),
    )


def iter_turn_contexts(sessions: list[dict],
                       catalog: MusicCatalogLoader) -> Iterator[TurnContext]:
    """Yields the 8 TurnContexts of every session, in order."""
    for session in sessions:
        for turn_number in range(1, NUM_TURNS + 1):
            yield build_turn_context(session, turn_number, catalog)


def finalize_top_k(ranked: list[tuple[str, float]], played: tuple[str, ...],
                   topk: int = 20, exclude_played: bool = True) -> list[str]:
    """Drops duplicates (and played tracks if `exclude_played`), keeps order, returns at most `topk` IDs.

    The only place that cuts a ranking to the final top-k.
    """
    skip = set(played) if exclude_played else set()
    result = []
    for track_id, _ in ranked:
        if track_id in skip:
            continue
        skip.add(track_id)  # later duplicates are skipped too
        result.append(track_id)
        if len(result) == topk:
            break
    return result


def _check_finalize() -> None:
    """Asserts finalize_top_k on a toy ranking: duplicates, played tracks and the cut."""
    ranked = [("a", 5.0), ("p", 4.0), ("b", 3.0), ("a", 2.0), ("c", 1.0)]
    assert finalize_top_k(ranked, ("p",), topk=20) == ["a", "b", "c"]
    assert finalize_top_k(ranked, ("p",), topk=2) == ["a", "b"]
    assert finalize_top_k(ranked, ("p",), topk=20, exclude_played=False) == [
        "a", "p", "b", "c"]
    assert finalize_top_k([], ("p",)) == []


def _check_session(session: dict, catalog: MusicCatalogLoader) -> None:
    """Asserts the leak-safe boundary on every turn of one session."""
    all_played = _played_tracks_by_turn(session)  # independent implementation
    for ctx in iter_turn_contexts([session], catalog):
        t = ctx.turn_number
        gold = session["conversations"][3 *
                                        # read here only
                                        (t - 1) + 1]["content"]
        assert len(ctx.history) == 3 * (t - 1), (t, len(ctx.history))
        assert len(ctx.played_track_ids) == t - 1, (t, ctx.played_track_ids)
        assert list(ctx.played_track_ids) == all_played[:t - 1], t
        assert gold not in ctx.played_track_ids, (t, gold)
        assert ctx.baseline_query.endswith(f"user: {ctx.current_message}"), t


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Self-check of the context builder")
    parser.add_argument("--split", default="test")
    parser.add_argument("--n_sessions", type=int, default=3)
    args = parser.parse_args()

    _check_finalize()
    catalog = MusicCatalogLoader()
    sessions = load_sessions(args.split)[:args.n_sessions]
    for session in sessions:
        _check_session(session, catalog)

    for t in (1, 2, NUM_TURNS):
        ctx = build_turn_context(sessions[0], t, catalog)
        print(f"turn {t}: {len(ctx.history)} history messages, "
              f"played = {ctx.played_track_ids}, "
              f"current = {ctx.current_message[:60]!r}")
    print(f"[{args.split}] all checks passed on {len(sessions)} sessions")


if __name__ == "__main__":
    main()
