/**
 * MobileCallIntel — Screen 5: Call Intelligence for Perennia AI mobile.
 *
 * Shows live call monitoring with AI agent statuses and recent call history.
 * Accessed from AriaVoiceHome via the Call Intelligence button.
 * This is a detail/modal view — no AriaTabNav.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { callMonitoringAPI } from '../../services/api';
import './MobileCallIntel.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AI_AGENTS = [
  { name: 'Sentiment Analyzer', color: '#34A853' },
  { name: 'Objection Detector', color: '#7EB8F7' },
  { name: 'Coaching Agent',     color: '#9B7FE8' },
  { name: 'Compliance Monitor', color: '#FBBC04' },
  { name: 'Summary Writer',     color: '#7EB8F7' },
];

const POLL_INTERVAL_MS = 3000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a duration in seconds to "Xm Ys" or "Xh Ym".
 */
function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h ${rm}m`;
  }
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/**
 * How many minutes ago a timestamp was.
 */
function minutesAgo(isoString) {
  if (!isoString) return 0;
  const diff = Date.now() - new Date(isoString).getTime();
  return Math.max(0, Math.floor(diff / 60000));
}

/**
 * Format an ISO date to a short display string.
 */
function formatDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();

  if (isToday) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * Get caller display name from a session object.
 */
function getCallerName(session) {
  return session.caller_name || session.client_name || 'Unknown Caller';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MobileCallIntel() {
  const navigate = useNavigate();

  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});

  const pollRef = useRef(null);

  // ---- Fetch sessions on mount ----
  const fetchSessions = useCallback(async () => {
    try {
      const data = await callMonitoringAPI.listSessions({ limit: 10 });
      const list = Array.isArray(data) ? data : (data?.sessions || []);
      setSessions(list);

      // Identify active session
      const active = list.find(
        (s) => s.status === 'active' || s.status === 'in_progress'
      );
      setActiveSession(active || null);
      setError(null);
    } catch (err) {
      console.error('[MobileCallIntel] Failed to fetch sessions:', err);
      setError('Unable to load call sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // ---- Poll active session for agent updates ----
  useEffect(() => {
    if (!activeSession?.id) {
      // Clear poll if no active session
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const data = await callMonitoringAPI.getSession(activeSession.id);
        if (data) {
          // Update active session with fresh data
          setActiveSession(data);

          // Extract agent statuses if returned
          if (data.agent_statuses) {
            setAgentStatuses(data.agent_statuses);
          }

          // If session ended, refresh full list
          if (data.status !== 'active' && data.status !== 'in_progress') {
            fetchSessions();
          }
        }
      } catch (err) {
        console.error('[MobileCallIntel] Poll error:', err);
      }
    };

    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [activeSession?.id, fetchSessions]);

  // ---- Computed values ----
  const hasActiveCall = !!activeSession;
  const completedSessions = sessions.filter(
    (s) => s.status !== 'active' && s.status !== 'in_progress'
  );
  const agentCount = AI_AGENTS.length;

  // ---- Build agent status text ----
  const getAgentStatus = (agentName) => {
    // Check if server returned per-agent statuses
    const key = agentName.toLowerCase().replace(/\s+/g, '_');
    if (agentStatuses[key]) {
      return agentStatuses[key];
    }
    return hasActiveCall ? 'Listening...' : 'Standby';
  };

  // ---- Render ----
  return (
    <div className="mci-screen">
      {/* Safe-area padding */}
      <div className="mci-status-bar" />

      {/* Header */}
      <div className="mci-header">
        <div className="mci-header-top">
          <button
            className="mci-back-btn"
            onClick={() => navigate('/aria-voice')}
            type="button"
          >
            &larr; Back
          </button>
          {hasActiveCall && (
            <div className="mci-live-badge">
              <span className="mci-live-dot" />
              <span className="mci-live-text">Live</span>
            </div>
          )}
        </div>

        <h1 className="mci-title">Call Intelligence</h1>
        <p className="mci-subtitle">{agentCount} AI Agents Monitoring</p>
      </div>

      {/* Scrollable body */}
      <div className="mci-body">
        {loading && (
          <div className="mci-loading">
            <span className="mci-loading-text">Loading sessions...</span>
          </div>
        )}

        {error && !loading && (
          <div className="mci-error">
            <span className="mci-error-text">{error}</span>
          </div>
        )}

        {!loading && !error && (
          <>
            {/* ---- Active Call Card ---- */}
            {hasActiveCall ? (
              <div className="mci-card">
                <p className="mci-call-title">
                  {getCallerName(activeSession)}
                  {activeSession.call_type ? ` \u2014 ${activeSession.call_type}` : ''}
                </p>
                <p className="mci-call-meta">
                  Started {minutesAgo(activeSession.started_at)} min ago
                  {activeSession.phone_number
                    ? ` \u00B7 ${activeSession.phone_number}`
                    : ''}
                </p>

                <hr className="mci-divider" />

                <p className="mci-agents-title">Active Agents</p>
                {AI_AGENTS.map((agent) => (
                  <div className="mci-agent-row" key={agent.name}>
                    <span
                      className="mci-agent-dot"
                      style={{ background: agent.color }}
                    />
                    <span className="mci-agent-name">{agent.name}</span>
                    <span className="mci-agent-status">
                      {getAgentStatus(agent.name)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              /* ---- No active call — agents in standby ---- */
              <div className="mci-card">
                <div className="mci-empty">
                  <p className="mci-empty-text">No active calls</p>
                </div>

                <hr className="mci-divider" />

                <p className="mci-agents-title">Agents</p>
                {AI_AGENTS.map((agent) => (
                  <div
                    className="mci-agent-row mci-agent-row--standby"
                    key={agent.name}
                  >
                    <span
                      className="mci-agent-dot"
                      style={{ background: agent.color }}
                    />
                    <span className="mci-agent-name">{agent.name}</span>
                    <span className="mci-agent-status">Standby</span>
                  </div>
                ))}
              </div>
            )}

            {/* ---- Recent Calls ---- */}
            {completedSessions.length > 0 && (
              <>
                <p className="mci-section-title">Recent Calls</p>
                {completedSessions.map((session) => (
                  <div className="mci-recent-card" key={session.id}>
                    <p className="mci-recent-title">
                      Recent &mdash; {getCallerName(session)}
                    </p>
                    <p className="mci-recent-meta">
                      {formatDate(session.started_at)}
                      {session.duration
                        ? ` \u00B7 ${formatDuration(session.duration)}`
                        : session.ended_at && session.started_at
                        ? ` \u00B7 ${formatDuration(
                            (new Date(session.ended_at) -
                              new Date(session.started_at)) /
                              1000
                          )}`
                        : ''}
                      {session.call_type
                        ? ` \u00B7 ${session.call_type}`
                        : ''}
                    </p>
                  </div>
                ))}
              </>
            )}

            {/* No sessions at all */}
            {!hasActiveCall && completedSessions.length === 0 && (
              <div className="mci-empty" style={{ marginTop: 16 }}>
                <p className="mci-empty-text">
                  No recent call sessions found
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
