"""Verification check for SOUNDS_LIKE (T6) and LYRICS_SEARCH (T8)."""

import numpy as np
from retrieval import MusicCatalogLoader
from musiccrs.state import DialogueState, Services
from musiccrs.data.vectors import TrackVectors
from musiccrs.data.db import TrackDB
from musiccrs.checks.check_lyrics import check_lyrics_vectors
from musiccrs.handlers.similar import handle_sounds_like, handle_lyrics_search


class MockParsed:
    def __init__(self, slots):
        self.slots = slots


def test_similar_handlers():
    print("=== Testing T6 (Sounds Like) and T8 (Lyrics Search) ===")

    # 1. Load catalog track IDs (must be exactly 47,071)
    catalog_loader = MusicCatalogLoader()
    if hasattr(catalog_loader, "all_tracks"):
        tracks_data = catalog_loader.all_tracks
        if isinstance(tracks_data, dict):
            track_ids = list(tracks_data.keys())
        else:
            track_ids = [t["track_id"] if isinstance(t, dict) else getattr(t, "track_id") for t in tracks_data]
    elif hasattr(catalog_loader, "metadata_dict"):
        track_ids = list(catalog_loader.metadata_dict.keys())
    else:
        raw = getattr(catalog_loader, "tracks", getattr(catalog_loader, "data", []))
        track_ids = [t["track_id"] if isinstance(t, dict) else getattr(t, "track_id", t) for t in raw]

    # 2. Get valid lyrics_ok mask
    _, lyrics_ok = check_lyrics_vectors("cache/musiccrs.db")

    # 3. Database
    db = TrackDB("cache/musiccrs.db")

    # 4. Mock Scorer & Retriever
    class MockDenseScorer:
        def encode_queries(self, texts):
            v = np.random.randn(len(texts), 1024).astype(np.float32)
            return v / np.linalg.norm(v, axis=1, keepdims=True)

    class MockFusion:
        scorers = {"dense": MockDenseScorer()}

    class MockRetriever:
        fusion = MockFusion()

    # 5. Initialize TrackVectors using confirmed signature
    vectors = TrackVectors(track_ids, None, lyrics_ok)

    services = Services(
        db=db,
        retriever=MockRetriever(),
        llm=None,
        vectors=vectors,
    )
    state = DialogueState()

    # Test T6
    print("\n--- Testing handle_sounds_like ('Numb') ---")
    parsed_t6 = MockParsed({"track": "Numb", "artist": "Linkin Park"})
    act_t6 = handle_sounds_like(parsed_t6, state, services)
    print("Response Intent:", getattr(act_t6.intent, "label", str(act_t6.intent)))
    for anno in act_t6.annotations:
        print("  - Slot:", anno.slot, "| Value:", anno.value)

    # Test T8
    print("\n--- Testing handle_lyrics_search ('leaving home') ---")
    parsed_t8 = MockParsed({"theme": "leaving home"})
    act_t8 = handle_lyrics_search(parsed_t8, state, services)
    print("Response Intent:", getattr(act_t8.intent, "label", str(act_t8.intent)))
    for anno in act_t8.annotations:
        print("  - Slot:", anno.slot, "| Value:", anno.value)


if __name__ == "__main__":
    test_similar_handlers()