import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './MissionControl.css';

function MissionControl() {
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [recentActions, setRecentActions] = useState([]);
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [metricsView, setMetricsView] = useState(7); // 7 or 30 days
  const [selectedAgent, setSelectedAgent] = useState(null);

  useEffect(() => {
    loadAllData();

    // Auto-refresh every 30 seconds
    const interval = setInterval(() => {
      loadAllData();
    }, 30 * 1000);

    return () => clearInterval(interval);
  }, [metricsView, selectedAgent]);

  const loadAllData = async () => {
    const token = localStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };

    try {
      setLoading(true);

      // Load all data in parallel
      const agentParam = selectedAgent ? `&agent_name=${selectedAgent}` : '';
      const [healthRes, metricsRes, actionsRes, insightsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/mission-control/health?days=${metricsView}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/metrics?days=${metricsView}${agentParam}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/recent-actions?limit=20${agentParam}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/insights?limit=10&status=active`, { headers })
      ]);

      if (healthRes.ok) {
        const data = await healthRes.json();
        setHealth(data);
      }

      if (metricsRes.ok) {
        const data = await metricsRes.json();
        setMetrics(data);
      }

      if (actionsRes.ok) {
        const data = await actionsRes.json();
        setRecentActions(data.actions || []);
      }

      if (insightsRes.ok) {
        const data = await insightsRes.json();
        setInsights(data.insights || []);
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

  const getHealthStatusClass = (status) => {
    switch (status) {
      case 'excellent':
        return 'status-excellent';
      case 'good':
        return 'status-good';
      case 'fair':
        return 'status-fair';
      case 'needs_attention':
        return 'status-warning';
      default:
        return 'status-default';
    }
  };

  const getHealthStatusIcon = (status) => {
    switch (status) {
      case 'excellent':
        return '🟢';
      case 'good':
        return '🟡';
      case 'fair':
        return '🟠';
      case 'needs_attention':
        return '🔴';
      default:
        return '⚪';
    }
  };

  const getOutcomeIcon = (outcome) => {
    switch (outcome) {
      case 'success':
        return '✅';
      case 'failure':
        return '❌';
      case 'pending':
        return '⏳';
      default:
        return '⚪';
    }
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

  if (loading && !health) {
    return (
      <div className="mission-control-page">
        <div className="loading">
          <div className="spinner"></div>
          <p>Loading Mission Control...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mission-control-page">
      <div className="page-header">
        <div>
          <h1>🎯 Mission Control</h1>
          <p>AI Colleague Performance & Autonomous Operations</p>
        </div>
        <div className="header-actions">
          <span className="last-updated">Last updated: {formatTimestamp(lastUpdated)}</span>
          <button className="btn-refresh" onClick={handleRefresh}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* TOP STRIP - AI Health Score */}
      <div className="status-strip">
        <div className={`health-card ${getHealthStatusClass(health?.health_status)}`}>
          <div className="health-icon">
            {getHealthStatusIcon(health?.health_status)}
          </div>
          <div className="health-content">
            <div className="health-label">Overall AI Health</div>
            <div className="health-score">{health?.overall_score?.toFixed(1) || 0}</div>
            <div className="health-status">{health?.health_status?.replace('_', ' ').toUpperCase() || 'UNKNOWN'}</div>
          </div>
        </div>

        <div className="metrics-summary">
          <div className="summary-card">
            <div className="summary-label">Total Actions</div>
            <div className="summary-value">{health?.metrics?.total_actions || 0}</div>
          </div>
          <div className="summary-card">
            <div className="summary-label">Autonomous</div>
            <div className="summary-value">{health?.metrics?.autonomous_actions || 0}</div>
            <div className="summary-percent">
              {((health?.metrics?.autonomous_actions / health?.metrics?.total_actions * 100) || 0).toFixed(0)}%
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-label">Success Rate</div>
            <div className="summary-value">{health?.component_scores?.accuracy?.toFixed(0) || 0}%</div>
          </div>
          <div className="summary-card">
            <div className="summary-label">Approval Rate</div>
            <div className="summary-value">{health?.component_scores?.approval?.toFixed(0) || 0}%</div>
          </div>
        </div>
      </div>

      {/* SECTION 1: COMPONENT SCORES */}
      <section className="mc-section">
        <div className="section-header">
          <h2>AI Performance Components</h2>
          <div className="view-toggle">
            <button
              className={metricsView === 7 ? 'active' : ''}
              onClick={() => setMetricsView(7)}
            >
              7 Days
            </button>
            <button
              className={metricsView === 30 ? 'active' : ''}
              onClick={() => setMetricsView(30)}
            >
              30 Days
            </button>
          </div>
        </div>

        <div className="component-scores-grid">
          <div className="score-card">
            <div className="score-icon">🤖</div>
            <div className="score-content">
              <div className="score-label">Autonomy Score</div>
              <div className="score-value">{health?.component_scores?.autonomy?.toFixed(1) || 0}</div>
              <div className="score-description">
                How often AI acts independently
              </div>
            </div>
          </div>

          <div className="score-card">
            <div className="score-icon">🎯</div>
            <div className="score-content">
              <div className="score-label">Accuracy Score</div>
              <div className="score-value">{health?.component_scores?.accuracy?.toFixed(1) || 0}</div>
              <div className="score-description">
                Success rate of AI actions
              </div>
            </div>
          </div>

          <div className="score-card">
            <div className="score-icon">✅</div>
            <div className="score-content">
              <div className="score-label">Approval Score</div>
              <div className="score-value">{health?.component_scores?.approval?.toFixed(1) || 0}</div>
              <div className="score-description">
                Actions approved by users
              </div>
            </div>
          </div>

          <div className="score-card">
            <div className="score-icon">💪</div>
            <div className="score-content">
              <div className="score-label">Confidence Score</div>
              <div className="score-value">{health?.component_scores?.confidence?.toFixed(1) || 0}</div>
              <div className="score-description">
                AI's confidence in decisions
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 2: AGENT METRICS */}
      {metrics?.agents && Object.keys(metrics.agents).length > 0 && (
        <section className="mc-section">
          <div className="section-header">
            <h2>Agent Performance Breakdown</h2>
          </div>

          <div className="agents-grid">
            {Object.entries(metrics.agents).map(([agentName, agentMetrics]) => (
              <div key={agentName} className="agent-card">
                <div className="agent-header">
                  <h3>{agentName}</h3>
                  <button
                    className={`btn-filter ${selectedAgent === agentName ? 'active' : ''}`}
                    onClick={() => setSelectedAgent(selectedAgent === agentName ? null : agentName)}
                  >
                    {selectedAgent === agentName ? 'Show All' : 'Filter'}
                  </button>
                </div>
                <div className="agent-metrics">
                  <div className="agent-metric">
                    <span className="metric-label">Total Actions</span>
                    <span className="metric-value">{agentMetrics.total}</span>
                  </div>
                  <div className="agent-metric">
                    <span className="metric-label">Autonomous</span>
                    <span className="metric-value">{agentMetrics.autonomous} ({agentMetrics.autonomy_rate}%)</span>
                  </div>
                  <div className="agent-metric">
                    <span className="metric-label">Success Rate</span>
                    <span className="metric-value">{agentMetrics.success_rate}%</span>
                  </div>
                  <div className="agent-metric">
                    <span className="metric-label">Avg Confidence</span>
                    <span className="metric-value">{agentMetrics.avg_confidence}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* SECTION 3: RECENT ACTIONS */}
      <section className="mc-section">
        <div className="section-header">
          <h2>Recent AI Actions</h2>
          {selectedAgent && (
            <span className="filter-badge">Filtered: {selectedAgent}</span>
          )}
        </div>

        <div className="actions-list">
          {recentActions.length === 0 ? (
            <div className="empty-state">
              <p>No recent actions to display</p>
            </div>
          ) : (
            recentActions.map((action) => (
              <div key={action.id} className="action-card">
                <div className="action-header">
                  <div className="action-meta">
                    <span className="action-agent">{action.agent_name}</span>
                    <span className="action-type">{action.action_type}</span>
                    <span className="action-time">{formatTimestamp(action.created_at)}</span>
                  </div>
                  <div className="action-badges">
                    {action.autonomy_level && (
                      <span className={`badge autonomy-${action.autonomy_level}`}>
                        {action.autonomy_level === 'full' ? '🤖 Autonomous' : '🤝 Assisted'}
                      </span>
                    )}
                    {action.outcome && (
                      <span className={`badge outcome-${action.outcome}`}>
                        {getOutcomeIcon(action.outcome)} {action.outcome}
                      </span>
                    )}
                    {action.confidence_score && (
                      <span className="badge confidence">
                        💪 {action.confidence_score}%
                      </span>
                    )}
                  </div>
                </div>
                {action.reasoning && (
                  <div className="action-reasoning">
                    {action.reasoning}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {/* SECTION 4: AI INSIGHTS */}
      {insights.length > 0 && (
        <section className="mc-section">
          <div className="section-header">
            <h2>AI-Discovered Insights</h2>
          </div>

          <div className="insights-list">
            {insights.map((insight) => (
              <div key={insight.id} className="insight-card">
                <div className="insight-header">
                  <div className="insight-type">{insight.insight_type}</div>
                  {insight.pattern_confidence && (
                    <div className="insight-confidence">
                      {insight.pattern_confidence}% confident
                    </div>
                  )}
                </div>
                <div className="insight-description">
                  {insight.pattern_description}
                </div>
                {insight.recommended_action && (
                  <div className="insight-recommendation">
                    <strong>💡 Recommendation:</strong> {insight.recommended_action}
                  </div>
                )}
                <div className="insight-footer">
                  <span className="insight-priority priority-{insight.priority}">
                    {insight.priority?.toUpperCase() || 'NORMAL'}
                  </span>
                  <span className="insight-time">
                    Discovered {formatTimestamp(insight.discovered_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default MissionControl;
