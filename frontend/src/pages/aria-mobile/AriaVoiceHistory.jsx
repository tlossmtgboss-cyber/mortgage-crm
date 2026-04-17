/**
 * AriaVoiceHistory — Voice conversation history for Aria mobile.
 *
 * Shows a chronological list of past voice sessions with duration,
 * summary, sentiment, and outcome. Tapping a session shows the full
 * transcript and tool actions executed.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../services/api';
import AriaTabNav from '../../components/mobile/AriaTabNav';
import './AriaVoiceHistory.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds) {
  if (!seconds || seconds < 1) return '< 1s';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  const dayMs = 86_400_000;

  if (diff < dayMs) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  if (diff < 2 * dayMs) return 'Yesterday';
  if (diff < 7 * dayMs) {
    return d.toLocaleDateString([], { weekday: 'short' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

const SENTIMENT_COLORS = {
  positive: '#4ADE80',
  neutral: '#5A7AAA',
  negative: '#F87171',
  mixed: '#FBBF24',
};

const OUTCOME_LABELS = {
  action_taken: 'Action Taken',
  info_provided: 'Info Provided',
  escalated: 'Escalated',
  abandoned: 'Abandoned',
  completed: 'Completed',
  error: 'Error',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AriaVoiceHistory() {
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [selectedCall, setSelectedCall] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [analytics, setAnalytics] = useState(null);

  // Load call history
  const loadHistory = useCallback(async (signal) => {
    setLoading(true);
    setLoadError(null);
    try {
      const [callsRes, analyticsRes] = await Promise.all([
        api.get('/api/v1/mobile-voice/calls?limit=50'),
        api.get('/api/v1/mobile-voice/analytics?days=30'),
      ]);
      if (!signal?.aborted) {
        setCalls(callsRes.data?.calls || []);
        setAnalytics(analyticsRes.data || null);
      }
    } catch (err) {
      console.error('[AriaVoiceHistory] Load error:', err);
      if (!signal?.aborted) setLoadError('Failed to load voice history');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const historyAbortRef = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    historyAbortRef.current = controller;
    loadHistory(controller.signal);
    return () => controller.abort();
  }, [loadHistory]);

  // Load call detail — abort in-flight requests to prevent stale overwrites
  const detailAbortRef = useRef(null);
  const handleSelectCall = useCallback(async (call) => {
    if (selectedCall?.session_uuid === call.session_uuid) {
      setSelectedCall(null);
      return;
    }
    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;
    setDetailLoading(true);
    try {
      const res = await api.get(`/api/v1/mobile-voice/calls/${call.session_uuid}`, { signal: controller.signal });
      if (!controller.signal.aborted) setSelectedCall(res.data);
    } catch (err) {
      if (err?.name === 'CanceledError' || controller.signal.aborted) return;
      console.error('[AriaVoiceHistory] Detail error:', err);
      setSelectedCall({ ...call, transcript: null });
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  }, [selectedCall]);

  return (
    <div className="avh-history">
      <div className="avh-history-header">
        <h1 className="avh-history-title">Voice History</h1>
        {analytics && (
          <div className="avh-history-stats">
            <div className="avh-stat">
              <span className="avh-stat-value">{analytics.total_calls}</span>
              <span className="avh-stat-label">Calls</span>
            </div>
            <div className="avh-stat">
              <span className="avh-stat-value">{formatDuration(Math.round(analytics.avg_duration_seconds ?? 0))}</span>
              <span className="avh-stat-label">Avg</span>
            </div>
            <div className="avh-stat">
              <span className="avh-stat-value">{analytics.total_tools_executed ?? 0}</span>
              <span className="avh-stat-label">Actions</span>
            </div>
          </div>
        )}
      </div>

      <div className="avh-history-list">
        {loading ? (
          <div className="avh-history-empty">Loading...</div>
        ) : loadError ? (
          <div className="avh-history-empty">
            <p>{loadError}</p>
            <button
              className="avh-retry-btn"
              onClick={() => {
                historyAbortRef.current?.abort();
                const c = new AbortController();
                historyAbortRef.current = c;
                loadHistory(c.signal);
              }}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : calls.length === 0 ? (
          <div className="avh-history-empty">
            <p>No voice conversations yet.</p>
            <p className="avh-history-empty-sub">Tap the mic on the Home tab to start talking to Aria.</p>
          </div>
        ) : (
          calls.map((call) => (
            <React.Fragment key={call.session_uuid}>
              <button
                className={`avh-call-card ${selectedCall?.session_uuid === call.session_uuid ? 'avh-call-card--selected' : ''}`}
                onClick={() => handleSelectCall(call)}
                type="button"
              >
                <div className="avh-call-card-top">
                  <span className="avh-call-time">{formatDate(call.started_at)}</span>
                  <span className="avh-call-duration">{formatDuration(call.duration_seconds)}</span>
                </div>
                {call.summary && (
                  <p className="avh-call-summary">{call.summary}</p>
                )}
                <div className="avh-call-meta">
                  {call.sentiment && (
                    <span
                      className="avh-call-pill"
                      style={{ color: SENTIMENT_COLORS[call.sentiment] || '#5A7AAA' }}
                    >
                      {call.sentiment}
                    </span>
                  )}
                  {call.outcome && (
                    <span className="avh-call-pill avh-call-pill--outcome">
                      {OUTCOME_LABELS[call.outcome] || call.outcome}
                    </span>
                  )}
                  {call.tool_count > 0 && (
                    <span className="avh-call-pill avh-call-pill--tools">
                      {call.tool_count} tool{call.tool_count !== 1 ? 's' : ''}
                    </span>
                  )}
                  <span className="avh-call-pill avh-call-pill--msgs">
                    {call.message_count} msg{call.message_count !== 1 ? 's' : ''}
                  </span>
                </div>
              </button>

              {/* Expanded detail panel */}
              {selectedCall?.session_uuid === call.session_uuid && (
                <div className="avh-call-detail">
                  {detailLoading ? (
                    <div className="avh-call-detail-loading">Loading transcript...</div>
                  ) : selectedCall.transcript ? (
                    <div className="avh-transcript">
                      {selectedCall.transcript.map((msg, i) => (
                        <div key={`${selectedCall.session_uuid}-msg-${i}`} className={`avh-msg avh-msg--${msg.role}`}>
                          <span className="avh-msg-role">{msg.role === 'user' ? 'You' : 'Aria'}</span>
                          <p className="avh-msg-text">{msg.content}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="avh-call-detail-loading">No transcript available</div>
                  )}

                  {selectedCall.tools_executed && selectedCall.tools_executed.length > 0 && (
                    <div className="avh-tools-section">
                      <h3 className="avh-tools-title">Actions Executed</h3>
                      {selectedCall.tools_executed.map((tool, i) => (
                        <div key={`${selectedCall.session_uuid}-tool-${i}`} className="avh-tool-item">
                          <span className="avh-tool-name">{tool.tool || tool.name || 'Unknown'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </React.Fragment>
          ))
        )}
      </div>

      <AriaTabNav variant="dark" activeTab="history" />
    </div>
  );
}
