import React, { useState, useEffect, useCallback, useRef } from 'react';
import './HoldMusicDashboard.css';

const API_BASE = '/api/v1/hold-music';

// Source type display mappings
const SOURCE_LABELS = {
  url: 'Custom URL',
  upload: 'Uploaded File',
  telnyx_default: 'Telnyx Default'
};

const SOURCE_ICONS = {
  url: '🔗',
  upload: '📤',
  telnyx_default: '🎵'
};

const HoldMusicDashboard = () => {
  const [musicList, setMusicList] = useState([]);
  const [telnyxDefaults, setTelnyxDefaults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMusic, setSelectedMusic] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [playingId, setPlayingId] = useState(null);
  const audioRef = useRef(null);

  const fetchMusicList = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}?include_inactive=true`);
      if (!response.ok) throw new Error('Failed to fetch hold music');
      const data = await response.json();
      setMusicList(data.music || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTelnyxDefaults = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/telnyx-defaults`);
      if (!response.ok) throw new Error('Failed to fetch Telnyx defaults');
      const data = await response.json();
      setTelnyxDefaults(data.options || []);
    } catch (err) {
      console.error('Error fetching Telnyx defaults:', err);
    }
  }, []);

  useEffect(() => {
    fetchMusicList();
    fetchTelnyxDefaults();
  }, [fetchMusicList, fetchTelnyxDefaults]);

  const handleCreate = async (musicData) => {
    try {
      const response = await fetch(API_BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(musicData)
      });
      if (!response.ok) throw new Error('Failed to create hold music');
      setShowCreateModal(false);
      fetchMusicList();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdate = async (musicId, musicData) => {
    try {
      const response = await fetch(`${API_BASE}/${musicId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(musicData)
      });
      if (!response.ok) throw new Error('Failed to update hold music');
      setShowEditModal(false);
      setSelectedMusic(null);
      fetchMusicList();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (musicId) => {
    if (!window.confirm('Are you sure you want to delete this hold music?')) return;
    try {
      const response = await fetch(`${API_BASE}/${musicId}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete hold music');
      fetchMusicList();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSetDefault = async (musicId) => {
    try {
      const response = await fetch(`${API_BASE}/${musicId}/set-default`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to set default');
      fetchMusicList();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleToggleActive = async (musicId, currentStatus) => {
    await handleUpdate(musicId, { is_active: !currentStatus });
  };

  const handlePlay = (music) => {
    if (playingId === music.id) {
      // Stop playing
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }
      setPlayingId(null);
    } else {
      // Start playing
      if (audioRef.current) {
        audioRef.current.src = music.audio_url;
        audioRef.current.play().catch(e => console.error('Playback error:', e));
      }
      setPlayingId(music.id);
    }
  };

  const handleAudioEnded = () => {
    setPlayingId(null);
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="hm-loading">
        <div className="hm-spinner"></div>
        <p>Loading hold music...</p>
      </div>
    );
  }

  return (
    <div className="hm-dashboard">
      {/* Hidden audio element for playback */}
      <audio ref={audioRef} onEnded={handleAudioEnded} />

      {/* Header */}
      <div className="hm-header">
        <div>
          <h1>Hold Music Library</h1>
          <p className="hm-subtitle">Manage music for call queues, transfers, and conferences</p>
        </div>
        <div className="hm-header-actions">
          <button
            className="hm-btn hm-btn-primary"
            onClick={() => setShowCreateModal(true)}
          >
            <span className="hm-icon">+</span>
            Add Music
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="hm-error-banner">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Stats Row */}
      <div className="hm-stats-row">
        <div className="hm-stat-card">
          <div className="hm-stat-value">{musicList.filter(m => m.is_active).length}</div>
          <div className="hm-stat-label">Active Tracks</div>
        </div>
        <div className="hm-stat-card">
          <div className="hm-stat-value">{musicList.filter(m => m.source_type === 'telnyx_default').length}</div>
          <div className="hm-stat-label">Telnyx Defaults</div>
        </div>
        <div className="hm-stat-card">
          <div className="hm-stat-value">{musicList.filter(m => m.source_type === 'url').length}</div>
          <div className="hm-stat-label">Custom URLs</div>
        </div>
        <div className="hm-stat-card hm-stat-highlight">
          <div className="hm-stat-value">{musicList.find(m => m.is_default)?.name?.slice(0, 10) || 'None'}</div>
          <div className="hm-stat-label">Default Track</div>
        </div>
      </div>

      {/* Music Grid */}
      <div className="hm-section">
        <h2>Your Hold Music</h2>
        {musicList.length === 0 ? (
          <div className="hm-empty">
            <span className="hm-empty-icon">🎶</span>
            <h3>No Hold Music</h3>
            <p>Add your first hold music track to enhance your caller experience.</p>
            <button
              className="hm-btn hm-btn-primary"
              onClick={() => setShowCreateModal(true)}
            >
              Add Music
            </button>
          </div>
        ) : (
          <div className="hm-grid">
            {musicList.map(music => (
              <MusicCard
                key={music.id}
                music={music}
                isPlaying={playingId === music.id}
                onPlay={() => handlePlay(music)}
                onEdit={() => {
                  setSelectedMusic(music);
                  setShowEditModal(true);
                }}
                onDelete={() => handleDelete(music.id)}
                onSetDefault={() => handleSetDefault(music.id)}
                onToggleActive={() => handleToggleActive(music.id, music.is_active)}
                formatDuration={formatDuration}
              />
            ))}
          </div>
        )}
      </div>

      {/* Telnyx Defaults Section */}
      <div className="hm-section">
        <h2>Telnyx Default Library</h2>
        <p className="hm-section-desc">Pre-built hold music options from Telnyx - no hosting required.</p>
        <div className="hm-telnyx-grid">
          {telnyxDefaults.map(track => (
            <TelnyxDefaultCard
              key={track.key}
              track={track}
              isAdded={musicList.some(m => m.telnyx_music_name === track.key)}
              onAdd={() => {
                setShowCreateModal(true);
                // Pre-fill with Telnyx default
                setTimeout(() => {
                  const event = new CustomEvent('prefill-telnyx', { detail: track });
                  window.dispatchEvent(event);
                }, 100);
              }}
            />
          ))}
        </div>
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <CreateMusicModal
          telnyxDefaults={telnyxDefaults}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreate}
        />
      )}

      {/* Edit Modal */}
      {showEditModal && selectedMusic && (
        <EditMusicModal
          music={selectedMusic}
          onClose={() => {
            setShowEditModal(false);
            setSelectedMusic(null);
          }}
          onUpdate={(data) => handleUpdate(selectedMusic.id, data)}
        />
      )}
    </div>
  );
};

// Music Card Component
const MusicCard = ({ music, isPlaying, onPlay, onEdit, onDelete, onSetDefault, onToggleActive, formatDuration }) => {
  return (
    <div className={`hm-card ${!music.is_active ? 'inactive' : ''} ${music.is_default ? 'default' : ''}`}>
      <div className="hm-card-header">
        <div className="hm-card-icon">
          <span>{SOURCE_ICONS[music.source_type]}</span>
        </div>
        <div className="hm-card-badges">
          {music.is_default && <span className="hm-badge hm-badge-default">Default</span>}
          {!music.is_active && <span className="hm-badge hm-badge-inactive">Inactive</span>}
        </div>
      </div>

      <div className="hm-card-body">
        <h3>{music.name}</h3>
        {music.description && <p className="hm-card-desc">{music.description}</p>}
        <div className="hm-card-meta">
          <span className="hm-meta-item">
            <span className="hm-meta-icon">📁</span>
            {SOURCE_LABELS[music.source_type]}
          </span>
          {music.duration_seconds && (
            <span className="hm-meta-item">
              <span className="hm-meta-icon">⏱️</span>
              {formatDuration(music.duration_seconds)}
            </span>
          )}
        </div>
        {music.comfort_messages && music.comfort_messages.length > 0 && (
          <div className="hm-card-comfort">
            <span className="hm-comfort-label">💬 {music.comfort_messages.length} comfort messages</span>
          </div>
        )}
      </div>

      <div className="hm-card-actions">
        <button
          className={`hm-btn-play ${isPlaying ? 'playing' : ''}`}
          onClick={onPlay}
          disabled={!music.audio_url}
          title={isPlaying ? 'Stop' : 'Preview'}
        >
          {isPlaying ? '⏹️' : '▶️'}
        </button>
        <div className="hm-card-buttons">
          {!music.is_default && music.is_active && (
            <button className="hm-btn-icon" onClick={onSetDefault} title="Set as Default">
              ⭐
            </button>
          )}
          <button className="hm-btn-icon" onClick={onToggleActive} title={music.is_active ? 'Deactivate' : 'Activate'}>
            {music.is_active ? '🔘' : '⚪'}
          </button>
          <button className="hm-btn-icon" onClick={onEdit} title="Edit">
            ✏️
          </button>
          <button className="hm-btn-icon hm-btn-delete" onClick={onDelete} title="Delete">
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
};

// Telnyx Default Card
const TelnyxDefaultCard = ({ track, isAdded, onAdd }) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(null);

  const handlePlayPreview = () => {
    if (isPlaying) {
      audioRef.current?.pause();
      setIsPlaying(false);
    } else {
      audioRef.current?.play();
      setIsPlaying(true);
    }
  };

  return (
    <div className={`hm-telnyx-card ${isAdded ? 'added' : ''}`}>
      <audio
        ref={audioRef}
        src={track.url}
        onEnded={() => setIsPlaying(false)}
      />
      <div className="hm-telnyx-info">
        <span className="hm-telnyx-icon">🎵</span>
        <span className="hm-telnyx-name">{track.name}</span>
      </div>
      <div className="hm-telnyx-actions">
        <button
          className={`hm-btn-play-small ${isPlaying ? 'playing' : ''}`}
          onClick={handlePlayPreview}
        >
          {isPlaying ? '⏹️' : '▶️'}
        </button>
        {isAdded ? (
          <span className="hm-telnyx-added">✓ Added</span>
        ) : (
          <button className="hm-btn hm-btn-small hm-btn-secondary" onClick={onAdd}>
            + Add
          </button>
        )}
      </div>
    </div>
  );
};

// Create Music Modal
const CreateMusicModal = ({ telnyxDefaults, onClose, onCreate }) => {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    source_type: 'telnyx_default',
    audio_url: '',
    telnyx_music_name: 'classical',
    duration_seconds: null,
    is_default: false,
    comfort_messages: [],
    comfort_message_interval: 30
  });
  const [newComfortMsg, setNewComfortMsg] = useState('');
  const [error, setError] = useState(null);

  // Listen for prefill events from Telnyx default cards
  useEffect(() => {
    const handlePrefill = (e) => {
      const track = e.detail;
      setFormData(prev => ({
        ...prev,
        name: track.name,
        source_type: 'telnyx_default',
        telnyx_music_name: track.key
      }));
    };

    window.addEventListener('prefill-telnyx', handlePrefill);
    return () => window.removeEventListener('prefill-telnyx', handlePrefill);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setError('Name is required');
      return;
    }
    if (formData.source_type === 'url' && !formData.audio_url.trim()) {
      setError('Audio URL is required for custom URL source');
      return;
    }
    onCreate(formData);
  };

  const handleAddComfortMessage = () => {
    if (newComfortMsg.trim()) {
      setFormData({
        ...formData,
        comfort_messages: [...formData.comfort_messages, newComfortMsg.trim()]
      });
      setNewComfortMsg('');
    }
  };

  const handleRemoveComfortMessage = (index) => {
    setFormData({
      ...formData,
      comfort_messages: formData.comfort_messages.filter((_, i) => i !== index)
    });
  };

  return (
    <div className="hm-modal-overlay" onClick={onClose}>
      <div className="hm-modal" onClick={e => e.stopPropagation()}>
        <div className="hm-modal-header">
          <h2>Add Hold Music</h2>
          <button className="hm-close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="hm-modal-body">
            {error && <div className="hm-form-error">{error}</div>}

            <div className="hm-form-group">
              <label>Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Classical Hold, After Hours Music"
              />
            </div>

            <div className="hm-form-group">
              <label>Description</label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief description of this music"
              />
            </div>

            <div className="hm-form-group">
              <label>Source Type</label>
              <div className="hm-source-options">
                <label className={`hm-source-option ${formData.source_type === 'telnyx_default' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="source_type"
                    value="telnyx_default"
                    checked={formData.source_type === 'telnyx_default'}
                    onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                  />
                  <span className="hm-source-icon">🎵</span>
                  <span>Telnyx Default</span>
                </label>
                <label className={`hm-source-option ${formData.source_type === 'url' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="source_type"
                    value="url"
                    checked={formData.source_type === 'url'}
                    onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                  />
                  <span className="hm-source-icon">🔗</span>
                  <span>Custom URL</span>
                </label>
              </div>
            </div>

            {formData.source_type === 'telnyx_default' && (
              <div className="hm-form-group">
                <label>Telnyx Music</label>
                <select
                  value={formData.telnyx_music_name}
                  onChange={(e) => setFormData({ ...formData, telnyx_music_name: e.target.value })}
                >
                  {telnyxDefaults.map(track => (
                    <option key={track.key} value={track.key}>{track.name}</option>
                  ))}
                </select>
              </div>
            )}

            {formData.source_type === 'url' && (
              <div className="hm-form-group">
                <label>Audio URL *</label>
                <input
                  type="url"
                  value={formData.audio_url}
                  onChange={(e) => setFormData({ ...formData, audio_url: e.target.value })}
                  placeholder="https://example.com/music.mp3"
                />
                <span className="hm-hint">Must be a publicly accessible MP3 or WAV file</span>
              </div>
            )}

            <div className="hm-form-group">
              <label>Comfort Messages</label>
              <div className="hm-comfort-input">
                <input
                  type="text"
                  value={newComfortMsg}
                  onChange={(e) => setNewComfortMsg(e.target.value)}
                  placeholder="e.g., Your call is important to us..."
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddComfortMessage())}
                />
                <button
                  type="button"
                  className="hm-btn hm-btn-secondary hm-btn-small"
                  onClick={handleAddComfortMessage}
                >
                  Add
                </button>
              </div>
              {formData.comfort_messages.length > 0 && (
                <div className="hm-comfort-list">
                  {formData.comfort_messages.map((msg, idx) => (
                    <div key={idx} className="hm-comfort-item">
                      <span>"{msg}"</span>
                      <button type="button" onClick={() => handleRemoveComfortMessage(idx)}>×</button>
                    </div>
                  ))}
                </div>
              )}
              <span className="hm-hint">Messages played periodically while caller waits</span>
            </div>

            {formData.comfort_messages.length > 0 && (
              <div className="hm-form-group">
                <label>Message Interval (seconds)</label>
                <input
                  type="number"
                  value={formData.comfort_message_interval}
                  onChange={(e) => setFormData({ ...formData, comfort_message_interval: parseInt(e.target.value) })}
                  min={10}
                  max={120}
                />
              </div>
            )}

            <div className="hm-form-group hm-checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                />
                Set as default hold music
              </label>
            </div>
          </div>
          <div className="hm-modal-footer">
            <button type="button" className="hm-btn hm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="hm-btn hm-btn-primary">
              Add Music
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Edit Music Modal
const EditMusicModal = ({ music, onClose, onUpdate }) => {
  const [formData, setFormData] = useState({
    name: music.name || '',
    description: music.description || '',
    audio_url: music.audio_url || '',
    comfort_messages: music.comfort_messages || [],
    comfort_message_interval: music.comfort_message_interval || 30
  });
  const [newComfortMsg, setNewComfortMsg] = useState('');
  const [error, setError] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setError('Name is required');
      return;
    }
    onUpdate(formData);
  };

  const handleAddComfortMessage = () => {
    if (newComfortMsg.trim()) {
      setFormData({
        ...formData,
        comfort_messages: [...formData.comfort_messages, newComfortMsg.trim()]
      });
      setNewComfortMsg('');
    }
  };

  const handleRemoveComfortMessage = (index) => {
    setFormData({
      ...formData,
      comfort_messages: formData.comfort_messages.filter((_, i) => i !== index)
    });
  };

  return (
    <div className="hm-modal-overlay" onClick={onClose}>
      <div className="hm-modal" onClick={e => e.stopPropagation()}>
        <div className="hm-modal-header">
          <h2>Edit Hold Music</h2>
          <button className="hm-close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="hm-modal-body">
            {error && <div className="hm-form-error">{error}</div>}

            <div className="hm-form-group">
              <label>Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            <div className="hm-form-group">
              <label>Description</label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

            {music.source_type === 'url' && (
              <div className="hm-form-group">
                <label>Audio URL</label>
                <input
                  type="url"
                  value={formData.audio_url}
                  onChange={(e) => setFormData({ ...formData, audio_url: e.target.value })}
                />
              </div>
            )}

            <div className="hm-form-group">
              <label>Comfort Messages</label>
              <div className="hm-comfort-input">
                <input
                  type="text"
                  value={newComfortMsg}
                  onChange={(e) => setNewComfortMsg(e.target.value)}
                  placeholder="Add a comfort message..."
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddComfortMessage())}
                />
                <button
                  type="button"
                  className="hm-btn hm-btn-secondary hm-btn-small"
                  onClick={handleAddComfortMessage}
                >
                  Add
                </button>
              </div>
              {formData.comfort_messages.length > 0 && (
                <div className="hm-comfort-list">
                  {formData.comfort_messages.map((msg, idx) => (
                    <div key={idx} className="hm-comfort-item">
                      <span>"{msg}"</span>
                      <button type="button" onClick={() => handleRemoveComfortMessage(idx)}>×</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {formData.comfort_messages.length > 0 && (
              <div className="hm-form-group">
                <label>Message Interval (seconds)</label>
                <input
                  type="number"
                  value={formData.comfort_message_interval}
                  onChange={(e) => setFormData({ ...formData, comfort_message_interval: parseInt(e.target.value) })}
                  min={10}
                  max={120}
                />
              </div>
            )}
          </div>
          <div className="hm-modal-footer">
            <button type="button" className="hm-btn hm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="hm-btn hm-btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default HoldMusicDashboard;
