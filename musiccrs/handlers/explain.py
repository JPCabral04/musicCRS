"""EXPLAIN (Part 4, F3): "why the second one?", "why did you pick Numb?".

T1: a stub, so the parser and HANDLERS can be checked end to end.
T7 builds the explanation from the stored signals (state.signals), with no LLM.
"""
import html

from ..state import Reply


def handle_explain(parsed, state, services):
    """EXPLAIN: not built yet (T7). Says what was understood.

    "/why 2" -> "Explanations are not built yet. I understood: {'option': '2'}"
    """
    understood = html.escape(str(parsed.slots), quote=False)
    return Reply("Explanations are not built yet. I understood: " + understood)
