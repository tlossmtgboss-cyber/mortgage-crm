/**
 * AriaCallHistory -- Call audit trail for loan officers.
 *
 * Shows a paginated list of Aria voice calls with direction, duration,
 * summary, and sentiment. Expanding a row shows the full transcript with
 * speaker labels, recording playback, and action-item notes.
 *
 * Queries: GET /api/v1/aria/calls, GET /api/v1/aria/calls/stats,
 *          GET /api/v1/aria/calls/:id
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import './AriaCallHistory.css';

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
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function parseTranscript(raw) {
  if (!raw) return [];
  // Transcript stored as "ROLE: content\nROLE: content..."
  const lines = raw.split('\n').filter(Boolean);
  return lines.map((line) => {
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) return { speaker: 'unknown', text: line.trim() };
    const speaker = line.slice(0, colonIdx).trim().toLowerCase();
    const text = line.slice(colonIdx + 1).trim();
    // Normalize speaker labels
    const isAria =
      speaker === 'assistant' ||
      speaker === 'bot' ||
      speaker === 'aria' ||
      speaker === 'ai';
    return { speaker: isAria ? 'aria' : 'caller', text };
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AriaCallHistory() {
  const [calls, setCalls] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const perPage = 20;

  // Filters
  const [directionFilter, setDirectionFilter] = useState(null); // null = all
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Detail expansion
  const [expandedCallId, setExpandedCallId] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const detailAbortRef = useRef(null);
  const searchTimerRef = useRef(null);

  // Load stats
  useEffect(() => {
    api
      .get('/api/v1/aria/calls/stats?days=30')
      .then((res) => setStats(res.data))
      .catch((err) => console.warn('Failed to load call stats:', err));
  }, []);

  // Load call list
  const loadCalls = useCallback(
    async (pageNum) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set('page', String(pageNum));
        params.set('per_page', String(perPage));
        if (directionFilter) params.set('direction', directionFilter);
        if (searchQuery) params.set('search', searchQuery);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);

        const res = await api.get(`/api/v1/aria/calls?${params.toString()}`);
        const data = res.data;
        setCalls(data.calls || []);
        setTotal(data.total || 0);
        setHasMore(data.has_more || false);
      } catch (err) {
        console.error('Failed to load call history:', err);
        setError('Failed to load call history. Please try again.');
      } finally {
        setLoading(false);
      }
    },
    [directionFilter, searchQuery, dateFrom, dateTo]
  );

  // Reload on filter/page change
  useEffect(() => {
    loadCalls(page);
  }, [page, loadCalls]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [directionFilter, searchQuery, dateFrom, dateTo]);

  // Debounce search
  const handleSearchChange = (e) => {
    const val = e.target.value;
    clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setSearchQuery(val);
    }, 400);
  };

  // Load call detail
  const handleExpandCall = useCallback(
    async (callId) => {
      if (expandedCallId === callId) {
        setExpandedCallId(null);
        setDetailData(null);
        return;
      }

      detailAbortRef.current?.abort();
      const controller = new AbortController();
      detailAbortRef.current = controller;

      setExpandedCallId(callId);
      setDetailLoading(true);
      setDetailData(null);

      try {
        const res = await api.get(`/api/v1/aria/calls/${callId}`, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setDetailData(res.data);
        }
      } catch (err) {
        if (err?.name === 'CanceledError' || controller.signal.aborted) return;
        console.error('Failed to load call detail:', err);
        setDetailData({ error: true });
      } finally {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      }
    },
    [expandedCallId]
  );

  // Cleanup
  useEffect(() => {
    return () => {
      detailAbortRef.current?.abort();
      clearTimeout(searchTimerRef.current);
    };
  }, []);

  // Render transcript lines
  const renderTranscript = (transcript) => {
    const lines = parseTranscript(transcript);
    if (lines.length === 0) return <p className="ach-empty-sub">No transcript available</p>;

    return (
      <div className="ach-transcript">
        {lines.map((line, i) => (
          <div key={i} className="ach-transcript-line">
            <span className={`ach-transcript-speaker ${line.speaker}`}>
              {line.speaker === 'aria' ? 'Aria' : 'Caller'}
            </span>
            <span className="ach-transcript-text">{line.text}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="aria-call-history">
      {/* Header */}
      <div className="ach-header">
        <div>
          <h1>Aria Call Audit Trail</h1>
          <p className="ach-header-sub">
            Review what Aria said on every call -- transcripts, summaries, and recordings
          </p>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="ach-stats">
          <div className="ach-stat-card">
            <span className="ach-stat-value">{stats.total_calls}</span>
            <span className="ach-stat-label">Total Calls (30d)</span>
          </div>
          <div className="ach-stat-card">
            <span className="ach-stat-value">{stats.inbound_calls}</span>
            <span className="ach-stat-label">Inbound</span>
          </div>
          <div className="ach-stat-card">
            <span className="ach-stat-value">{stats.outbound_calls}</span>
            <span className="ach-stat-label">Outbound</span>
          </div>
          <div className="ach-stat-card">
            <span className="ach-stat-value">{formatDuration(stats.avg_duration)}</span>
            <span className="ach-stat-label">Avg Duration</span>
          </div>
          <div className="ach-stat-card">
            <span className="ach-stat-value">{stats.calls_with_transcript}</span>
            <span className="ach-stat-label">With Transcript</span>
          </div>
          <div className="ach-stat-card">
            <span className="ach-stat-value">{stats.positive_calls}</span>
            <span className="ach-stat-label">Positive</span>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="ach-filters">
        <button
          className={`ach-filter-btn ${!directionFilter ? 'active' : ''}`}
          onClick={() => setDirectionFilter(null)}
          type="button"
        >
          All
        </button>
        <button
          className={`ach-filter-btn ${directionFilter === 'inbound' ? 'active' : ''}`}
          onClick={() => setDirectionFilter('inbound')}
          type="button"
        >
          Inbound
        </button>
        <button
          className={`ach-filter-btn ${directionFilter === 'outbound' ? 'active' : ''}`}
          onClick={() => setDirectionFilter('outbound')}
          type="button"
        >
          Outbound
        </button>
        <input
          type="text"
          className="ach-search-input"
          placeholder="Search transcripts, summaries, names..."
          onChange={handleSearchChange}
        />
        <input
          type="date"
          className="ach-date-input"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          title="From date"
        />
        <input
          type="date"
          className="ach-date-input"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          title="To date"
        />
      </div>

      {/* Call list */}
      {loading ? (
        <div className="ach-loading">Loading call history...</div>
      ) : error ? (
        <div className="ach-error">
          {error}
          <br />
          <button
            className="ach-filter-btn"
            style={{ marginTop: 12 }}
            onClick={() => loadCalls(page)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : calls.length === 0 ? (
        <div className="ach-empty">
          <p className="ach-empty-title">No calls found</p>
          <p className="ach-empty-sub">
            {directionFilter || searchQuery || dateFrom || dateTo
              ? 'Try adjusting your filters'
              : 'When Aria handles calls, they will appear here with full transcripts'}
          </p>
        </div>
      ) : (
        <>
          <div className="ach-call-list">
            {calls.map((call) => (
              <React.Fragment key={call.id}>
                <div
                  className={`ach-call-row ${expandedCallId === call.id ? 'expanded' : ''}`}
                  onClick={() => handleExpandCall(call.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleExpandCall(call.id)}
                >
                  {/* Direction icon */}
                  <div className={`ach-direction-icon ${call.direction || 'inbound'}`}>
                    {call.direction === 'outbound' ? '↗' : '↙'}
                  </div>

                  {/* Call info */}
                  <div className="ach-call-info">
                    <div className="ach-call-top">
                      <span className="ach-call-name">
                        {call.caller_name || call.lead_name || 'Unknown Caller'}
                      </span>
                      {call.phone_number && (
                        <span className="ach-call-phone">{call.phone_number}</span>
                      )}
                    </div>
                    {call.summary && (
                      <p className="ach-call-summary-text">{call.summary}</p>
                    )}
                    <div className="ach-call-tags">
                      {call.sentiment && (
                        <span className={`ach-tag sentiment-${call.sentiment}`}>
                          {call.sentiment}
                        </span>
                      )}
                      {call.has_transcript && (
                        <span className="ach-tag has-transcript">transcript</span>
                      )}
                      {call.recording_url && (
                        <span className="ach-tag has-recording">recording</span>
                      )}
                      {call.lead_name && (
                        <span className="ach-tag">Lead: {call.lead_name}</span>
                      )}
                    </div>
                  </div>

                  {/* Meta */}
                  <div className="ach-call-meta">
                    <span className="ach-call-date">{formatDate(call.started_at)}</span>
                    <span className="ach-call-time">{formatTime(call.started_at)}</span>
                    {call.duration != null && (
                      <span className="ach-call-duration">{formatDuration(call.duration)}</span>
                    )}
                  </div>
                </div>

                {/* Expanded detail */}
                {expandedCallId === call.id && (
                  <div className="ach-detail-panel">
                    {detailLoading ? (
                      <div className="ach-loading" style={{ padding: 30 }}>
                        Loading call detail...
                      </div>
                    ) : detailData?.error ? (
                      <div className="ach-error" style={{ padding: 20 }}>
                        Failed to load call detail
                      </div>
                    ) : detailData ? (
                      <>
                        {/* Summary */}
                        {detailData.summary && (
                          <div className="ach-detail-section">
                            <h3>Summary</h3>
                            <p className="ach-detail-summary">{detailData.summary}</p>
                          </div>
                        )}

                        {/* Transcript */}
                        <div className="ach-detail-section">
                          <h3>Transcript</h3>
                          {renderTranscript(detailData.transcript)}
                        </div>

                        {/* Recording */}
                        {detailData.recording_url && (
                          <div className="ach-detail-section">
                            <h3>Recording</h3>
                            <div className="ach-recording">
                              <audio controls preload="none" src={detailData.recording_url}>
                                Your browser does not support audio playback.
                              </audio>
                              <a
                                href={detailData.recording_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="ach-recording-link"
                              >
                                Open in new tab
                              </a>
                            </div>
                          </div>
                        )}

                        {/* Notes / Action Items */}
                        {detailData.notes && detailData.notes.length > 0 && (
                          <div className="ach-detail-section">
                            <h3>Action Items</h3>
                            <div className="ach-notes-list">
                              {detailData.notes.map((note) => (
                                <div key={note.id} className="ach-note-item">
                                  <span className="ach-note-type">{note.type || 'note'}</span>
                                  <span className="ach-note-content">{note.content}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : null}
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>

          {/* Pagination */}
          <div className="ach-pagination">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              type="button"
            >
              Previous
            </button>
            <span className="ach-pagination-info">
              Page {page} of {Math.max(1, Math.ceil(total / perPage))} ({total} calls)
            </span>
            <button disabled={!hasMore} onClick={() => setPage((p) => p + 1)} type="button">
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
