"""
Track Resolver (T6) - Alejandro
Given a loose track reference (and optionally an artist), finds the matching
tracks in the library database (TrackDB).
"""

import re
from difflib import SequenceMatcher
from .db import TrackDB, Track, normalize, base_name

def _extract_artist_from_track_string(track_str: str) -> tuple[str, str | None]:
    """
    Extracts title and artist if the 'track' slot contains patterns like 'song by artist'.
    Example: 'its my life by bon jovi' -> ('its my life', 'bon jovi')
    """
    if not track_str:
        return "", None
    
    patterns = [
        r"^(.*?)\s+(?:by|de)\s+(.*)$",
        r"^(.*?)\s+-\s+(.*)$"
    ]
    for pattern in patterns:
        match = re.match(pattern, track_str, re.IGNORECASE)
        if match:
            t_part = match.group(1).strip()
            a_part = match.group(2).strip()
            if t_part and a_part:
                return t_part, a_part

    return track_str, None


def _similarity_score(query: str, target: str) -> float:
    """Calculates similarity ratio between two normalized strings (0.0 to 1.0)."""
    if not query or not target:
        return 0.0
    return SequenceMatcher(None, normalize(query), normalize(target)).ratio()


def resolve(db: TrackDB, track: str | None, artist: str | None = None) -> list[Track]:
    """
    Resolves a loose query into a ranked list of candidate Track objects.
    
    Strategy:
    1. If no track title is provided but an artist is -> return artist's tracks.
    2. Extract artist if inline inside 'track' slot ("its my life by bon jovi").
    3. Look for exact matches in DB (db.find_by_name).
    4. Fall back to FTS5 fuzzy match (db.fuzzy_candidates) and rescore with difflib.
    5. Filter out low-quality fuzzy matches.
    """
    if not track and not artist:
        return []

    # Clean inline "X by Y" if parser did not split the artist
    if track and not artist:
        extracted_track, extracted_artist = _extract_artist_from_track_string(track)
        if extracted_artist:
            track = extracted_track
            artist = extracted_artist

    # Only artist was provided
    if not track and artist:
        return db.artist_tracks(artist)

    track_norm = normalize(track or "")
    artist_norm = normalize(artist) if artist else None

    # 1. Exact match in DB (normalized name and base_name)
    exact_matches = db.find_by_name(track_norm, artist_norm)
    if exact_matches:
        return exact_matches

    # 2. Fuzzy match / FTS5 candidates
    query_text = f"{track_norm} {artist_norm}" if artist_norm else track_norm
    candidates = db.fuzzy_candidates(query_text, limit=50)

    if not candidates:
        return []

    # 3. Rescore candidates using difflib sequence matching
    scored_candidates: list[tuple[float, Track]] = []
    
    for cand in candidates:
        t_score = _similarity_score(track_norm, cand.name)
        b_score = _similarity_score(track_norm, base_name(cand.name))
        best_title_score = max(t_score, b_score)

        if artist_norm:
            a_scores = [_similarity_score(artist_norm, a) for a in cand.artists]
            best_artist_score = max(a_scores) if a_scores else 0.0
            combined_score = (best_title_score * 0.6) + (best_artist_score * 0.4)
        else:
            combined_score = best_title_score

        # Minimum threshold to avoid false positives
        if combined_score >= 0.45 or best_title_score >= 0.6:
            scored_candidates.append((combined_score, cand))

    # Sort descending by similarity score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Deduplicate candidate tracks by ID
    seen_ids = set()
    result = []
    for score, cand in scored_candidates:
        if cand.track_id not in seen_ids:
            seen_ids.add(cand.track_id)
            result.append(cand)

    return result