/**
 * Dashboard Overview Component
 *
 * Main dashboard for Call Intelligence showing:
 * - Key metrics (pending, active, completed, conversion)
 * - Recent calls requiring attention
 * - Quick access to review queue
 * - Activity charts
 */

import React from 'react';

const DashboardOverview = ({
  metrics,
  pendingSessions,
  activeSessions,
  completedSessions,
  onSelectSession,
  onViewReviewQueue,
  onViewActiveCalls,
}) => {
  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format time ago
  const formatTimeAgo = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  // Get status badge class
  const getStatusClass = (status) => {
    switch (status) {
      case 'active':
      case 'capturing':
        return 'status-active';
      case 'processing':
        return 'status-processing';
      case 'completed':
        return 'status-completed';
      default:
        return '';
    }
  };

  // Urgent calls (active for more than 30 min or pending review for more than 24h)
  const urgentCalls = [
    ...activeSessions.filter(s => {
      const started = new Date(s.started_at);
      const now = new Date();
      return (now - started) > 1800000; // 30 minutes
    }),
    ...pendingSessions.slice(0, 3),
  ].slice(0, 5);

  return (
    <div className="dashboard-overview">
      {/* Metrics Cards */}
      <div className="metrics-grid">
        <div className="metric-card pending">
          <div className="metric-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2" />
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.pending_reviews}</div>
            <div className="metric-label">Pending Reviews</div>
          </div>
          {metrics.pending_reviews > 0 && (
            <button className="metric-action" onClick={onViewReviewQueue}>
              Review Now
            </button>
          )}
        </div>

        <div className="metric-card active">
          <div className="metric-icon pulse">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.active_calls}</div>
            <div className="metric-label">Active Calls</div>
          </div>
          {metrics.active_calls > 0 && (
            <button className="metric-action" onClick={onViewActiveCalls}>
              Monitor
            </button>
          )}
        </div>

        <div className="metric-card completed">
          <div className="metric-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.completed_today}</div>
            <div className="metric-label">Completed Today</div>
          </div>
        </div>

        <div className="metric-card conversion">
          <div className="metric-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 20V10" />
              <path d="M18 20V4" />
              <path d="M6 20v-4" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.conversion_rate}%</div>
            <div className="metric-label">Conversion Rate</div>
          </div>
        </div>
      </div>

      {/* Urgent Attention Section */}
      {urgentCalls.length > 0 && (
        <div className="urgent-section">
          <div className="section-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              Requires Attention
            </h3>
            <span className="count">{urgentCalls.length}</span>
          </div>
          <div className="urgent-list">
            {urgentCalls.map(session => (
              <div
                key={session.id}
                className="urgent-item"
                onClick={() => onSelectSession(session)}
              >
                <div className="urgent-main">
                  <span className={`status-dot ${getStatusClass(session.status)}`}></span>
                  <div className="urgent-info">
                    <div className="urgent-title">
                      {session.metadata?.caller_name || 'Unknown Caller'}
                    </div>
                    <div className="urgent-meta">
                      <span>{formatDuration(session.duration_seconds)}</span>
                      <span className="divider">|</span>
                      <span>{formatTimeAgo(session.started_at)}</span>
                    </div>
                  </div>
                </div>
                <div className="urgent-badges">
                  <span className={`status-badge ${getStatusClass(session.status)}`}>
                    {session.status}
                  </span>
                  {session.approval_status === 'pending' && (
                    <span className="approval-badge">Needs Review</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Calls Section */}
      {activeSessions.length > 0 && (
        <div className="active-section">
          <div className="section-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
              </svg>
              Live Calls
            </h3>
            <button className="view-all-btn" onClick={onViewActiveCalls}>
              View All
            </button>
          </div>
          <div className="active-calls-grid">
            {activeSessions.slice(0, 4).map(session => (
              <div
                key={session.id}
                className="active-call-card"
                onClick={() => onSelectSession(session)}
              >
                <div className="call-status">
                  <span className="live-indicator"></span>
                  LIVE
                </div>
                <div className="call-info">
                  <div className="caller-name">
                    {session.metadata?.caller_name || 'Active Call'}
                  </div>
                  <div className="call-duration">
                    {formatDuration(session.duration_seconds)}
                  </div>
                </div>
                <div className="call-mode">
                  {session.capture_mode?.replace('_', ' ')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Completed */}
      <div className="recent-section">
        <div className="section-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Recent Activity
          </h3>
        </div>
        {completedSessions.length === 0 ? (
          <div className="empty-state">
            <p>No completed calls yet</p>
          </div>
        ) : (
          <div className="recent-list">
            {completedSessions.slice(0, 5).map(session => (
              <div
                key={session.id}
                className="recent-item"
                onClick={() => onSelectSession(session)}
              >
                <div className="recent-info">
                  <div className="recent-title">
                    {session.metadata?.caller_name || 'Completed Call'}
                  </div>
                  <div className="recent-meta">
                    <span>{formatDuration(session.duration_seconds)}</span>
                    <span className="divider">|</span>
                    <span>{session.capture_mode?.replace('_', ' ')}</span>
                  </div>
                </div>
                <div className="recent-time">
                  {formatTimeAgo(session.ended_at)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="quick-stats">
        <div className="stat-item">
          <div className="stat-label">Avg Call Duration</div>
          <div className="stat-value">
            {formatDuration(
              completedSessions.length > 0
                ? Math.round(
                    completedSessions.reduce((sum, s) => sum + (s.duration_seconds || 0), 0) /
                    completedSessions.length
                  )
                : 0
            )}
          </div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Total This Week</div>
          <div className="stat-value">{completedSessions.length}</div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Apps Created</div>
          <div className="stat-value">0</div>
        </div>
      </div>
    </div>
  );
};

export default DashboardOverview;
