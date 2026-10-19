"""Check the LLM intent parser (T3) on musiccrs/nlu_examples.json.

Run from the repo root, with the API key set:
    export LLM_API_KEY="sk-..."
    python -m musiccrs.check_nlu

Prints every example (ok / FAIL, ms), the pass rate and the ms per parse.
T3 is done when at least 90% of the examples pass.
"""
import json
import sys
import time

from .data.db import normalize
from .llm import create_client
from .nlu.parser import parse
from .state import DialogueState

EXAMPLES_PATH = "musiccrs/nlu_examples.json"
PASS_RATE_NEEDED = 0.9

# How a slot value is compared with the expected one:
# names ignore case, punctuation and accents ("It's My Life" = "its my life");
# the user's own words (a description, a selection) only have to be there;
# every other slot (question, topic, different) must be exactly equal.
NORMALIZED_SLOTS = ("track", "artist")
FREE_TEXT_SLOTS = ("description", "selection")


def make_state(pending_kind):
    """A DialogueState with 5 fake pending options when pending_kind is set.

    None             -> DialogueState()  (nothing pending)
    "recommendation" -> 5 pending options, pending_kind "recommendation"
    """
    if pending_kind is None:
        return DialogueState()
    options = ["option1", "option2", "option3", "option4", "option5"]
    return DialogueState(pending_options=options, pending_kind=pending_kind)


def slots_match(expected, got):
    """True when `got` has exactly the expected slot names, with matching values.

    expected {"track": "It's My Life"}      got {"track": "its my life"}                 -> True
    expected {"track": "Hotel California"}  got {"track": "...", "artist": "Eagles"}     -> False
    expected {"description": "sad songs"}   got {"description": "sad love songs"}        -> True
    """
    # The same slot names on both sides. "text" is ignored: our code adds it on UNKNOWN.
    got_names = []
    for name in got:
        if name != "text":
            got_names.append(name)
    expected_names = list(expected)
    if sorted(got_names) != sorted(expected_names):
        return False

    # Then the values, slot by slot.
    for name in expected_names:
        if name in FREE_TEXT_SLOTS:
            continue
        if name in NORMALIZED_SLOTS:
            if normalize(expected[name]) != normalize(got[name]):
                return False
        else:
            if expected[name] != got[name]:
                return False
    return True


def run_check(llm, path):
    """Parse every example with the LLM, print the results, return (passed, total)."""
    with open(path, encoding="utf-8") as file:
        examples = json.load(file)

    passed = 0
    times_ms = []
    for example in examples:
        state = make_state(example["pending_kind"])

        start = time.perf_counter()
        parsed = parse(example["text"], state, llm)
        elapsed_ms = (time.perf_counter() - start) * 1000
        times_ms.append(elapsed_ms)

        intent_ok = parsed.name == example["intent"]
        slots_ok = slots_match(example["slots"], parsed.slots)
        if intent_ok and slots_ok:
            passed = passed + 1
            print(f"ok   {elapsed_ms:6.0f} ms  {example['text']}")
        else:
            print(f"FAIL {elapsed_ms:6.0f} ms  {example['text']}")
            print(f"       expected {example['intent']} {example['slots']}")
            print(f"       got      {parsed.name} {parsed.slots}")

    total = len(examples)
    rate = passed / total
    mean_ms = sum(times_ms) / total
    max_ms = max(times_ms)
    print()
    print(f"Passed {passed}/{total} ({rate:.1%}); T3 needs {PASS_RATE_NEEDED:.0%}")
    print(f"ms per parse: mean {mean_ms:.0f}, max {max_ms:.0f}")
    return passed, total


def main():
    llm = create_client()
    if llm is None:
        print('LLM_API_KEY is not set. Set it first: export LLM_API_KEY="sk-..."')
        sys.exit(1)

    passed, total = run_check(llm, EXAMPLES_PATH)
    if passed / total < PASS_RATE_NEEDED:
        sys.exit(1)


if __name__ == "__main__":
    main()
