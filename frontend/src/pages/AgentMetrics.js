import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentMetricsAPI } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './AgentMetrics.css';

function AgentMetrics() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - admin only
  const canAccess = isAdmin || hasAnyPermission(['admin.manage', 'system.admin', 'agents.manage']) || userRole === 'admin';

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  // Data states
  const [metrics, setMetrics] = useState(null);
  const [toolMetrics, setToolMetrics] = useState(null);
  const [errors, setErrors] = useState(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);

      const [metricsData, toolData, errorData] = await Promise.all([
        agentMetricsAPI.getAgentMetrics(days),
        agentMetricsAPI.getAgentToolMetrics(days),
        agentMetricsAPI.getAgentErrors(days),
      ]);

      setMetrics(metricsData);
      setToolMetrics(toolData);
      setErrors(errorData);
    } catch (err) {
      console.error('Error fetching agent metrics:', err);
      setError('Failed to load agent performance data. Please try again.');
      if (isRefresh) {
        toast.error('Failed to refresh data');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [days]);

  useEffect(() => {
    if (canAccess) {
      fetchData();
    }
  }, [canAccess, fetchData]);

  const handleRefresh = () => {
    fetchData(true);
  };

  const handleTimeRangeChange = (newDays) => {
    setDays(newDays);
  };

  // Derive summary from metrics data
  const summary = metrics ? {
    totalInvocations: metrics.total_invocations || 0,
    successRate: metrics.success_rate || 0,
    avgResponseTime: metrics.avg_response_time_ms || 0,
    activeAgents: metrics.active_agents || 0,
  } : null;

  const agentRoles = metrics?.by_role || [];
  const tools = toolMetrics?.tools || [];
  const errorLog = errors?.errors || [];

  // Helpers
  const getSuccessRateClass = (rate) => {
    if (rate >= 95) return 'excellent';
    if (rate >= 85) return 'good';
    if (rate >= 70) return 'warning';
    return 'critical';
  };

  const getSuccessRateLabel = (rate) => {
    if (rate >= 95) return 'Excellent';
    if (rate >= 85) return 'Good';
    if (rate >= 70) return 'Warning';
    return 'Critical';
  };

  const formatDuration = (ms) => {
    if (ms == null) return '--';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatNumber = (num) => {
    if (num == null) return '0';
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString();
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Access denied
  if (!canAccess) {
    return (
      <div className="agent-metrics">
        <div className="access-denied">
          <i className="fas fa-lock"></i>
          <h2>Access Denied</h2>
          <p>You need admin permissions to view agent performance metrics.</p>
        </div>
      </div>
    );
  }

  // Loading
  if (loading) {
    return (
      <div className="agent-metrics loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Agent Metrics...</p>
        </div>
      </div>
    );
  }

  // Error
  if (error && !metrics) {
    return (
      <div className="agent-metrics">
        <div className="metrics-header">
          <div className="header-left">
            <h1><i className="fas fa-chart-bar"></i> Agent Performance</h1>
            <p className="subtitle">AI agent invocation metrics and tool performance</p>
          </div>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={() => fetchData()}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-metrics">
      {/* Header */}
      <div className="metrics-header">
        <div className="header-left">
          <h1><i className="fas fa-chart-bar"></i> Agent Performance</h1>
          <p className="subtitle">AI agent invocation metrics, tool performance, and error tracking</p>
        </div>
        <div className="header-right">
          <div className="time-range-selector">
            {[
              { label: '7d', value: 7 },
              { label: '30d', value: 30 },
              { label: '90d', value: 90 },
            ].map(({ label, value }) => (
              <button
                key={value}
                className={days === value ? 'active' : ''}
                onClick={() => handleTimeRangeChange(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            className={`refresh-btn ${refreshing ? 'spinning' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <i className="fas fa-sync-alt"></i>
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="summary-cards">
          <div className="summary-card invocations">
            <div className="card-icon">
              <i className="fas fa-bolt"></i>
            </div>
            <div className="card-content">
              <span className="card-value">{formatNumber(summary.totalInvocations)}</span>
              <span className="card-label">Total Invocations</span>
            </div>
          </div>

          <div className="summary-card success-rate">
            <div className="card-icon">
              <i className="fas fa-check-circle"></i>
            </div>
            <div className="card-content">
              <span className="card-value">{summary.successRate.toFixed(1)}%</span>
              <span className="card-label">Success Rate</span>
            </div>
          </div>

          <div className="summary-card response-time">
            <div className="card-icon">
              <i className="fas fa-clock"></i>
            </div>
            <div className="card-content">
              <span className="card-value">{formatDuration(summary.avgResponseTime)}</span>
              <span className="card-label">Avg Response Time</span>
            </div>
          </div>

          <div className="summary-card active-agents">
            <div className="card-icon">
              <i className="fas fa-robot"></i>
            </div>
            <div className="card-content">
              <span className="card-value">{summary.activeAgents}</span>
              <span className="card-label">Active Agents</span>
            </div>
          </div>
        </div>
      )}

      {/* Agent Role Breakdown */}
      <div className="metrics-section">
        <div className="section-header">
          <h2><i className="fas fa-users-cog"></i> Agent Role Breakdown</h2>
          {agentRoles.length > 0 && (
            <span className="section-badge">{agentRoles.length} roles</span>
          )}
        </div>
        {agentRoles.length === 0 ? (
          <div className="empty-state">
            <i className="fas fa-inbox"></i>
            <p>No agent role data available for this period.</p>
          </div>
        ) : (
          <div className="metrics-table-wrapper">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Invocations</th>
                  <th>Success Rate</th>
                  <th>Avg Duration</th>
                  <th>Top Tool</th>
                </tr>
              </thead>
              <tbody>
                {agentRoles.map((role) => {
                  const rateClass = getSuccessRateClass(role.success_rate || 0);
                  return (
                    <tr key={role.role_name}>
                      <td><span className="role-name">{role.role_name}</span></td>
                      <td>{formatNumber(role.invocations)}</td>
                      <td>
                        <div className="rate-bar-container">
                          <div className="rate-bar">
                            <div
                              className={`rate-bar-fill ${rateClass}`}
                              style={{ width: `${Math.min(role.success_rate || 0, 100)}%` }}
                            />
                          </div>
                          <span className="rate-value">{(role.success_rate || 0).toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="duration">{formatDuration(role.avg_duration_ms)}</td>
                      <td><span className="top-tool">{role.top_tool || '--'}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Tool Performance */}
      <div className="metrics-section">
        <div className="section-header">
          <h2><i className="fas fa-wrench"></i> Tool Performance</h2>
          {tools.length > 0 && (
            <span className="section-badge">{tools.length} tools</span>
          )}
        </div>
        {tools.length === 0 ? (
          <div className="empty-state">
            <i className="fas fa-inbox"></i>
            <p>No tool performance data available for this period.</p>
          </div>
        ) : (
          <div className="metrics-table-wrapper">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Tool</th>
                  <th>Invocations</th>
                  <th>Success Rate</th>
                  <th>Avg Duration</th>
                  <th>Errors</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {tools.map((tool) => {
                  const rateClass = getSuccessRateClass(tool.success_rate || 0);
                  return (
                    <tr key={tool.tool_name}>
                      <td><span className="tool-name">{tool.tool_name}</span></td>
                      <td>{formatNumber(tool.invocations)}</td>
                      <td>
                        <div className="rate-bar-container">
                          <div className="rate-bar">
                            <div
                              className={`rate-bar-fill ${rateClass}`}
                              style={{ width: `${Math.min(tool.success_rate || 0, 100)}%` }}
                            />
                          </div>
                          <span className="rate-value">{(tool.success_rate || 0).toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="duration">{formatDuration(tool.avg_duration_ms)}</td>
                      <td>{tool.error_count || 0}</td>
                      <td>
                        <span className={`status-indicator ${rateClass}`}>
                          <span className="status-dot"></span>
                          {getSuccessRateLabel(tool.success_rate || 0)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Error Log */}
      <div className="metrics-section">
        <div className="section-header">
          <h2><i className="fas fa-exclamation-circle"></i> Recent Errors</h2>
          {errorLog.length > 0 && (
            <span className="section-badge">{errorLog.length} errors</span>
          )}
        </div>
        {errorLog.length === 0 ? (
          <div className="empty-state">
            <i className="fas fa-check-circle" style={{ color: '#28a745' }}></i>
            <p>No errors recorded in this period.</p>
          </div>
        ) : (
          <div>
            {errorLog.map((entry, idx) => (
              <div className="error-log-entry" key={idx}>
                <span className="error-timestamp">{formatTimestamp(entry.timestamp)}</span>
                <span className="error-role">{entry.agent_role || 'unknown'}</span>
                <span className="error-message">{entry.error_message || 'Unknown error'}</span>
                {entry.tool_name && (
                  <span className="error-tool">{entry.tool_name}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMetrics;
