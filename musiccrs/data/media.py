import urllib.request
import urllib.parse
import json
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.annotation import Annotation

# In-memory cache to store resolved track media: track_id -> {"cover": str|None, "preview": str|None}
_MEDIA_CACHE = {}


def get_media(track, catalog=None):
    """Retrieves cover image and 30-second audio preview URL for a track using Deezer API.

    Args:
        track: Track object or dict containing track metadata.
        catalog: Optional catalog reference to extract ISRC.

    Returns:
        dict: {"cover": str or None, "preview": str or None}
    """
    if track is None:
        return {"cover": None, "preview": None}

    # Extract track_id safely
    track_id = getattr(track, "track_id", None) or (track.get("id") or track.get("track_id") if isinstance(track, dict) else None)
    
    if track_id and track_id in _MEDIA_CACHE:
        return _MEDIA_CACHE[track_id]

    media = {"cover": None, "preview": None}

    # Extract track attributes
    if isinstance(track, dict):
        track_name = track.get("name", "")
        artists = track.get("artists", [])
    else:
        track_name = getattr(track, "name", "")
        artists = getattr(track, "artists", [])

    artist_name = artists[0] if (artists and len(artists) > 0) else ""

    # 1. Try ISRC lookup if available in catalog
    isrc = None
    if catalog and hasattr(catalog, "metadata_dict") and track_id and track_id in catalog.metadata_dict:
        meta = catalog.metadata_dict[track_id]
        isrc = meta.get("isrc") or meta.get("ISRC")

    if isrc:
        try:
            url = f"https://api.deezer.com/track/isrc:{isrc}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "id" in data:
                    media["cover"] = data.get("album", {}).get("cover_medium")
                    media["preview"] = data.get("preview")
        except Exception:
            pass

    # 2. Fallback: Search Deezer with clean search terms
    if not media["preview"] and track_name:
        # Clean title (remove '- Remastered', '(Live)', etc.)
        clean_title = track_name.split(" - ")[0].split(" (")[0].strip()
        
        # Build search queries from specific to general
        queries = []
        if artist_name:
            queries.append(f"{artist_name} {clean_title}")
        queries.append(clean_title)

        for q in queries:
            try:
                encoded_query = urllib.parse.quote(q)
                url = f"https://api.deezer.com/search?q={encoded_query}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    hits = data.get("data", [])
                    if hits:
                        first_hit = hits[0]
                        media["cover"] = media["cover"] or first_hit.get("album", {}).get("cover_medium")
                        media["preview"] = first_hit.get("preview")
                        if media["preview"]:
                            break  # Stop search once a valid preview is found
            except Exception:
                pass

    if track_id:
        _MEDIA_CACHE[track_id] = media

    return media


def media_act(track_ids, db, catalog=None):
    """Creates a DialogueAct with intent MEDIA containing cover and preview URLs for a list of tracks."""
    annotations = []
    for tid in track_ids:
        track = db.get(tid)
        if track:
            media = get_media(track, catalog)
            payload = {
                "id": tid,
                "name": getattr(track, "name", "Unknown"),
                "artist": getattr(track, "artists", ["Unknown"])[0] if getattr(track, "artists", None) else "Unknown",
                "cover": media["cover"],
                "preview": media["preview"],
            }
            anno = Annotation("track", json.dumps(payload))
            anno.slot = "track"
            anno.slot_address = "track"
            annotations.append(anno)

    return DialogueAct(intent=Intent("MEDIA"), annotations=annotations)


if __name__ == "__main__":
    from musiccrs.data.db import TrackDB
    db = TrackDB("cache/musiccrs.db")
    print("=== Testing Deezer Media Lookup (T2) ===")
    sample_tracks = db.find_by_name("Smells Like Teen Spirit")
    if sample_tracks:
        t = sample_tracks[0]
        res = get_media(t)
        print(f"Track: {t.name} — Artist: {t.artists[0] if t.artists else 'Unknown'}")
        print(f"Cover URL:   {res['cover']}")
        print(f"Preview URL: {res['preview']}")