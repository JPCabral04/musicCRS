import React, { useState, useEffect } from 'react';
import './PlaylistPanel.css';

export interface PlaylistTrack {
  id: string;
  name: string;
  artist: string;
  duration_ms: number;
}

interface PlaylistPanelProps {
  messages: any[];
  onSendMessage: (message: string) => void;
}

export const PlaylistPanel: React.FC<PlaylistPanelProps> = ({ messages, onSendMessage }) => {
  const [playlist, setPlaylist] = useState<PlaylistTrack[]>([]);
  const [inputTrack, setInputTrack] = useState('');

  // Extract the latest PLAYLIST dialogue act from agent messages
  useEffect(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.sender === 'MusicCRS' && msg.message?.dialogue_acts) {
        const playlistAct = msg.message.dialogue_acts.find(
          (act: any) => act.intent === 'PLAYLIST' || act.intent?.name === 'PLAYLIST'
        );

        if (playlistAct) {
          const tracks: PlaylistTrack[] = [];
          if (playlistAct.annotations) {
            playlistAct.annotations.forEach((anno: any) => {
              if (anno.slot === 'track' || anno.slot_type === 'track') {
                try {
                  const trackData = typeof anno.value === 'string' ? JSON.parse(anno.value) : anno.value;
                  tracks.push({
                    id: trackData.id,
                    name: trackData.name,
                    artist: trackData.artist || 'Unknown',
                    duration_ms: trackData.duration_ms || 0,
                  });
                } catch (e) {
                  console.error('Failed to parse playlist track JSON', e);
                }
              }
            });
          }
          setPlaylist(tracks);
          break;
        }
      }
    }
  }, [messages]);

  const handleRemove = (trackId: string) => {
    onSendMessage(`/remove ${trackId}`);
  };

  const handleClear = () => {
    onSendMessage('/clear');
  };

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputTrack.trim()) {
      onSendMessage(`add ${inputTrack.trim()}`);
      setInputTrack('');
    }
  };

  const formatTotalDuration = () => {
    const totalMs = playlist.reduce((sum, t) => sum + t.duration_ms, 0);
    const totalMin = Math.floor(totalMs / 60000);
    return `${totalMin} min`;
  };

  return (
    <div className="playlist-panel">
      <div className="playlist-header">
        <h3>My Playlist</h3>
        <span className="playlist-meta">
          {playlist.length} {playlist.length === 1 ? 'song' : 'songs'} ({formatTotalDuration()})
        </span>
      </div>

      <form onSubmit={handleAddSubmit} className="playlist-add-form">
        <input
          type="text"
          placeholder="Add a track..."
          value={inputTrack}
          onChange={(e) => setInputTrack(e.target.value)}
        />
        <button type="submit">+</button>
      </form>

      <div className="playlist-tracks">
        {playlist.length === 0 ? (
          <p className="empty-playlist">Your playlist is empty.</p>
        ) : (
          <ol className="track-list">
            {playlist.map((track) => (
              <li key={track.id} className="track-item">
                <div className="track-info">
                  <span className="track-name">{track.name}</span>
                  <span className="track-artist">{track.artist}</span>
                </div>
                <button
                  className="remove-btn"
                  onClick={() => handleRemove(track.id)}
                  title="Remove track"
                >
                  &times;
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      {playlist.length > 0 && (
        <div className="playlist-footer">
          <button className="clear-btn" onClick={handleClear}>
            Clear Playlist
          </button>
        </div>
      )}
    </div>
  );
};