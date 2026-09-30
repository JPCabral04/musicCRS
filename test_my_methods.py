import time
from datasets import load_dataset
from retrieval.bm25 import BM25Retriever
from retrieval.bm25_plus import BM25PlusRetriever
from retrieval.session_cf import SameArtistScorer
from retrieval.data_loader import MusicCatalogLoader


def test_run() -> None:
    print("--- 1. Loading catalog and test dataset sample ---")
    catalog = MusicCatalogLoader()
    
    # Load a small sample of the test set for fast evaluation
    ds = load_dataset("talkpl-ai/TalkPlayData-Challenge-Dataset", split="test")
    sample_sessions = ds.select(range(10))  # Evaluate first 10 sessions

    print("\n--- 2. Initializing Retrieval Modules ---")
    print("Initializing Baseline BM25Retriever...")
    bm25_base = BM25Retriever()

    print("Initializing BM25PlusRetriever (T4)...")
    bm25_plus = BM25PlusRetriever()

    print("Initializing SameArtistScorer (T5)...")
    same_artist = SameArtistScorer(catalog)

    print("\n--- 3. Evaluating Turn-by-Turn Predictions ---")
    
    for s_idx, session in enumerate(sample_sessions):
        session_id = session["session_id"]
        print(f"\n================ Session {s_idx + 1}/{len(sample_sessions)} ({session_id}) ================")
        conversations = session["conversations"]
        
        played_tracks: list[str] = []
        user_messages: list[str] = []
        
        # Each session contains 8 turns (3 messages per turn: user, music, assistant)
        for turn_idx in range(8):
            u_msg = conversations[turn_idx * 3]["content"]
            gold_track = conversations[turn_idx * 3 + 1]["content"]  # Ground truth track ID
            
            user_messages.append(u_msg)
            history_text = " ".join(user_messages[:-1])
            
            print(f"\n Turn {turn_idx + 1}:")
            print(f"  User input: '{u_msg[:60]}...'")
            print(f"  Gold Track ID: {gold_track}")
            
            # --- 1. BM25 Baseline ---
            base_preds = bm25_base.text_to_item_retrieval(u_msg, topk=20)
            base_rank = (
                base_preds.index(gold_track) + 1
                if gold_track in base_preds
                else "Not in Top-20"
            )
            
            # --- 2. BM25Plus (T4) ---
            plus_preds_tuples = bm25_plus.score_from_parts(
                current_message=u_msg,
                history_text=history_text,
                played_track_ids=played_tracks,
                topk=20,
            )
            plus_preds = [tid for tid, _ in plus_preds_tuples]
            plus_rank = (
                plus_preds.index(gold_track) + 1
                if gold_track in plus_preds
                else "Not in Top-20"
            )

            # --- 3. SameArtistScorer (T5) ---
            artist_preds_tuples = same_artist.score(
                played_track_ids=played_tracks, topk=20
            )
            artist_preds = [tid for tid, _ in artist_preds_tuples]
            artist_rank = (
                artist_preds.index(gold_track) + 1
                if gold_track in artist_preds
                else "Not in Top-20"
            )

            print(f"    BM25 Baseline Rank : {base_rank}")
            print(f"    BM25Plus (T4) Rank  : {plus_rank}")
            print(f"    SameArtist (T5) Rank: {artist_rank}")

            # Append current gold track to history for subsequent turns
            played_tracks.append(gold_track)


if __name__ == "__main__":
    test_run()