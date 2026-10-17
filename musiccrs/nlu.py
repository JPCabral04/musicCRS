"""Understanding the user's message (T2: slash commands by rules; T3 adds the LLM parser)."""
from .state import ParsedIntent

# Slash commands that take no argument: command -> intent name.
SIMPLE_COMMANDS = {
    "/list": "SHOW",
    "/clear": "CLEAR",
    "/recommend": "RECOMMEND",
    "/help": "HELP",
    "/quit": "QUIT",
}


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


def parse_command(text):
    """Turn a slash command into a ParsedIntent, by rules (no LLM).

    Returns None when the text is not a slash command, so the caller can
    send it to the LLM parser instead (T3).

    "/add nirvana: smells like teen spirit"
        -> ParsedIntent("ADD", {"artist": "nirvana", "track": "smells like teen spirit"})
    "/remove 0b9aea6c" -> ParsedIntent("REMOVE", {"track_id": "0b9aea6c"})
    "/list"            -> ParsedIntent("SHOW", {})
    "add some nirvana" -> None
    """
    text = text.strip()
    if not text.startswith("/"):
        return None

    # Split into the command word and the rest:
    # "/add nirvana: smells like teen spirit" -> "/add" and "nirvana: smells like teen spirit"
    position = text.find(" ")
    if position == -1:
        command = text.lower()
        rest = ""
    else:
        command = text[:position].lower()
        rest = text[position + 1:].strip()

    # /add [artist]: [track] and /del [artist]: [track]
    if command == "/add" or command == "/del":
        if command == "/add":
            intent_name = "ADD"
        else:
            intent_name = "REMOVE"

        slots = {}
        if rest != "":
            artist, track = split_artist_track(rest)
            slots["track"] = track
            if artist is not None:
                slots["artist"] = artist
        return ParsedIntent(intent_name, slots)

    # /remove <track_id>: sent by the remove button of the playlist panel (T5).
    if command == "/remove":
        slots = {}
        if rest != "":
            slots["track_id"] = rest
        return ParsedIntent("REMOVE", slots)

    # Commands without an argument: /list, /clear, /recommend, /help, /quit
    if command in SIMPLE_COMMANDS:
        intent_name = SIMPLE_COMMANDS[command]
        return ParsedIntent(intent_name, {})

    # A slash command we do not know, e.g. "/play".
    return ParsedIntent("UNKNOWN", {"text": text})
