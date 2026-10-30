"""Album covers and 30-second previews from the Deezer search API (Part 4, T2).

    python -m musiccrs.data.media    # prints the cover and preview of Smells Like Teen Spirit

No API key is needed. Each track is looked up at most once per server run (cached by track ID).
"""
import json
import time
import urllib.parse
import urllib.request

from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation

_INTENT_MEDIA = Intent("MEDIA")

# Seconds to wait for one Deezer answer.
TIMEOUT_S = 2.0

# Seconds one media_act may spend on Deezer: the reply must come back within 3-5 s.
# Tracks left after that get no cover in this reply (they are looked up next time).
MEDIA_BUDGET_S = 2.0

# Track ID -> {"cover": url or None, "preview": url or None}.
_MEDIA_CACHE = {}


def search_deezer(query):
    """The first Deezer hit for a search text, or None (no hit, no network, a timeout).

    "Nirvana Smells Like Teen Spirit" -> {"album": {"cover_medium": "https://..."},
                                          "preview": "https://...mp3", ...}
    """
    url = "https://api.deezer.com/search?q=" + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        # OSError covers no network and timeouts; ValueError a broken JSON answer.
        return None
    hits = data.get("data", [])
    if len(hits) == 0:
        return None
    return hits[0]


def get_media(track):
    """Cover and preview URLs of a catalog track, from Deezer.

    Smells Like Teen Spirit (Nirvana) -> {"cover": "https://...jpg", "preview": "https://...mp3"}
    Not found -> {"cover": None, "preview": None}
    """
    if track.track_id in _MEDIA_CACHE:
        return _MEDIA_CACHE[track.track_id]

    # "Smells Like Teen Spirit - Remastered (2021)" -> "Smells Like Teen Spirit"
    title = track.name.split(" - ")[0]
    title = title.split(" (")[0].strip()

    media = {"cover": None, "preview": None}
    # Artist and title first; the title alone when Deezer finds nothing with the artist.
    queries = [track.artists[0] + " " + title, title]
    for query in queries:
        hit = search_deezer(query)
        if hit is None:
            continue
        media["cover"] = hit.get("album", {}).get("cover_medium")
        media["preview"] = hit.get("preview")
        if media["preview"]:
            break

    _MEDIA_CACHE[track.track_id] = media
    return media


def media_act(track_ids, db):
    """Cover and preview of each shown song, as one MEDIA dialogue act (chat cards, T4).

    One annotation per song, in the order shown. Its value is JSON text:
    SlotValueAnnotation("track", '{"id": "e9383e0c-...", "name": "Smells Like Teen Spirit",
                                   "artist": "Nirvana", "cover": "https://...jpg",
                                   "preview": "https://...mp3"}')
    Lookups are one after the other (no parallel requests) and stop after MEDIA_BUDGET_S.
    """
    start = time.perf_counter()
    annotations = []
    for track_id in track_ids:
        track = db.get(track_id)
        seconds = time.perf_counter() - start
        if track_id in _MEDIA_CACHE or seconds < MEDIA_BUDGET_S:
            media = get_media(track)
        else:
            media = {"cover": None, "preview": None}
        track_info = {
            "id": track_id,
            "name": track.name,
            "artist": track.artists[0],
            "cover": media["cover"],
            "preview": media["preview"],
        }
        annotations.append(SlotValueAnnotation("track", json.dumps(track_info)))
    return DialogueAct(intent=_INTENT_MEDIA, annotations=annotations)


if __name__ == "__main__":
    from .db import TrackDB

    db = TrackDB()
    track = db.find_by_name("smells like teen spirit", "nirvana")[0]
    start = time.perf_counter()
    media = get_media(track)
    ms = round((time.perf_counter() - start) * 1000)
    print(track.name + " by " + track.artists[0] + " (" + str(ms) + " ms)")
    print("Cover:   " + str(media["cover"]))
    print("Preview: " + str(media["preview"]))
