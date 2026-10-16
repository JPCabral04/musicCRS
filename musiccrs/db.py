"""Track database for the Part 2 agent (T1)."""
import re
import unicodedata


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
