/**
 * Review Queue Component
 *
 * Left panel showing list of calls pending review or completed.
 * Features:
 * - Filterable/sortable list
 * - Session cards with key info
 * - Selection state for detail view
 */

import React, { useState, useMemo } from 'react';

const ReviewQueue = ({
  sessions,
  selectedSession,
  onSelectSession,
  isCompletedView = false,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('date_desc');
  const [filterMode, setFilterMode] = useState('all');

  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return `Today ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    if (date.toDateString() === yesterday.toDateString()) {
      return `Yesterday ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    return date.toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get capture mode display
  const getModeDisplay = (mode) => {
    const modes = {
      mobile_app: { label: 'Mobile', color: '#B8924A' },
      crm_web_call: { label: 'CRM Call', color: '#2D7A52' },
      ambient_mic: { label: 'Ambient', color: '#f59e0b' },
      video_call: { label: 'Video', color: '#ec4899' },
    };
    return modes[mode] || { label: mode || 'Unknown', color: '#6b7280' };
  };

  // Filter and sort sessions
  const filteredSessions = useMemo(() => {
    let result = [...sessions];

    // Search filter
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(s =>
        (s.metadata?.caller_name || '').toLowerCase().includes(term) ||
        (s.metadata?.phone || '').includes(term) ||
        (s.metadata?.loan_purpose || '').toLowerCase().includes(term)
      );
    }

    // Mode filter
    if (filterMode !== 'all') {
      result = result.filter(s => s.capture_mode === filterMode);
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'date_asc':
          return new Date(a.started_at) - new Date(b.started_at);
        case 'date_desc':
          return new Date(b.started_at) - new Date(a.started_at);
        case 'duration_desc':
          return (b.duration_seconds || 0) - (a.duration_seconds || 0);
        case 'duration_asc':
          return (a.duration_seconds || 0) - (b.duration_seconds || 0);
        default:
          return 0;
      }
    });

    return result;
  }, [sessions, searchTerm, sortBy, filterMode]);

  // Count artifacts for a session
  const getArtifactCount = (session) => {
    return session.artifact_count || 0;
  };

  return (
    <div className="review-queue">
      {/* Header */}
      <div className="rq-header">
        <h3>{isCompletedView ? 'Completed Calls' : 'Review Queue'}</h3>
        <span className="rq-count">{filteredSessions.length}</span>
      </div>

      {/* Search & Filters */}
      <div className="rq-filters">
        <div className="rq-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search calls..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="rq-filter-row">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rq-select"
          >
            <option value="date_desc">Newest First</option>
            <option value="date_asc">Oldest First</option>
            <option value="duration_desc">Longest First</option>
            <option value="duration_asc">Shortest First</option>
          </select>
          <select
            value={filterMode}
            onChange={(e) => setFilterMode(e.target.value)}
            className="rq-select"
          >
            <option value="all">All Sources</option>
            <option value="mobile_app">Mobile</option>
            <option value="crm_web_call">CRM Call</option>
            <option value="ambient_mic">Ambient</option>
            <option value="video_call">Video</option>
          </select>
        </div>
      </div>

      {/* Session List */}
      <div className="rq-list">
        {filteredSessions.length === 0 ? (
          <div className="rq-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
            </svg>
            <p>No calls {isCompletedView ? 'completed' : 'pending review'}</p>
          </div>
        ) : (
          filteredSessions.map(session => {
            const modeInfo = getModeDisplay(session.capture_mode);
            const isSelected = selectedSession?.id === session.id;

            return (
              <div
                key={session.id}
                className={`rq-item ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectSession(session)}
              >
                <div className="rq-item-header">
                  <div className="rq-item-title">
                    {session.metadata?.caller_name || 'Unknown Caller'}
                  </div>
                  <div
                    className="rq-item-mode"
                    style={{ backgroundColor: `${modeInfo.color}20`, color: modeInfo.color }}
                  >
                    {modeInfo.label}
                  </div>
                </div>

                <div className="rq-item-meta">
                  <span className="rq-item-date">
                    {formatDate(session.started_at || session.ended_at)}
                  </span>
                  <span className="rq-item-divider">|</span>
                  <span className="rq-item-duration">
                    {formatDuration(session.duration_seconds)}
                  </span>
                </div>

                {session.metadata?.loan_purpose && (
                  <div className="rq-item-purpose">
                    {session.metadata.loan_purpose}
                  </div>
                )}

                <div className="rq-item-footer">
                  {getArtifactCount(session) > 0 && (
                    <span className="rq-item-artifacts">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      {getArtifactCount(session)} items
                    </span>
                  )}
                  {isCompletedView && (
                    <span className={`rq-item-status ${session.approval_status}`}>
                      {session.approval_status === 'approved' ? 'Approved' : 'Rejected'}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default ReviewQueue;
