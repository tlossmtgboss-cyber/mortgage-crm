// Conference Room Dashboard - Manage and monitor conference calls
import React, { useState, useEffect, useCallback } from 'react';
import './ConferenceRoomDashboard.css';
import { toast } from '../../utils/toast';

const ConferenceRoomDashboard = () => {
  const [conferences, setConferences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedConference, setSelectedConference] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showQuickJoinModal, setShowQuickJoinModal] = useState(false);

  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  const fetchConferences = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/conferences`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch conferences: ${response.status}`);
      }

      const data = await response.json();
      setConferences(data.conferences || []);
      setError(null);
    } catch (err) {
      setError(err?.message || 'Failed to load conferences');
      // Demo data fallback
      setConferences([
        {
          id: 1,
          room_name: 'team-standup',
          friendly_name: 'Daily Team Standup',
          max_participants: 25,
          status: 'active',
          pin_required: false,
          record_conference: false,
          is_active: true,
          participant_count: 5,
          started_at: new Date().toISOString(),
          created_by: 'John Smith'
        },
        {
          id: 2,
          room_name: 'client-review',
          friendly_name: 'Client Loan Review',
          max_participants: 10,
          status: 'waiting',
          pin_required: true,
          record_conference: true,
          is_active: true,
          participant_count: 0,
          created_by: 'Jane Doe'
        }
      ]);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL]);

  useEffect(() => {
    fetchConferences();
    const interval = setInterval(fetchConferences, 15000);
    return () => clearInterval(interval);
  }, [fetchConferences]);

  const handleEndConference = async (conferenceId) => {
    if (!window.confirm('Are you sure you want to end this conference?')) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/conferences/${conferenceId}/end`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to end conference');
      }

      fetchConferences();
      setSelectedConference(null);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleJoinConference = async (conference) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/conferences/${conference.id}/join`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ as_host: true })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to join conference');
      }

      const data = await response.json();
      toast.success(`Joining conference. Dial-in: ${data.dial_in_number || 'Check your phone'}`);
      fetchConferences();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const getStatusBadge = (conference) => {
    if (conference.participant_count > 0) {
      return { label: 'In Progress', class: 'cr-badge-active' };
    }
    if (conference.status === 'waiting') {
      return { label: 'Waiting', class: 'cr-badge-waiting' };
    }
    if (!conference.is_active) {
      return { label: 'Ended', class: 'cr-badge-ended' };
    }
    return { label: 'Ready', class: 'cr-badge-ready' };
  };

  const formatDuration = (startedAt) => {
    if (!startedAt) return '--';
    const start = new Date(startedAt);
    const now = new Date();
    const diffMs = now - start;
    const mins = Math.floor(diffMs / 60000);
    const hours = Math.floor(mins / 60);
    if (hours > 0) {
      return `${hours}h ${mins % 60}m`;
    }
    return `${mins}m`;
  };

  if (loading) {
    return (
      <div className="cr-dashboard">
        <div className="cr-loading">
          <div className="cr-spinner"></div>
          <p>Loading conference rooms...</p>
        </div>
      </div>
    );
  }

  const activeConferences = conferences.filter(c => c.participant_count > 0);
  const totalParticipants = conferences.reduce((sum, c) => sum + (c.participant_count || 0), 0);

  return (
    <div className="cr-dashboard">
      <div className="cr-header">
        <div className="cr-header-left">
          <h1>Conference Rooms</h1>
          <p className="cr-subtitle">Create and manage multi-party conference calls</p>
        </div>
        <div className="cr-header-right">
          <button className="cr-btn cr-btn-secondary" onClick={fetchConferences}>
            <span className="cr-icon">&#x21bb;</span> Refresh
          </button>
          <button className="cr-btn cr-btn-outline" onClick={() => setShowQuickJoinModal(true)}>
            <span className="cr-icon">&#x260E;</span> Quick Join
          </button>
          <button className="cr-btn cr-btn-primary" onClick={() => setShowCreateModal(true)}>
            <span className="cr-icon">+</span> New Conference
          </button>
        </div>
      </div>

      {error && (
        <div className="cr-error-banner">
          <span className="cr-icon">&#x26A0;</span>
          {error}
          <button onClick={fetchConferences}>Retry</button>
        </div>
      )}

      <div className="cr-stats-row">
        <div className="cr-stat-card">
          <div className="cr-stat-value">{conferences.length}</div>
          <div className="cr-stat-label">Total Rooms</div>
        </div>
        <div className="cr-stat-card cr-stat-highlight">
          <div className="cr-stat-value">{activeConferences.length}</div>
          <div className="cr-stat-label">Active Conferences</div>
        </div>
        <div className="cr-stat-card">
          <div className="cr-stat-value">{totalParticipants}</div>
          <div className="cr-stat-label">Total Participants</div>
        </div>
        <div className="cr-stat-card">
          <div className="cr-stat-value">
            {conferences.filter(c => c.record_conference).length}
          </div>
          <div className="cr-stat-label">Recording Enabled</div>
        </div>
      </div>

      {activeConferences.length > 0 && (
        <div className="cr-section">
          <h2 className="cr-section-title">
            <span className="cr-live-dot"></span>
            Active Conferences
          </h2>
          <div className="cr-grid">
            {activeConferences.map(conference => (
              <ConferenceCard
                key={conference.id}
                conference={conference}
                onSelect={() => setSelectedConference(conference)}
                onJoin={() => handleJoinConference(conference)}
                onEnd={() => handleEndConference(conference.id)}
                isSelected={selectedConference?.id === conference.id}
                formatDuration={formatDuration}
                getStatusBadge={getStatusBadge}
              />
            ))}
          </div>
        </div>
      )}

      <div className="cr-section">
        <h2 className="cr-section-title">All Conference Rooms</h2>
        <div className="cr-grid">
          {conferences.filter(c => c.participant_count === 0).map(conference => (
            <ConferenceCard
              key={conference.id}
              conference={conference}
              onSelect={() => setSelectedConference(conference)}
              onJoin={() => handleJoinConference(conference)}
              onEnd={() => handleEndConference(conference.id)}
              isSelected={selectedConference?.id === conference.id}
              formatDuration={formatDuration}
              getStatusBadge={getStatusBadge}
            />
          ))}
        </div>
      </div>

      {conferences.length === 0 && (
        <div className="cr-empty-state">
          <div className="cr-empty-icon">&#x1F3A4;</div>
          <h3>No Conference Rooms</h3>
          <p>Create your first conference room to start hosting multi-party calls.</p>
          <button className="cr-btn cr-btn-primary" onClick={() => setShowCreateModal(true)}>
            Create Conference Room
          </button>
        </div>
      )}

      {/* Conference Detail Panel */}
      {selectedConference && (
        <ConferenceDetailPanel
          conference={selectedConference}
          onClose={() => setSelectedConference(null)}
          onJoin={() => handleJoinConference(selectedConference)}
          onEnd={() => handleEndConference(selectedConference.id)}
          formatDuration={formatDuration}
          getStatusBadge={getStatusBadge}
        />
      )}

      {/* Create Conference Modal */}
      {showCreateModal && (
        <CreateConferenceModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            fetchConferences();
          }}
          apiBaseUrl={API_BASE_URL}
        />
      )}

      {/* Quick Join Modal */}
      {showQuickJoinModal && (
        <QuickJoinModal
          onClose={() => setShowQuickJoinModal(false)}
          apiBaseUrl={API_BASE_URL}
        />
      )}
    </div>
  );
};

// Conference Card Component
const ConferenceCard = ({ conference, onSelect, onJoin, onEnd, isSelected, formatDuration, getStatusBadge }) => {
  const status = getStatusBadge(conference);
  const isActive = conference.participant_count > 0;

  return (
    <div
      className={`cr-card ${isSelected ? 'cr-card-selected' : ''} ${isActive ? 'cr-card-active' : ''}`}
      onClick={onSelect}
    >
      <div className="cr-card-header">
        <div className="cr-card-title">
          <h3>{conference.friendly_name}</h3>
          <span className="cr-card-name">{conference.room_name}</span>
        </div>
        <div className={`cr-card-badge ${status.class}`}>
          {status.label}
        </div>
      </div>

      <div className="cr-card-info">
        <div className="cr-info-row">
          <span className="cr-icon">&#x1F465;</span>
          <span>{conference.participant_count || 0} / {conference.max_participants} participants</span>
        </div>
        {isActive && (
          <div className="cr-info-row">
            <span className="cr-icon">&#x23F1;</span>
            <span>Duration: {formatDuration(conference.started_at)}</span>
          </div>
        )}
        <div className="cr-info-row">
          <span className="cr-icon">{conference.pin_required ? '&#x1F512;' : '&#x1F513;'}</span>
          <span>{conference.pin_required ? 'PIN Required' : 'No PIN'}</span>
        </div>
        {conference.record_conference && (
          <div className="cr-info-row cr-recording">
            <span className="cr-icon">&#x23FA;</span>
            <span>Recording</span>
          </div>
        )}
      </div>

      <div className="cr-card-footer">
        <span className="cr-created-by">Created by {conference.created_by || 'Unknown'}</span>
      </div>

      <div className="cr-card-actions">
        <button
          className="cr-btn cr-btn-join"
          onClick={(e) => {
            e.stopPropagation();
            onJoin();
          }}
        >
          <span className="cr-icon">&#x260E;</span>
          {isActive ? 'Join' : 'Start'}
        </button>
        {isActive && (
          <button
            className="cr-btn cr-btn-danger-outline"
            onClick={(e) => {
              e.stopPropagation();
              onEnd();
            }}
          >
            End
          </button>
        )}
        <button
          className="cr-btn cr-btn-outline"
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
        >
          Details
        </button>
      </div>
    </div>
  );
};

// Conference Detail Panel
const ConferenceDetailPanel = ({ conference, onClose, onJoin, onEnd, formatDuration, getStatusBadge }) => {
  const status = getStatusBadge(conference);
  const isActive = conference.participant_count > 0;

  return (
    <div className="cr-detail-panel">
      <div className="cr-detail-header">
        <h2>{conference.friendly_name}</h2>
        <button className="cr-close-btn" onClick={onClose}>&times;</button>
      </div>

      <div className="cr-detail-content">
        <div className={`cr-detail-status ${status.class}`}>
          {isActive && <span className="cr-live-dot"></span>}
          {status.label}
          {isActive && ` - ${formatDuration(conference.started_at)}`}
        </div>

        <div className="cr-detail-section">
          <h4>Room Information</h4>
          <div className="cr-detail-row">
            <span>Room Name:</span>
            <strong>{conference.room_name}</strong>
          </div>
          <div className="cr-detail-row">
            <span>Max Participants:</span>
            <strong>{conference.max_participants}</strong>
          </div>
          <div className="cr-detail-row">
            <span>Current Participants:</span>
            <strong>{conference.participant_count || 0}</strong>
          </div>
          <div className="cr-detail-row">
            <span>Created By:</span>
            <strong>{conference.created_by || 'Unknown'}</strong>
          </div>
        </div>

        <div className="cr-detail-section">
          <h4>Settings</h4>
          <div className="cr-detail-row">
            <span>PIN Required:</span>
            <strong>{conference.pin_required ? 'Yes' : 'No'}</strong>
          </div>
          {conference.pin_required && conference.participant_pin && (
            <div className="cr-detail-row">
              <span>Participant PIN:</span>
              <strong className="cr-pin">{conference.participant_pin}</strong>
            </div>
          )}
          {conference.pin_required && conference.host_pin && (
            <div className="cr-detail-row">
              <span>Host PIN:</span>
              <strong className="cr-pin">{conference.host_pin}</strong>
            </div>
          )}
          <div className="cr-detail-row">
            <span>Recording:</span>
            <strong className={conference.record_conference ? 'cr-text-warning' : ''}>
              {conference.record_conference ? 'Enabled' : 'Disabled'}
            </strong>
          </div>
        </div>

        {conference.participants && conference.participants.length > 0 && (
          <div className="cr-detail-section">
            <h4>Participants ({conference.participants.length})</h4>
            <div className="cr-participant-list">
              {conference.participants.map((p, idx) => (
                <div key={idx} className="cr-participant">
                  <span className="cr-participant-name">{p.name || p.phone}</span>
                  <span className={`cr-participant-status ${p.is_muted ? 'muted' : ''}`}>
                    {p.is_muted ? '&#x1F507;' : '&#x1F50A;'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="cr-detail-actions">
          <button className="cr-btn cr-btn-join cr-btn-full" onClick={onJoin}>
            <span className="cr-icon">&#x260E;</span>
            {isActive ? 'Join Conference' : 'Start Conference'}
          </button>
          {isActive && (
            <>
              <button className="cr-btn cr-btn-secondary">
                <span className="cr-icon">&#x1F507;</span> Mute All
              </button>
              <button className="cr-btn cr-btn-danger" onClick={onEnd}>
                End Conference
              </button>
            </>
          )}
          <button className="cr-btn cr-btn-outline">
            <span className="cr-icon">&#x270E;</span> Edit Room
          </button>
        </div>
      </div>
    </div>
  );
};

// Create Conference Modal
const CreateConferenceModal = ({ onClose, onCreated, apiBaseUrl }) => {
  const [formData, setFormData] = useState({
    room_name: '',
    friendly_name: '',
    max_participants: 50,
    pin_required: false,
    record_conference: false
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${apiBaseUrl}/api/v1/conferences`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create conference');
      }

      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cr-modal-overlay" onClick={onClose}>
      <div className="cr-modal" onClick={e => e.stopPropagation()}>
        <div className="cr-modal-header">
          <h2>Create Conference Room</h2>
          <button className="cr-close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="cr-modal-body">
            {error && <div className="cr-form-error">{error}</div>}

            <div className="cr-form-group">
              <label>Room Name (internal)</label>
              <input
                type="text"
                value={formData.room_name}
                onChange={e => setFormData({...formData, room_name: e.target.value.toLowerCase().replace(/\s+/g, '-')})}
                placeholder="e.g., team-standup"
                required
              />
              <span className="cr-form-hint">Used for identification, no spaces</span>
            </div>

            <div className="cr-form-group">
              <label>Display Name</label>
              <input
                type="text"
                value={formData.friendly_name}
                onChange={e => setFormData({...formData, friendly_name: e.target.value})}
                placeholder="e.g., Daily Team Standup"
                required
              />
            </div>

            <div className="cr-form-group">
              <label>Max Participants</label>
              <input
                type="number"
                value={formData.max_participants}
                onChange={e => setFormData({...formData, max_participants: parseInt(e.target.value)})}
                min={2}
                max={250}
              />
              <span className="cr-form-hint">Maximum 250 participants</span>
            </div>

            <div className="cr-form-group cr-checkbox-group">
              <label className="cr-checkbox">
                <input
                  type="checkbox"
                  checked={formData.pin_required}
                  onChange={e => setFormData({...formData, pin_required: e.target.checked})}
                />
                <span className="cr-checkmark"></span>
                Require PIN to join
              </label>
              <span className="cr-form-hint">PINs will be auto-generated for host and participants</span>
            </div>

            <div className="cr-form-group cr-checkbox-group">
              <label className="cr-checkbox">
                <input
                  type="checkbox"
                  checked={formData.record_conference}
                  onChange={e => setFormData({...formData, record_conference: e.target.checked})}
                />
                <span className="cr-checkmark"></span>
                Record conference
              </label>
              <span className="cr-form-hint">Participants will be notified of recording</span>
            </div>
          </div>

          <div className="cr-modal-footer">
            <button type="button" className="cr-btn cr-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="cr-btn cr-btn-primary" disabled={saving}>
              {saving ? 'Creating...' : 'Create Room'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Quick Join Modal
const QuickJoinModal = ({ onClose, apiBaseUrl }) => {
  const [roomName, setRoomName] = useState('');
  const [pin, setPin] = useState('');
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState(null);

  const handleJoin = async (e) => {
    e.preventDefault();
    setJoining(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${apiBaseUrl}/api/v1/conferences/join-by-name`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ room_name: roomName, pin: pin || undefined })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to join conference');
      }

      const data = await response.json();
      toast.info(`Joining conference. ${data.message || 'Check your phone for the call.'}`);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setJoining(false);
    }
  };

  return (
    <div className="cr-modal-overlay" onClick={onClose}>
      <div className="cr-modal cr-modal-small" onClick={e => e.stopPropagation()}>
        <div className="cr-modal-header">
          <h2>Quick Join Conference</h2>
          <button className="cr-close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleJoin}>
          <div className="cr-modal-body">
            {error && <div className="cr-form-error">{error}</div>}

            <div className="cr-form-group">
              <label>Room Name</label>
              <input
                type="text"
                value={roomName}
                onChange={e => setRoomName(e.target.value)}
                placeholder="Enter room name"
                required
              />
            </div>

            <div className="cr-form-group">
              <label>PIN (if required)</label>
              <input
                type="text"
                value={pin}
                onChange={e => setPin(e.target.value)}
                placeholder="Enter PIN"
                maxLength={6}
              />
            </div>
          </div>

          <div className="cr-modal-footer">
            <button type="button" className="cr-btn cr-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="cr-btn cr-btn-join" disabled={joining}>
              {joining ? 'Joining...' : 'Join Conference'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ConferenceRoomDashboard;
