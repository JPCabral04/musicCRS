"""Understanding the user's message (T2: slash commands by rules; T3 adds the LLM parser)."""
from ..handlers.selection import rule_indices
from ..llm import ask_json
from .prompt import PROMPT_TEMPLATE
from ..state import ParsedIntent

# Every intent the agent knows: the handlers are registered under these names.
# Part 2 (frozen after T3), then the four Part 4 intents (frozen after Part 4 T1).
INTENTS = ("ADD", "REMOVE", "SHOW", "CLEAR", "HELP", "ASK_TRACK", "ASK_ARTIST",
           "RECOMMEND", "CREATE_PLAYLIST", "SELECT", "GREETING", "QUIT", "UNKNOWN",
           "CRITIQUE", "SOUNDS_LIKE", "LYRICS_SEARCH", "EXPLAIN")

# Every slot name a ParsedIntent may carry. Part 2 slots first, then the Part 4 ones.
# Two of them are set by our code only, never by the LLM:
#   track_id: from "/remove <id>" (the remove button of the playlist panel);
#   text:     the user's own message, on UNKNOWN.
# Part 4 slots:
#   like, dislike:   CRITIQUE, one shown track as a number or a name ("2", "bon jovi");
#   attribute:       CRITIQUE, one of CRITIQUE_ATTRIBUTES;
#   direction:       CRITIQUE, one of CRITIQUE_DIRECTIONS ("older" = year, less);
#   tag:             CRITIQUE with attribute "tag" ("acoustic");
#   theme:           LYRICS_SEARCH, what the songs are about ("leaving home");
#   option:          EXPLAIN, one shown track as a number or a name.
# SOUNDS_LIKE reuses track and artist.
SLOT_NAMES = ("track", "artist", "track_id", "question", "description", "selection",
              "different", "topic", "text",
              "like", "dislike", "attribute", "direction", "tag", "theme", "option")

# Allowed values of the CRITIQUE slots "attribute" and "direction" (Part 4, F1.2).
CRITIQUE_ATTRIBUTES = ("year", "popularity", "tag")
CRITIQUE_DIRECTIONS = ("more", "less")

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


def parse_critique_command(rest):
    """The slots of "/critique <attribute> <direction> [tag]" (Part 4, F1.2).

    "year less"          -> {"attribute": "year", "direction": "less"}
    "tag more acoustic"  -> {"attribute": "tag", "direction": "more", "tag": "acoustic"}
    "tag less hard rock" -> {"attribute": "tag", "direction": "less", "tag": "hard rock"}
    "colour more"        -> {"direction": "more"}  (not an allowed attribute: dropped)
    """
    # split(maxsplit=2) cuts at the first two runs of spaces only, so a tag with
    # spaces stays in one piece: "tag less hard rock" -> ["tag", "less", "hard rock"].
    parts = rest.split(maxsplit=2)

    raw_slots = {}
    if len(parts) >= 1:
        raw_slots["attribute"] = parts[0]
    if len(parts) >= 2:
        raw_slots["direction"] = parts[1]
    if len(parts) >= 3:
        raw_slots["tag"] = parts[2]

    # The same checks as for the LLM's slots: wrong values are dropped.
    slots = {}
    for name in raw_slots:
        value = clean_slot_value(name, raw_slots[name], "CRITIQUE")
        if value is not None:
            slots[name] = value
    return slots


def parse_command(text):
    """Turn a slash command into a ParsedIntent, by rules (no LLM).

    Returns None when the text is not a slash command, so the caller can
    send it to the LLM parser instead (T3).

    "/add nirvana: smells like teen spirit"
        -> ParsedIntent("ADD", {"artist": "nirvana", "track": "smells like teen spirit"})
    "/remove 0b9aea6c" -> ParsedIntent("REMOVE", {"track_id": "0b9aea6c"})
    "/list"            -> ParsedIntent("SHOW", {})
    "add some nirvana" -> None

    Part 4 commands:
    "/like 2"             -> ParsedIntent("CRITIQUE", {"like": "2"})
    "/dislike bon jovi"   -> ParsedIntent("CRITIQUE", {"dislike": "bon jovi"})
    "/critique year less" -> ParsedIntent("CRITIQUE", {"attribute": "year", "direction": "less"})
    "/sounds nirvana: in bloom"
                          -> ParsedIntent("SOUNDS_LIKE", {"artist": "nirvana", "track": "in bloom"})
    "/about leaving home" -> ParsedIntent("LYRICS_SEARCH", {"theme": "leaving home"})
    "/why 2"              -> ParsedIntent("EXPLAIN", {"option": "2"})
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

    # /select <choice>: sent by the option buttons of the chat (R4, R6, R8 lists).
    # "/select 2" -> ParsedIntent("SELECT", {"selection": "2"}), read by the T11 rules.
    if command == "/select":
        slots = {}
        if rest != "":
            slots["selection"] = rest
        return ParsedIntent("SELECT", slots)

    # Part 4. /like <n or name> and /dislike <n or name>: example critiques (F1.1).
    if command == "/like" or command == "/dislike":
        slots = {}
        if rest != "":
            slot_name = command[1:]          # "/like" -> "like"
            slots[slot_name] = rest
        return ParsedIntent("CRITIQUE", slots)

    # /critique <attribute> <direction> [tag]: attribute critiques (F1.2).
    if command == "/critique":
        slots = parse_critique_command(rest)
        return ParsedIntent("CRITIQUE", slots)

    # /sounds [artist]: [track]: songs that sound like a track (F2.1).
    if command == "/sounds":
        slots = {}
        if rest != "":
            artist, track = split_artist_track(rest)
            slots["track"] = track
            if artist is not None:
                slots["artist"] = artist
        return ParsedIntent("SOUNDS_LIKE", slots)

    # /about <theme>: songs whose lyrics are about a theme (F2.2).
    if command == "/about":
        slots = {}
        if rest != "":
            slots["theme"] = rest
        return ParsedIntent("LYRICS_SEARCH", slots)

    # /why <n or name>: why a shown track was recommended (F3).
    if command == "/why":
        slots = {}
        if rest != "":
            slots["option"] = rest
        return ParsedIntent("EXPLAIN", slots)

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
    ("like", 2, "CRITIQUE")                  -> "2"
    ("attribute", "Year", "CRITIQUE")        -> "year"
    ("direction", "older", "CRITIQUE")       -> None     (must be "more" or "less")
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
    if name == "attribute":
        value = value.lower()
        if value in CRITIQUE_ATTRIBUTES:
            return value
        return None
    if name == "direction":
        value = value.lower()
        if value in CRITIQUE_DIRECTIONS:
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
        # Unknown slot names are dropped, and so are the two slots only our code sets.
        if name not in SLOT_NAMES:
            continue
        if name == "track_id" or name == "text":
            continue
        value = clean_slot_value(name, raw_slots[name], intent_name)
        if value is not None:
            slots[name] = value

    return ParsedIntent(intent_name, slots)


def parse(text, state, llm):
    """Understand one user message: slash commands by rules, everything else by the LLM.

    "/add nirvana: smells like teen spirit"
        -> ParsedIntent("ADD", {"artist": "nirvana", "track": "smells like teen spirit"})  (no LLM)
    "add hotel california by the eagles"
        -> ParsedIntent("ADD", {"track": "hotel california", "artist": "the eagles"})    (1 LLM call)
    "what's the weather?"
        -> ParsedIntent("UNKNOWN", {"text": "what's the weather?"})
    "the first one", with 2 options pending
        -> ParsedIntent("SELECT", {"selection": "the first one"})                       (no LLM)
    any free text when llm is None (no API key)
        -> ParsedIntent("UNKNOWN", {"text": ...})
    """
    # 1. Slash commands (the simulator and the UI buttons): rules, no LLM.
    parsed = parse_command(text)
    if parsed is not None:
        return parsed

    # 2. Options are pending and the R7 rules understand every word ("the first one",
    #    "all of them", "none", "1 and 3"): a selection, no LLM. Anything else
    #    ("all except the one by Metallica", "show my playlist") still goes to the LLM.
    if len(state.pending_options) > 0:
        indices = rule_indices(text, len(state.pending_options))
        if indices is not None:
            return ParsedIntent("SELECT", {"selection": text})

    # 3. Without an LLM client, free text cannot be understood.
    if llm is None:
        return ParsedIntent("UNKNOWN", {"text": text})

    # 4. One LLM call (two if the first answer has no valid JSON).
    #    The system message holds the rules; the user message is only the user's text.
    system_message = {"role": "system", "content": build_prompt(state)}
    user_message = {"role": "user", "content": text}
    data = ask_json(llm, [system_message, user_message])

    # 5. Keep only allowed intents and slots. A failed call (data is None) gives UNKNOWN.
    parsed = to_parsed_intent(data)

    # On UNKNOWN, keep the user's own words, as parse_command does for "/play".
    if parsed.name == "UNKNOWN":
        parsed.slots["text"] = text
    return parsed
