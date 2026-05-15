/**
 * BorrowerPortalDashboard Component
 *
 * Main dashboard for the borrower portal showing loan progress,
 * milestones, tasks, documents, and activity feed.
 */

import React from 'react';
import { useBorrowerDashboard, useMumDashboard } from '../../hooks/usePortalData';
import MilestoneTimeline, { MilestoneTimelineVertical } from './MilestoneTimeline';
import CloseOnTimeCalendar, { CloseCountdownWidget } from './CloseOnTimeCalendar';
import './BorrowerPortalDashboard.css';

const LIFECYCLE_STAGES = {
  PROSPECT: { label: 'Prospect', color: '#9CA3AF' },
  LEAD: { label: 'Lead', color: '#3B82F6' },
  PREAPPROVAL: { label: 'Pre-Approval', color: '#B8924A' },
  UNDER_CONTRACT: { label: 'Under Contract', color: '#F59E0B' },
  PROCESSING: { label: 'Processing', color: '#EC4899' },
  CLEAR_TO_CLOSE: { label: 'Clear to Close', color: '#2D7A52' },
  FUNDED: { label: 'Funded', color: '#2D7A52' },
  MUM: { label: 'Member Until Maturity', color: '#B8924A' },
  ANNUAL_REFRESH: { label: 'Annual Refresh', color: '#F97316' },
};

/**
 * Main Borrower Portal Dashboard
 */
export default function BorrowerPortalDashboard({ loanId, borrowerName }) {
  const { data, loading, error, refetch } = useBorrowerDashboard(loanId);

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="portal-error">
        <span className="error-icon">⚠️</span>
        <h2>Unable to load your portal</h2>
        <p>{error}</p>
        <button onClick={refetch} className="retry-btn">
          Try Again
        </button>
      </div>
    );
  }

  const {
    portalStatus,
    milestoneProgress,
    countdown,
    documentSummary,
    recentActivity,
    borrowerTasks,
  } = data;

  const stage = LIFECYCLE_STAGES[portalStatus?.lifecycle?.stage] || LIFECYCLE_STAGES.PROSPECT;

  return (
    <div className="borrower-portal-dashboard">
      {/* Welcome Header */}
      <header className="portal-header">
        <div className="header-content">
          <h1>Welcome{borrowerName ? `, ${borrowerName}` : ''}!</h1>
          <p className="stage-badge" style={{ backgroundColor: `${stage.color}15`, color: stage.color }}>
            {stage.label}
          </p>
        </div>

        {/* Quick Countdown Widget */}
        {countdown?.has_schedule && (
          <div className="header-countdown">
            <CloseCountdownWidget loanId={loanId} />
          </div>
        )}
      </header>

      {/* Main Content Grid */}
      <div className="dashboard-grid">
        {/* Progress Overview Card */}
        <section className="dashboard-card progress-card">
          <h2>Your Loan Progress</h2>
          <div className="progress-overview">
            <div className="progress-circle">
              <svg viewBox="0 0 100 100">
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  fill="none"
                  stroke="#e5e7eb"
                  strokeWidth="10"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  fill="none"
                  stroke="#2D7A52"
                  strokeWidth="10"
                  strokeDasharray={`${milestoneProgress.progress_percent * 2.83} 283`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <span className="progress-value">{milestoneProgress.progress_percent}%</span>
            </div>
            <div className="progress-stats">
              <div className="stat">
                <span className="stat-value">{milestoneProgress.completed}</span>
                <span className="stat-label">Completed</span>
              </div>
              <div className="stat">
                <span className="stat-value">{milestoneProgress.in_progress}</span>
                <span className="stat-label">In Progress</span>
              </div>
              <div className="stat">
                <span className="stat-value">{milestoneProgress.pending}</span>
                <span className="stat-label">Remaining</span>
              </div>
            </div>
          </div>

          {milestoneProgress.current_milestone && (
            <div className="current-step">
              <span className="current-label">Current Step:</span>
              <span className="current-name">{milestoneProgress.current_milestone.name}</span>
            </div>
          )}
        </section>

        {/* Your Tasks Card */}
        <section className="dashboard-card tasks-card">
          <div className="card-header">
            <h2>Your Tasks</h2>
            {borrowerTasks.length > 0 && (
              <span className="badge">{borrowerTasks.length}</span>
            )}
          </div>

          {borrowerTasks.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">✅</span>
              <p>No pending tasks right now!</p>
            </div>
          ) : (
            <ul className="tasks-list">
              {borrowerTasks.slice(0, 5).map((task) => (
                <li key={task.id} className="task-item">
                  <div className="task-info">
                    <span className="task-name">{task.name}</span>
                    <span className="task-milestone">{task.milestone_name}</span>
                  </div>
                  {task.is_required && (
                    <span className="required-badge">Required</span>
                  )}
                </li>
              ))}
            </ul>
          )}

          {borrowerTasks.length > 5 && (
            <button className="view-all-btn">
              View All ({borrowerTasks.length}) Tasks
            </button>
          )}
        </section>

        {/* Documents Card */}
        <section className="dashboard-card documents-card">
          <h2>Documents</h2>
          <div className="document-stats">
            <div className="doc-stat">
              <span className="doc-value">{documentSummary.by_status.approved}</span>
              <span className="doc-label">Approved</span>
            </div>
            <div className="doc-stat pending">
              <span className="doc-value">{documentSummary.pending_review}</span>
              <span className="doc-label">Pending Review</span>
            </div>
            <div className="doc-stat needs-action">
              <span className="doc-value">{documentSummary.needs_reupload}</span>
              <span className="doc-label">Needs Reupload</span>
            </div>
          </div>
          <div className="doc-progress">
            <div className="doc-progress-bar">
              <div
                className="doc-progress-fill"
                style={{ width: `${documentSummary.completion_rate}%` }}
              />
            </div>
            <span className="doc-progress-text">
              {documentSummary.completion_rate}% Complete
            </span>
          </div>
        </section>

        {/* Recent Activity Card */}
        <section className="dashboard-card activity-card">
          <h2>Recent Activity</h2>
          {recentActivity.length === 0 ? (
            <div className="empty-state">
              <p>No recent activity</p>
            </div>
          ) : (
            <ul className="activity-list">
              {recentActivity.map((activity) => (
                <li key={activity.id} className="activity-item">
                  <span className="activity-icon">{getActivityIcon(activity.activity_type)}</span>
                  <div className="activity-content">
                    <p className="activity-description">{activity.description}</p>
                    <span className="activity-time">{formatTime(activity.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Risk Alerts */}
        {portalStatus.risks?.active_count > 0 && (
          <section className="dashboard-card risks-card">
            <h2>
              <span className="warning-icon">⚠️</span>
              Attention Needed
            </h2>
            <p className="risk-message">
              There {portalStatus.risks.active_count === 1 ? 'is' : 'are'}{' '}
              {portalStatus.risks.active_count} item{portalStatus.risks.active_count === 1 ? '' : 's'}{' '}
              that need your attention. Please contact your loan officer for details.
            </p>
          </section>
        )}
      </div>

      {/* Milestone Timeline */}
      <section className="dashboard-section">
        <h2>Your Loan Journey</h2>
        <MilestoneTimeline loanId={loanId} borrowerView={true} />
      </section>

      {/* Close-On-Time Calendar (if applicable) */}
      {countdown?.has_schedule && (
        <section className="dashboard-section">
          <h2>Closing Timeline</h2>
          <CloseOnTimeCalendar loanId={loanId} />
        </section>
      )}
    </div>
  );
}

/**
 * MUM (Member Until Maturity) Dashboard
 */
export function MumPortalDashboard({ loanId, borrowerName }) {
  const { data, loading, error, refetch } = useMumDashboard(loanId);

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="portal-error">
        <span className="error-icon">⚠️</span>
        <h2>Unable to load your portal</h2>
        <p>{error}</p>
        <button onClick={refetch} className="retry-btn">
          Try Again
        </button>
      </div>
    );
  }

  const { portalStatus, homeValueDashboard, recentActivity } = data;

  return (
    <div className="borrower-portal-dashboard mum-portal">
      {/* Welcome Header */}
      <header className="portal-header">
        <div className="header-content">
          <h1>Welcome back{borrowerName ? `, ${borrowerName}` : ''}!</h1>
          <p className="mum-badge">
            <span className="badge-icon">🏠</span>
            Member Until Maturity
          </p>
        </div>
      </header>

      {/* Home Value Dashboard */}
      {homeValueDashboard.has_baseline && (
        <section className="dashboard-card home-value-card">
          <h2>Your Home Value</h2>
          <div className="home-value-display">
            <div className="value-main">
              <span className="value-label">Current Estimate</span>
              <span className="value-amount">
                ${homeValueDashboard.current_valuation?.estimated_value?.toLocaleString()}
              </span>
            </div>

            {homeValueDashboard.current_valuation && (
              <div className="value-change">
                <span
                  className={`change-badge ${homeValueDashboard.current_valuation.appreciation_percent >= 0 ? 'positive' : 'negative'}`}
                >
                  {homeValueDashboard.current_valuation.appreciation_percent >= 0 ? '↑' : '↓'}
                  {Math.abs(homeValueDashboard.current_valuation.appreciation_percent)}%
                </span>
                <span className="change-label">Since Purchase</span>
              </div>
            )}
          </div>

          {/* Equity Display */}
          {homeValueDashboard.equity && (
            <div className="equity-section">
              <div className="equity-bar">
                <div
                  className="equity-fill"
                  style={{ width: `${homeValueDashboard.equity.equity_percent}%` }}
                />
                <div
                  className="loan-fill"
                  style={{ width: `${homeValueDashboard.equity.ltv}%` }}
                />
              </div>
              <div className="equity-labels">
                <span>Equity: {homeValueDashboard.equity.equity_percent}%</span>
                <span>Loan: {homeValueDashboard.equity.ltv}%</span>
              </div>
            </div>
          )}

          {/* Insights */}
          {homeValueDashboard.insights && homeValueDashboard.insights.length > 0 && (
            <div className="insights-section">
              <h3>Insights</h3>
              {homeValueDashboard.insights.slice(0, 2).map((insight) => (
                <div key={insight.id} className="insight-card">
                  <h4>{insight.title}</h4>
                  <p>{insight.description}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Recent Activity */}
      <section className="dashboard-card activity-card">
        <h2>Recent Activity</h2>
        {recentActivity.length === 0 ? (
          <div className="empty-state">
            <p>No recent activity</p>
          </div>
        ) : (
          <ul className="activity-list">
            {recentActivity.map((activity) => (
              <li key={activity.id} className="activity-item">
                <span className="activity-icon">{getActivityIcon(activity.activity_type)}</span>
                <div className="activity-content">
                  <p className="activity-description">{activity.description}</p>
                  <span className="activity-time">{formatTime(activity.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Quick Actions */}
      <section className="dashboard-card quick-actions-card">
        <h2>Quick Actions</h2>
        <div className="quick-actions">
          <button className="quick-action-btn">
            <span className="action-icon">📄</span>
            <span>View Statements</span>
          </button>
          <button className="quick-action-btn">
            <span className="action-icon">💰</span>
            <span>Make Payment</span>
          </button>
          <button className="quick-action-btn">
            <span className="action-icon">📊</span>
            <span>Refinance Options</span>
          </button>
          <button className="quick-action-btn">
            <span className="action-icon">📞</span>
            <span>Contact Us</span>
          </button>
        </div>
      </section>
    </div>
  );
}

/**
 * Get icon for activity type
 */
function getActivityIcon(activityType) {
  const icons = {
    stage_transition: '🔄',
    milestone_update: '✅',
    milestone_completed: '🎉',
    document_uploaded: '📄',
    document_status_changed: '📋',
    task_completed: '✓',
    heartbeat: '💓',
    default: '📌',
  };
  return icons[activityType] || icons.default;
}

/**
 * Format timestamp for display
 */
function formatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  // Less than 1 minute
  if (diff < 60000) return 'Just now';
  // Less than 1 hour
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  // Less than 24 hours
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  // Less than 7 days
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Dashboard Skeleton Loader
 */
function DashboardSkeleton() {
  return (
    <div className="borrower-portal-dashboard skeleton">
      <header className="portal-header">
        <div className="skeleton-text" style={{ width: '250px', height: '32px' }} />
        <div className="skeleton-text" style={{ width: '120px', height: '24px' }} />
      </header>
      <div className="dashboard-grid">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="dashboard-card skeleton-card">
            <div className="skeleton-text" style={{ width: '150px', height: '20px' }} />
            <div className="skeleton-block" style={{ height: '100px' }} />
          </div>
        ))}
      </div>
    </div>
  );
}
