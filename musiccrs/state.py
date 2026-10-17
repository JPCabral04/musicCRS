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
