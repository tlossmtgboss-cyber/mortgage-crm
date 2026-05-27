import React, { useState, useEffect, useCallback } from 'react';
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

  const loadAllData = useCallback(async () => {
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
  }, [metricsView, selectedAgent]);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 30000);
    return () => clearInterval(interval);
  }, [loadAllData]);

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
    if (score >= 80) return 'mc-fill-excellent';
    if (score >= 60) return 'mc-fill-good';
    if (score >= 40) return 'mc-fill-fair';
    return 'mc-fill-poor';
  };

  const getAgentSuccessClass = (rate) => {
    if (rate >= 80) return 'mc-agent-high';
    if (rate >= 50) return 'mc-agent-mid';
    return 'mc-agent-low';
  };

  if (loading && !health) {
    return (
      <div className="mc-page">
        <div className="mc-skeleton">
          <div className="mc-skel-strip">
            {[...Array(5)].map((_, i) => <div key={i} className="mc-skel-card" />)}
          </div>
          <div className="mc-skel-block" />
          <div className="mc-skel-block" />
        </div>
      </div>
    );
  }

  const healthStatus = health?.health_status || 'unknown';
  const totalActions = health?.metrics?.total_actions || 0;
  const autonomousActions = health?.metrics?.autonomous_actions || 0;
  const autonomousPct = totalActions > 0 ? Math.round(autonomousActions / totalActions * 100) : 0;

  const scoreItems = [
    { key: 'autonomy', label: 'Autonomy', desc: 'Independent actions', color: '#2D7A52', icon: '⚙' },
    { key: 'accuracy', label: 'Accuracy', desc: 'Success rate', color: '#3b82f6', icon: '◎' },
    { key: 'approval', label: 'Approval', desc: 'Approved by users', color: '#B8924A', icon: '✓' },
    { key: 'confidence', label: 'Confidence', desc: 'Decision confidence', color: '#8b5cf6', icon: '★' },
  ];

  return (
    <div className="mc-page">
      {/* HEADER */}
      <div className="mc-header">
        <div className="mc-header-left">
          <h1 className="mc-title">
            <span className={`mc-dot mc-dot-${healthStatus}`} />
            Mission Control
          </h1>
          <p className="mc-subtitle">AI Colleague Performance & Autonomous Operations</p>
        </div>
        <div className="mc-header-right">
          <span className="mc-updated">Updated {formatTimestamp(lastUpdated)}</span>
          <button className="mc-btn-refresh" onClick={loadAllData}>Refresh</button>
        </div>
      </div>

      {/* KPI STRIP */}
      <div className="mc-kpi-strip">
        <div className={`mc-kpi mc-kpi-primary mc-kpi-${healthStatus}`}>
          <div className="mc-kpi-top">
            <span className={`mc-dot mc-dot-${healthStatus}`} style={{ width: 14, height: 14 }} />
            <span className="mc-kpi-label">Overall AI Health</span>
          </div>
          <div className="mc-kpi-number">{health?.overall_score?.toFixed(1) || '0.0'}</div>
          <div className={`mc-kpi-status mc-status-${healthStatus}`}>
            {healthStatus.replace('_', ' ').toUpperCase()}
          </div>
        </div>

        <div className="mc-kpi">
          <div className="mc-kpi-icon mc-icon-blue">{'⚡'}</div>
          <div className="mc-kpi-label">Total Actions</div>
          <div className="mc-kpi-number">{totalActions}</div>
        </div>

        <div className="mc-kpi">
          <div className="mc-kpi-icon mc-icon-green">{'⚙'}</div>
          <div className="mc-kpi-label">Autonomous</div>
          <div className="mc-kpi-number">{autonomousActions}</div>
          <div className="mc-kpi-sub">{autonomousPct}% of total</div>
        </div>

        <div className="mc-kpi">
          <div className="mc-kpi-icon mc-icon-gold">{'✓'}</div>
          <div className="mc-kpi-label">Success Rate</div>
          <div className="mc-kpi-number">{health?.component_scores?.accuracy?.toFixed(0) || 0}%</div>
        </div>

        <div className="mc-kpi">
          <div className="mc-kpi-icon mc-icon-purple">{'★'}</div>
          <div className="mc-kpi-label">Approval Rate</div>
          <div className="mc-kpi-number">{health?.component_scores?.approval?.toFixed(0) || 0}%</div>
        </div>
      </div>

      {/* COMPONENT SCORES */}
      <div className="mc-card">
        <div className="mc-card-header">
          <h2 className="mc-card-title">AI Performance Components</h2>
          <div className="mc-toggle">
            <button className={metricsView === 7 ? 'mc-toggle-active' : ''} onClick={() => setMetricsView(7)}>7 Days</button>
            <button className={metricsView === 30 ? 'mc-toggle-active' : ''} onClick={() => setMetricsView(30)}>30 Days</button>
          </div>
        </div>

        <div className="mc-scores-row">
          {scoreItems.map(({ key, label, desc, color, icon }) => {
            const score = health?.component_scores?.[key] || 0;
            return (
              <div key={key} className="mc-score-item">
                <div className="mc-score-top">
                  <div className="mc-score-icon" style={{ backgroundColor: `${color}15`, color }}>{icon}</div>
                  <div>
                    <div className="mc-score-name">{label}</div>
                    <div className="mc-score-desc">{desc}</div>
                  </div>
                </div>
                <div className="mc-score-num" style={{ color }}>{score.toFixed(1)}</div>
                <div className="mc-bar">
                  <div className={`mc-bar-fill ${getProgressClass(score)}`} style={{ width: `${Math.min(score, 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* AGENT METRICS */}
      {metrics?.agents && Object.keys(metrics.agents).length > 0 && (
        <div className="mc-card">
          <div className="mc-card-header">
            <h2 className="mc-card-title">Agent Performance</h2>
          </div>
          <div className="mc-agents-row">
            {Object.entries(metrics.agents).map(([agentName, m]) => (
              <div key={agentName} className={`mc-agent ${getAgentSuccessClass(m.success_rate)}`}>
                <div className="mc-agent-top">
                  <h3 className="mc-agent-name">{agentName}</h3>
                  <button
                    className={`mc-btn-sm ${selectedAgent === agentName ? 'mc-btn-sm-active' : ''}`}
                    onClick={() => setSelectedAgent(selectedAgent === agentName ? null : agentName)}
                  >
                    {selectedAgent === agentName ? 'Clear' : 'Filter'}
                  </button>
                </div>
                <div className="mc-agent-stats">
                  <div className="mc-stat"><span className="mc-stat-label">Actions</span><span className="mc-stat-val">{m.total}</span></div>
                  <div className="mc-stat"><span className="mc-stat-label">Autonomous</span><span className="mc-stat-val">{m.autonomous} ({m.autonomy_rate}%)</span></div>
                  <div className="mc-stat"><span className="mc-stat-label">Success</span><span className="mc-stat-val">{m.success_rate}%</span></div>
                  <div className="mc-stat"><span className="mc-stat-label">Confidence</span><span className="mc-stat-val">{m.avg_confidence}%</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* PENDING APPROVALS */}
      <div className="mc-card">
        <div className="mc-card-header">
          <h2 className="mc-card-title">Pending Approvals</h2>
        </div>
        <ApprovalQueue embedded={true} />
      </div>

      {/* RECENT ACTIONS */}
      <div className="mc-card">
        <div className="mc-card-header">
          <h2 className="mc-card-title">Recent AI Actions</h2>
          {selectedAgent && <span className="mc-filter-tag">Filtered: {selectedAgent}</span>}
        </div>

        <div className="mc-actions">
          {recentActions.length === 0 ? (
            <div className="mc-empty">
              <p>No recent actions to display</p>
            </div>
          ) : (
            recentActions.map((action) => (
              <div key={action.id} className={`mc-action mc-action-${action.outcome || 'pending'}`}>
                <div className="mc-action-row">
                  <div className="mc-action-info">
                    <span className="mc-action-agent">{action.agent_name}</span>
                    <span className="mc-action-type">{action.action_type}</span>
                    <span className="mc-action-time">{formatTimestamp(action.created_at)}</span>
                  </div>
                  <div className="mc-action-pills">
                    {action.autonomy_level && (
                      <span className={`mc-pill mc-pill-${action.autonomy_level}`}>
                        {action.autonomy_level === 'full' ? 'Autonomous' : 'Assisted'}
                      </span>
                    )}
                    {action.outcome && (
                      <span className={`mc-pill mc-pill-outcome-${action.outcome}`}>{action.outcome}</span>
                    )}
                    {action.confidence_score != null && (
                      <span className="mc-pill mc-pill-conf">{action.confidence_score}%</span>
                    )}
                  </div>
                </div>
                {action.reasoning && (
                  <div className="mc-action-reason">{action.reasoning}</div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* AI INSIGHTS */}
      {insights.length > 0 && (
        <div className="mc-card">
          <div className="mc-card-header">
            <h2 className="mc-card-title">AI-Discovered Insights</h2>
          </div>
          <div className="mc-insights">
            {insights.map((insight) => (
              <div key={insight.id} className="mc-insight">
                <div className="mc-insight-top">
                  <span className="mc-insight-type">{insight.insight_type}</span>
                  {insight.pattern_confidence != null && (
                    <span className="mc-insight-conf">{insight.pattern_confidence}% confident</span>
                  )}
                </div>
                <div className="mc-insight-text">{insight.pattern_description}</div>
                {insight.recommended_action && (
                  <div className="mc-insight-rec">
                    <strong>Recommendation:</strong> {insight.recommended_action}
                  </div>
                )}
                <div className="mc-insight-bottom">
                  <span className={`mc-priority mc-priority-${insight.priority || 'normal'}`}>
                    {(insight.priority || 'NORMAL').toUpperCase()}
                  </span>
                  <span className="mc-insight-time">{formatTimestamp(insight.discovered_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default MissionControl;
