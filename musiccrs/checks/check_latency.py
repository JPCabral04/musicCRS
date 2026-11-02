"""Check the time and the LLM calls per turn (T13, Part 4 F5): one scripted conversation
through the parser and the handlers.

Run from the repo root (needs LLM_API_KEY, the free-text turns go through the LLM):
    python -m musiccrs.checks.check_latency

Each turn does what MusicCRS.receive_utterance does, without the socket: parse, then the
handler from HANDLERS, on one DialogueState that carries over from turn to turn. For each
turn it prints the intent, the ms, the LLM calls and the start of the reply, and checks the
intent, the playlist length after the turn, that the turn took at most 3 s and made at most
3 LLM calls. Then it prints the mean and max ms per intent, and the median and 95th
percentile ms and the LLM calls over all turns. Exits with code 1 if a check fails.

The ADD turns for songs that are not in the catalog come from the course simulator's
scripts (checked in the DB on Oct 20).
"""
import math
import sys
import time

from .. import llm
from ..musiccrs import HANDLERS, calls_text, create_services
from ..nlu.parser import parse
from ..state import DialogueState

# Our own limit: the course allows 3-5 s per reply, we aim for the lower end.
MAX_TURN_MS = 3000

# Our own aim for LLM calls per turn (the course allows several): the parser, its one
# retry, and one more call for R7 "all except ..." or R8.
MAX_TURN_CALLS = 3

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
    # Part 4: critiques of the list above, why, sounds like, lyrics (none change the playlist).
    ("more like the second one", "CRITIQUE", 6),
    ("older", "CRITIQUE", 6),
    ("why the second one?", "EXPLAIN", 6),
    ("songs that sound like Smells Like Teen Spirit", "SOUNDS_LIKE", 6),
    ("songs about leaving home", "LYRICS_SEARCH", 6),
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


def percentile(values, share):
    """The value below which `share` of the values lie (nearest rank, no interpolation).

    ([120, 80, 300, 95], 0.5) -> sorted [80, 95, 120, 300], rank ceil(0.5 * 4) = 2 -> 95
    ([120, 80, 300, 95], 0.95) -> rank ceil(0.95 * 4) = 4 -> 300
    """
    ordered = sorted(values)
    rank = math.ceil(share * len(ordered))
    if rank < 1:
        rank = 1
    return ordered[rank - 1]


def run_turn(services, state, text):
    """Runs one turn like receive_utterance does and returns
    (intent name, reply text, ms, LLM calls)."""
    start = time.perf_counter()
    llm.call_count = 0

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
    return parsed.name, reply_text, ms, llm.call_count


def main():
    services = create_services()
    if services.llm is None:
        print("This check needs LLM_API_KEY: without it every free-text turn is UNKNOWN.")
        sys.exit(1)

    state = DialogueState()
    problems = []
    ms_per_intent = {}
    all_ms = []
    all_calls = []

    for text, expected_intent, expected_length in CONVERSATION:
        intent, reply_text, ms, calls = run_turn(services, state, text)
        length = len(state.playlist)
        all_ms.append(ms)
        all_calls.append(calls)

        print("\n> " + text)
        print("  [" + intent + "] " + str(round(ms)) + " ms, " + calls_text(calls)
              + ", playlist " + str(length) + ": " + short_text(reply_text))

        if intent != expected_intent:
            problems.append("'" + text + "': intent " + intent + ", expected " + expected_intent)
        if expected_length is not None and length != expected_length:
            problems.append("'" + text + "': playlist has " + str(length)
                            + " songs, expected " + str(expected_length))
        if ms > MAX_TURN_MS:
            problems.append("'" + text + "': took " + str(round(ms)) + " ms")
        if calls > MAX_TURN_CALLS:
            problems.append("'" + text + "': made " + calls_text(calls))

        if intent not in ms_per_intent:
            ms_per_intent[intent] = []
        ms_per_intent[intent].append(ms)

    print("\nms per turn, by intent:")
    for intent in ms_per_intent:
        times = ms_per_intent[intent]
        mean = sum(times) / len(times)
        print("  " + intent.ljust(16) + " mean " + str(round(mean)).rjust(5)
              + ", max " + str(round(max(times))).rjust(5) + "  (" + str(len(times)) + " turns)")

    total_calls = sum(all_calls)
    print("\nAll " + str(len(all_ms)) + " turns: median " + str(round(percentile(all_ms, 0.5)))
          + " ms, 95th percentile " + str(round(percentile(all_ms, 0.95))) + " ms, max "
          + str(round(max(all_ms))) + " ms")
    print("LLM calls: " + str(total_calls) + " in total, "
          + str(round(total_calls / len(all_calls), 2)) + " per turn, max "
          + str(max(all_calls)) + " in one turn")

    if len(problems) > 0:
        print("FAIL:")
        for problem in problems:
            print("  " + problem)
        sys.exit(1)
    print("OK: " + str(len(CONVERSATION)) + " turns, every one under "
          + str(MAX_TURN_MS) + " ms and at most " + str(MAX_TURN_CALLS)
          + " LLM calls, with the expected intent and playlist length.")


if __name__ == "__main__":
    main()
