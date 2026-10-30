# Demo Script (Audio, Lyrics, Media & Evaluation)

### Step 1: Media Retrieval & Playlist Interaction (T2, T4)
1. Launch the backend server:
   `python -m musiccrs.musiccrs`
2. Open the frontend web UI in the browser (`http://localhost:3000`).
3. Add a song to the playlist (e.g., type `add Rockabye` or use the `+` input field in the right panel).
4. **Demonstrate Media**: Point out the loaded album cover from Deezer and play the 30-second audio preview.
5. Add a second song (e.g., `add You See Big Girl`) and play its preview to show that the first audio automatically pauses.

### Step 2: Audio & Lyrics Vector Search (T6, T8)
1. **Acoustic Search (T6)**: Type a prompt asking for acoustic similarity (e.g., *"Find songs that sound like Smells Like Teen Spirit"*).
   * *Expected output*: The system retrieves songs matching the audio representation space.
2. **Lyrical Content Search (T8)**: Type a query targeting song themes (e.g., *"Find songs about leaving home"*).
   * *Expected output*: The system leverages the lyrics embeddings to retrieve relevant tracks.

### Step 3: Offline Evaluation Script (T10)
1. Run the offline evaluation script in the terminal:
   `python -m musiccrs.checks.eval_audio`
2. Show the output metrics comparing Same-Artist Overlap across Audio (CLAP), Text/Metadata, and Random baselines.