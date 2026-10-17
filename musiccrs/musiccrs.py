"""MusicCRS conversational agent.

Run from the repo root as a module (so the package imports work):
    python -m musiccrs.musiccrs
"""

import json

import ollama
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.platforms import FlaskSocketPlatform

from .db import TrackDB
from .state import DialogueState, Services

OLLAMA_HOST = "https://ollama.ux.uis.no"
OLLAMA_MODEL = "llama3.3:70b"
OLLAMA_API_KEY = "SET YOUR API KEY HERE"

_INTENT_OPTIONS = Intent("OPTIONS")
_INTENT_PLAYLIST = Intent("PLAYLIST")

# The heavy objects (DB, retriever, LLM client), shared by every agent.
# Set once in __main__ below, before the server accepts any connection.
SERVICES = None


def create_services(use_llm=True):
    """Load the heavy objects once, at startup."""
    db = TrackDB()

    llm = None
    if use_llm:
        llm = ollama.Client(
            host=OLLAMA_HOST,
            headers={"Authorization": "Bearer " + OLLAMA_API_KEY},
        )

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

        For now the agent only understands specific command.

        Args:
            utterance: User utterance.
        """
        response = ""
        dialogue_acts = []
        if utterance.text.startswith("/info"):
            response = self._info()
        elif utterance.text.startswith("/ask_llm "):
            prompt = utterance.text[9:]
            response = self._ask_llm(prompt)
        elif utterance.text.startswith("/options"):
            options = [
                "Play some jazz music",
                "Recommend me some pop songs",
                "Create a workout playlist",
            ]
            response = self._options(options)
            dialogue_acts = [
                DialogueAct(
                    intent=_INTENT_OPTIONS,
                    annotations=[
                        SlotValueAnnotation("option", option) for option in options
                    ],
                )
            ]
        elif utterance.text == "/quit":
            self.goodbye()
            return
        else:
            response = "I'm sorry, I don't understand that command."

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )

    # --- Response handlers ---

    def _info(self) -> str:
        """Gives information about the agent."""
        return "I am MusicCRS, a conversational recommender system for music."

    def _ask_llm(self, prompt: str) -> str:
        """Calls a large language model (LLM) with the given prompt.

        Args:
            prompt: Prompt to send to the LLM.

        Returns:
            Response from the LLM.
        """
        if not self.services.llm:
            return "The agent is not configured to use an LLM"

        llm_response = self.services.llm.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={
                "stream": False,
                "temperature": 0.7,  # optional: controls randomness
                "max_tokens": 100,  # optional: limits the length of the response
            },
        )

        return f"LLM response: {llm_response['response']}"

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )


if __name__ == "__main__":
    # Load the DB and the LLM client once, before any user connects.
    SERVICES = create_services()
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
