"""MusicCRS conversational agent.

Run from the repo root as a module (so the package imports work):
    python -m musiccrs.musiccrs
"""

import json

from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.platforms import FlaskSocketPlatform
from openai import OpenAI

from .db import TrackDB
from .handlers_playlist import handle_add, handle_clear, handle_remove, handle_show
from .nlu import parse_command
from .state import DialogueState, ParsedIntent, Reply, Services

LLM_BASE_URL = "https://openwebui.ux.uis.no/api"
LLM_MODEL = "gorina10.gemma-4-31b"
LLM_API_KEY = "SET YOUR API KEY HERE"

_INTENT_OPTIONS = Intent("OPTIONS")
_INTENT_PLAYLIST = Intent("PLAYLIST")

# Intent name -> handler function. Every handler is handler(parsed, state, services) -> Reply.
# Each new task adds its own lines (RECOMMEND in T4, HELP in T12, ...).
HANDLERS = {
    "ADD": handle_add,
    "REMOVE": handle_remove,
    "SHOW": handle_show,
    "CLEAR": handle_clear,
}

# Shown when the agent cannot handle a message (until the HELP handler of T12 exists).
COMMANDS_TEXT = ("You can use: /add artist: track, /del artist: track, "
                 "/list, /clear, /quit.")

# The heavy objects (DB, retriever, LLM client), shared by every agent.
# Set once in __main__ below, before the server accepts any connection.
SERVICES = None


def create_services(use_llm=True):
    """Load the heavy objects once, at startup."""
    db = TrackDB()

    llm = None
    if use_llm:
        llm = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    # The retriever (FinalRetriever) is added in T4.
    return Services(db=db, retriever=None, llm=llm)


def playlist_act(state, db):
    """The whole playlist as one PLAYLIST dialogue act, for the playlist panel (R1).

    One annotation per track, in playlist order. Its value is JSON text:
    SlotValueAnnotation("track", '{"id": "e9383e0c-...", "name": "Smells Like Teen Spirit",
                                   "artist": "Nirvana", "duration_ms": 301920}')
    An empty playlist gives an act with no annotations, so the panel shows nothing.
    """
    annotations = []
    for track_id in state.playlist:
        track = db.get(track_id)
        track_info = {
            "id": track.track_id,
            "name": track.name,
            "artist": track.artists[0],
            "duration_ms": track.duration_ms,
        }
        value = json.dumps(track_info)
        annotations.append(SlotValueAnnotation("track", value))
    return DialogueAct(intent=_INTENT_PLAYLIST, annotations=annotations)


class MusicCRS(Agent):
    def __init__(self, agent_id="MusicCRS"):
        """One agent per browser tab.

        DialogueKit creates the agent on every new connection as
        MusicCRS("MusicCRS"), so the first argument is the agent ID.
        """
        super().__init__(id=agent_id)

        if SERVICES is None:
            raise RuntimeError("Services are not loaded. Start the agent with: "
                               "python -m musiccrs.musiccrs")
        self.services = SERVICES      # shared by every tab
        self.state = DialogueState()  # this tab's own playlist

    def welcome(self) -> None:
        """Sends the agent's welcome message."""
        utterance = AnnotatedUtterance(
            "Hello, I'm MusicCRS. I can build a playlist with you and recommend songs. "
            "Type /help to see what I can do.",
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def goodbye(self) -> None:
        """Quits the conversation."""
        utterance = AnnotatedUtterance(
            "It was nice talking to you. Bye",
            dialogue_acts=[DialogueAct(intent=self.stop_intent)],
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def receive_utterance(self, utterance: Utterance) -> None:
        """Gets called each time there is a new user utterance.

        parse -> handler from HANDLERS -> reply text + a PLAYLIST act if the playlist changed.
        """
        # 1. Understand the message. Slash commands only for now; T3 adds the LLM parser.
        parsed = parse_command(utterance.text)
        if parsed is None:
            parsed = ParsedIntent("UNKNOWN", {"text": utterance.text})

        if parsed.name == "QUIT":
            self.goodbye()
            return

        # 2. Copy the playlist, to see afterwards whether the handler changed it.
        playlist_before = list(self.state.playlist)

        # 3. Run the handler for this intent, or a fallback reply.
        if parsed.name in HANDLERS:
            handler = HANDLERS[parsed.name]
            reply = handler(parsed, self.state, self.services)
        elif parsed.name == "UNKNOWN":
            reply = Reply("Sorry, I did not understand that. " + COMMANDS_TEXT)
        else:
            reply = Reply("Sorry, I cannot do that yet. " + COMMANDS_TEXT)

        # 4. Send the whole playlist to the panel when it changed, or when the user asked to see it.
        dialogue_acts = list(reply.dialogue_acts)
        playlist_changed = self.state.playlist != playlist_before
        if playlist_changed or parsed.name == "SHOW":
            dialogue_acts.append(playlist_act(self.state, self.services.db))

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                reply.text,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )


if __name__ == "__main__":
    # Load the DB and the LLM client once, before any user connects.
    SERVICES = create_services()
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
