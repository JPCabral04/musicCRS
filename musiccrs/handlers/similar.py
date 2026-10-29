"""SOUNDS_LIKE and LYRICS_SEARCH (Part 4, F2), owned by Alejandro.

T1 (JP): stubs, so the parser and HANDLERS can be checked end to end.
T6 builds "songs that sound like X" (audio vectors, services.vectors.nearest("audio", ...)),
T8 builds "songs about leaving home" (lyrics vectors). Both show their list with
show_tracks() from handlers/shown.py.
"""
import html

from ..state import Reply


def handle_sounds_like(parsed, state, services):
    """SOUNDS_LIKE: not built yet (T6). Says what was understood.

    "/sounds nirvana: in bloom"
        -> "'Sounds like' is not built yet. I understood: {'track': 'in bloom', 'artist': 'nirvana'}"
    """
    understood = html.escape(str(parsed.slots), quote=False)
    return Reply("'Sounds like' is not built yet. I understood: " + understood)


def handle_lyrics_search(parsed, state, services):
    """LYRICS_SEARCH: not built yet (T8). Says what was understood.

    "/about leaving home"
        -> "Lyrics search is not built yet. I understood: {'theme': 'leaving home'}"
    """
    understood = html.escape(str(parsed.slots), quote=False)
    return Reply("Lyrics search is not built yet. I understood: " + understood)
