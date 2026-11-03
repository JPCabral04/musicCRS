"""MusicCRS conversational agent.

Run from the repo root as a module (so the package imports work):
    python -m musiccrs.musiccrs
"""

import json
import time

from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.platforms import FlaskSocketPlatform

from retrieval.final_retriever import FinalRetriever

from .data.db import TrackDB
from .data.media import get_media, media_act
from .data.vectors import TrackVectors
from .handlers.critique import handle_critique
from .handlers.explain import handle_explain
from .handlers.playlist import (describe_track, handle_add, handle_clear, handle_help,
                                handle_remove, handle_show)
from .handlers.qa import handle_ask_artist, handle_ask_track
from .handlers.recs import handle_create_playlist, handle_recommend
from .handlers.selection import handle_select
from .handlers.similar import handle_lyrics_search, handle_sounds_like
from . import llm
from .llm import create_client
from .nlu.parser import parse
from .state import DialogueState, Reply, Services

_INTENT_PLAYLIST = Intent("PLAYLIST")


def handle_greeting(parsed, state, services):
    """Reply to a greeting ("hello", "hi", "thanks") with what the agent can do.

    "Hello!" -> "Hi! I can add and remove songs in your playlist, ..."
    """
    text = ("Hi! I can add and remove songs in your playlist, answer questions about "
            "songs and artists, recommend songs for your playlist, and make a whole "
            "playlist from a description. Type /help to see examples.")
    return Reply(text)


# Intent name -> handler function. Every handler is handler(parsed, state, services) -> Reply.
# QUIT has no handler: receive_utterance ends the conversation itself.
HANDLERS = {
    "GREETING": handle_greeting,
    "ADD": handle_add,
    "REMOVE": handle_remove,
    "SHOW": handle_show,
    "CLEAR": handle_clear,
    "HELP": handle_help,
    "RECOMMEND": handle_recommend,
    "CREATE_PLAYLIST": handle_create_playlist,
    "SELECT": handle_select,
    "ASK_TRACK": handle_ask_track,
    "ASK_ARTIST": handle_ask_artist,
    # Part 4 (stubs in T1).
    "CRITIQUE": handle_critique,
    "SOUNDS_LIKE": handle_sounds_like,
    "LYRICS_SEARCH": handle_lyrics_search,
    "EXPLAIN": handle_explain,
}

# Shown when the agent cannot handle a message.
COMMANDS_TEXT = ("Ask me 'what can you do?' or type /help to see what I can do.")

# The heavy objects (DB, retriever, LLM client), shared by every agent.
# Set once in __main__ below, before the server accepts any connection.
SERVICES = None


def create_services(use_llm=True):
    """Load the heavy objects once, at startup."""
    db = TrackDB()

    # "client", not "llm": llm is the module that counts the calls (print_turn_time).
    client = None
    if use_llm:
        client = create_client()
        if client is None:
            print("LLM_API_KEY is not set: the agent runs with slash commands only.")

    # The Part 1 retriever (BM25, same artist, BPR, dense): loaded once, it takes seconds.
    print("Loading the retriever...")
    start = time.perf_counter()
    retriever = FinalRetriever()
    # One search right away, so the first user does not pay the first-call cost
    # (the first dense encode on the GPU took 894 ms, the next ones about 150 ms, Oct 20).
    retriever.text_to_item_retrieval("warm up", 1)
    seconds = time.perf_counter() - start
    print("Retriever loaded in " + str(round(seconds, 1)) + " s.")

    # The Part 4 track vectors. The metadata matrix is the dense scorer's own (no copy);
    # audio and lyrics are read from cache/embeddings/.
    print("Loading the track vectors...")
    start = time.perf_counter()
    scorers = retriever.fusion.scorers
    dense = scorers["dense"]
    vectors = TrackVectors(dense.track_ids, dense.matrix, dense.has_vector)
    seconds = time.perf_counter() - start
    print("Track vectors loaded in " + str(round(seconds, 1)) + " s:")
    print("  " + vectors.size_text("metadata"))
    print("  " + vectors.size_text("audio"))
    print("  " + vectors.size_text("lyrics"))

    return Services(db=db, retriever=retriever, llm=client, vectors=vectors)


def playlist_act(state, db):
    """The whole playlist as one PLAYLIST dialogue act, for the playlist panel (R1, T4).

    One annotation per track, in playlist order. Its value is JSON text:
    SlotValueAnnotation("track", '{"id": "e9383e0c-...", "name": "Smells Like Teen Spirit",
                                   "artist": "Nirvana", "duration_ms": 301920,
                                   "cover": "https://...jpg", "preview": "https://...mp3"}')
    cover and preview come from Deezer (get_media, cached by track ID); null when not found.
    An empty playlist gives an act with no annotations, so the panel shows nothing.
    """
    annotations = []
    for track_id in state.playlist:
        track = db.get(track_id)
        media = get_media(track)
        track_info = {
            "id": track.track_id,
            "name": track.name,
            "artist": track.artists[0],
            "duration_ms": track.duration_ms,
            "cover": media["cover"],
            "preview": media["preview"],
        }
        value = json.dumps(track_info)
        annotations.append(SlotValueAnnotation("track", value))
    return DialogueAct(intent=_INTENT_PLAYLIST, annotations=annotations)


def calls_text(count):
    """The number of LLM calls in words: 0 -> "0 LLM calls", 1 -> "1 LLM call"."""
    if count == 1:
        return "1 LLM call"
    return str(count) + " LLM calls"


def print_turn_time(intent_name, start):
    """Print how long one turn took and how many LLM calls it made, in the backend
    terminal (T13 latency check, Part 4 F5 log).

    intent_name="CRITIQUE", start 0.412 s ago, 1 call -> prints "[CRITIQUE] 412 ms, 1 LLM call"
    """
    milliseconds = (time.perf_counter() - start) * 1000
    print("[" + intent_name + "] " + str(round(milliseconds)) + " ms, "
          + calls_text(llm.call_count))


def track_names(track_ids, db):
    """TEMP study aid: ["id-1", "id-2"] -> ["Bad Medicine by Bon Jovi", "Yellow by Coldplay"]."""
    names = []
    for track_id in track_ids:
        names.append(describe_track(db.get(track_id)))
    return names


def indented_json(value):
    """TEMP study aid: JSON with 2-space indent, its later lines pushed 2 more to the right."""
    return json.dumps(value, indent=2).replace("\n", "\n  ")


def print_state(state, db):
    """TEMP study aid: all of DialogueState as valid JSON, track IDs shown as names.

    One line per track in "signals" (why it was shown); "shown" (a set) sorted by name.
    """
    critique = None
    if state.critique is not None:
        critique = dict(state.critique)
        critique["base_ids"] = track_names(state.critique["base_ids"], db)
        critique["liked"] = track_names(state.critique["liked"], db)
        critique["disliked"] = track_names(state.critique["disliked"], db)

    signal_lines = []
    for track_id in state.signals:
        signal = dict(state.signals[track_id])
        for key in ("base_ids", "liked", "disliked"):
            if key in signal:
                signal[key] = track_names(signal[key], db)
        signal_lines.append("    " + json.dumps(track_names([track_id], db)[0])
                            + ": " + json.dumps(signal))

    pieces = [
        '  "playlist": ' + indented_json(track_names(state.playlist, db)),
        '  "pending_options": ' + indented_json(track_names(state.pending_options, db)),
        '  "pending_kind": ' + json.dumps(state.pending_kind),
        '  "last_shown": ' + indented_json(track_names(state.last_shown, db)),
        '  "shown": ' + indented_json(sorted(track_names(state.shown, db))),
        '  "signals": {\n' + ",\n".join(signal_lines) + "\n  }",
        '  "critique": ' + indented_json(critique),
    ]
    print("{\n" + ",\n".join(pieces) + "\n}")


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

        parse -> handler from HANDLERS -> reply text + a PLAYLIST act if the playlist changed
        + a MEDIA act if the reply shows options.
        """
        # Start the clock and the LLM-call count: both printed at the end cover the whole turn.
        start = time.perf_counter()
        llm.call_count = 0

        # 1. Understand the message: slash commands by rules, other text by one LLM call.
        parsed = parse(utterance.text, self.state, self.services.llm)

        if parsed.name == "QUIT":
            self.goodbye()
            print_turn_time(parsed.name, start)
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

        # 5. A reply with option buttons also gets their covers and previews (chat cards).
        # Every handler that sends OPTIONS has just put the same songs in pending_options.
        shows_options = False
        for act in reply.dialogue_acts:
            if str(act.intent) == "OPTIONS":
                shows_options = True
        if shows_options:
            dialogue_acts.append(media_act(self.state.pending_options, self.services.db))

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                reply.text,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )
        print_state(self.state, self.services.db)  # TEMP study aid: remove before committing
        print_turn_time(parsed.name, start)


if __name__ == "__main__":
    # Load the DB and the LLM client once, before any user connects.
    SERVICES = create_services()
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
