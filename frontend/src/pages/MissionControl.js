import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './MissionControl.css';

function MissionControl() {
  const [summary, setSummary] = useState(null);
  const [aiMetrics, setAiMetrics] = useState([]);
  const [integrations, setIntegrations] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [security, setSecurity] = useState(null);
  const [changelog, setChangelog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [metricsView, setMetricsView] = useState('7'); // 7 or 30 days

  useEffect(() => {
    loadAllData();

    // Auto-refresh every 5 minutes
    const interval = setInterval(() => {
      loadAllData();
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, [metricsView]);

  const loadAllData = async () => {
    const token = localStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };

    try {
      setLoading(true);

      // Load all data in parallel
      const [summaryRes, metricsRes, integrationsRes, jobsRes, alertsRes, securityRes, changelogRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/mission-control/summary`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/ai-metrics?days=${metricsView}`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/integrations`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/jobs`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/alerts`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/security`, { headers }),
        fetch(`${API_BASE_URL}/api/mission-control/changelog`, { headers })
      ]);

      if (summaryRes.ok) {
        const data = await summaryRes.json();
        setSummary(data);
      }

      if (metricsRes.ok) {
        const data = await metricsRes.json();
        setAiMetrics(data.metrics);
      }

      if (integrationsRes.ok) {
        const data = await integrationsRes.json();
        setIntegrations(data.integrations);
      }

      if (jobsRes.ok) {
        const data = await jobsRes.json();
        setJobs(data.jobs);
      }

      if (alertsRes.ok) {
        const data = await alertsRes.json();
        setAlerts(data.alerts);
      }

      if (securityRes.ok) {
        const data = await securityRes.json();
        setSecurity(data);
      }

      if (changelogRes.ok) {
        const data = await changelogRes.json();
        setChangelog(data.changelogs);
      }

      setLastUpdated(new Date());
      setLoading(false);
    } catch (error) {
      console.error('Failed to load Mission Control data:', error);
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    await loadAllData();
  };

  const handleResolveAlert = async (alertId) => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch(`${API_BASE_URL}/api/mission-control/alerts/${alertId}/resolve`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        // Reload alerts
        const alertsRes = await fetch(`${API_BASE_URL}/api/mission-control/alerts`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (alertsRes.ok) {
          const data = await alertsRes.json();
          setAlerts(data.alerts);
        }
      }
    } catch (error) {
      console.error('Failed to resolve alert:', error);
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'healthy':
      case 'success':
      case 'connected':
        return 'status-badge-success';
      case 'degraded':
      case 'warning':
        return 'status-badge-warning';
      case 'critical':
      case 'failed':
      case 'down':
      case 'disconnected':
        return 'status-badge-error';
      default:
        return 'status-badge-default';
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical':
        return '🔴';
      case 'warning':
        return '⚠️';
      default:
        return 'ℹ️';
    }
  };

  const formatDuration = (ms) => {
    if (!ms) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return date.toLocaleDateString();
  };

  if (loading && !summary) {
    return (
      <div className="mission-control-page">
        <div className="loading">Loading Mission Control...</div>
      </div>
    );
  }

  const latestMetrics = aiMetrics[0] || {};
  const previousMetrics = aiMetrics[1] || {};

  return (
    <div className="mission-control-page">
      <div className="page-header">
        <div>
          <h1>Mission Control</h1>
          <p>System Health & AI Performance</p>
        </div>
        <div className="header-actions">
          <span className="last-updated">Last updated: {formatTimestamp(lastUpdated)}</span>
          <button className="btn-secondary" onClick={handleRefresh}>
            🔄 Refresh Now
          </button>
        </div>
      </div>

      {/* TOP STRIP - Global Status */}
      <div className="status-strip">
        <div className="status-card">
          <div className="status-label">System Health</div>
          <div className={`status-value ${getStatusBadgeClass(summary?.overall_status)}`}>
            {summary?.overall_status === 'healthy' && '✅ Healthy'}
            {summary?.overall_status === 'degraded' && '⚠️ Degraded'}
            {summary?.overall_status === 'critical' && '🔴 Critical'}
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">AI Improvement Today</div>
          <div className="status-value">
            {summary?.ai_improvement_index?.toFixed(1) || '100'}
            <span className={summary?.ai_improvement_delta >= 0 ? 'delta-positive' : 'delta-negative'}>
              {summary?.ai_improvement_delta >= 0 ? '+' : ''}{summary?.ai_improvement_delta?.toFixed(1)}%
            </span>
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Active Alerts</div>
          <div className="status-value">
            {summary?.critical_alerts_count > 0 && (
              <span className="alert-count critical">{summary.critical_alerts_count} Critical</span>
            )}
            {summary?.warning_alerts_count > 0 && (
              <span className="alert-count warning">{summary.warning_alerts_count} Warnings</span>
            )}
            {!summary?.critical_alerts_count && !summary?.warning_alerts_count && (
              <span className="alert-count success">All Clear</span>
            )}
          </div>
        </div>
      </div>

      {/* SECTION 1: AI LEARNING & PERFORMANCE */}
      <section className="mc-section">
        <div className="section-header">
          <h2>AI Learning & Performance</h2>
          <div className="view-toggle">
            <button
              className={metricsView === '7' ? 'active' : ''}
              onClick={() => setMetricsView('7')}
            >
              7 Days
            </button>
            <button
              className={metricsView === '30' ? 'active' : ''}
              onClick={() => setMetricsView('30')}
            >
              30 Days
            </button>
          </div>
        </div>

        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-icon">🤖</div>
            <div className="metric-content">
              <div className="metric-label">AI Automation Rate</div>
              <div className="metric-value">{(latestMetrics.automation_rate || 0).toFixed(1)}%</div>
              <div className="metric-subtext">
                {latestMetrics.tasks_auto_completed || 0} of {latestMetrics.tasks_total || 0} tasks automated
              </div>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-icon">👥</div>
            <div className="metric-content">
              <div className="metric-label">Human Escalations</div>
              <div className="metric-value">{latestMetrics.tasks_escalated_to_humans || 0}</div>
              <div className="metric-subtext">
                {(latestMetrics.escalation_rate || 0).toFixed(1)}% escalation rate
              </div>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-icon">⚡</div>
            <div className="metric-content">
              <div className="metric-label">Avg Resolution Time</div>
              <div className="metric-value">
                {formatDuration((latestMetrics.avg_ai_resolution_time_seconds || 0) * 1000)}
              </div>
              <div className="metric-subtext">
                Saving {formatDuration((latestMetrics.time_saved_seconds || 0) * 1000)} per task
              </div>
            </div>
          </div>

          <div className="metric-card highlight">
            <div className="metric-icon">📈</div>
            <div className="metric-content">
              <div className="metric-label">AI Improvement Index</div>
              <div className="metric-value">{(latestMetrics.ai_improvement_index || 100).toFixed(1)}</div>
              <div className="metric-subtext">
                Composite performance score
              </div>
            </div>
          </div>
        </div>

        {/* AI Narrative */}
        {changelog[0] && (
          <div className="ai-narrative">
            <h3>Today's AI Summary</h3>
            <p>{changelog[0].summary || 'AI is learning and improving daily.'}</p>
          </div>
        )}
      </section>

      {/* SECTION 2: INTEGRATIONS HEALTH */}
      <section className="mc-section">
        <div className="section-header">
          <h2>Integrations Health</h2>
        </div>

        <div className="integrations-grid">
          {integrations.length === 0 ? (
            <div className="empty-state">
              <p>No integrations configured yet.</p>
            </div>
          ) : (
            integrations.map((integration, index) => (
              <div key={index} className="integration-card">
                <div className="integration-header">
                  <div className="integration-name">{integration.name}</div>
                  <span className={`status-badge ${getStatusBadgeClass(integration.status)}`}>
                    {integration.status}
                  </span>
                </div>
                <div className="integration-details">
                  <div className="detail-row">
                    <span>Last Success:</span>
                    <span>{formatTimestamp(integration.last_success_at)}</span>
                  </div>
                  <div className="detail-row">
                    <span>Errors (24h):</span>
                    <span className={integration.error_count_24h > 0 ? 'error-text' : ''}>
                      {integration.error_count_24h}
                    </span>
                  </div>
                  {integration.latency_ms && (
                    <div className="detail-row">
                      <span>Latency:</span>
                      <span>{integration.latency_ms}ms</span>
                    </div>
                  )}
                  {integration.last_error_message && (
                    <div className="error-message">
                      {integration.last_error_message}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* SECTION 3: DATA PIPELINES & JOBS */}
      <section className="mc-section">
        <div className="section-header">
          <h2>Data Pipelines & Jobs</h2>
        </div>

        <div className="jobs-table">
          {jobs.length === 0 ? (
            <div className="empty-state">
              <p>No jobs configured yet.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Job Name</th>
                  <th>Type</th>
                  <th>Last Run</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Records</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job, index) => (
                  <tr key={index}>
                    <td>{job.job_name}</td>
                    <td>{job.job_type || 'N/A'}</td>
                    <td>{formatTimestamp(job.last_run_at)}</td>
                    <td>
                      <span className={`status-badge ${getStatusBadgeClass(job.status)}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{formatDuration(job.duration_ms)}</td>
                    <td>{job.records_processed || 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* SECTION 4: SECURITY & COMPLIANCE */}
      <section className="mc-section">
        <div className="section-header">
          <h2>Security & Compliance</h2>
        </div>

        {security && (
          <div className="security-grid">
            <div className="security-card">
              <div className="security-label">2FA Coverage</div>
              <div className="security-value">
                {security.tfa_coverage_percent}%
                <span className="security-subtext">
                  {security.active_users_with_2fa} of {security.active_users_total} users
                </span>
              </div>
            </div>

            <div className="security-card">
              <div className="security-label">High-Privilege Actions (24h)</div>
              <div className="security-value">{security.high_privilege_actions_24h}</div>
            </div>

            <div className="security-card">
              <div className="security-label">Failed Logins (24h)</div>
              <div className="security-value">{security.failed_login_attempts_24h}</div>
            </div>

            {security.last_permission_change_user && (
              <div className="security-card">
                <div className="security-label">Last Permission Change</div>
                <div className="security-value">
                  {security.last_permission_change_user}
                  <span className="security-subtext">
                    {formatTimestamp(security.last_permission_change_at)}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* SECTION 5: ALERTS & RECOMMENDED ACTIONS */}
      {alerts.length > 0 && (
        <section className="mc-section">
          <div className="section-header">
            <h2>Alerts & Recommended Actions</h2>
          </div>

          <div className="alerts-list">
            {alerts.map((alert) => (
              <div key={alert.id} className={`alert-card alert-${alert.severity}`}>
                <div className="alert-header">
                  <div className="alert-title">
                    <span className="alert-icon">{getSeverityIcon(alert.severity)}</span>
                    {alert.title}
                  </div>
                  <button
                    className="btn-resolve"
                    onClick={() => handleResolveAlert(alert.id)}
                  >
                    Mark Resolved
                  </button>
                </div>
                <div className="alert-message">{alert.message}</div>
                {alert.suggested_action && (
                  <div className="alert-action">
                    <strong>Suggested Action:</strong> {alert.suggested_action}
                  </div>
                )}
                <div className="alert-time">{formatTimestamp(alert.created_at)}</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default MissionControl;
