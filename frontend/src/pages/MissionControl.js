import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import ApprovalQueue from '../components/ApprovalQueue';
import './MissionControl.css';
import { getToken } from '../utils/tokenStore';

function MissionControl() {
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [recentActions, setRecentActions] = useState([]);
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [metricsView, setMetricsView] = useState(7);
  const [selectedAgent, setSelectedAgent] = useState(null);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(() => { loadAllData(); }, 30 * 1000);
    return () => clearInterval(interval);
  }, [metricsView, selectedAgent]);

  const loadAllData = async () => {
    const token = getToken();
    const headers = { 'Authorization': `Bearer ${token}` };

    try {
      setLoading(true);
      const agentParam = selectedAgent ? `&agent_name=${selectedAgent}` : '';
      const [healthRes, metricsRes, actionsRes, insightsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/mission-control/health?days=${metricsView}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/metrics?days=${metricsView}${agentParam}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/recent-actions?limit=20${agentParam}`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/mission-control/insights?limit=10&status=active`, { headers })
      ]);

      if (healthRes.ok) setHealth(await healthRes.json());
      if (metricsRes.ok) setMetrics(await metricsRes.json());
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

  const getProgressClass = (score) => {
    if (score >= 80) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'fair';
    return 'poor';
  };

  const getAgentSuccessClass = (rate) => {
    if (rate >= 80) return 'success-high';
    if (rate >= 50) return 'success-mid';
    return 'success-low';
  };

  if (loading && !health) {
    return (
      <div className="mission-control-page">
        <div className="mc-skeleton">
          <div className="mc-skeleton-strip">
            {[...Array(5)].map((_, i) => <div key={i} className="mc-skeleton-card" />)}
          </div>
          <div className="mc-skeleton-section" />
          <div className="mc-skeleton-section" />
        </div>
      </div>
    );
  }

  const healthStatus = health?.health_status || 'unknown';
  const totalActions = health?.metrics?.total_actions || 0;
  const autonomousActions = health?.metrics?.autonomous_actions || 0;
  const autonomousPct = totalActions > 0 ? Math.round(autonomousActions / totalActions * 100) : 0;

  return (
    <div className="mission-control-page">
      {/* HEADER */}
      <div className="mc-page-header">
        <div>
          <h1>
            <span className={`health-dot ${healthStatus}`} />
            Mission Control
          </h1>
          <p>AI Colleague Performance & Autonomous Operations</p>
        </div>
        <div className="header-actions">
          <span className="last-updated">Last updated: {formatTimestamp(lastUpdated)}</span>
          <button className="btn-refresh" onClick={loadAllData}>Refresh</button>
        </div>
      </div>

      {/* TOP HEALTH STRIP */}
      <div className="mc-health-strip">
        <div className={`mc-health-card primary ${healthStatus}`}>
          <div className="icon-circle green">
            <span className={`health-dot ${healthStatus}`} style={{ width: 16, height: 16 }} />
          </div>
          <div className="mc-card-content">
            <div className="mc-card-label">Overall AI Health</div>
            <div className="mc-card-value large">{health?.overall_score?.toFixed(1) || '0.0'}</div>
            <div className={`mc-card-sub status-${healthStatus}`}>
              {healthStatus.replace('_', ' ').toUpperCase()}
            </div>
          </div>
        </div>

        <div className="mc-health-card">
          <div className="icon-circle blue">
            <span role="img" aria-label="actions">&#9889;</span>
          </div>
          <div className="mc-card-content">
            <div className="mc-card-label">Total Actions</div>
            <div className="mc-card-value">{totalActions}</div>
          </div>
        </div>

        <div className="mc-health-card">
          <div className="icon-circle green">
            <span role="img" aria-label="autonomous">&#9881;</span>
          </div>
          <div className="mc-card-content">
            <div className="mc-card-label">Autonomous</div>
            <div className="mc-card-value">{autonomousActions}</div>
            <div className="mc-card-sub">{autonomousPct}%</div>
          </div>
        </div>

        <div className="mc-health-card">
          <div className="icon-circle gold">
            <span role="img" aria-label="success">&#10003;</span>
          </div>
          <div className="mc-card-content">
            <div className="mc-card-label">Success Rate</div>
            <div className="mc-card-value">{health?.component_scores?.accuracy?.toFixed(0) || 0}%</div>
          </div>
        </div>

        <div className="mc-health-card">
          <div className="icon-circle purple">
            <span role="img" aria-label="approval">&#9733;</span>
          </div>
          <div className="mc-card-content">
            <div className="mc-card-label">Approval Rate</div>
            <div className="mc-card-value">{health?.component_scores?.approval?.toFixed(0) || 0}%</div>
          </div>
        </div>
      </div>

      {/* COMPONENT SCORES */}
      <section className="mc-section">
        <div className="mc-section-header">
          <h2>AI Performance Components</h2>
          <div className="view-toggle">
            <button className={metricsView === 7 ? 'active' : ''} onClick={() => setMetricsView(7)}>7 Days</button>
            <button className={metricsView === 30 ? 'active' : ''} onClick={() => setMetricsView(30)}>30 Days</button>
          </div>
        </div>

        <div className="mc-scores-grid">
          {[
            { key: 'autonomy', label: 'Autonomy Score', desc: 'How often AI acts independently', icon: '&#9881;', bg: 'rgba(45, 122, 82, 0.1)' },
            { key: 'accuracy', label: 'Accuracy Score', desc: 'Success rate of AI actions', icon: '&#127919;', bg: 'rgba(59, 130, 246, 0.1)' },
            { key: 'approval', label: 'Approval Score', desc: 'Actions approved by users', icon: '&#10003;', bg: 'rgba(184, 146, 74, 0.1)' },
            { key: 'confidence', label: 'Confidence Score', desc: "AI's confidence in decisions", icon: '&#128170;', bg: 'rgba(139, 92, 246, 0.1)' },
          ].map(({ key, label, desc, icon, bg }) => {
            const score = health?.component_scores?.[key] || 0;
            return (
              <div key={key} className="mc-score-card">
                <div className="mc-score-header">
                  <div className="mc-score-icon" style={{ background: bg }}>
                    <span dangerouslySetInnerHTML={{ __html: icon }} />
                  </div>
                  <div className="mc-score-label">{label}</div>
                </div>
                <div className="mc-score-value">{score.toFixed(1)}</div>
                <div className="mc-score-desc">{desc}</div>
                <div className="mc-progress-bar">
                  <div
                    className={`mc-progress-fill ${getProgressClass(score)}`}
                    style={{ width: `${Math.min(score, 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* AGENT METRICS */}
      {metrics?.agents && Object.keys(metrics.agents).length > 0 && (
        <section className="mc-section">
          <div className="mc-section-header">
            <h2>Agent Performance Breakdown</h2>
          </div>

          <div className="mc-agents-grid">
            {Object.entries(metrics.agents).map(([agentName, m]) => (
              <div key={agentName} className={`mc-agent-card ${getAgentSuccessClass(m.success_rate)}`}>
                <div className="mc-agent-header">
                  <h3>{agentName}</h3>
                  <button
                    className={`btn-filter ${selectedAgent === agentName ? 'active' : ''}`}
                    onClick={() => setSelectedAgent(selectedAgent === agentName ? null : agentName)}
                  >
                    {selectedAgent === agentName ? 'Show All' : 'Filter'}
                  </button>
                </div>
                <div className="mc-agent-metrics">
                  <div className="mc-agent-metric">
                    <span className="label">Total Actions</span>
                    <span className="value">{m.total}</span>
                  </div>
                  <div className="mc-agent-metric">
                    <span className="label">Autonomous</span>
                    <span className="value">{m.autonomous} ({m.autonomy_rate}%)</span>
                  </div>
                  <div className="mc-agent-metric">
                    <span className="label">Success Rate</span>
                    <span className="value">{m.success_rate}%</span>
                  </div>
                  <div className="mc-agent-metric">
                    <span className="label">Avg Confidence</span>
                    <span className="value">{m.avg_confidence}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* PENDING APPROVALS */}
      <section className="mc-section">
        <div className="mc-section-header">
          <h2>Pending Approvals</h2>
        </div>
        <ApprovalQueue embedded={true} />
      </section>

      {/* RECENT ACTIONS */}
      <section className="mc-section">
        <div className="mc-section-header">
          <h2>Recent AI Actions</h2>
          {selectedAgent && <span className="filter-badge">Filtered: {selectedAgent}</span>}
        </div>

        <div className="mc-actions-list">
          {recentActions.length === 0 ? (
            <div className="mc-empty-state">
              <div className="mc-empty-icon">&#128202;</div>
              <p>No recent actions to display</p>
            </div>
          ) : (
            recentActions.map((action) => (
              <div key={action.id} className={`mc-action-card outcome-${action.outcome || 'pending'}`}>
                <div className="mc-action-header">
                  <div className="mc-action-meta">
                    <span className="mc-action-agent">{action.agent_name}</span>
                    <span className="mc-action-type">{action.action_type}</span>
                    <span className="mc-action-time">{formatTimestamp(action.created_at)}</span>
                  </div>
                  <div className="mc-action-badges">
                    {action.autonomy_level && (
                      <span className={`mc-badge autonomy-${action.autonomy_level}`}>
                        {action.autonomy_level === 'full' ? 'Autonomous' : 'Assisted'}
                      </span>
                    )}
                    {action.outcome && (
                      <span className={`mc-badge outcome-${action.outcome}`}>{action.outcome}</span>
                    )}
                    {action.confidence_score && (
                      <span className="mc-badge confidence">{action.confidence_score}%</span>
                    )}
                  </div>
                </div>
                {action.reasoning && (
                  <div className="mc-action-reasoning">{action.reasoning}</div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {/* AI INSIGHTS */}
      {insights.length > 0 && (
        <section className="mc-section">
          <div className="mc-section-header">
            <h2>AI-Discovered Insights</h2>
          </div>

          <div className="mc-insights-list">
            {insights.map((insight) => (
              <div key={insight.id} className="mc-insight-card">
                <div className="mc-insight-header">
                  <div className="mc-insight-type">{insight.insight_type}</div>
                  {insight.pattern_confidence && (
                    <div className="mc-insight-confidence">{insight.pattern_confidence}% confident</div>
                  )}
                </div>
                <div className="mc-insight-desc">{insight.pattern_description}</div>
                {insight.recommended_action && (
                  <div className="mc-insight-recommendation">
                    <strong>Recommendation:</strong> {insight.recommended_action}
                  </div>
                )}
                <div className="mc-insight-footer">
                  <span className={`mc-priority-badge ${insight.priority || 'normal'}`}>
                    {(insight.priority || 'NORMAL').toUpperCase()}
                  </span>
                  <span className="mc-insight-time">Discovered {formatTimestamp(insight.discovered_at)}</span>
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
