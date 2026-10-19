"""
Quick check script for T10 (R5 questions).
"""

from musiccrs.data.db import TrackDB
from musiccrs.state import DialogueState, ParsedIntent, Services
from musiccrs.handlers.qa import handle_ask_track, handle_ask_artist

db = TrackDB("cache/musiccrs.db")
services = Services(db=db, retriever=None, llm=None)
state = DialogueState()

print("--- 1. Testing ASK_TRACK (artist) ---")
p1 = ParsedIntent(name="ASK_TRACK", slots={"track": "hotel california", "question": "artist"})
print(handle_ask_track(p1, state, services).text)

print("\n--- 2. Testing ASK_TRACK (release_year) ---")
p2 = ParsedIntent(name="ASK_TRACK", slots={"track": "its my life", "artist": "bon jovi", "question": "release_year"})
print(handle_ask_track(p2, state, services).text)

print("\n--- 3. Testing ASK_ARTIST (track_count) ---")
p3 = ParsedIntent(name="ASK_ARTIST", slots={"artist": "queen", "question": "track_count"})
print(handle_ask_artist(p3, state, services).text)

print("\n--- 4. Testing ASK_ARTIST (genres) ---")
p4 = ParsedIntent(name="ASK_ARTIST", slots={"artist": "nirvana", "question": "genres"})
print(handle_ask_artist(p4, state, services).text)