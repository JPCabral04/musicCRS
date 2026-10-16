"""Track database for the Part 2 agent (T1)."""
import re
import unicodedata
from pathlib import Path

# Where the database file lives: <repo root>/cache/musiccrs.db
this_file = Path(__file__).resolve()
musiccrs_folder = this_file.parent
repo_root = musiccrs_folder.parent
DEFAULT_DB_PATH = repo_root / "cache" / "musiccrs.db"


def normalize(text: str) -> str:
    """Turn a song or artist name into a simple form for matching.

    "Don't Stop Me Now!" -> "dont stop me now"
    "Beyoncé"            -> "beyonce"
    "Simon & Garfunkel"  -> "simon and garfunkel"
    """
    # Split each accented letter into the letter plus a separate accent mark.
    text = unicodedata.normalize("NFKD", text)

    # Keep every character that is not an accent mark.
    without_accents = ""
    for char in text:
        if not unicodedata.combining(char):
            without_accents = without_accents + char
    text = without_accents

    text = text.lower()

    # Delete apostrophes, so "don't" becomes "dont" (what users type).
    text = text.replace("'", "")
    text = text.replace("’", "")  # the curly apostrophe ’

    text = text.replace("&", " and ")

    # Replace every run of characters that are not letters or digits by one space.
    text = re.sub(r"[\W_]+", " ", text)

    # Remove the spaces at the start and the end.
    text = text.strip()
    return text


def base_name(name: str) -> str:
    """Normalized name without the version suffix and without bracketed parts.

    "Hotel California - 2013 Remaster"  -> "hotel california"
    "Letting Go (feat. Sarah Green)"    -> "letting go"
    """
    # Keep only what comes before the first " - ".
    parts = name.split(" - ")
    base = parts[0]

    # Remove everything inside (...) and [...].
    base = re.sub(r"\(.*?\)", " ", base)
    base = re.sub(r"\[.*?\]", " ", base)

    base = normalize(base)

    # If nothing is left (the whole name was in brackets), use the full name.
    if base == "":
        base = normalize(name)
    return base
