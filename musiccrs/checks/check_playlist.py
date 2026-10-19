"""
Quick check script for T6, T7, T8, and T12 handlers.
"""

from musiccrs.data.db import TrackDB
from musiccrs.state import DialogueState, ParsedIntent, Services
from musiccrs.handlers.playlist import (
    handle_add,
    handle_remove,
    handle_show,
    handle_clear,
    handle_help,
)

db = TrackDB("cache/musiccrs.db")
services = Services(db=db, retriever=None, llm=None)
state = DialogueState()

print("--- 1. Testing ADD (Exact & Loose) ---")
parsed_add = ParsedIntent(name="ADD", slots={"track": "smells like teen spirit", "artist": "nirvana"})
reply = handle_add(parsed_add, state, services)
print("ADD Reply:", reply.text)
print("Playlist IDs:", state.playlist)

print("\n--- 2. Testing ADD (R4 Disambiguation) ---")
parsed_love = ParsedIntent(name="ADD", slots={"track": "Love"})
reply_love = handle_add(parsed_love, state, services)
print("Disambiguation Reply:\n", reply_love.text)
print("Pending Kind:", state.pending_kind)
print("Pending Options Count:", len(state.pending_options))

print("\n--- 3. Testing SHOW ---")
parsed_show = ParsedIntent(name="SHOW", slots={})
reply_show = handle_show(parsed_show, state, services)
print("SHOW Reply:\n", reply_show.text)

print("\n--- 4. Testing REMOVE ---")
parsed_rem = ParsedIntent(name="REMOVE", slots={"track": "smells like teen spirit"})
reply_rem = handle_remove(parsed_rem, state, services)
print("REMOVE Reply:", reply_rem.text)
print("Playlist IDs after remove:", state.playlist)

print("\n--- 5. Testing HELP (T12) ---")
parsed_help = ParsedIntent(name="HELP", slots={})
reply_help = handle_help(parsed_help, state, services)
print("HELP Reply:\n", reply_help.text)