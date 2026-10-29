import React, { useState, useEffect } from 'react';
import './PlaylistPanel.css';

export interface PlaylistTrack {
  id: string;
  name: string;
  artist: string;
  duration_ms: number;
  cover?: string | null;
  preview?: string | null;
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
      
      const acts = msg.dialogue_acts || msg.message?.dialogue_acts || msg.dialogue_act;

      if (acts && Array.isArray(acts)) {
        const playlistAct = acts.find(
          (act: any) =>
            act.intent === 'PLAYLIST' ||
            act.intent?.name === 'PLAYLIST' ||
            act.intent?.intent_type === 'PLAYLIST'
        );

        if (playlistAct) {
          const tracks: PlaylistTrack[] = [];
          const annotations = playlistAct.annotations || playlistAct.annotation;

          if (annotations && Array.isArray(annotations)) {
            annotations.forEach((anno: any) => {
              const slot = anno.slot || anno.slot_type || anno.slot_address;
              if (slot === 'track' || slot === 'TRACK') {
                try {
                  const trackData =
                    typeof anno.value === 'string'
                      ? JSON.parse(anno.value)
                      : anno.value;

                  if (trackData && trackData.id) {
                    tracks.push({
                      id: trackData.id,
                      name: trackData.name,
                      artist: trackData.artist || 'Unknown',
                      duration_ms: trackData.duration_ms || 0,
                      cover: trackData.cover || null,
                      preview: trackData.preview || null,
                    });
                  }
                } catch (e) {
                  console.error('Failed to parse playlist track JSON', e);
                }
              }
            });
          }
          setPlaylist(tracks);
          break; // Stop at most recent playlist act
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
              <li key={track.id} className="track-item flex-column align-items-start">
                <div className="d-flex align-items-center w-100 justify-content-between">
                  <div className="d-flex align-items-center" style={{ gap: '8px' }}>
                    {track.cover ? (
                      <img
                        src={track.cover}
                        alt={track.name}
                        style={{ width: '36px', height: '36px', borderRadius: '4px', objectFit: 'cover' }}
                      />
                    ) : (
                      <div
                        className="d-flex align-items-center justify-content-center bg-secondary text-white"
                        style={{ width: '36px', height: '36px', borderRadius: '4px', fontSize: '10px' }}
                      >
                        🎵
                      </div>
                    )}
                    <div className="track-info">
                      <span className="track-name">{track.name}</span>
                      <span className="track-artist">{track.artist}</span>
                    </div>
                  </div>
                  <button
                    className="remove-btn"
                    onClick={() => handleRemove(track.id)}
                    title="Remove track"
                  >
                    &times;
                  </button>
                </div>

                {track.preview && (
                  <audio controls preload="none" className="mt-1 w-100" style={{ height: '24px' }}>
                    <source src={track.preview} type="audio/mpeg" />
                  </audio>
                )}
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