"""Check R7 selection (T11): which of the shown options a user's words pick.

Run from the repo root:
    python -m musiccrs.checks.check_select

Rule cases always run (no LLM, no DB). LLM cases run only when LLM_API_KEY is set,
and print the ms per LLM call. Exits with code 1 if a case fails.
"""
import sys
import time

from ..data.db import Track
from ..handlers.selection import options_text, rule_indices, select_indices
from ..llm import create_client


def make_track(name, artists):
    """A Track with only a name and artists: enough for selection, no DB needed."""
    return Track(track_id="id-" + name, name=name, artists=tuple(artists), album="",
                 popularity=0, release_date="", duration_ms=0, tags=())


# 5 options, as R6 would show them. All are real catalog tracks (checked Oct 19).
# Only one Metallica track is in the catalog, so Bon Jovi is the artist to exclude.
OPTIONS = [
    make_track("Come As You Are", ["Nirvana"]),
    make_track("Yellow", ["Coldplay"]),
    make_track("Toxic", ["Britney Spears"]),
    make_track("It's My Life", ["Bon Jovi"]),
    make_track("Under Pressure", ["Queen", "David Bowie"]),
]

# (what the user says, expected 0-based indices). None = the rules give up (the LLM decides).
RULE_CASES = [
    ("all of them", [0, 1, 2, 3, 4]),
    ("everything", [0, 1, 2, 3, 4]),
    ("none", []),
    ("no thanks", []),
    ("the first two", [0, 1]),
    ("the last two", [3, 4]),
    ("1 and 3", [0, 2]),
    ("the second one", [1]),
    ("I'll take the third and the fourth", [2, 3]),
    ("the last one", [4]),
    ("the sixth", None),
    ("both", None),
    ("yes please", None),
    ("no, the second one", None),
    ("the first one by Bon Jovi", None),
    ("all except the one by Bon Jovi", None),
]

# Cases the rules cannot read, so the LLM must answer. None = "not a choice from the list".
LLM_CASES = [
    ("all except the one by Bon Jovi", [0, 1, 2, 4]),
    ("everything but Toxic", [0, 1, 3, 4]),
    ("just the Coldplay one", [1]),
    ("the Nirvana song and the Queen one", [0, 4]),
    ("the one with David Bowie", [4]),
    ("what's the weather in Oslo?", None),
]


def check_rules():
    """Runs every rule case and returns the list of failures."""
    print("Rule cases (no LLM):")
    failures = []
    for text, expected in RULE_CASES:
        got = rule_indices(text, len(OPTIONS))
        if got == expected:
            status = "ok  "
        else:
            status = "FAIL"
            failures.append(text)
        print("  " + status + " " + repr(text) + " -> " + str(got)
              + "  (expected " + str(expected) + ")")
    return failures


def check_llm(llm):
    """Runs every LLM case through select_indices and returns (failures, ms per case)."""
    print("LLM cases:")
    failures = []
    all_ms = []
    for text, expected in LLM_CASES:
        # Make sure the case really needs the LLM: the rules must give up on it.
        if rule_indices(text, len(OPTIONS)) is not None:
            failures.append(text)
            print("  FAIL " + repr(text) + " is read by the rules, not an LLM case")
            continue

        start = time.perf_counter()
        got = select_indices(text, OPTIONS, llm)
        ms = 1000 * (time.perf_counter() - start)
        all_ms.append(ms)

        if got == expected:
            status = "ok  "
        else:
            status = "FAIL"
            failures.append(text)
        print("  " + status + " " + repr(text) + " -> " + str(got)
              + "  (expected " + str(expected) + ", " + str(round(ms)) + " ms)")
    return failures, all_ms


def main():
    print("Options:")
    print(options_text(OPTIONS))
    print()

    failures = check_rules()
    print()

    llm = create_client()
    if llm is None:
        print("LLM_API_KEY is not set: LLM cases skipped.")
    else:
        llm_failures, all_ms = check_llm(llm)
        failures.extend(llm_failures)
        if len(all_ms) > 0:
            print("ms per LLM case: mean " + str(round(sum(all_ms) / len(all_ms)))
                  + ", max " + str(round(max(all_ms))))

    print()
    if len(failures) > 0:
        print("FAIL: " + str(len(failures)) + " case(s).")
        sys.exit(1)
    print("OK: every case passed.")


if __name__ == "__main__":
    main()
