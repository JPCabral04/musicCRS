"""Check the time per turn (T13): one scripted conversation through the parser and the handlers.

Run from the repo root (needs LLM_API_KEY, the free-text turns go through the LLM):
    python -m musiccrs.checks.check_latency

Each turn does what MusicCRS.receive_utterance does, without the socket: parse, then the
handler from HANDLERS, on one DialogueState that carries over from turn to turn. For each
turn it prints the intent, the ms and the start of the reply, and checks the intent, the
playlist length after the turn, and that the turn took at most 3 s. Then it prints the mean
and max ms per intent. Exits with code 1 if a check fails.

The ADD turns for songs that are not in the catalog come from the course simulator's
scripts (checked in the DB on Oct 20).
"""
import sys
import time

from ..musiccrs import HANDLERS, create_services
from ..nlu.parser import parse
from ..state import DialogueState

# Our own limit: the course allows 3-5 s per reply, we aim for the lower end.
MAX_TURN_MS = 3000

# (user message, expected intent, expected playlist length after the turn).
# None = the length is not checked (it depends on the LLM or on a decision still open).
CONVERSATION = [
    ("Hello!", "GREETING", 0),
    ("what can you do?", "HELP", 0),
    ("add Bad Medicine by Bon Jovi", "ADD", 1),
    ("please add Always by Bon Jovi", "ADD", 1),                    # not in the catalog
    ("add Money, Money, Money by ABBA", "ADD", 1),                  # no ABBA at all
    ("add We Believe by Good Charlotte", "ADD", 1),                 # only the RHCP one exists
    ("add Wake Me Up When September Ends by Green Day", "ADD", 1),  # 2 versions: options
    ("the first one", "SELECT", 2),
    ("add Disenchanted by My Chemical Romance", "ADD", 3),
    ("add Hotel California by the Eagles", "ADD", 3),               # "Eagles" in the catalog: options
    ("the first one", "SELECT", 4),
    ("add Goodbye by Chris Young", "ADD", 4),                       # not in the catalog
    ("add Goodbye", "ADD", 4),                                      # R4: 5 options
    ("the second one", "SELECT", 5),
    ("remove Money, Money, Money", "REMOVE", 5),                    # not in the playlist
    ("remove the Bon Jovi song", "REMOVE", 4),                      # by artist only
    ("show me my playlist", "SHOW", 4),
    ("who sings Hotel California?", "ASK_TRACK", 4),
    ("how many songs does Bon Jovi have?", "ASK_ARTIST", 4),
    ("recommend me some songs", "RECOMMEND", 4),
    ("add the first two", "SELECT", 6),
    ("make me a playlist for a rainy evening", "CREATE_PLAYLIST", None),
    ("add Bohemian Rhapsody by Queen", "ADD", None),                # only an a cappella mix
    ("clear my playlist", "CLEAR", 0),
    ("goodbye", "QUIT", 0),
]


def short_text(text):
    """The first 90 characters of a reply, on one line, to print it."""
    one_line = text.replace("\n", " ")
    if len(one_line) > 90:
        return one_line[:90] + "..."
    return one_line


def run_turn(services, state, text):
    """Runs one turn like receive_utterance does and returns (intent name, reply text, ms)."""
    start = time.perf_counter()

    parsed = parse(text, state, services.llm)
    if parsed.name in HANDLERS:
        handler = HANDLERS[parsed.name]
        reply = handler(parsed, state, services)
        reply_text = reply.text
    elif parsed.name == "QUIT":
        reply_text = "(goodbye)"
    else:
        reply_text = "(no handler for " + parsed.name + ")"

    ms = 1000 * (time.perf_counter() - start)
    return parsed.name, reply_text, ms


def main():
    services = create_services()
    if services.llm is None:
        print("This check needs LLM_API_KEY: without it every free-text turn is UNKNOWN.")
        sys.exit(1)

    state = DialogueState()
    problems = []
    ms_per_intent = {}

    for text, expected_intent, expected_length in CONVERSATION:
        intent, reply_text, ms = run_turn(services, state, text)
        length = len(state.playlist)

        print("\n> " + text)
        print("  [" + intent + "] " + str(round(ms)) + " ms, playlist " + str(length)
              + ": " + short_text(reply_text))

        if intent != expected_intent:
            problems.append("'" + text + "': intent " + intent + ", expected " + expected_intent)
        if expected_length is not None and length != expected_length:
            problems.append("'" + text + "': playlist has " + str(length)
                            + " songs, expected " + str(expected_length))
        if ms > MAX_TURN_MS:
            problems.append("'" + text + "': took " + str(round(ms)) + " ms")

        if intent not in ms_per_intent:
            ms_per_intent[intent] = []
        ms_per_intent[intent].append(ms)

    print("\nms per turn, by intent:")
    for intent in ms_per_intent:
        times = ms_per_intent[intent]
        mean = sum(times) / len(times)
        print("  " + intent.ljust(16) + " mean " + str(round(mean)).rjust(5)
              + ", max " + str(round(max(times))).rjust(5) + "  (" + str(len(times)) + " turns)")

    if len(problems) > 0:
        print("FAIL:")
        for problem in problems:
            print("  " + problem)
        sys.exit(1)
    print("OK: " + str(len(CONVERSATION)) + " turns, every one under "
          + str(MAX_TURN_MS) + " ms, with the expected intent and playlist length.")


if __name__ == "__main__":
    main()
