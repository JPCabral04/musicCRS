"""EXPLAIN (Part 4, F3): "why the second one?", "why did you pick Numb?".

The reasons are built with templates from facts only: what was stored in state.signals
when the song was shown (how it was found, the critique, the retriever ranks, the
similarity), and what the database says now (tags shared with the songs it came from,
an artist already in the playlist). No LLM writes them, so a reason cannot be invented.
"""
import html

from ..state import Reply
from .critique import critique_text, lower_tags, names_text
from .playlist import describe_track
from .shown import pick_shown

# The Part 1 retrievers (named as in retrieval/methods/fusion.py), in words, in this order.
RETRIEVER_WORDS = {
    "bm25_plus": "matching the words of your songs",
    "same_artist": "being by an artist of your songs",
    "bpr_sim": "the listening patterns of other users",
    "dense": "the meaning of your request",
}

# At most this many shared tags in the sentence.
MAX_TAGS = 3


def similarity_text(value):
    """A stored similarity with two decimals: 0.8234 -> "0.82"."""
    return str(round(float(value), 2))


def base_ids_of(signals):
    """The songs a shown song came from, to compare tags with.

    recommend -> the songs it was based on (the playlist or the named seed)
    critique  -> the liked songs, if any; audio -> the seed song;
    lyrics (a theme, no songs) or anything else -> [].
    """
    source = signals["source"]
    if source == "recommend":
        return signals["base_ids"]
    if source == "critique":
        return signals["liked"]
    if source == "audio":
        return [signals["seed_id"]]
    return []


def base_text(base_ids, db):
    """Up to 3 songs by name, more as a count: "<b>Numb by Linkin Park</b>" / "the 7 songs it was based on"."""
    if len(base_ids) <= 3:
        return names_text(base_ids, db)
    return "the " + str(len(base_ids)) + " songs it was based on"


def found_sentence(signals, db):
    """How the song was found, from its source, or None for an unknown source.

    recommend -> "I recommended it for <b>Numb by Linkin Park</b>."
    critique  -> "It came from your critique "More like <b>Toxic by Britney Spears</b>, older
                  than 2002", as one of the songs closest in sound to it (audio similarity 0.82)."
    audio     -> "It sounds close to <b>Numb by Linkin Park</b> (audio similarity 0.91)."
    lyrics    -> "Its lyrics are close to the theme 'leaving home' (lyrics similarity 0.58)."
    """
    source = signals["source"]

    if source == "recommend":
        sentence = "I recommended it for " + base_text(signals["base_ids"], db)
        if signals["different"]:
            sentence = sentence + ", leaving out their artists (you asked for something different)"
        return sentence + "."

    if source == "critique":
        # critique_text reads the same liked / disliked / filters keys the signals have.
        asked = critique_text(signals, db)
        # Without its final ":" ("More like X, older than 2002:" -> "More like X, older than 2002").
        asked = asked[:-1]
        return ("It came from your critique \"" + asked + "\", as one of the songs closest in "
                "sound to it (audio similarity " + similarity_text(signals["similarity"]) + ").")

    if source == "audio":
        return ("It sounds close to " + names_text([signals["seed_id"]], db)
                + " (audio similarity " + similarity_text(signals["similarity"]) + ").")

    if source == "lyrics":
        theme = html.escape(signals["theme"], quote=False)
        return ("Its lyrics are close to the theme '" + theme + "' (lyrics similarity "
                + similarity_text(signals["similarity"]) + ").")

    return None


def retrievers_sentence(signals):
    """Which Part 1 retrievers ranked it, and where (R6 only), or None.

    {"bm25_plus": 3, "bpr_sim": 12} -> "It was found by matching the words of your songs (#3),
                                        the listening patterns of other users (#12)."
    """
    if "retrievers" not in signals:
        return None
    ranks = signals["retrievers"]

    parts = []
    for name in RETRIEVER_WORDS:
        if name in ranks:
            parts.append(RETRIEVER_WORDS[name] + " (#" + str(ranks[name]) + ")")
    if len(parts) == 0:
        return None
    return "It was found by " + ", ".join(parts) + "."


def tags_sentence(track, signals, db):
    """The tags the song shares with the songs it came from (checked in the DB now), or None.

    Come As You Are (grunge, rock, 90s), seed tagged (Grunge, alternative, 90s)
        -> "It shares the tags <i>grunge</i>, <i>90s</i> with <b>Smells Like Teen Spirit by Nirvana</b>."
    Upper and lower case count as the same tag. At most MAX_TAGS, in the song's own order.
    Two or more songs are "those songs": found_sentence has just named them.
    """
    base_ids = base_ids_of(signals)
    base_tags = set()
    for base_id in base_ids:
        base_tags.update(lower_tags(db.get(base_id)))

    shared = []
    for tag in track.tags:
        tag_lower = tag.lower()
        if tag_lower in base_tags and tag_lower not in shared:
            shared.append(tag_lower)
        if len(shared) == MAX_TAGS:
            break
    if len(shared) == 0:
        return None

    words = []
    for tag in shared:
        words.append("<i>" + html.escape(tag, quote=False) + "</i>")
    if len(words) == 1:
        start = "It shares the tag "
    else:
        start = "It shares the tags "
    if len(base_ids) == 1:
        songs = names_text(base_ids, db)
    else:
        songs = "those songs"
    return start + ", ".join(words) + " with " + songs + "."


def artist_sentence(track, state, db):
    """An artist of the song who already has another song in the playlist (checked now), or None.

    Numb (Linkin Park), playlist with In the End (Linkin Park)
        -> "Its artist Linkin Park is already in your playlist."
    """
    playlist_artists = set()
    for playlist_id in state.playlist:
        # The song itself, added after it was shown, is not a reason for showing it.
        if playlist_id == track.track_id:
            continue
        for artist in db.get(playlist_id).artists:
            playlist_artists.add(artist)

    for artist in track.artists:
        if artist in playlist_artists:
            return "Its artist " + html.escape(artist, quote=False) + " is already in your playlist."
    return None


def explain_track(track_id, state, db):
    """The reasons for one shown song, as a list of sentences (one per fact found). No LLM.

    Bad Medicine (Bon Jovi), recommended for a rock playlist ->
        ["I recommended it for <b>Smells Like Teen Spirit by Nirvana</b>, ...",
         "It was found by matching the words of your songs (#116), being by an artist of your songs (#1).",
         "It shares the tags <i>hard rock</i>, <i>jon bon jovi</i>, <i>favorite</i> with those songs.",
         "Its artist Bon Jovi is already in your playlist."]
    """
    signals = state.signals[track_id]
    track = db.get(track_id)
    sentences = []

    sentence = found_sentence(signals, db)
    if sentence is not None:
        sentences.append(sentence)

    sentence = retrievers_sentence(signals)
    if sentence is not None:
        sentences.append(sentence)

    sentence = tags_sentence(track, signals, db)
    if sentence is not None:
        sentences.append(sentence)

    sentence = artist_sentence(track, state, db)
    if sentence is not None:
        sentences.append(sentence)

    return sentences


def handle_explain(parsed, state, services):
    """EXPLAIN: pick_shown(option) -> explain_track. A song not in the last list is not explained.

    "/why 2" after a recommendation -> "Why I showed you <b>It's My Life by Bon Jovi</b>:" + the reasons.
    The state does not change: the options are still pending afterwards ("add the second one").
    """
    if len(state.last_shown) == 0:
        return Reply("There is no list of recommended songs to explain yet. "
                     "Ask me for recommendations first.")

    if "option" not in parsed.slots:
        return Reply("Which song? For example: 'why the second one?' or '/why 2'.")
    value = parsed.slots["option"]

    track_id = pick_shown(value, state, services.db)
    if track_id is None:
        asked = html.escape(str(value), quote=False)
        return Reply("I could not find '" + asked + "' in the last list I showed you. "
                     "Say a number from 1 to " + str(len(state.last_shown))
                     + ", or part of a title or an artist.")

    sentences = explain_track(track_id, state, services.db)
    if len(sentences) == 0:
        sentences.append("I have no stored reason for that song.")

    track = services.db.get(track_id)
    text = "Why I showed you <b>" + describe_track(track) + "</b>:\n<ul>\n"
    for sentence in sentences:
        text = text + "<li>" + sentence + "</li>\n"
    text = text + "</ul>\n"
    return Reply(text)
