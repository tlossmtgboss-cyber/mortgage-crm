/**
 * Twilio Status Callbacks Dashboard
 *
 * Monitors and displays:
 * - Twilio webhook callback events (status + recordings)
 * - Call attempts with status tracking
 * - Disposition management
 * - Real-time call status updates
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './TwilioStatusCallbacks.css';

const API_URL = process.env.REACT_APP_API_URL || '';

// Status badge colors
const STATUS_COLORS = {
  queued: '#6b7280',
  dialing: '#3b82f6',
  ringing: '#f59e0b',
  in_progress: '#10b981',
  completed: '#059669',
  failed: '#ef4444',
  canceled: '#9ca3af',
  busy: '#f97316'
};

// Disposition labels
const DISPOSITIONS = {
  scheduled: { label: 'Scheduled', color: '#10b981', icon: '📅' },
  not_interested: { label: 'Not Interested', color: '#6b7280', icon: '❌' },
  no_answer: { label: 'No Answer', color: '#f59e0b', icon: '📵' },
  voicemail_left: { label: 'Voicemail Left', color: '#8b5cf6', icon: '📧' },
  wrong_number: { label: 'Wrong Number', color: '#ef4444', icon: '🚫' },
  dnc: { label: 'Do Not Call', color: '#dc2626', icon: '⛔' },
  callback_requested: { label: 'Callback Requested', color: '#3b82f6', icon: '🔄' },
  failed: { label: 'Failed', color: '#ef4444', icon: '❗' }
};

const TwilioStatusCallbacks = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessSettings = isAdmin || hasAnyPermission(['settings.manage', 'admin.manage', 'system.admin']) || userRole === 'admin';
  const [loading, setLoading] = useState(true);
  const [callbackLogs, setCallbackLogs] = useState([]);
  const [callAttempts, setCallAttempts] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('callbacks');

  // Filters
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Lookup state
  const [lookupCallSid, setLookupCallSid] = useState('');
  const [lookupResult, setLookupResult] = useState(null);

  // Pagination
  const [callbacksPage, setCallbacksPage] = useState(0);
  const [attemptsPage, setAttemptsPage] = useState(0);
  const pageSize = 25;

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const fetchCallbackLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        limit: pageSize,
        offset: callbacksPage * pageSize
      });
      if (eventTypeFilter) params.append('event_type', eventTypeFilter);

      const res = await fetch(
        `${API_URL}/api/v1/twilio/callback-logs?${params}`,
        { headers: getAuthHeaders() }
      );

      if (res.ok) {
        const data = await res.json();
        setCallbackLogs(data.entries || []);
      }
    } catch (err) {
      console.error('Error fetching callback logs:', err);
    }
  }, [callbacksPage, eventTypeFilter]);

  const fetchCallAttempts = useCallback(async () => {
    try {
      // Note: This endpoint would need to be added to the backend
      // For now, we'll use the callback logs as a proxy
      const params = new URLSearchParams({
        limit: pageSize,
        offset: attemptsPage * pageSize
      });

      const res = await fetch(
        `${API_URL}/api/v1/twilio/callback-logs?${params}`,
        { headers: getAuthHeaders() }
      );

      if (res.ok) {
        const data = await res.json();
        // Group by call_sid to show unique attempts
        const attempts = {};
        (data.entries || []).forEach(entry => {
          if (!attempts[entry.call_sid]) {
            attempts[entry.call_sid] = {
              call_sid: entry.call_sid,
              latest_status: entry.call_status,
              event_count: 1,
              first_seen: entry.received_at,
              last_seen: entry.received_at
            };
          } else {
            attempts[entry.call_sid].event_count++;
            attempts[entry.call_sid].latest_status = entry.call_status;
            attempts[entry.call_sid].last_seen = entry.received_at;
          }
        });
        setCallAttempts(Object.values(attempts));
      }
    } catch (err) {
      console.error('Error fetching call attempts:', err);
    }
  }, [attemptsPage]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    await Promise.all([fetchCallbackLogs(), fetchCallAttempts()]);
    setLoading(false);
  }, [fetchCallbackLogs, fetchCallAttempts]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleLookupCall = async () => {
    if (!lookupCallSid.trim()) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/twilio/call-attempts/${lookupCallSid.trim()}`,
        { headers: getAuthHeaders() }
      );

      if (res.ok) {
        const data = await res.json();
        setLookupResult(data);
      } else {
        setLookupResult({ error: 'Call attempt not found' });
      }
    } catch (err) {
      setLookupResult({ error: 'Failed to lookup call' });
    }
  };

  const handleSetOutcome = async (attemptId, outcome) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/twilio/call-attempts/${attemptId}/outcome?outcome=${outcome}`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (res.ok) {
        setSuccess(`Outcome set to ${DISPOSITIONS[outcome]?.label || outcome}`);
        setTimeout(() => setSuccess(null), 3000);
        fetchData();
      } else {
        setError('Failed to set outcome');
      }
    } catch (err) {
      setError('Failed to set outcome');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getStatusBadge = (status) => {
    const color = STATUS_COLORS[status] || '#6b7280';
    return (
      <span className="status-badge" style={{ backgroundColor: color }}>
        {status?.replace('_', ' ') || 'unknown'}
      </span>
    );
  };

  const getDispositionBadge = (disposition) => {
    const config = DISPOSITIONS[disposition];
    if (!config) return <span className="disposition-badge">-</span>;
    return (
      <span className="disposition-badge" style={{ backgroundColor: config.color }}>
        {config.icon} {config.label}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="twilio-status-callbacks">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading Twilio Callbacks...</p>
        </div>
      </div>
    );
  }

  if (!canAccessSettings) {
    return (
      <div className="twilio-status-callbacks">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Twilio Status Callbacks.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="twilio-status-callbacks">
      <div className="page-header">
        <div>
          <h1>Twilio Status Callbacks</h1>
          <p>Monitor webhook events, call attempts, and dispositions</p>
        </div>
        <button className="btn btn-secondary" onClick={fetchData}>
          🔄 Refresh
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Tabs */}
      <div className="callbacks-tabs">
        <button
          className={activeTab === 'callbacks' ? 'active' : ''}
          onClick={() => setActiveTab('callbacks')}
        >
          Webhook Events
        </button>
        <button
          className={activeTab === 'attempts' ? 'active' : ''}
          onClick={() => setActiveTab('attempts')}
        >
          Call Attempts
        </button>
        <button
          className={activeTab === 'lookup' ? 'active' : ''}
          onClick={() => setActiveTab('lookup')}
        >
          Lookup Call
        </button>
        <button
          className={activeTab === 'stats' ? 'active' : ''}
          onClick={() => setActiveTab('stats')}
        >
          Statistics
        </button>
      </div>

      {/* Webhook Events Tab */}
      {activeTab === 'callbacks' && (
        <div className="callbacks-tab">
          <div className="filters-bar">
            <select
              value={eventTypeFilter}
              onChange={(e) => {
                setEventTypeFilter(e.target.value);
                setCallbacksPage(0);
              }}
            >
              <option value="">All Event Types</option>
              <option value="status">Status Updates</option>
              <option value="recording">Recordings</option>
            </select>
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Received</th>
                  <th>Call SID</th>
                  <th>Event Type</th>
                  <th>Status</th>
                  <th>Recording SID</th>
                </tr>
              </thead>
              <tbody>
                {callbackLogs.map((log) => (
                  <tr key={log.id}>
                    <td className="date-cell">{formatDate(log.received_at)}</td>
                    <td className="callsid-cell">
                      <code>{log.call_sid?.substring(0, 20)}...</code>
                    </td>
                    <td>
                      <span className={`event-type event-${log.event_type}`}>
                        {log.event_type}
                      </span>
                    </td>
                    <td>{log.call_status ? getStatusBadge(log.call_status) : '-'}</td>
                    <td>
                      {log.recording_sid ? (
                        <code className="recording-sid">{log.recording_sid?.substring(0, 15)}...</code>
                      ) : '-'}
                    </td>
                  </tr>
                ))}
                {callbackLogs.length === 0 && (
                  <tr>
                    <td colSpan="5" className="empty-state">
                      No webhook events recorded yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button
              disabled={callbacksPage === 0}
              onClick={() => setCallbacksPage(p => p - 1)}
            >
              Previous
            </button>
            <span>Page {callbacksPage + 1}</span>
            <button
              disabled={callbackLogs.length < pageSize}
              onClick={() => setCallbacksPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Call Attempts Tab */}
      {activeTab === 'attempts' && (
        <div className="attempts-tab">
          <div className="filters-bar">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="completed">Completed</option>
              <option value="in_progress">In Progress</option>
              <option value="failed">Failed</option>
              <option value="no_answer">No Answer</option>
            </select>
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Call SID</th>
                  <th>Latest Status</th>
                  <th>Events</th>
                  <th>First Seen</th>
                  <th>Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {callAttempts.map((attempt) => (
                  <tr key={attempt.call_sid}>
                    <td className="callsid-cell">
                      <code
                        className="clickable"
                        onClick={() => {
                          setLookupCallSid(attempt.call_sid);
                          setActiveTab('lookup');
                          handleLookupCall();
                        }}
                      >
                        {attempt.call_sid?.substring(0, 20)}...
                      </code>
                    </td>
                    <td>{getStatusBadge(attempt.latest_status)}</td>
                    <td>
                      <span className="event-count">{attempt.event_count}</span>
                    </td>
                    <td className="date-cell">{formatDate(attempt.first_seen)}</td>
                    <td className="date-cell">{formatDate(attempt.last_seen)}</td>
                  </tr>
                ))}
                {callAttempts.length === 0 && (
                  <tr>
                    <td colSpan="5" className="empty-state">
                      No call attempts recorded yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button
              disabled={attemptsPage === 0}
              onClick={() => setAttemptsPage(p => p - 1)}
            >
              Previous
            </button>
            <span>Page {attemptsPage + 1}</span>
            <button
              disabled={callAttempts.length < pageSize}
              onClick={() => setAttemptsPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Lookup Tab */}
      {activeTab === 'lookup' && (
        <div className="lookup-tab">
          <div className="lookup-card">
            <h3>Lookup Call Attempt</h3>
            <p>Enter a Twilio Call SID to view detailed information</p>

            <div className="lookup-input-group">
              <input
                type="text"
                value={lookupCallSid}
                onChange={(e) => setLookupCallSid(e.target.value)}
                placeholder="CA... (Twilio Call SID)"
              />
              <button className="btn btn-primary" onClick={handleLookupCall}>
                Lookup
              </button>
            </div>

            {lookupResult && !lookupResult.error && (
              <div className="lookup-result">
                <h4>Call Details</h4>

                <div className="result-grid">
                  <div className="result-item">
                    <label>Call SID</label>
                    <code>{lookupResult.provider_call_id}</code>
                  </div>
                  <div className="result-item">
                    <label>Status</label>
                    {getStatusBadge(lookupResult.status)}
                  </div>
                  <div className="result-item">
                    <label>Disposition</label>
                    {getDispositionBadge(lookupResult.disposition)}
                  </div>
                  <div className="result-item">
                    <label>Direction</label>
                    <span>{lookupResult.direction}</span>
                  </div>
                </div>

                <div className="result-grid">
                  <div className="result-item">
                    <label>From</label>
                    <span>{lookupResult.from_number || '-'}</span>
                  </div>
                  <div className="result-item">
                    <label>To</label>
                    <span>{lookupResult.to_number || '-'}</span>
                  </div>
                  <div className="result-item">
                    <label>Duration</label>
                    <span>{formatDuration(lookupResult.duration_seconds)}</span>
                  </div>
                  <div className="result-item">
                    <label>SIP Code</label>
                    <span>{lookupResult.sip_response_code || '-'}</span>
                  </div>
                </div>

                <div className="result-grid">
                  <div className="result-item">
                    <label>Started</label>
                    <span>{formatDate(lookupResult.started_at)}</span>
                  </div>
                  <div className="result-item">
                    <label>Answered</label>
                    <span>{formatDate(lookupResult.answered_at)}</span>
                  </div>
                  <div className="result-item">
                    <label>Ended</label>
                    <span>{formatDate(lookupResult.ended_at)}</span>
                  </div>
                </div>

                {lookupResult.recording_url && (
                  <div className="recording-section">
                    <label>Recording</label>
                    <audio controls src={lookupResult.recording_url}>
                      Your browser does not support audio playback.
                    </audio>
                  </div>
                )}

                {lookupResult.agent_notes && (
                  <div className="notes-section">
                    <label>Agent Notes</label>
                    <div className="notes-box">{lookupResult.agent_notes}</div>
                  </div>
                )}

                {/* Set Outcome Section */}
                <div className="outcome-section">
                  <label>Set Outcome</label>
                  <div className="outcome-buttons">
                    {Object.entries(DISPOSITIONS).map(([key, config]) => (
                      <button
                        key={key}
                        className="outcome-btn"
                        style={{ borderColor: config.color }}
                        onClick={() => handleSetOutcome(lookupResult.id, key)}
                      >
                        {config.icon} {config.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {lookupResult?.error && (
              <div className="lookup-error">{lookupResult.error}</div>
            )}
          </div>
        </div>
      )}

      {/* Statistics Tab */}
      {activeTab === 'stats' && (
        <div className="stats-tab">
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon">📊</div>
              <div className="stat-content">
                <div className="stat-value">{callbackLogs.length}</div>
                <div className="stat-label">Recent Events</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">📞</div>
              <div className="stat-content">
                <div className="stat-value">{callAttempts.length}</div>
                <div className="stat-label">Unique Calls</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">✅</div>
              <div className="stat-content">
                <div className="stat-value">
                  {callAttempts.filter(a => a.latest_status === 'completed').length}
                </div>
                <div className="stat-label">Completed</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">❌</div>
              <div className="stat-content">
                <div className="stat-value">
                  {callAttempts.filter(a => a.latest_status === 'failed').length}
                </div>
                <div className="stat-label">Failed</div>
              </div>
            </div>
          </div>

          <div className="status-breakdown">
            <h3>Status Breakdown</h3>
            <div className="breakdown-grid">
              {Object.entries(STATUS_COLORS).map(([status, color]) => {
                const count = callAttempts.filter(a => a.latest_status === status).length;
                return (
                  <div key={status} className="breakdown-item">
                    <div className="breakdown-bar" style={{
                      backgroundColor: color,
                      width: `${Math.max(5, (count / callAttempts.length) * 100)}%`
                    }}></div>
                    <span className="breakdown-label">{status.replace('_', ' ')}</span>
                    <span className="breakdown-count">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="info-card">
            <h3>Webhook Configuration</h3>
            <p>Configure your Twilio webhook URLs to point to these endpoints:</p>
            <div className="endpoint-list">
              <div className="endpoint">
                <label>Status Callback:</label>
                <code>{API_URL}/api/v1/twilio/status-callback</code>
              </div>
              <div className="endpoint">
                <label>Recording Callback:</label>
                <code>{API_URL}/api/v1/twilio/recording-callback</code>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TwilioStatusCallbacks;
