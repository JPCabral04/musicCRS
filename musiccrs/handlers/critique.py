"""CRITIQUE (Part 4, F1): "more like the second one", "less like the one by Bon Jovi",
"older", "more popular", "more acoustic".

T1: a stub, so the parser and HANDLERS can be checked end to end.
T3 builds the example critiques (F1.1), T5 the attribute critiques (F1.2).
"""
import html

from ..state import Reply


def handle_critique(parsed, state, services):
    """CRITIQUE: not built yet (T3, T5). Says what was understood.

    "/like 2" -> "Critiques are not built yet. I understood: {'like': '2'}"
    """
    understood = html.escape(str(parsed.slots), quote=False)
    return Reply("Critiques are not built yet. I understood: " + understood)
