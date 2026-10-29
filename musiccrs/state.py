"""Shared types of the Part 2 agent (T2): the dialogue state and the handler contract."""
from dataclasses import dataclass, field


@dataclass
class DialogueState:
    """Everything the agent remembers about one user (one browser tab)."""

    # Track IDs in the user's playlist, in the order they were added.
    playlist: list = field(default_factory=list)

    # Track IDs of the last list shown to the user (R4 choices or R6/R8 recommendations),
    # so that "the second one" (R7) knows what it refers to.
    pending_options: list = field(default_factory=list)

    # What the pending options are: "disambiguation", "recommendation", or None.
    pending_kind: str = None

    # Part 4 (T1), filled by handlers/shown.py.
    # The last list of recommended tracks shown, in order. Unlike pending_options it is
    # kept after "add the first two", so "more like the second one" and "why the second
    # one?" still know which list they refer to.
    last_shown: list = field(default_factory=list)

    # Every track ID shown in a recommended list or playlist in this conversation.
    # Never emptied: a track already shown is never shown again (F1.2).
    shown: set = field(default_factory=set)

    # Track ID -> why it was shown, a plain dict such as {"source": "recommend", ...}.
    # "Why this song?" (F3) builds its sentences only from these.
    signals: dict = field(default_factory=dict)

    # The current critique session (F1): the list the critiques start from, plus what was
    # liked, disliked and filtered so far. None until a recommended list is shown.
    critique: dict = None


@dataclass
class ParsedIntent:
    """What the user wants: the intent name plus its slots.

    "/add nirvana: smells like teen spirit"
        -> ParsedIntent("ADD", {"artist": "nirvana", "track": "smells like teen spirit"})
    """
    name: str     # "ADD", "REMOVE", "SHOW", "CLEAR", "RECOMMEND", "HELP", "QUIT", "UNKNOWN", ...
    slots: dict = field(default_factory=dict)


@dataclass
class Reply:
    """What a handler sends back: the text, plus any dialogue acts (e.g. OPTIONS)."""
    text: str
    dialogue_acts: list = field(default_factory=list)


@dataclass
class Services:
    """Heavy objects, created once at startup and shared by every agent (every tab)."""
    db: object          # TrackDB (T1)
    retriever: object   # FinalRetriever (from T4; None until then)
    llm: object         # openai.OpenAI, or None when the agent runs without an LLM
    # TrackVectors (Part 4, T1): metadata, audio and lyrics vectors + nearest().
    # None by default, so the checks that need no vectors can leave it out.
    vectors: object = None
