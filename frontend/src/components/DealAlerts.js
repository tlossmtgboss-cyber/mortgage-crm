/**
 * Deal Alerts Components
 *
 * Proactive deal monitoring and alerting system.
 * Provides notification bell, alert cards, and full dashboard.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './DealAlerts.css';
import { toast } from '../utils/toast';
import api from '../services/api';

// =============================================================================
// Alert Priority Badge
// =============================================================================

export function AlertPriorityBadge({ priority }) {
  const priorityConfig = {
    critical: { label: 'Critical', className: 'priority-critical' },
    high: { label: 'High', className: 'priority-high' },
    medium: { label: 'Medium', className: 'priority-medium' },
    low: { label: 'Low', className: 'priority-low' },
  };

  const config = priorityConfig[priority] || priorityConfig.medium;

  return (
    <span className={`alert-priority-badge ${config.className}`}>
      {config.label}
    </span>
  );
}

// =============================================================================
// Alert Type Icon
// =============================================================================

function AlertTypeIcon({ type }) {
  const iconMap = {
    rate_lock_expiring: '🔒',
    stalled_loan: '⏸️',
    compliance_deadline: '📋',
    sla_at_risk: '⚠️',
    document_missing: '📄',
    condition_outstanding: '📝',
    closing_delayed: '📅',
    pricing_variance: '💰',
    fraud_flag: '🚨',
    credit_change: '📊',
  };

  return <span className="alert-type-icon">{iconMap[type] || '⚡'}</span>;
}

// =============================================================================
// Single Alert Card
// =============================================================================

export function AlertCard({
  alert,
  onAcknowledge,
  onResolve,
  onSnooze,
  onViewLoan,
  compact = false
}) {
  const [showActions, setShowActions] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleAcknowledge = async (e) => {
    e.stopPropagation();
    setLoading(true);
    try {
      await onAcknowledge?.(alert.id);
    } finally {
      setLoading(false);
    }
  };

  const handleResolve = async (e) => {
    e.stopPropagation();
    setLoading(true);
    try {
      await onResolve?.(alert.id);
    } finally {
      setLoading(false);
    }
  };

  const handleSnooze = async (e, hours) => {
    e.stopPropagation();
    setLoading(true);
    try {
      await onSnooze?.(alert.id, hours);
    } finally {
      setLoading(false);
    }
  };

  const formatTimeAgo = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  if (compact) {
    return (
      <div
        className={`alert-card compact ${alert.priority}`}
        onClick={() => onViewLoan?.(alert.loan_id)}
      >
        <div className="alert-card-header">
          <AlertTypeIcon type={alert.type} />
          <span className="alert-title">{alert.title}</span>
          <AlertPriorityBadge priority={alert.priority} />
        </div>
        <div className="alert-meta">
          <span className="loan-number">{alert.loan_number}</span>
          <span className="time-ago">{formatTimeAgo(alert.created_at)}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`alert-card ${alert.priority} ${alert.status}`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="alert-card-main">
        <div className="alert-card-header">
          <AlertTypeIcon type={alert.type} />
          <div className="alert-header-text">
            <h4 className="alert-title">{alert.title}</h4>
            <span className="alert-subtitle">
              {alert.borrower_name} - {alert.loan_number}
            </span>
          </div>
          <AlertPriorityBadge priority={alert.priority} />
        </div>

        <p className="alert-message">{alert.message}</p>

        {alert.recommended_action && (
          <div className="alert-recommendation">
            <strong>Recommended:</strong> {alert.recommended_action}
          </div>
        )}

        <div className="alert-footer">
          <div className="alert-tags">
            {alert.tags?.map((tag, idx) => (
              <span key={idx} className="alert-tag">{tag}</span>
            ))}
          </div>
          <div className="alert-meta">
            <span className="time-ago">{formatTimeAgo(alert.created_at)}</span>
            {alert.due_date && (
              <span className="due-date">Due: {new Date(alert.due_date).toLocaleDateString()}</span>
            )}
          </div>
        </div>
      </div>

      {showActions && alert.status !== 'resolved' && (
        <div className="alert-actions">
          {alert.status !== 'acknowledged' && (
            <button
              className="action-btn acknowledge"
              onClick={handleAcknowledge}
              disabled={loading}
            >
              Acknowledge
            </button>
          )}
          <button
            className="action-btn resolve"
            onClick={handleResolve}
            disabled={loading}
          >
            Resolve
          </button>
          <div className="snooze-dropdown">
            <button className="action-btn snooze" disabled={loading}>
              Snooze
            </button>
            <div className="snooze-options">
              <button onClick={(e) => handleSnooze(e, 1)}>1 hour</button>
              <button onClick={(e) => handleSnooze(e, 4)}>4 hours</button>
              <button onClick={(e) => handleSnooze(e, 24)}>1 day</button>
              <button onClick={(e) => handleSnooze(e, 72)}>3 days</button>
            </div>
          </div>
          <button
            className="action-btn view-loan"
            onClick={(e) => {
              e.stopPropagation();
              onViewLoan?.(alert.loan_id);
            }}
          >
            View Loan
          </button>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Notification Bell (for header)
// =============================================================================

export function DealAlertsBell({ userId }) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (userId) params.append('user_id', userId);

      const { data } = await api.get(`/api/v1/deal-alerts/summary?${params}`);
      setSummary(data);
    } catch (error) {
      console.error('Error fetching alert summary:', error);
    }
  }, [userId]);

  const fetchRecentAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/v1/deal-alerts/?status=active&limit=5');
      setAlerts(data);
    } catch (error) {
      console.error('Error fetching alerts:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [fetchSummary]);

  useEffect(() => {
    if (showDropdown) {
      fetchRecentAlerts();
    }
  }, [showDropdown, fetchRecentAlerts]);

  const totalCount = summary?.total_alerts || 0;
  const criticalCount = summary?.critical_count || 0;

  return (
    <div className="deal-alerts-bell">
      <button
        className={`bell-button ${criticalCount > 0 ? 'has-critical' : ''}`}
        onClick={() => setShowDropdown(!showDropdown)}
      >
        <span className="bell-icon">🔔</span>
        {totalCount > 0 && (
          <span className={`badge ${criticalCount > 0 ? 'critical' : ''}`}>
            {totalCount > 99 ? '99+' : totalCount}
          </span>
        )}
      </button>

      {showDropdown && (
        <>
          <div className="dropdown-overlay" onClick={() => setShowDropdown(false)} />
          <div className="alerts-dropdown">
            <div className="dropdown-header">
              <h3>Deal Alerts</h3>
              {summary && (
                <div className="summary-counts">
                  {summary.critical_count > 0 && (
                    <span className="count critical">{summary.critical_count} Critical</span>
                  )}
                  {summary.high_count > 0 && (
                    <span className="count high">{summary.high_count} High</span>
                  )}
                </div>
              )}
            </div>

            <div className="dropdown-content">
              {loading ? (
                <div className="loading-state">Loading...</div>
              ) : alerts.length > 0 ? (
                alerts.map(alert => (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    compact
                    onViewLoan={(loanId) => {
                      setShowDropdown(false);
                      navigate(`/loans/${loanId}`);
                    }}
                  />
                ))
              ) : (
                <div className="empty-state">
                  <span className="empty-icon">✓</span>
                  <p>No active alerts</p>
                </div>
              )}
            </div>

            <div className="dropdown-footer">
              <button
                className="view-all-btn"
                onClick={() => {
                  setShowDropdown(false);
                  navigate('/deal-alerts');
                }}
              >
                View All Alerts
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// =============================================================================
// Alert Summary Cards
// =============================================================================

function AlertSummaryCards({ summary }) {
  if (!summary) return null;

  return (
    <div className="alert-summary-cards">
      <div className="summary-card total">
        <span className="summary-value">{summary.total_alerts}</span>
        <span className="summary-label">Total Alerts</span>
      </div>
      <div className="summary-card critical">
        <span className="summary-value">{summary.critical_count}</span>
        <span className="summary-label">Critical</span>
      </div>
      <div className="summary-card high">
        <span className="summary-value">{summary.high_count}</span>
        <span className="summary-label">High</span>
      </div>
      <div className="summary-card at-risk">
        <span className="summary-value">{summary.loans_at_risk}</span>
        <span className="summary-label">Loans at Risk</span>
      </div>
      <div className="summary-card today">
        <span className="summary-value">{summary.alerts_today}</span>
        <span className="summary-label">Today</span>
      </div>
      <div className="summary-card resolved">
        <span className="summary-value">{summary.resolved_today}</span>
        <span className="summary-label">Resolved Today</span>
      </div>
    </div>
  );
}

// =============================================================================
// Priority Actions Panel
// =============================================================================

function PriorityActionsPanel({ actions, onViewLoan }) {
  if (!actions || actions.length === 0) return null;

  return (
    <div className="priority-actions-panel">
      <h3>Priority Actions</h3>
      <div className="actions-list">
        {actions.map((action, idx) => (
          <div key={idx} className="priority-action-item">
            <div className="action-number">{idx + 1}</div>
            <div className="action-content">
              <p className="action-text">{action.action}</p>
              {action.loan_id && (
                <button
                  className="take-action-btn"
                  onClick={() => onViewLoan?.(action.loan_id)}
                >
                  Take Action
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Alert Filters
// =============================================================================

function AlertFilters({ filters, onChange }) {
  return (
    <div className="alert-filters">
      <div className="filter-group">
        <label>Status</label>
        <select
          value={filters.status || ''}
          onChange={(e) => onChange({ ...filters, status: e.target.value || null })}
        >
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="snoozed">Snoozed</option>
        </select>
      </div>

      <div className="filter-group">
        <label>Priority</label>
        <select
          value={filters.priority || ''}
          onChange={(e) => onChange({ ...filters, priority: e.target.value || null })}
        >
          <option value="">All</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="filter-group">
        <label>Type</label>
        <select
          value={filters.alert_type || ''}
          onChange={(e) => onChange({ ...filters, alert_type: e.target.value || null })}
        >
          <option value="">All Types</option>
          <option value="rate_lock_expiring">Rate Lock Expiring</option>
          <option value="stalled_loan">Stalled Loan</option>
          <option value="compliance_deadline">Compliance Deadline</option>
          <option value="sla_at_risk">SLA at Risk</option>
          <option value="document_missing">Document Missing</option>
          <option value="condition_outstanding">Condition Outstanding</option>
          <option value="closing_delayed">Closing Delayed</option>
        </select>
      </div>
    </div>
  );
}

// =============================================================================
// Main Dashboard Component
// =============================================================================

export function DealAlertsDashboard({ userId, embedded = false }) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [priorityActions, setPriorityActions] = useState([]);
  const [filters, setFilters] = useState({ status: 'active' });
  const [loading, setLoading] = useState(true);
  const [selectedAlerts, setSelectedAlerts] = useState([]);
  const [scanning, setScanning] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch summary, alerts, and priority actions in parallel
      const [summaryRes, alertsRes, actionsRes] = await Promise.all([
        api.get('/api/v1/deal-alerts/summary').catch(() => null),
        api.get(`/api/v1/deal-alerts/?${new URLSearchParams(filters)}`).catch(() => null),
        api.get('/api/v1/deal-alerts/priority-actions').catch(() => null),
      ]);

      if (summaryRes?.data) setSummary(summaryRes.data);
      if (alertsRes?.data) setAlerts(alertsRes.data);
      if (actionsRes?.data) setPriorityActions(actionsRes.data.priority_actions || []);
    } catch (error) {
      console.error('Error fetching deal alerts:', error);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleScanPipeline = async () => {
    setScanning(true);
    try {
      const { data: result } = await api.get('/api/v1/deal-alerts/scan');
      toast.success(`Scan complete: ${result.alerts_generated} new alerts generated`);
      fetchData();
    } catch (error) {
      console.error('Error scanning pipeline:', error);
    } finally {
      setScanning(false);
    }
  };

  const handleAcknowledge = async (alertId) => {
    try {
      await api.post(`/api/v1/deal-alerts/${alertId}/acknowledge`);
      fetchData();
    } catch (error) {
      console.error('Error acknowledging alert:', error);
    }
  };

  const handleResolve = async (alertId) => {
    try {
      await api.post(`/api/v1/deal-alerts/${alertId}/resolve`, { resolution_note: 'Resolved via dashboard' });
      fetchData();
    } catch (error) {
      console.error('Error resolving alert:', error);
    }
  };

  const handleSnooze = async (alertId, hours) => {
    try {
      await api.post(`/api/v1/deal-alerts/${alertId}/snooze`, { snooze_hours: hours });
      fetchData();
    } catch (error) {
      console.error('Error snoozing alert:', error);
    }
  };

  const handleBulkAcknowledge = async () => {
    if (selectedAlerts.length === 0) return;

    try {
      await api.post('/api/v1/deal-alerts/bulk-acknowledge', { alert_ids: selectedAlerts });
      setSelectedAlerts([]);
      fetchData();
    } catch (error) {
      console.error('Error bulk acknowledging:', error);
    }
  };

  const handleViewLoan = (loanId) => {
    navigate(`/loans/${loanId}`);
  };

  const toggleAlertSelection = (alertId) => {
    setSelectedAlerts(prev =>
      prev.includes(alertId)
        ? prev.filter(id => id !== alertId)
        : [...prev, alertId]
    );
  };

  if (loading) {
    if (embedded) {
      return (
        <div className="deal-alerts-embedded loading">
          <div className="loading-spinner small" />
        </div>
      );
    }
    return (
      <div className="deal-alerts-dashboard loading">
        <div className="loading-spinner" />
        <p>Loading deal alerts...</p>
      </div>
    );
  }

  // Embedded compact view for dashboard
  if (embedded) {
    const criticalAlerts = alerts.filter(a => a.priority === 'critical').slice(0, 2);
    const highAlerts = alerts.filter(a => a.priority === 'high').slice(0, 2);
    const topAlerts = [...criticalAlerts, ...highAlerts].slice(0, 3);

    return (
      <a href="/deal-alerts" className="deal-alerts-embedded" style={{ textDecoration: 'none', color: 'inherit' }}>
        <div className="embedded-header">
          <div className="embedded-title">
            <h3>Deal Alerts</h3>
            {summary && summary.total_alerts > 0 && (
              <span className={`alert-badge ${summary.critical_count > 0 ? 'critical' : 'normal'}`}>
                {summary.total_alerts}
              </span>
            )}
          </div>
        </div>

        <div className="embedded-summary">
          {summary?.critical_count > 0 && (
            <div className="summary-stat critical">
              <span className="stat-value">{summary.critical_count}</span>
              <span className="stat-label">Critical</span>
            </div>
          )}
          {summary?.high_count > 0 && (
            <div className="summary-stat high">
              <span className="stat-value">{summary.high_count}</span>
              <span className="stat-label">High</span>
            </div>
          )}
          {summary?.loans_at_risk > 0 && (
            <div className="summary-stat at-risk">
              <span className="stat-value">{summary.loans_at_risk}</span>
              <span className="stat-label">Loans at Risk</span>
            </div>
          )}
          {(!summary || (summary.critical_count === 0 && summary.high_count === 0 && summary.loans_at_risk === 0)) && (
            <div className="summary-stat healthy">
              <span className="stat-icon">✓</span>
              <span className="stat-label">Pipeline Healthy</span>
            </div>
          )}
        </div>

        {topAlerts.length > 0 && (
          <div className="embedded-alerts">
            {topAlerts.map(alert => (
              <div key={alert.id} className={`mini-alert ${alert.priority}`}>
                <span className="mini-alert-icon">
                  {alert.priority === 'critical' ? '🚨' : '⚠️'}
                </span>
                <div className="mini-alert-content">
                  <span className="mini-alert-title">{alert.title}</span>
                  <span className="mini-alert-loan">{alert.loan_number}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="embedded-footer">
          <span>Click to view all alerts</span>
          <span className="arrow">→</span>
        </div>
      </a>
    );
  }

  return (
    <div className="deal-alerts-dashboard">
      <div className="dashboard-header">
        <div className="header-title">
          <h1>Deal Alerts</h1>
          <p>Proactive monitoring of your pipeline</p>
        </div>
        <div className="header-actions">
          <button
            className="scan-btn"
            onClick={handleScanPipeline}
            disabled={scanning}
          >
            {scanning ? 'Scanning...' : 'Scan Pipeline'}
          </button>
        </div>
      </div>

      <AlertSummaryCards summary={summary} />

      <div className="dashboard-content">
        <div className="alerts-section">
          <div className="section-header">
            <h2>All Alerts</h2>
            <AlertFilters filters={filters} onChange={setFilters} />
          </div>

          {selectedAlerts.length > 0 && (
            <div className="bulk-actions">
              <span>{selectedAlerts.length} selected</span>
              <button onClick={handleBulkAcknowledge}>
                Acknowledge Selected
              </button>
              <button onClick={() => setSelectedAlerts([])}>
                Clear Selection
              </button>
            </div>
          )}

          <div className="alerts-list">
            {alerts.length > 0 ? (
              alerts.map(alert => (
                <div key={alert.id} className="alert-item-wrapper">
                  <input
                    type="checkbox"
                    checked={selectedAlerts.includes(alert.id)}
                    onChange={() => toggleAlertSelection(alert.id)}
                    className="alert-checkbox"
                  />
                  <AlertCard
                    alert={alert}
                    onAcknowledge={handleAcknowledge}
                    onResolve={handleResolve}
                    onSnooze={handleSnooze}
                    onViewLoan={handleViewLoan}
                  />
                </div>
              ))
            ) : (
              <div className="empty-alerts">
                <span className="empty-icon">✓</span>
                <h3>No alerts matching filters</h3>
                <p>Your pipeline is looking healthy!</p>
              </div>
            )}
          </div>
        </div>

        <div className="sidebar">
          <PriorityActionsPanel
            actions={priorityActions}
            onViewLoan={handleViewLoan}
          />

          {summary?.by_type && (
            <div className="alerts-by-type">
              <h3>By Type</h3>
              <div className="type-breakdown">
                {Object.entries(summary.by_type).map(([type, count]) => (
                  <div key={type} className="type-item">
                    <span className="type-name">{type.replace(/_/g, ' ')}</span>
                    <span className="type-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Dashboard Widget (Compact version for embedding)
// =============================================================================

export function DealAlertsWidget({ userId, onViewAll }) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryRes, alertsRes] = await Promise.all([
          api.get('/api/v1/deal-alerts/summary').catch(() => null),
          api.get('/api/v1/deal-alerts/?status=active&priority=critical&limit=3').catch(() => null),
        ]);

        if (summaryRes?.data) setSummary(summaryRes.data);
        if (alertsRes?.data) setAlerts(alertsRes.data);
      } catch (error) {
        console.error('Error fetching widget data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [userId]);

  if (loading) {
    return (
      <div className="deal-alerts-widget loading">
        <div className="loading-spinner small" />
      </div>
    );
  }

  return (
    <div className="deal-alerts-widget">
      <div className="widget-header">
        <h3>Deal Alerts</h3>
        {summary && (
          <span className={`alert-count ${summary.critical_count > 0 ? 'critical' : ''}`}>
            {summary.total_alerts}
          </span>
        )}
      </div>

      <div className="widget-summary">
        {summary?.critical_count > 0 && (
          <span className="mini-stat critical">{summary.critical_count} Critical</span>
        )}
        {summary?.high_count > 0 && (
          <span className="mini-stat high">{summary.high_count} High</span>
        )}
        {summary?.loans_at_risk > 0 && (
          <span className="mini-stat at-risk">{summary.loans_at_risk} At Risk</span>
        )}
      </div>

      <div className="widget-alerts">
        {alerts.length > 0 ? (
          alerts.map(alert => (
            <AlertCard
              key={alert.id}
              alert={alert}
              compact
              onViewLoan={(loanId) => navigate(`/loans/${loanId}`)}
            />
          ))
        ) : (
          <div className="widget-empty">
            <span>No critical alerts</span>
          </div>
        )}
      </div>

      <button
        className="widget-link"
        onClick={() => onViewAll ? onViewAll() : navigate('/deal-alerts')}
      >
        View All Alerts
      </button>
    </div>
  );
}

// =============================================================================
// Export page component
// =============================================================================

export function DealAlertsPage() {
  return (
    <div className="deal-alerts-page">
      <DealAlertsDashboard />
    </div>
  );
}

export default DealAlertsDashboard;
