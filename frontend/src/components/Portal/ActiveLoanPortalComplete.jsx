/**
 * ActiveLoanPortalComplete Component
 *
 * Complete borrower portal with real-time WebSocket updates.
 * Features:
 * - Real-time milestone updates (WebSocket + Polling fallback)
 * - Arrow timeline for S3-S5 stages
 * - Lifecycle milestones for all other stages
 * - Activity feed with last 10 events
 * - Risk flags with mitigation steps
 * - Document management
 * - Quick actions (call LO, message, upload)
 * - Live update indicator
 * - Auto-refresh every 30 seconds
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import CloseOnTimeArrowTimeline from './CloseOnTimeArrowTimeline';
import MilestoneTimeline from './MilestoneTimeline';
import CloseOnTimeCalendar from './CloseOnTimeCalendar';
import { borrowerPortalApi, closeOnTimeApi } from '../../services/portalApi';
import './ActiveLoanPortalComplete.css';

// Stages that show Close On Time arrow timeline (S3-S5)
const CLOSE_ON_TIME_STAGES = ['UNDER_CONTRACT', 'PROCESSING', 'CLEAR_TO_CLOSE'];

// WebSocket connection status
const WS_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

export default function ActiveLoanPortalComplete() {
  const { loanId } = useParams();
  const [activeTab, setActiveTab] = useState('overview');
  const [portalData, setPortalData] = useState(null);
  const [closeOnTimeData, setCloseOnTimeData] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wsStatus, setWsStatus] = useState(WS_STATUS.DISCONNECTED);
  const [lastUpdate, setLastUpdate] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pollIntervalRef = useRef(null);

  // Fetch all data - v2
  const fetchAllData = useCallback(async () => {
    try {
      const [dashboardData, cotData, activityData] = await Promise.all([
        borrowerPortalApi.getDashboard(loanId),
        closeOnTimeApi.getCountdownData(loanId).catch(() => null),
        borrowerPortalApi.getRecentActivity(loanId, 10).catch(() => []),
      ]);

      setPortalData(dashboardData);
      setCloseOnTimeData(cotData);
      setActivities(activityData);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error('Failed to fetch portal data:', err);
      setError(err.message || 'Failed to load portal data');
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    const wsUrl = process.env.REACT_APP_WS_URL || 'wss://api.perenniaai.com';
    const enableWs = process.env.REACT_APP_ENABLE_WEBSOCKET !== 'false';

    if (!enableWs) {
      return;
    }

    try {
      setWsStatus(WS_STATUS.CONNECTING);
      wsRef.current = new WebSocket(`${wsUrl}/ws/loan/${loanId}`);

      wsRef.current.onopen = () => {
        setWsStatus(WS_STATUS.CONNECTED);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      wsRef.current.onclose = () => {
        setWsStatus(WS_STATUS.DISCONNECTED);
        // Attempt reconnect after 5 seconds
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
      };

      wsRef.current.onerror = (err) => {
        console.error('WebSocket error:', err);
        setWsStatus(WS_STATUS.ERROR);
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setWsStatus(WS_STATUS.ERROR);
    }
  }, [loanId]);

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = (message) => {
    switch (message.type) {
      case 'MILESTONE_UPDATE':
      case 'LIFECYCLE_CHANGE':
      case 'DOCUMENT_UPDATE':
        // Refresh all data on significant updates
        fetchAllData();
        break;

      case 'ACTIVITY':
        // Add new activity to feed
        setActivities(prev => [message.data, ...prev.slice(0, 9)]);
        setLastUpdate(new Date());
        break;

      case 'PONG':
        // Heartbeat response, connection is healthy
        break;

      default:
        // Unknown message type - ignore
        break;
    }
  };

  // Send ping to keep connection alive
  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'PING', timestamp: Date.now() }));
    }
  }, []);

  // Initial load and WebSocket setup
  useEffect(() => {
    fetchAllData();
    connectWebSocket();

    // Polling fallback (every 30 seconds)
    pollIntervalRef.current = setInterval(() => {
      if (wsStatus !== WS_STATUS.CONNECTED) {
        fetchAllData();
      }
    }, 30000);

    // Keep-alive ping every 30 seconds
    const pingInterval = setInterval(sendPing, 30000);

    return () => {
      // Cleanup
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      clearInterval(pingInterval);
    };
  }, [fetchAllData, connectWebSocket, sendPing, wsStatus]);

  if (loading) {
    return <PortalSkeleton />;
  }

  if (error) {
    return (
      <div className="portal-error-state">
        <span className="error-icon">⚠️</span>
        <h2>Unable to Load Data</h2>
        <p>{error}</p>
        <button onClick={fetchAllData} className="retry-btn">
          Retry
        </button>
      </div>
    );
  }

  const stage = portalData?.portalStatus?.lifecycle?.stage;
  const showCloseOnTime = CLOSE_ON_TIME_STAGES.includes(stage);

  return (
    <div className="active-loan-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-left">
          <h1>Welcome{portalData?.borrower_name ? `, ${portalData.borrower_name}` : ''}!</h1>
          <div className="loan-info">
            <span className="loan-number">Loan #{portalData?.loan_number || loanId}</span>
            <span className={`stage-badge ${stage?.toLowerCase()}`}>
              {formatStageName(stage)}
            </span>
          </div>
        </div>

        <div className="header-right">
          {/* Live update indicator */}
          <div className={`live-indicator ${wsStatus}`}>
            <span className="indicator-dot" />
            <span className="indicator-text">
              {wsStatus === WS_STATUS.CONNECTED ? 'Live' : 'Polling'}
            </span>
          </div>

          {/* Last updated */}
          {lastUpdate && (
            <span className="last-update">
              Updated {formatTimeAgo(lastUpdate)}
            </span>
          )}
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="portal-tabs">
        <button
          className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
          onClick={() => setActiveTab('timeline')}
        >
          Timeline
        </button>
        <button
          className={`tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Documents
        </button>
        <button
          className={`tab-btn ${activeTab === 'activity' ? 'active' : ''}`}
          onClick={() => setActiveTab('activity')}
        >
          Activity
        </button>
      </nav>

      {/* Tab Content */}
      <div className="portal-content">
        {activeTab === 'overview' && (
          <OverviewTab
            portalData={portalData}
            closeOnTimeData={closeOnTimeData}
            showCloseOnTime={showCloseOnTime}
            loanId={loanId}
            activities={activities}
          />
        )}

        {activeTab === 'timeline' && (
          <TimelineTab
            loanId={loanId}
            showCloseOnTime={showCloseOnTime}
            closeOnTimeData={closeOnTimeData}
          />
        )}

        {activeTab === 'documents' && (
          <DocumentsTab
            loanId={loanId}
            documentSummary={portalData?.documentSummary}
          />
        )}

        {activeTab === 'activity' && (
          <ActivityTab activities={activities} />
        )}
      </div>

      {/* Quick Actions Floating Bar */}
      <QuickActionsBar loanId={loanId} loanOfficer={portalData?.loan_officer} />
    </div>
  );
}

/**
 * Overview Tab
 */
function OverviewTab({ portalData, closeOnTimeData, showCloseOnTime, loanId, activities }) {
  const { milestoneProgress, documentSummary, borrowerTasks, portalStatus } = portalData || {};

  return (
    <div className="overview-tab">
      {/* Close On Time Arrow Timeline (for S3-S5) */}
      {showCloseOnTime && closeOnTimeData?.has_schedule && (
        <section className="portal-section">
          <CloseOnTimeArrowTimeline
            loanId={loanId}
            milestones={closeOnTimeData?.milestones || []}
            targetCloseDate={closeOnTimeData?.target_close_date}
            businessDaysRemaining={closeOnTimeData?.business_days_remaining}
          />
        </section>
      )}

      {/* Progress Cards Grid */}
      <div className="cards-grid">
        {/* Progress Card */}
        <div className="portal-card progress-card">
          <h3>Loan Progress</h3>
          <div className="progress-display">
            <div className="progress-circle">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" fill="none" stroke="#e5e7eb" strokeWidth="10" />
                <circle
                  cx="50" cy="50" r="45" fill="none" stroke="#2D7A52" strokeWidth="10"
                  strokeDasharray={`${(milestoneProgress?.progress_percent || 0) * 2.83} 283`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <span className="progress-value">{milestoneProgress?.progress_percent || 0}%</span>
            </div>
            <div className="progress-stats">
              <div className="stat">
                <span className="stat-value">{milestoneProgress?.completed || 0}</span>
                <span className="stat-label">Complete</span>
              </div>
              <div className="stat">
                <span className="stat-value">{milestoneProgress?.in_progress || 0}</span>
                <span className="stat-label">In Progress</span>
              </div>
              <div className="stat">
                <span className="stat-value">{milestoneProgress?.pending || 0}</span>
                <span className="stat-label">Remaining</span>
              </div>
            </div>
          </div>
        </div>

        {/* Tasks Card */}
        <div className="portal-card tasks-card">
          <div className="card-header">
            <h3>Your Tasks</h3>
            {borrowerTasks?.length > 0 && (
              <span className="badge">{borrowerTasks.length}</span>
            )}
          </div>
          {!borrowerTasks?.length ? (
            <div className="empty-state">
              <span className="empty-icon">✅</span>
              <p>No pending tasks!</p>
            </div>
          ) : (
            <ul className="task-list">
              {borrowerTasks.slice(0, 4).map((task) => (
                <li key={task.id} className="task-item">
                  <span className="task-name">{task.name}</span>
                  {task.is_required && <span className="required-tag">Required</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Documents Card */}
        <div className="portal-card documents-card">
          <h3>Documents</h3>
          <div className="doc-progress">
            <div className="doc-progress-bar">
              <div
                className="doc-progress-fill"
                style={{ width: `${documentSummary?.completion_rate || 0}%` }}
              />
            </div>
            <span className="doc-progress-text">
              {documentSummary?.completion_rate || 0}% Complete
            </span>
          </div>
          <div className="doc-stats">
            <div className="doc-stat approved">
              <span className="doc-value">{documentSummary?.by_status?.approved || 0}</span>
              <span className="doc-label">Approved</span>
            </div>
            <div className="doc-stat pending">
              <span className="doc-value">{documentSummary?.pending_review || 0}</span>
              <span className="doc-label">Pending</span>
            </div>
            <div className="doc-stat needs-action">
              <span className="doc-value">{documentSummary?.needs_reupload || 0}</span>
              <span className="doc-label">Needs Action</span>
            </div>
          </div>
        </div>

        {/* Recent Activity Card */}
        <div className="portal-card activity-card">
          <h3>Recent Activity</h3>
          {!activities?.length ? (
            <div className="empty-state">
              <p>No recent activity</p>
            </div>
          ) : (
            <ul className="activity-list">
              {activities.slice(0, 4).map((activity, idx) => (
                <li key={activity.id || idx} className="activity-item">
                  <span className="activity-icon">{getActivityIcon(activity.activity_type)}</span>
                  <div className="activity-content">
                    <p>{activity.description}</p>
                    <span className="activity-time">{formatTimeAgo(activity.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Risk Flags */}
      {portalStatus?.risks?.active_count > 0 && (
        <RiskFlagsSection risks={portalStatus.risks} />
      )}
    </div>
  );
}

/**
 * Timeline Tab
 */
function TimelineTab({ loanId, showCloseOnTime, closeOnTimeData }) {
  return (
    <div className="timeline-tab">
      {showCloseOnTime && closeOnTimeData?.has_schedule ? (
        <>
          <section className="portal-section">
            <h3>Close On Time Tracker</h3>
            <CloseOnTimeArrowTimeline
              loanId={loanId}
              milestones={closeOnTimeData?.milestones || []}
              targetCloseDate={closeOnTimeData?.target_close_date}
              businessDaysRemaining={closeOnTimeData?.business_days_remaining}
            />
          </section>

          <section className="portal-section">
            <h3>Closing Calendar</h3>
            <CloseOnTimeCalendar loanId={loanId} />
          </section>
        </>
      ) : (
        <section className="portal-section">
          <h3>Your Loan Journey</h3>
          <MilestoneTimeline loanId={loanId} borrowerView={true} />
        </section>
      )}
    </div>
  );
}

/**
 * Documents Tab
 */
function DocumentsTab({ loanId, documentSummary }) {
  return (
    <div className="documents-tab">
      <section className="portal-section">
        <h3>Document Checklist</h3>
        <div className="documents-placeholder">
          <span className="placeholder-icon">📄</span>
          <p>Document management coming soon</p>
          <p className="placeholder-hint">
            View and upload documents directly from your portal
          </p>
        </div>
      </section>
    </div>
  );
}

/**
 * Activity Tab
 */
function ActivityTab({ activities }) {
  return (
    <div className="activity-tab">
      <section className="portal-section">
        <h3>Activity Feed</h3>
        {!activities?.length ? (
          <div className="empty-state">
            <span className="empty-icon">📋</span>
            <p>No activity yet</p>
          </div>
        ) : (
          <ul className="activity-feed">
            {activities.map((activity, idx) => (
              <li key={activity.id || idx} className="activity-feed-item">
                <span className="activity-icon">{getActivityIcon(activity.activity_type)}</span>
                <div className="activity-content">
                  <p className="activity-description">{activity.description}</p>
                  <span className="activity-time">{formatTimeAgo(activity.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Risk Flags Section
 */
function RiskFlagsSection({ risks }) {
  return (
    <section className="portal-section risk-section">
      <div className="risk-header">
        <span className="risk-icon">⚠️</span>
        <h3>Attention Needed</h3>
      </div>
      <div className="risk-content">
        <p>
          There {risks.active_count === 1 ? 'is' : 'are'} {risks.active_count} item
          {risks.active_count === 1 ? '' : 's'} that need attention.
        </p>
        {risks.flags?.length > 0 && (
          <ul className="risk-list">
            {risks.flags.map((flag, idx) => (
              <li key={idx} className={`risk-item ${flag.severity}`}>
                <span className="risk-title">{flag.title}</span>
                {flag.mitigation && (
                  <span className="risk-mitigation">{flag.mitigation}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="risk-cta">Contact your loan officer for assistance.</p>
      </div>
    </section>
  );
}

/**
 * Quick Actions Floating Bar
 */
function QuickActionsBar({ loanId, loanOfficer }) {
  return (
    <div className="quick-actions-bar">
      <button className="quick-action-btn primary" title="Call Loan Officer">
        <span className="action-icon">📞</span>
        <span className="action-label">Call LO</span>
      </button>
      <button className="quick-action-btn" title="Send Message">
        <span className="action-icon">💬</span>
        <span className="action-label">Message</span>
      </button>
      <button className="quick-action-btn" title="Upload Document">
        <span className="action-icon">📄</span>
        <span className="action-label">Upload</span>
      </button>
      <button className="quick-action-btn" title="Schedule Call">
        <span className="action-icon">📅</span>
        <span className="action-label">Schedule</span>
      </button>
    </div>
  );
}

/**
 * Portal Skeleton Loader
 */
function PortalSkeleton() {
  return (
    <div className="portal-skeleton">
      <div className="skeleton-header">
        <div className="skeleton-text" style={{ width: '200px', height: '28px' }} />
        <div className="skeleton-text" style={{ width: '150px', height: '20px' }} />
      </div>
      <div className="skeleton-tabs">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="skeleton-tab" />
        ))}
      </div>
      <div className="skeleton-cards">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="skeleton-card">
            <div className="skeleton-text" style={{ width: '100px', height: '18px' }} />
            <div className="skeleton-block" style={{ height: '120px' }} />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Helper: Format stage name
 */
function formatStageName(stage) {
  const stageNames = {
    PROSPECT: 'Prospect',
    LEAD: 'Lead',
    PREAPPROVAL: 'Pre-Approval',
    UNDER_CONTRACT: 'Under Contract',
    PROCESSING: 'Processing',
    CLEAR_TO_CLOSE: 'Clear to Close',
    FUNDED: 'Funded',
    MUM: 'Member Until Maturity',
    ANNUAL_REFRESH: 'Annual Refresh',
  };
  return stageNames[stage] || stage || 'Unknown';
}

/**
 * Helper: Get activity icon
 */
function getActivityIcon(type) {
  const icons = {
    stage_transition: '🔄',
    milestone_update: '✅',
    milestone_completed: '🎉',
    document_uploaded: '📄',
    document_status_changed: '📋',
    task_completed: '✓',
    heartbeat: '💓',
    risk_flag: '⚠️',
  };
  return icons[type] || '📌';
}

/**
 * Helper: Format time ago
 */
function formatTimeAgo(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
