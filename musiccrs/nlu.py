"""Understanding the user's message (T2: slash commands by rules; T3 adds the LLM parser)."""
from .prompt import PROMPT_TEMPLATE
from .state import ParsedIntent

# Every intent the agent knows. Frozen after T3: the handlers are registered under these names.
INTENTS = ("ADD", "REMOVE", "SHOW", "CLEAR", "HELP", "ASK_TRACK", "ASK_ARTIST",
           "RECOMMEND", "CREATE_PLAYLIST", "SELECT", "GREETING", "QUIT", "UNKNOWN")

# Every slot name a ParsedIntent may carry. Frozen after T3.
# track_id only comes from "/remove <id>"; the LLM never fills it.
SLOT_NAMES = ("track", "artist", "track_id", "question", "description", "selection",
              "different", "topic")

# Allowed values of the "question" slot (R5, answered from the DB in T10).
TRACK_QUESTIONS = ("artist", "album", "release_year", "duration")
ARTIST_QUESTIONS = ("track_count", "top_track", "albums", "genres")

# Allowed values of the "topic" slot of HELP (R3, T12): which feature the user asks about.
HELP_TOPICS = ("add", "remove", "show", "clear", "questions", "recommend",
               "create_playlist", "select")

# Slot values longer than this are dropped: a real title, name or description is short,
# and a long value is more likely an instruction smuggled into a slot.
MAX_SLOT_LENGTH = 200

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


def build_prompt(state):
    """The system prompt for the LLM parser, with this user's pending options filled in.

    state.pending_kind None             -> "Pending options: none"
    "recommendation", 5 pending options -> "Pending options: 5 recommended songs ..."
    The LLM needs this to know whether "the second one" is a SELECT.
    """
    count = len(state.pending_options)
    if state.pending_kind == "recommendation" and count > 0:
        pending_text = (str(count) + " recommended songs were just shown; "
                        "the user may pick some, all or none of them")
    elif state.pending_kind == "disambiguation" and count > 0:
        pending_text = (str(count) + " songs with the same name were just shown; "
                        "the user should pick one of them")
    else:
        pending_text = "none"

    prompt = PROMPT_TEMPLATE.replace("<PENDING>", pending_text)
    return prompt


def clean_slot_value(name, value, intent_name):
    """The slot value to keep, or None to drop the slot.

    ("track", "  Hotel California ", "ADD")  -> "Hotel California"
    ("track", 1999, "ADD")                   -> "1999"   (a title the model wrote as a number)
    ("different", True, "RECOMMEND")         -> True
    ("question", "album", "ASK_TRACK")       -> "album"
    ("question", "lyrics", "ASK_TRACK")      -> None     (not an allowed question)
    ("question", "album", "ASK_ARTIST")      -> None     (album is a track question)
    ("topic", "remove", "HELP")              -> "remove"
    ("track", "", "ADD")                     -> None
    """
    # "different" is a yes/no slot: keep it only when it is true.
    if name == "different":
        if value is True or value == "true":
            return True
        return None

    # Every other slot is text. The model may write a title like 1999 as a number.
    # (bool is checked first because Python counts True and False as numbers too.)
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or isinstance(value, float):
        value = str(value)
    if not isinstance(value, str):
        return None

    value = value.strip()
    if value == "" or len(value) > MAX_SLOT_LENGTH:
        return None

    # Slots with a fixed list of allowed values.
    if name == "question":
        if intent_name == "ASK_TRACK" and value in TRACK_QUESTIONS:
            return value
        if intent_name == "ASK_ARTIST" and value in ARTIST_QUESTIONS:
            return value
        return None
    if name == "topic":
        if value in HELP_TOPICS:
            return value
        return None

    return value


def to_parsed_intent(data):
    """Turn the LLM's JSON object into a ParsedIntent, keeping only what is allowed.

    {"intent": "ADD", "slots": {"track": "hotel california", "artist": "eagles"}}
        -> ParsedIntent("ADD", {"track": "hotel california", "artist": "eagles"})
    {"intent": "PLAY_MUSIC", "slots": {}}            -> ParsedIntent("UNKNOWN", {})
    {"intent": "add", "slots": {"mood": "happy"}}    -> ParsedIntent("ADD", {})
    None                                             -> ParsedIntent("UNKNOWN", {})
    """
    if not isinstance(data, dict):
        return ParsedIntent("UNKNOWN", {})

    # The intent must be one of INTENTS. "add " or "Add" is accepted as "ADD".
    intent_name = data.get("intent")
    if not isinstance(intent_name, str):
        return ParsedIntent("UNKNOWN", {})
    intent_name = intent_name.strip().upper()
    if intent_name not in INTENTS:
        return ParsedIntent("UNKNOWN", {})

    raw_slots = data.get("slots")
    if not isinstance(raw_slots, dict):
        raw_slots = {}

    slots = {}
    for name in raw_slots:
        # Unknown slot names are dropped. track_id only ever comes from "/remove <id>".
        if name not in SLOT_NAMES:
            continue
        if name == "track_id":
            continue
        value = clean_slot_value(name, raw_slots[name], intent_name)
        if value is not None:
            slots[name] = value

    return ParsedIntent(intent_name, slots)
