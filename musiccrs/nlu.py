"""Understanding the user's message (T2: slash commands by rules; T3 adds the LLM parser)."""


def split_artist_track(text):
    """Split "artist: track" into (artist, track). Without ": " the artist is None.

    "nirvana: smells like teen spirit"  -> ("nirvana", "smells like teen spirit")
    "smells like teen spirit"           -> (None, "smells like teen spirit")
    "nirvana: Coda: A Burn Scar"        -> ("nirvana", "Coda: A Burn Scar")
    """
    # Find the first ": " (colon + space). -1 means there is none.
    # A colon without a space ("Nu:Tone") does not count.
    position = text.find(": ")
    if position == -1:
        track = text.strip()
        return None, track

    # The artist is before the first ": ", the track is everything after it.
    artist = text[:position].strip()
    track = text[position + 2:].strip()

    # ": smells like teen spirit" has an empty artist: treat it as no artist.
    if artist == "":
        return None, track
    return artist, track
