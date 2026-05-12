/**
 * PerenniaClientPortalUltimate Component
 *
 * All-in-one production-ready client portal with dynamic stage-based views.
 *
 * Features:
 * - Real-time WebSocket updates with polling fallback (30s)
 * - 7 dynamic tabs that change based on lifecycle stage
 * - Arrow timeline for S3-S5 stages (Under Contract to Clear to Close)
 * - Home value intelligence for MUM stage
 * - Scenario/Presentation engine for MUM stage
 * - Document management with upload/download
 * - Activity feed with live updates
 * - Risk flags with mitigation steps
 * - Quick actions bar
 * - Responsive design with mobile support
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import CloseOnTimeArrowTimeline from './CloseOnTimeArrowTimeline';
import MilestoneTimeline from './MilestoneTimeline';
import CloseOnTimeCalendar from './CloseOnTimeCalendar';
import {
  borrowerPortalApi,
  closeOnTimeApi,
  lifecycleApi,
  documentApi,
  homeValueApi
} from '../../services/portalApi';
import './PerenniaClientPortalUltimate.css';

// =============================================================================
// CONSTANTS & CONFIGURATION
// =============================================================================

// Lifecycle stages
const LIFECYCLE_STAGES = {
  PROSPECT: 'PROSPECT',
  LEAD: 'LEAD',
  PREAPPROVAL: 'PREAPPROVAL',
  UNDER_CONTRACT: 'UNDER_CONTRACT',
  PROCESSING: 'PROCESSING',
  CLEAR_TO_CLOSE: 'CLEAR_TO_CLOSE',
  FUNDED: 'FUNDED',
  MUM: 'MUM',
  ANNUAL_REFRESH: 'ANNUAL_REFRESH',
};

// Stages that show Close On Time arrow timeline (S3-S5)
const CLOSE_ON_TIME_STAGES = [
  LIFECYCLE_STAGES.UNDER_CONTRACT,
  LIFECYCLE_STAGES.PROCESSING,
  LIFECYCLE_STAGES.CLEAR_TO_CLOSE,
];

// Stages that show MUM features
const MUM_STAGES = [
  LIFECYCLE_STAGES.MUM,
  LIFECYCLE_STAGES.ANNUAL_REFRESH,
];

// WebSocket connection status
const WS_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

// Tab configurations by stage
const TAB_CONFIG = {
  default: ['overview', 'timeline', 'documents', 'activity'],
  active_loan: ['overview', 'timeline', 'documents', 'tasks', 'activity', 'team'],
  mum: ['overview', 'home_value', 'scenarios', 'documents', 'activity', 'team'],
};

// Stage display names
const STAGE_NAMES = {
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

// Activity type icons
const ACTIVITY_ICONS = {
  stage_transition: '🔄',
  milestone_update: '✅',
  milestone_completed: '🎉',
  document_uploaded: '📄',
  document_status_changed: '📋',
  document_approved: '✓',
  document_rejected: '❌',
  task_completed: '✓',
  task_created: '📌',
  heartbeat: '💓',
  risk_flag: '⚠️',
  risk_resolved: '✅',
  note_added: '📝',
  message_sent: '💬',
  call_logged: '📞',
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function PerenniaClientPortalUltimate() {
  const { loanId, token } = useParams();
  const effectiveLoanId = loanId || null;

  // State
  const [activeTab, setActiveTab] = useState('overview');
  const [portalData, setPortalData] = useState(null);
  const [closeOnTimeData, setCloseOnTimeData] = useState(null);
  const [homeValueData, setHomeValueData] = useState(null);
  const [activities, setActivities] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wsStatus, setWsStatus] = useState(WS_STATUS.DISCONNECTED);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [showNotification, setShowNotification] = useState(null);
  const [resolvedLoanId, setResolvedLoanId] = useState(effectiveLoanId);

  // Refs
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pollIntervalRef = useRef(null);

  // =============================================================================
  // DATA FETCHING
  // =============================================================================

  // Resolve token to loan ID if needed
  const resolveToken = useCallback(async () => {
    if (effectiveLoanId) {
      setResolvedLoanId(effectiveLoanId);
      return effectiveLoanId;
    }

    if (token) {
      try {
        const response = await borrowerPortalApi.getPortalByToken(token);
        const id = response.loan_id || response.loanId;
        setResolvedLoanId(id);
        return id;
      } catch (err) {
        console.error('Failed to resolve token:', err);
        setError('Invalid or expired access link');
        return null;
      }
    }

    setError('No loan ID or access token provided');
    return null;
  }, [effectiveLoanId, token]);

  // Fetch all portal data
  const fetchAllData = useCallback(async () => {
    const id = resolvedLoanId || await resolveToken();
    if (!id) return;

    try {
      // Fetch core data in parallel
      const [dashboardData, activityData, docData] = await Promise.all([
        borrowerPortalApi.getBorrowerDashboard(id).catch(() => borrowerPortalApi.getDashboard(id)),
        lifecycleApi.getRecentActivity(id, 20, true).catch(() => []),
        documentApi.getLoanDocuments(id, null, null, true).catch(() => []),
      ]);

      setPortalData(dashboardData);
      setActivities(Array.isArray(activityData) ? activityData : activityData?.activities || []);
      setDocuments(Array.isArray(docData) ? docData : docData?.documents || []);

      // Fetch stage-specific data
      const stage = dashboardData?.portalStatus?.lifecycle?.stage ||
                   dashboardData?.lifecycle?.stage ||
                   dashboardData?.stage;

      if (CLOSE_ON_TIME_STAGES.includes(stage)) {
        const cotData = await closeOnTimeApi.getCountdownData(id).catch(() => null);
        setCloseOnTimeData(cotData);
      }

      if (MUM_STAGES.includes(stage)) {
        const hvData = await homeValueApi.getHomeValueDashboard(id).catch(() => null);
        setHomeValueData(hvData);
      }

      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error('Failed to fetch portal data:', err);
      setError(err.message || 'Failed to load portal data');
    } finally {
      setLoading(false);
    }
  }, [resolvedLoanId, resolveToken]);

  // =============================================================================
  // WEBSOCKET CONNECTION
  // =============================================================================

  const connectWebSocket = useCallback(() => {
    if (!resolvedLoanId) return;

    const wsUrl = process.env.REACT_APP_WS_URL ||
                  (window.location.protocol === 'https:' ? 'wss:' : 'ws:') +
                  '//' + window.location.host;
    const enableWs = process.env.REACT_APP_ENABLE_WEBSOCKET !== 'false';

    if (!enableWs) {
      console.log('WebSocket disabled, using polling only');
      return;
    }

    try {
      setWsStatus(WS_STATUS.CONNECTING);
      // Security: Token sent as first message after connect, not in URL query
      // string, to avoid leaking JWT into server/proxy logs and browser history.
      const wsEndpoint = `${wsUrl}/ws/loan/${resolvedLoanId}`;
      wsRef.current = new WebSocket(wsEndpoint);

      wsRef.current.onopen = () => {
        if (token) {
          wsRef.current.send(JSON.stringify({ type: 'auth', token }));
        }
        console.log('Portal WebSocket connected');
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
        console.log('Portal WebSocket disconnected');
        setWsStatus(WS_STATUS.DISCONNECTED);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
      };

      wsRef.current.onerror = (err) => {
        console.error('Portal WebSocket error:', err);
        setWsStatus(WS_STATUS.ERROR);
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setWsStatus(WS_STATUS.ERROR);
    }
  }, [resolvedLoanId, token]);

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((message) => {
    console.log('WebSocket message received:', message.type);

    switch (message.type) {
      case 'CONNECTION_ESTABLISHED':
        showToast('Connected to live updates', 'success');
        break;

      case 'MILESTONE_UPDATE':
        fetchAllData();
        showToast(`Milestone updated: ${message.data?.milestone_name}`, 'info');
        break;

      case 'LIFECYCLE_CHANGE':
        fetchAllData();
        showToast(`Stage changed to: ${STAGE_NAMES[message.data?.new_stage] || message.data?.new_stage}`, 'success');
        break;

      case 'DOCUMENT_UPDATE':
        fetchAllData();
        showToast(`Document ${message.data?.status}: ${message.data?.file_name || message.data?.document_type}`, 'info');
        break;

      case 'CLOSE_ON_TIME_UPDATE':
        fetchAllData();
        break;

      case 'NOTIFICATION':
        showToast(message.data?.message || message.data?.title, message.data?.notification_type || 'info');
        break;

      case 'ACTIVITY':
        setActivities(prev => [message.data, ...prev.slice(0, 19)]);
        setLastUpdate(new Date());
        break;

      case 'PING':
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'PONG', timestamp: Date.now() }));
        }
        break;

      default:
        console.log('Unknown WebSocket message type:', message.type);
    }
  }, [fetchAllData]);

  // Show toast notification
  const showToast = useCallback((message, type = 'info') => {
    setShowNotification({ message, type });
    setTimeout(() => setShowNotification(null), 4000);
  }, []);

  // Send WebSocket ping
  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'PING', timestamp: Date.now() }));
    }
  }, []);

  // =============================================================================
  // EFFECTS
  // =============================================================================

  // Initial load
  useEffect(() => {
    resolveToken().then(id => {
      if (id) {
        setResolvedLoanId(id);
      }
    });
  }, [resolveToken]);

  // Fetch data when loan ID is resolved
  useEffect(() => {
    if (resolvedLoanId) {
      fetchAllData();
      connectWebSocket();

      // Polling fallback (every 30 seconds)
      pollIntervalRef.current = setInterval(() => {
        if (wsStatus !== WS_STATUS.CONNECTED) {
          fetchAllData();
        }
      }, 30000);

      // Keep-alive ping
      const pingInterval = setInterval(sendPing, 30000);

      return () => {
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
    }
  }, [resolvedLoanId, fetchAllData, connectWebSocket, sendPing, wsStatus]);

  // =============================================================================
  // COMPUTED VALUES
  // =============================================================================

  const stage = useMemo(() => {
    return portalData?.portalStatus?.lifecycle?.stage ||
           portalData?.lifecycle?.stage ||
           portalData?.stage ||
           LIFECYCLE_STAGES.LEAD;
  }, [portalData]);

  const showCloseOnTime = useMemo(() => {
    return CLOSE_ON_TIME_STAGES.includes(stage);
  }, [stage]);

  const showMumFeatures = useMemo(() => {
    return MUM_STAGES.includes(stage);
  }, [stage]);

  const availableTabs = useMemo(() => {
    if (showMumFeatures) return TAB_CONFIG.mum;
    if (showCloseOnTime) return TAB_CONFIG.active_loan;
    return TAB_CONFIG.default;
  }, [showCloseOnTime, showMumFeatures]);

  const borrowerName = useMemo(() => {
    return portalData?.borrower_name ||
           portalData?.borrower?.name ||
           portalData?.portalStatus?.borrower_name ||
           '';
  }, [portalData]);

  const loanNumber = useMemo(() => {
    return portalData?.loan_number ||
           portalData?.loan?.number ||
           resolvedLoanId ||
           '';
  }, [portalData, resolvedLoanId]);

  // =============================================================================
  // RENDER
  // =============================================================================

  if (loading) {
    return <PortalSkeleton />;
  }

  if (error) {
    return (
      <div className="portal-error-state">
        <span className="error-icon">⚠️</span>
        <h2>Unable to Load Portal</h2>
        <p>{error}</p>
        <button onClick={fetchAllData} className="retry-btn">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="perennia-portal-ultimate">
      {/* Toast Notification */}
      {showNotification && (
        <div className={`toast-notification ${showNotification.type}`}>
          <span className="toast-message">{showNotification.message}</span>
          <button className="toast-close" onClick={() => setShowNotification(null)}>×</button>
        </div>
      )}

      {/* Header */}
      <header className="portal-header">
        <div className="header-left">
          <div className="brand">
            <span className="brand-logo">🏠</span>
            <span className="brand-name">Perennia</span>
          </div>
          <div className="welcome-section">
            <h1>Welcome{borrowerName ? `, ${borrowerName}` : ''}!</h1>
            <div className="loan-info">
              <span className="loan-number">Loan #{loanNumber}</span>
              <span className={`stage-badge stage-${stage?.toLowerCase()}`}>
                {STAGE_NAMES[stage] || stage}
              </span>
            </div>
          </div>
        </div>

        <div className="header-right">
          <div className={`live-indicator ${wsStatus}`}>
            <span className="indicator-dot" />
            <span className="indicator-text">
              {wsStatus === WS_STATUS.CONNECTED ? 'Live' : 'Polling'}
            </span>
          </div>
          {lastUpdate && (
            <span className="last-update">
              Updated {formatTimeAgo(lastUpdate)}
            </span>
          )}
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="portal-tabs">
        {availableTabs.map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {getTabLabel(tab)}
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {activeTab === 'overview' && (
          <OverviewTab
            portalData={portalData}
            closeOnTimeData={closeOnTimeData}
            homeValueData={homeValueData}
            showCloseOnTime={showCloseOnTime}
            showMumFeatures={showMumFeatures}
            loanId={resolvedLoanId}
            activities={activities}
            documents={documents}
          />
        )}

        {activeTab === 'timeline' && (
          <TimelineTab
            loanId={resolvedLoanId}
            showCloseOnTime={showCloseOnTime}
            closeOnTimeData={closeOnTimeData}
            stage={stage}
          />
        )}

        {activeTab === 'home_value' && (
          <HomeValueTab
            loanId={resolvedLoanId}
            homeValueData={homeValueData}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'scenarios' && (
          <ScenariosTab
            loanId={resolvedLoanId}
            homeValueData={homeValueData}
            portalData={portalData}
          />
        )}

        {activeTab === 'documents' && (
          <DocumentsTab
            loanId={resolvedLoanId}
            documents={documents}
            documentSummary={portalData?.documentSummary}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'tasks' && (
          <TasksTab
            loanId={resolvedLoanId}
            borrowerTasks={portalData?.borrowerTasks || []}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'activity' && (
          <ActivityTab activities={activities} />
        )}

        {activeTab === 'team' && (
          <TeamTab
            loanOfficer={portalData?.loan_officer || portalData?.loanOfficer}
            processor={portalData?.processor}
          />
        )}
      </main>

      {/* Quick Actions Bar */}
      <QuickActionsBar
        loanId={resolvedLoanId}
        loanOfficer={portalData?.loan_officer || portalData?.loanOfficer}
        onRefresh={fetchAllData}
      />
    </div>
  );
}

// =============================================================================
// TAB COMPONENTS
// =============================================================================

/**
 * Overview Tab - Main dashboard view
 */
function OverviewTab({
  portalData,
  closeOnTimeData,
  homeValueData,
  showCloseOnTime,
  showMumFeatures,
  loanId,
  activities,
  documents
}) {
  const milestoneProgress = portalData?.milestoneProgress || portalData?.milestone_progress || {};
  const documentSummary = portalData?.documentSummary || portalData?.document_summary || {};
  const borrowerTasks = portalData?.borrowerTasks || portalData?.borrower_tasks || [];
  const risks = portalData?.portalStatus?.risks || portalData?.risks || {};

  return (
    <div className="overview-tab">
      {/* Close On Time Arrow Timeline (S3-S5) */}
      {showCloseOnTime && closeOnTimeData?.has_schedule && (
        <section className="portal-section timeline-section">
          <CloseOnTimeArrowTimeline
            loanId={loanId}
            milestones={closeOnTimeData?.milestones || []}
            targetCloseDate={closeOnTimeData?.target_close_date}
            businessDaysRemaining={closeOnTimeData?.business_days_remaining}
          />
        </section>
      )}

      {/* Home Value Summary (MUM) */}
      {showMumFeatures && homeValueData && (
        <section className="portal-section home-value-section">
          <HomeValueSummaryCard data={homeValueData} />
        </section>
      )}

      {/* Progress Cards Grid */}
      <div className="cards-grid">
        {/* Loan Progress Card */}
        <div className="portal-card progress-card">
          <h3>Loan Progress</h3>
          <ProgressCircle
            percent={milestoneProgress?.progress_percent || milestoneProgress?.completion_rate || 0}
          />
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
              <span className="stat-value">{milestoneProgress?.pending || milestoneProgress?.remaining || 0}</span>
              <span className="stat-label">Remaining</span>
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
              {borrowerTasks.slice(0, 4).map((task, idx) => (
                <li key={task.id || idx} className="task-item">
                  <span className="task-name">{task.name || task.title}</span>
                  {task.is_required && <span className="required-tag">Required</span>}
                </li>
              ))}
              {borrowerTasks.length > 4 && (
                <li className="task-more">+{borrowerTasks.length - 4} more</li>
              )}
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
              <span className="doc-value">{documentSummary?.by_status?.approved || documentSummary?.approved || 0}</span>
              <span className="doc-label">Approved</span>
            </div>
            <div className="doc-stat pending">
              <span className="doc-value">{documentSummary?.pending_review || documentSummary?.pending || 0}</span>
              <span className="doc-label">Pending</span>
            </div>
            <div className="doc-stat needs-action">
              <span className="doc-value">{documentSummary?.needs_reupload || documentSummary?.rejected || 0}</span>
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
                  <span className="activity-icon">
                    {ACTIVITY_ICONS[activity.activity_type] || '📌'}
                  </span>
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
      {risks?.active_count > 0 && (
        <RiskFlagsSection risks={risks} />
      )}
    </div>
  );
}

/**
 * Timeline Tab
 */
function TimelineTab({ loanId, showCloseOnTime, closeOnTimeData, stage }) {
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
 * Home Value Tab (MUM Stage)
 */
function HomeValueTab({ loanId, homeValueData, onRefresh }) {
  const [loading, setLoading] = useState(false);

  const handleRefreshInsights = async () => {
    setLoading(true);
    try {
      await homeValueApi.generateInsights(loanId);
      onRefresh();
    } catch (err) {
      console.error('Failed to generate insights:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!homeValueData) {
    return (
      <div className="home-value-tab">
        <div className="empty-state">
          <span className="empty-icon">🏠</span>
          <h3>Home Value Intelligence</h3>
          <p>Home value tracking will be available once your loan is funded.</p>
        </div>
      </div>
    );
  }

  const { current_value, baseline_value, appreciation, equity, insights } = homeValueData;

  return (
    <div className="home-value-tab">
      <section className="portal-section">
        <div className="section-header">
          <h3>Your Home's Value</h3>
          <button
            className="refresh-btn"
            onClick={handleRefreshInsights}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : '🔄 Refresh'}
          </button>
        </div>

        <div className="home-value-display">
          <div className="value-main">
            <span className="value-label">Estimated Value</span>
            <span className="value-amount">{formatCurrency(current_value?.estimated_value || 0)}</span>
            <span className="value-range">
              Range: {formatCurrency(current_value?.value_low || 0)} - {formatCurrency(current_value?.value_high || 0)}
            </span>
          </div>

          <div className="value-stats">
            <div className="value-stat">
              <span className="stat-label">Purchase Price</span>
              <span className="stat-value">{formatCurrency(baseline_value?.purchase_price || 0)}</span>
            </div>
            <div className="value-stat appreciation">
              <span className="stat-label">Appreciation</span>
              <span className={`stat-value ${appreciation?.total_change >= 0 ? 'positive' : 'negative'}`}>
                {appreciation?.total_change >= 0 ? '+' : ''}{formatCurrency(appreciation?.total_change || 0)}
              </span>
            </div>
            <div className="value-stat">
              <span className="stat-label">Equity</span>
              <span className="stat-value">{formatCurrency(equity?.total_equity || 0)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Equity Breakdown */}
      <section className="portal-section">
        <h3>Equity Breakdown</h3>
        <div className="equity-breakdown">
          <div className="equity-item">
            <span className="equity-label">Home Value</span>
            <span className="equity-value">{formatCurrency(current_value?.estimated_value || 0)}</span>
          </div>
          <div className="equity-item subtract">
            <span className="equity-label">Loan Balance</span>
            <span className="equity-value">- {formatCurrency(equity?.current_loan_balance || 0)}</span>
          </div>
          <div className="equity-item total">
            <span className="equity-label">Total Equity</span>
            <span className="equity-value">{formatCurrency(equity?.total_equity || 0)}</span>
          </div>
          <div className="equity-ltv">
            <span className="ltv-label">Current LTV</span>
            <span className="ltv-value">{((equity?.current_ltv || 0) * 100).toFixed(1)}%</span>
          </div>
        </div>
      </section>

      {/* Insights */}
      {insights?.length > 0 && (
        <section className="portal-section">
          <h3>Insights & Opportunities</h3>
          <div className="insights-list">
            {insights.map((insight, idx) => (
              <InsightCard key={insight.id || idx} insight={insight} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/**
 * Scenarios Tab (MUM Stage)
 */
function ScenariosTab({ loanId, homeValueData, portalData }) {
  const [activeScenario, setActiveScenario] = useState('refinance');
  const [calculatorInputs, setCalculatorInputs] = useState({
    newRate: 5.5,
    cashOutAmount: 50000,
    targetLtv: 80,
  });

  const currentEquity = homeValueData?.equity?.total_equity || 0;
  const currentValue = homeValueData?.current_value?.estimated_value || 0;
  const currentBalance = homeValueData?.equity?.current_loan_balance || 0;
  const currentRate = portalData?.loan?.interest_rate || 6.5;

  const scenarios = {
    refinance: {
      icon: '🔄',
      title: 'Refinance',
      description: 'Lower your monthly payment or shorten your term',
    },
    cashOut: {
      icon: '💰',
      title: 'Cash-Out Refinance',
      description: 'Access your home equity for major expenses',
    },
    heloc: {
      icon: '🏦',
      title: 'HELOC',
      description: 'Open a line of credit against your equity',
    },
    sell: {
      icon: '🏠',
      title: 'Sell Analysis',
      description: 'Estimate your proceeds if you sell',
    },
  };

  // Simple calculator logic
  const calculateRefinance = () => {
    const monthlyPaymentCurrent = (currentBalance * (currentRate / 100 / 12)) /
      (1 - Math.pow(1 + currentRate / 100 / 12, -360));
    const monthlyPaymentNew = (currentBalance * (calculatorInputs.newRate / 100 / 12)) /
      (1 - Math.pow(1 + calculatorInputs.newRate / 100 / 12, -360));
    return {
      currentPayment: monthlyPaymentCurrent,
      newPayment: monthlyPaymentNew,
      monthlySavings: monthlyPaymentCurrent - monthlyPaymentNew,
      yearlySavings: (monthlyPaymentCurrent - monthlyPaymentNew) * 12,
    };
  };

  const calculateCashOut = () => {
    const maxLoan = currentValue * (calculatorInputs.targetLtv / 100);
    const availableCash = maxLoan - currentBalance;
    return {
      maxLoanAmount: maxLoan,
      availableCashOut: Math.max(0, availableCash),
      newLoanAmount: currentBalance + calculatorInputs.cashOutAmount,
      newLtv: ((currentBalance + calculatorInputs.cashOutAmount) / currentValue) * 100,
    };
  };

  const calculateSell = () => {
    const sellingCosts = currentValue * 0.08; // ~8% selling costs
    const netProceeds = currentValue - currentBalance - sellingCosts;
    return {
      salePrice: currentValue,
      loanPayoff: currentBalance,
      sellingCosts,
      netProceeds,
    };
  };

  return (
    <div className="scenarios-tab">
      <section className="portal-section">
        <h3>Explore Your Options</h3>
        <p className="section-description">
          See what opportunities your home equity unlocks.
        </p>

        {/* Scenario Selector */}
        <div className="scenario-selector">
          {Object.entries(scenarios).map(([key, scenario]) => (
            <button
              key={key}
              className={`scenario-btn ${activeScenario === key ? 'active' : ''}`}
              onClick={() => setActiveScenario(key)}
            >
              <span className="scenario-icon">{scenario.icon}</span>
              <span className="scenario-title">{scenario.title}</span>
            </button>
          ))}
        </div>

        {/* Scenario Content */}
        <div className="scenario-content">
          {activeScenario === 'refinance' && (
            <div className="calculator refinance-calc">
              <h4>Rate Reduction Calculator</h4>
              <div className="calc-input">
                <label>New Interest Rate (%)</label>
                <input
                  type="number"
                  step="0.125"
                  value={calculatorInputs.newRate}
                  onChange={(e) => setCalculatorInputs({
                    ...calculatorInputs,
                    newRate: parseFloat(e.target.value) || 0,
                  })}
                />
              </div>
              <div className="calc-results">
                <div className="result-row">
                  <span>Current Payment</span>
                  <span>{formatCurrency(calculateRefinance().currentPayment)}/mo</span>
                </div>
                <div className="result-row">
                  <span>New Payment</span>
                  <span>{formatCurrency(calculateRefinance().newPayment)}/mo</span>
                </div>
                <div className="result-row highlight">
                  <span>Monthly Savings</span>
                  <span className="positive">{formatCurrency(calculateRefinance().monthlySavings)}</span>
                </div>
                <div className="result-row highlight">
                  <span>Yearly Savings</span>
                  <span className="positive">{formatCurrency(calculateRefinance().yearlySavings)}</span>
                </div>
              </div>
              <button className="cta-btn">Get a Refinance Quote</button>
            </div>
          )}

          {activeScenario === 'cashOut' && (
            <div className="calculator cashout-calc">
              <h4>Cash-Out Calculator</h4>
              <div className="calc-info">
                <span>Available Equity:</span>
                <span className="value">{formatCurrency(currentEquity)}</span>
              </div>
              <div className="calc-input">
                <label>Cash Out Amount ($)</label>
                <input
                  type="number"
                  step="5000"
                  value={calculatorInputs.cashOutAmount}
                  onChange={(e) => setCalculatorInputs({
                    ...calculatorInputs,
                    cashOutAmount: parseFloat(e.target.value) || 0,
                  })}
                />
              </div>
              <div className="calc-results">
                <div className="result-row">
                  <span>Max Available (80% LTV)</span>
                  <span>{formatCurrency(calculateCashOut().availableCashOut)}</span>
                </div>
                <div className="result-row">
                  <span>New Loan Amount</span>
                  <span>{formatCurrency(calculateCashOut().newLoanAmount)}</span>
                </div>
                <div className="result-row">
                  <span>New LTV</span>
                  <span>{calculateCashOut().newLtv.toFixed(1)}%</span>
                </div>
              </div>
              <button className="cta-btn">Explore Cash-Out Options</button>
            </div>
          )}

          {activeScenario === 'heloc' && (
            <div className="calculator heloc-calc">
              <h4>HELOC Availability</h4>
              <div className="heloc-summary">
                <div className="heloc-amount">
                  <span className="label">Estimated Credit Line</span>
                  <span className="value">{formatCurrency(currentEquity * 0.85)}</span>
                </div>
                <p className="heloc-note">
                  A Home Equity Line of Credit lets you borrow against your equity as needed,
                  only paying interest on what you use.
                </p>
              </div>
              <button className="cta-btn">Learn About HELOCs</button>
            </div>
          )}

          {activeScenario === 'sell' && (
            <div className="calculator sell-calc">
              <h4>Sell Analysis</h4>
              <div className="calc-results">
                <div className="result-row">
                  <span>Estimated Sale Price</span>
                  <span>{formatCurrency(calculateSell().salePrice)}</span>
                </div>
                <div className="result-row subtract">
                  <span>Loan Payoff</span>
                  <span>- {formatCurrency(calculateSell().loanPayoff)}</span>
                </div>
                <div className="result-row subtract">
                  <span>Estimated Selling Costs (~8%)</span>
                  <span>- {formatCurrency(calculateSell().sellingCosts)}</span>
                </div>
                <div className="result-row highlight">
                  <span>Net Proceeds</span>
                  <span className="positive">{formatCurrency(calculateSell().netProceeds)}</span>
                </div>
              </div>
              <button className="cta-btn">Get a Home Valuation</button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

/**
 * Documents Tab
 */
function DocumentsTab({ loanId, documents, documentSummary, onRefresh }) {
  const [filter, setFilter] = useState('all');
  const [uploading, setUploading] = useState(false);

  const filteredDocs = useMemo(() => {
    if (filter === 'all') return documents;
    return documents.filter(doc => doc.status === filter);
  }, [documents, filter]);

  const handleUpload = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;

    setUploading(true);
    // Upload logic would go here
    setTimeout(() => {
      setUploading(false);
      onRefresh();
    }, 1500);
  };

  return (
    <div className="documents-tab">
      <section className="portal-section">
        <div className="section-header">
          <h3>Document Center</h3>
          <label className="upload-btn">
            {uploading ? 'Uploading...' : '📤 Upload Document'}
            <input
              type="file"
              multiple
              onChange={handleUpload}
              disabled={uploading}
              style={{ display: 'none' }}
            />
          </label>
        </div>

        {/* Filter buttons */}
        <div className="doc-filters">
          <button
            className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All ({documents?.length || 0})
          </button>
          <button
            className={`filter-btn ${filter === 'approved' ? 'active' : ''}`}
            onClick={() => setFilter('approved')}
          >
            Approved
          </button>
          <button
            className={`filter-btn ${filter === 'pending' ? 'active' : ''}`}
            onClick={() => setFilter('pending')}
          >
            Pending Review
          </button>
          <button
            className={`filter-btn ${filter === 'rejected' ? 'active' : ''}`}
            onClick={() => setFilter('rejected')}
          >
            Needs Attention
          </button>
        </div>

        {/* Document List */}
        {!filteredDocs?.length ? (
          <div className="empty-state">
            <span className="empty-icon">📄</span>
            <p>No documents {filter !== 'all' ? `with status "${filter}"` : ''}</p>
          </div>
        ) : (
          <div className="documents-list">
            {filteredDocs.map((doc, idx) => (
              <DocumentCard key={doc.id || idx} document={doc} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * Tasks Tab
 */
function TasksTab({ loanId, borrowerTasks, onRefresh }) {
  return (
    <div className="tasks-tab">
      <section className="portal-section">
        <h3>Your Action Items</h3>

        {!borrowerTasks?.length ? (
          <div className="empty-state success">
            <span className="empty-icon">🎉</span>
            <h4>All caught up!</h4>
            <p>You have no pending tasks.</p>
          </div>
        ) : (
          <div className="tasks-list">
            {borrowerTasks.map((task, idx) => (
              <TaskCard key={task.id || idx} task={task} />
            ))}
          </div>
        )}
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
                <span className="activity-icon">
                  {ACTIVITY_ICONS[activity.activity_type] || '📌'}
                </span>
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
 * Team Tab
 */
function TeamTab({ loanOfficer, processor }) {
  return (
    <div className="team-tab">
      <section className="portal-section">
        <h3>Your Loan Team</h3>

        <div className="team-grid">
          {loanOfficer && (
            <div className="team-card">
              <div className="team-avatar">
                {loanOfficer.avatar ? (
                  <img src={loanOfficer.avatar} alt={loanOfficer.name} />
                ) : (
                  <span className="avatar-placeholder">
                    {loanOfficer.name?.charAt(0) || 'LO'}
                  </span>
                )}
              </div>
              <div className="team-info">
                <h4>{loanOfficer.name}</h4>
                <span className="team-role">Loan Officer</span>
                {loanOfficer.nmls && <span className="nmls">NMLS# {loanOfficer.nmls}</span>}
              </div>
              <div className="team-contact">
                {loanOfficer.phone && (
                  <a href={`tel:${loanOfficer.phone}`} className="contact-btn">
                    📞 {loanOfficer.phone}
                  </a>
                )}
                {loanOfficer.email && (
                  <a href={`mailto:${loanOfficer.email}`} className="contact-btn">
                    ✉️ Email
                  </a>
                )}
              </div>
            </div>
          )}

          {processor && (
            <div className="team-card">
              <div className="team-avatar">
                <span className="avatar-placeholder">
                  {processor.name?.charAt(0) || 'P'}
                </span>
              </div>
              <div className="team-info">
                <h4>{processor.name}</h4>
                <span className="team-role">Loan Processor</span>
              </div>
              <div className="team-contact">
                {processor.phone && (
                  <a href={`tel:${processor.phone}`} className="contact-btn">
                    📞 {processor.phone}
                  </a>
                )}
                {processor.email && (
                  <a href={`mailto:${processor.email}`} className="contact-btn">
                    ✉️ Email
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function ProgressCircle({ percent }) {
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (percent / 100) * circumference;

  return (
    <div className="progress-circle">
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="none" stroke="#e5e7eb" strokeWidth="10" />
        <circle
          cx="50" cy="50" r="45" fill="none" stroke="#10b981" strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
      </svg>
      <span className="progress-value">{percent}%</span>
    </div>
  );
}

function HomeValueSummaryCard({ data }) {
  const { current_value, appreciation, equity } = data || {};

  return (
    <div className="home-value-summary">
      <div className="hv-header">
        <span className="hv-icon">🏠</span>
        <h3>Home Value</h3>
      </div>
      <div className="hv-value">
        <span className="hv-amount">{formatCurrency(current_value?.estimated_value || 0)}</span>
        <span className={`hv-change ${appreciation?.total_change >= 0 ? 'positive' : 'negative'}`}>
          {appreciation?.total_change >= 0 ? '↑' : '↓'} {formatCurrency(Math.abs(appreciation?.total_change || 0))}
        </span>
      </div>
      <div className="hv-equity">
        <span className="label">Your Equity:</span>
        <span className="value">{formatCurrency(equity?.total_equity || 0)}</span>
      </div>
    </div>
  );
}

function InsightCard({ insight }) {
  return (
    <div className={`insight-card ${insight.type || 'info'}`}>
      <div className="insight-header">
        <span className="insight-icon">
          {insight.type === 'opportunity' ? '💡' : insight.type === 'alert' ? '⚠️' : 'ℹ️'}
        </span>
        <h4>{insight.title}</h4>
      </div>
      <p className="insight-text">{insight.message || insight.description}</p>
      {insight.action && (
        <button className="insight-action">{insight.action}</button>
      )}
    </div>
  );
}

function DocumentCard({ document }) {
  const statusColors = {
    approved: '#10b981',
    pending: '#f59e0b',
    rejected: '#ef4444',
    uploaded: '#3b82f6',
  };

  return (
    <div className="document-card">
      <span className="doc-icon">📄</span>
      <div className="doc-info">
        <h4>{document.name || document.document_type}</h4>
        <span className="doc-date">
          {document.uploaded_at ? formatTimeAgo(document.uploaded_at) : 'Not uploaded'}
        </span>
      </div>
      <span
        className="doc-status"
        style={{ color: statusColors[document.status] || '#6b7280' }}
      >
        {document.status || 'pending'}
      </span>
    </div>
  );
}

function TaskCard({ task }) {
  return (
    <div className={`task-card ${task.is_required ? 'required' : ''}`}>
      <div className="task-checkbox">
        <input type="checkbox" disabled />
      </div>
      <div className="task-info">
        <h4>{task.name || task.title}</h4>
        {task.description && <p>{task.description}</p>}
        {task.due_date && (
          <span className="task-due">Due: {formatTimeAgo(task.due_date)}</span>
        )}
      </div>
      {task.is_required && <span className="required-badge">Required</span>}
    </div>
  );
}

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
                <span className="risk-title">{flag.title || flag.description}</span>
                {flag.recommended_action && (
                  <span className="risk-mitigation">{flag.recommended_action}</span>
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

function QuickActionsBar({ loanId, loanOfficer, onRefresh }) {
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
      <button className="quick-action-btn" title="Refresh" onClick={onRefresh}>
        <span className="action-icon">🔄</span>
        <span className="action-label">Refresh</span>
      </button>
    </div>
  );
}

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

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function getTabLabel(tab) {
  const labels = {
    overview: 'Overview',
    timeline: 'Timeline',
    home_value: 'Home Value',
    scenarios: 'Scenarios',
    documents: 'Documents',
    tasks: 'Tasks',
    activity: 'Activity',
    team: 'Your Team',
  };
  return labels[tab] || tab;
}

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

function formatCurrency(amount) {
  if (amount === null || amount === undefined) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}
