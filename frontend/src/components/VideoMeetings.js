import React, { useState, useEffect, useCallback } from 'react';
import './VideoMeetings.css';
import RecordingPlayer from './VideoMeetings/RecordingPlayer';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const VideoMeetings = ({ onClose, leadId, loanId, contactId }) => {
  const [view, setView] = useState('meetings'); // meetings, templates, create, room
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data states
  const [meetings, setMeetings] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedMeeting, setSelectedMeeting] = useState(null);

  // Filter states
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('upcoming');

  // Create meeting form
  const [meetingForm, setMeetingForm] = useState({
    room_name: '',
    room_description: '',
    scheduled_start: '',
    duration_minutes: 30,
    meeting_type: 'general',
    recording_enabled: true,
    transcription_enabled: true,
    ai_assistant_enabled: true,
    waiting_room_enabled: true,
    template_id: null
  });

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showMeetingDetail, setShowMeetingDetail] = useState(false);
  const [showRecordingPlayer, setShowRecordingPlayer] = useState(false);
  const [selectedRecording, setSelectedRecording] = useState(null);

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Fetch initial data
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [meetingsRes, templatesRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/meetings/rooms?limit=50`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/meetings/templates`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/meetings/stats`, { headers: getAuthHeaders() })
      ]);

      if (meetingsRes.ok) {
        const meetingsData = await meetingsRes.json();
        setMeetings(meetingsData.meetings || []);
      }

      if (templatesRes.ok) {
        const templatesData = await templatesRes.json();
        setTemplates(templatesData.templates || []);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData.stats || null);
      }
    } catch (err) {
      setError('Failed to load meeting data');
      console.error('Meetings fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const createInstantMeeting = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/instant`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        // Open meeting in new tab
        window.open(data.meeting.join_url, '_blank');
        fetchData(); // Refresh list
      } else {
        setError('Failed to create instant meeting');
      }
    } catch (err) {
      setError('Failed to create instant meeting');
      console.error('Instant meeting error:', err);
    }
  };

  const createScheduledMeeting = async () => {
    try {
      const payload = {
        ...meetingForm,
        loan_id: loanId || null,
        lead_id: leadId || null
      };

      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        setShowCreateModal(false);
        setMeetingForm({
          room_name: '',
          room_description: '',
          scheduled_start: '',
          duration_minutes: 30,
          meeting_type: 'general',
          recording_enabled: true,
          transcription_enabled: true,
          ai_assistant_enabled: true,
          waiting_room_enabled: true,
          template_id: null
        });
        fetchData();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create meeting');
      }
    } catch (err) {
      setError('Failed to create meeting');
      console.error('Create meeting error:', err);
    }
  };

  const getMeetingDetails = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setSelectedMeeting(data);
        setShowMeetingDetail(true);
      }
    } catch (err) {
      console.error('Get meeting details error:', err);
    }
  };

  const startMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}/start`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
      }
    } catch (err) {
      console.error('Start meeting error:', err);
    }
  };

  const endMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}/end`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
        setShowMeetingDetail(false);
      }
    } catch (err) {
      console.error('End meeting error:', err);
    }
  };

  const cancelMeeting = async (meetingId) => {
    if (!window.confirm('Are you sure you want to cancel this meeting?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
        setShowMeetingDetail(false);
      }
    } catch (err) {
      console.error('Cancel meeting error:', err);
    }
  };

  const viewRecording = async (recordingId, meetingTitle) => {
    try {
      // Fetch transcript and analysis
      const [transcriptRes, analysisRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/transcript`, {
          headers: getAuthHeaders()
        }),
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/analysis`, {
          headers: getAuthHeaders()
        })
      ]);

      let transcript = {};
      let analysis = {};

      if (transcriptRes.ok) {
        transcript = await transcriptRes.json();
      }

      if (analysisRes.ok) {
        analysis = await analysisRes.json();
      }

      setSelectedRecording({
        id: recordingId,
        meeting_title: meetingTitle,
        recording_url: `${API_BASE}/api/v1/meetings/recordings/${recordingId}/stream`,
        transcript: transcript,
        analysis: analysis.analysis || {},
        created_at: new Date().toISOString()
      });
      setShowRecordingPlayer(true);
    } catch (err) {
      console.error('View recording error:', err);
      setError('Failed to load recording');
    }
  };

  const seedDefaultTemplates = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/templates/seed-defaults`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
      }
    } catch (err) {
      console.error('Seed templates error:', err);
    }
  };

  const applyTemplate = (template) => {
    setMeetingForm({
      ...meetingForm,
      room_name: template.template_name,
      meeting_type: template.template_key,
      duration_minutes: template.default_duration_minutes,
      recording_enabled: template.recording_enabled,
      ai_assistant_enabled: template.ai_assistant_enabled,
      template_id: template.id
    });
  };

  const getFilteredMeetings = () => {
    let filtered = [...meetings];

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(m => m.status === statusFilter);
    }

    // Date filter
    const now = new Date();
    if (dateFilter === 'upcoming') {
      filtered = filtered.filter(m => m.scheduled_start && new Date(m.scheduled_start) >= now);
    } else if (dateFilter === 'past') {
      filtered = filtered.filter(m => m.scheduled_start && new Date(m.scheduled_start) < now);
    } else if (dateFilter === 'today') {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const todayEnd = new Date(todayStart.getTime() + 24 * 60 * 60 * 1000);
      filtered = filtered.filter(m => {
        const start = new Date(m.scheduled_start);
        return start >= todayStart && start < todayEnd;
      });
    }

    return filtered;
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return 'Not scheduled';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const getStatusBadge = (status) => {
    const statusColors = {
      scheduled: { bg: '#dbeafe', color: '#1e40af' },
      active: { bg: '#dcfce7', color: '#166534' },
      waiting: { bg: '#fef3c7', color: '#92400e' },
      ended: { bg: '#f3f4f6', color: '#374151' },
      cancelled: { bg: '#fee2e2', color: '#991b1b' }
    };
    const style = statusColors[status] || statusColors.scheduled;
    return (
      <span
        className="status-badge"
        style={{ backgroundColor: style.bg, color: style.color }}
      >
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  const getTemplateIcon = (icon) => {
    const icons = {
      phone: '📞',
      document: '📄',
      folder: '📁',
      lock: '🔒',
      clipboard: '📋',
      users: '👥',
      video: '🎥'
    };
    return icons[icon] || '🎥';
  };

  // Render Stats Cards
  const renderStats = () => {
    if (!stats) return null;

    return (
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total_meetings}</div>
          <div className="stat-label">Total Meetings</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.meetings_this_week}</div>
          <div className="stat-label">This Week</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.upcoming_meetings}</div>
          <div className="stat-label">Upcoming</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.total_meeting_hours}h</div>
          <div className="stat-label">Total Hours</div>
        </div>
      </div>
    );
  };

  // Render Meetings List
  const renderMeetingsList = () => {
    const filteredMeetings = getFilteredMeetings();

    return (
      <div className="meetings-list-container">
        {/* Filters */}
        <div className="meetings-filters">
          <div className="filter-group">
            <label>Status:</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">All</option>
              <option value="scheduled">Scheduled</option>
              <option value="active">Active</option>
              <option value="ended">Ended</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Time:</label>
            <select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)}>
              <option value="all">All Time</option>
              <option value="upcoming">Upcoming</option>
              <option value="today">Today</option>
              <option value="past">Past</option>
            </select>
          </div>
        </div>

        {/* Meetings List */}
        {filteredMeetings.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">🎥</span>
            <h3>No meetings found</h3>
            <p>Create your first meeting to get started</p>
            <button className="primary-btn" onClick={() => setShowCreateModal(true)}>
              Schedule Meeting
            </button>
          </div>
        ) : (
          <div className="meetings-list">
            {filteredMeetings.map(meeting => (
              <div key={meeting.id} className="meeting-card" onClick={() => getMeetingDetails(meeting.id)}>
                <div className="meeting-card-header">
                  <h4>{meeting.room_name}</h4>
                  {getStatusBadge(meeting.status)}
                </div>
                <div className="meeting-card-body">
                  <div className="meeting-info">
                    <span className="info-item">
                      <span className="icon">📅</span>
                      {formatDateTime(meeting.scheduled_start)}
                    </span>
                    <span className="info-item">
                      <span className="icon">⏱️</span>
                      {meeting.duration_minutes} min
                    </span>
                    <span className="info-item">
                      <span className="icon">🏷️</span>
                      {meeting.meeting_type}
                    </span>
                  </div>
                  <div className="meeting-features">
                    {meeting.recording_enabled && <span className="feature-badge" title="Recording">🔴</span>}
                    {meeting.ai_assistant_enabled && <span className="feature-badge" title="AI Assistant">🤖</span>}
                  </div>
                </div>
                <div className="meeting-card-footer">
                  <span className="room-code">{meeting.room_code}</span>
                  {meeting.status === 'scheduled' && (
                    <button
                      className="action-btn start-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        startMeeting(meeting.id);
                      }}
                    >
                      Start
                    </button>
                  )}
                  {meeting.status === 'active' && (
                    <button
                      className="action-btn join-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.open(`/meeting/${meeting.room_code}`, '_blank');
                      }}
                    >
                      Join
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Render Templates
  const renderTemplates = () => {
    return (
      <div className="templates-container">
        <div className="templates-header">
          <h3>Meeting Templates</h3>
          <button className="secondary-btn" onClick={seedDefaultTemplates}>
            Load Defaults
          </button>
        </div>

        {templates.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📋</span>
            <h3>No templates yet</h3>
            <p>Load default templates to get started</p>
            <button className="primary-btn" onClick={seedDefaultTemplates}>
              Load Default Templates
            </button>
          </div>
        ) : (
          <div className="templates-grid">
            {templates.map(template => (
              <div key={template.id || template.template_key} className="template-card">
                <div className="template-icon" style={{ backgroundColor: template.color }}>
                  {getTemplateIcon(template.icon)}
                </div>
                <div className="template-info">
                  <h4>{template.template_name}</h4>
                  <p>{template.description}</p>
                  <div className="template-meta">
                    <span>{template.default_duration_minutes} min</span>
                    {template.recording_enabled && <span>Recording</span>}
                    {template.ai_assistant_enabled && <span>AI</span>}
                  </div>
                </div>
                <button
                  className="use-template-btn"
                  onClick={() => {
                    applyTemplate(template);
                    setShowCreateModal(true);
                  }}
                >
                  Use Template
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Render Create Meeting Modal
  const renderCreateModal = () => {
    if (!showCreateModal) return null;

    return (
      <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Schedule Meeting</h3>
            <button className="close-btn" onClick={() => setShowCreateModal(false)}>x</button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label>Meeting Name *</label>
              <input
                type="text"
                value={meetingForm.room_name}
                onChange={(e) => setMeetingForm({ ...meetingForm, room_name: e.target.value })}
                placeholder="e.g., Discovery Call with John"
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={meetingForm.room_description}
                onChange={(e) => setMeetingForm({ ...meetingForm, room_description: e.target.value })}
                placeholder="Meeting description..."
                rows={3}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Date & Time *</label>
                <input
                  type="datetime-local"
                  value={meetingForm.scheduled_start}
                  onChange={(e) => setMeetingForm({ ...meetingForm, scheduled_start: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Duration</label>
                <select
                  value={meetingForm.duration_minutes}
                  onChange={(e) => setMeetingForm({ ...meetingForm, duration_minutes: parseInt(e.target.value) })}
                >
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={45}>45 minutes</option>
                  <option value={60}>1 hour</option>
                  <option value={90}>1.5 hours</option>
                  <option value={120}>2 hours</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>Meeting Type</label>
              <select
                value={meetingForm.meeting_type}
                onChange={(e) => setMeetingForm({ ...meetingForm, meeting_type: e.target.value })}
              >
                <option value="general">General</option>
                <option value="discovery_call">Discovery Call</option>
                <option value="pre_approval_review">Pre-Approval Review</option>
                <option value="document_review">Document Review</option>
                <option value="rate_lock_discussion">Rate Lock Discussion</option>
                <option value="closing_prep">Closing Preparation</option>
                <option value="post_close_review">Post-Close Review</option>
                <option value="team_sync">Team Sync</option>
              </select>
            </div>

            <div className="form-section">
              <h4>Meeting Settings</h4>
              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.recording_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, recording_enabled: e.target.checked })}
                  />
                  <span>Enable Recording</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.transcription_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, transcription_enabled: e.target.checked })}
                  />
                  <span>Enable Transcription</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.ai_assistant_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, ai_assistant_enabled: e.target.checked })}
                  />
                  <span>Enable AI Assistant</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.waiting_room_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, waiting_room_enabled: e.target.checked })}
                  />
                  <span>Enable Waiting Room</span>
                </label>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button className="secondary-btn" onClick={() => setShowCreateModal(false)}>
              Cancel
            </button>
            <button
              className="primary-btn"
              onClick={createScheduledMeeting}
              disabled={!meetingForm.room_name || !meetingForm.scheduled_start}
            >
              Create Meeting
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Render Meeting Detail Modal
  const renderMeetingDetailModal = () => {
    if (!showMeetingDetail || !selectedMeeting) return null;

    const meeting = selectedMeeting.meeting;
    const participants = selectedMeeting.participants || [];
    const recordings = selectedMeeting.recordings || [];

    return (
      <div className="modal-overlay" onClick={() => setShowMeetingDetail(false)}>
        <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{meeting.room_name}</h3>
            <button className="close-btn" onClick={() => setShowMeetingDetail(false)}>x</button>
          </div>
          <div className="modal-body">
            {/* Meeting Info */}
            <div className="detail-section">
              <div className="detail-row">
                <span className="detail-label">Status:</span>
                {getStatusBadge(meeting.status)}
              </div>
              <div className="detail-row">
                <span className="detail-label">Room Code:</span>
                <span className="room-code-large">{meeting.room_code}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Scheduled:</span>
                <span>{formatDateTime(meeting.scheduled_start)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Duration:</span>
                <span>{meeting.duration_minutes} minutes</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Type:</span>
                <span>{meeting.meeting_type}</span>
              </div>
              {meeting.room_description && (
                <div className="detail-row">
                  <span className="detail-label">Description:</span>
                  <span>{meeting.room_description}</span>
                </div>
              )}
            </div>

            {/* Participants */}
            <div className="detail-section">
              <h4>Participants ({participants.length})</h4>
              {participants.length === 0 ? (
                <p className="no-data">No participants yet</p>
              ) : (
                <div className="participants-list">
                  {participants.map(p => (
                    <div key={p.id} className="participant-item">
                      <span className="participant-name">{p.display_name || p.email}</span>
                      <span className={`participant-role ${p.role}`}>{p.role}</span>
                      <span className={`participant-status ${p.status}`}>{p.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recordings */}
            <div className="detail-section">
              <h4>Recordings ({recordings.length})</h4>
              {recordings.length === 0 ? (
                <p className="no-data">No recordings yet</p>
              ) : (
                <div className="recordings-list">
                  {recordings.map(r => (
                    <div
                      key={r.id}
                      className="recording-item clickable"
                      onClick={() => viewRecording(r.id, meeting.room_name)}
                    >
                      <span className="recording-icon">🔴</span>
                      <span className="recording-name">{r.recording_name}</span>
                      <span className="recording-status">{r.status}</span>
                      {r.duration_seconds && (
                        <span className="recording-duration">
                          {Math.floor(r.duration_seconds / 60)}:{(r.duration_seconds % 60).toString().padStart(2, '0')}
                        </span>
                      )}
                      <span className="recording-play-btn">▶ Play</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* AI Summary */}
            {meeting.ai_summary && (
              <div className="detail-section">
                <h4>AI Summary</h4>
                <p className="ai-summary">{meeting.ai_summary}</p>
              </div>
            )}

            {/* AI Action Items */}
            {meeting.ai_action_items && meeting.ai_action_items.length > 0 && (
              <div className="detail-section">
                <h4>Action Items</h4>
                <ul className="action-items-list">
                  {meeting.ai_action_items.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div className="modal-footer">
            {meeting.status === 'scheduled' && (
              <>
                <button className="danger-btn" onClick={() => cancelMeeting(meeting.id)}>
                  Cancel Meeting
                </button>
                <button className="primary-btn" onClick={() => startMeeting(meeting.id)}>
                  Start Meeting
                </button>
              </>
            )}
            {meeting.status === 'active' && (
              <>
                <button className="danger-btn" onClick={() => endMeeting(meeting.id)}>
                  End Meeting
                </button>
                <button
                  className="primary-btn"
                  onClick={() => window.open(`/meeting/${meeting.room_code}`, '_blank')}
                >
                  Join Meeting
                </button>
              </>
            )}
            {meeting.status === 'ended' && (
              <button className="secondary-btn" onClick={() => setShowMeetingDetail(false)}>
                Close
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Main Render
  if (loading) {
    return (
      <div className="video-meetings-container">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading meetings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="video-meetings-container">
      {/* Header */}
      <div className="meetings-header">
        <div className="header-left">
          <h2>Video Meetings</h2>
          <p className="subtitle">AI-powered video conferencing for mortgage professionals</p>
        </div>
        <div className="header-actions">
          <button className="secondary-btn" onClick={createInstantMeeting}>
            <span className="btn-icon">🚀</span> Start Instant
          </button>
          <button className="primary-btn" onClick={() => setShowCreateModal(true)}>
            <span className="btn-icon">+</span> Schedule Meeting
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>x</button>
        </div>
      )}

      {/* Stats */}
      {renderStats()}

      {/* Navigation Tabs */}
      <div className="meetings-tabs">
        <button
          className={`tab-btn ${view === 'meetings' ? 'active' : ''}`}
          onClick={() => setView('meetings')}
        >
          My Meetings
        </button>
        <button
          className={`tab-btn ${view === 'templates' ? 'active' : ''}`}
          onClick={() => setView('templates')}
        >
          Templates
        </button>
      </div>

      {/* Content */}
      <div className="meetings-content">
        {view === 'meetings' && renderMeetingsList()}
        {view === 'templates' && renderTemplates()}
      </div>

      {/* Modals */}
      {renderCreateModal()}
      {renderMeetingDetailModal()}

      {/* Recording Player */}
      {showRecordingPlayer && selectedRecording && (
        <RecordingPlayer
          recording={selectedRecording}
          onClose={() => {
            setShowRecordingPlayer(false);
            setSelectedRecording(null);
          }}
        />
      )}
    </div>
  );
};

export default VideoMeetings;
