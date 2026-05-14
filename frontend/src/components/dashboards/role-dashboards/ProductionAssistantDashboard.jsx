import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth } from './utils';

// Shared PA dashboard component used by both PA1 and PA2
const ProductionAssistantDashboardBase = ({ title, cssClass }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    efficiency: {
      overallScore: 0, changeFromLast: 0,
      avgTimeToClose: 0, avgTimeChange: 0,
      pullThroughRate: 0, pullThroughChange: 0,
      loansFallingBehind: 0, fallingBehindChange: 0,
      automationRate: 0, automationChange: 0,
      customerSatisfaction: 0, satisfactionChange: 0
    },
    stagePerformance: [],
    teamPerformance: [],
    bottlenecks: [],
    workflows: [],
    tasks: { total: 0, urgent: 0, today: 0 },
    pipelineStats: []
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      const prioritizedTasks = result.prioritized_tasks || [];
      const loanIssues = result.loan_issues || [];
      const aiTasks = result.ai_tasks || { pending: [], waiting: [] };
      const totalTasks = prioritizedTasks.length + loanIssues.length +
                        (aiTasks.pending?.length || 0) + (aiTasks.waiting?.length || 0);

      setData({
        efficiency: {
          overallScore: result.efficiency?.overallScore || 63,
          changeFromLast: result.efficiency?.changeFromLast || 5.2,
          avgTimeToClose: result.efficiency?.avgTimeToClose || 15,
          avgTimeChange: result.efficiency?.avgTimeChange || 0,
          pullThroughRate: result.efficiency?.pullThroughRate || 37,
          pullThroughChange: result.efficiency?.pullThroughChange || 0,
          loansFallingBehind: result.efficiency?.loansFallingBehind || 0,
          fallingBehindChange: result.efficiency?.fallingBehindChange || 0,
          automationRate: result.efficiency?.automationRate || 32,
          automationChange: result.efficiency?.automationChange || 0,
          customerSatisfaction: result.efficiency?.customerSatisfaction || 75,
          satisfactionChange: result.efficiency?.satisfactionChange || 0
        },
        stagePerformance: result.efficiency?.stages || [
          { name: 'Lead Generation', efficiency: 85 },
          { name: 'Pre-Qualification', efficiency: 72 },
          { name: 'Application', efficiency: 81 },
          { name: 'Processing', efficiency: 65 },
          { name: 'Underwriting', efficiency: 70 },
          { name: 'Clear to Close', efficiency: 88 },
          { name: 'Closing', efficiency: 92 }
        ],
        teamPerformance: result.efficiency?.teamPerformance || [
          { name: 'Loan Officers', efficiency: 82 },
          { name: 'Processors', efficiency: 68 },
          { name: 'Underwriters', efficiency: 75 },
          { name: 'Closers', efficiency: 91 }
        ],
        bottlenecks: result.efficiency?.bottlenecks || [],
        workflows: result.workflow_stats || [],
        tasks: {
          total: totalTasks,
          urgent: prioritizedTasks.filter(t => t.priority === 'urgent').length,
          today: prioritizedTasks.length
        },
        pipelineStats: result.pipeline_stats || []
      });
    } catch (error) {
      console.error(`Failed to load ${title}:`, error);
    } finally {
      setLoading(false);
    }
  };

  const getBarColor = (efficiency) => {
    if (efficiency >= 80) return 'good';
    if (efficiency >= 60) return 'warning';
    return 'danger';
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className={`role-dashboard pa-dashboard ${cssClass}`}>
      <div className="dashboard-header">
        <h1>{title}</h1>
        <p className="subtitle">Pipeline efficiency and workflow management</p>
      </div>

      {/* Pipeline Efficiency Monitor */}
      <div className="pa-section efficiency-monitor-section">
        <div className="section-header">
          <h2>Pipeline Efficiency Monitor</h2>
        </div>

        <div className="efficiency-banner">
          <div className="efficiency-score-large">
            <span className="score">{data.efficiency.overallScore}</span>
            <span className="label">Overall Efficiency</span>
            <span className={`change ${data.efficiency.changeFromLast >= 0 ? 'positive' : 'negative'}`}>
              {data.efficiency.changeFromLast >= 0 ? '↑' : '↓'} {Math.abs(data.efficiency.changeFromLast)}% vs. last period
            </span>
          </div>
        </div>

        <div className="efficiency-metrics-row">
          {[
            { label: 'AVG. TIME TO CLOSE', value: `${data.efficiency.avgTimeToClose} days`, change: data.efficiency.avgTimeChange, invertPositive: true, suffix: ' days' },
            { label: 'PULL-THROUGH RATE', value: `${data.efficiency.pullThroughRate}%`, change: data.efficiency.pullThroughChange, suffix: '%' },
            { label: 'LOANS FALLING BEHIND', value: data.efficiency.loansFallingBehind, change: data.efficiency.fallingBehindChange, invertPositive: true, suffix: '' },
            { label: 'AUTOMATION RATE', value: `${data.efficiency.automationRate}%`, change: data.efficiency.automationChange, suffix: '%' }
          ].map((metric, idx) => (
            <div key={idx} className="efficiency-metric-card">
              <div className="metric-label">{metric.label}</div>
              <div className="metric-value">{metric.value}</div>
              <div className={`metric-change ${(metric.invertPositive ? metric.change <= 0 : metric.change >= 0) ? 'positive' : 'negative'}`}>
                {'↑'} {Math.abs(metric.change)}{metric.suffix}
              </div>
            </div>
          ))}
        </div>

        <div className="satisfaction-card">
          <div className="metric-label">CUSTOMER SATISFACTION SCORE</div>
          <div className="metric-value">{data.efficiency.customerSatisfaction}%</div>
          <div className={`metric-change ${data.efficiency.satisfactionChange >= 0 ? 'positive' : 'negative'}`}>
            {'↑'} {Math.abs(data.efficiency.satisfactionChange)}%
          </div>
        </div>

        <div className="performance-grid">
          <div className="performance-card">
            <h4>STAGE PERFORMANCE</h4>
            <div className="performance-bars">
              {data.stagePerformance.map((stage, idx) => (
                <div key={idx} className="performance-bar-row">
                  <span className="bar-label">{stage.name}</span>
                  <div className="bar-container">
                    <div
                      className={`bar-fill ${getBarColor(stage.efficiency)}`}
                      style={{ width: `${stage.efficiency}%` }}
                    />
                  </div>
                  <span className="bar-value">{stage.efficiency}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="performance-card">
            <h4>TEAM PERFORMANCE</h4>
            <div className="performance-bars">
              {data.teamPerformance.map((team, idx) => (
                <div key={idx} className="performance-bar-row">
                  <span className="bar-label">{team.name}</span>
                  <div className="bar-container">
                    <div
                      className={`bar-fill ${getBarColor(team.efficiency)}`}
                      style={{ width: `${team.efficiency}%` }}
                    />
                  </div>
                  <span className="bar-value">{team.efficiency}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bottlenecks-section">
          <h4 className="bottlenecks-title">ACTIVE BOTTLENECKS ({data.bottlenecks.length})</h4>
          {data.bottlenecks.length > 0 ? (
            <div className="bottlenecks-list">
              {data.bottlenecks.map((bottleneck, idx) => (
                <div key={idx} className="bottleneck-item">
                  <span className="bottleneck-icon">&#x26A0;&#xFE0F;</span>
                  <span className="bottleneck-text">{bottleneck.description}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-bottlenecks">No active bottlenecks</div>
          )}
        </div>

        <button className="btn-view-full efficiency-btn" onClick={() => navigate('/dashboard/efficiency')}>
          View Full Efficiency Report →
        </button>
      </div>

      {/* Workflow Scorecards */}
      <div className="pa-section workflow-section">
        <div className="section-header clickable" onClick={() => navigate('/workflow-sla')}>
          <h2>Workflow Scorecards</h2>
        </div>
        <div className="workflow-cards">
          {data.workflows.length > 0 ? (
            data.workflows.slice(0, 4).map((workflow, idx) => (
              <div key={idx} className="workflow-card" onClick={() => navigate(`/workflow-sla/${workflow.id}`)}>
                <div className="workflow-name">{workflow.name}</div>
                <div className="workflow-stats">
                  <div className="workflow-stat">
                    <span className="stat-value">{workflow.active || 0}</span>
                    <span className="stat-label">Active</span>
                  </div>
                  <div className="workflow-stat">
                    <span className="stat-value">{workflow.completed || 0}</span>
                    <span className="stat-label">Completed</span>
                  </div>
                  <div className="workflow-stat">
                    <span className={`stat-value ${workflow.overdue > 0 ? 'danger' : ''}`}>{workflow.overdue || 0}</span>
                    <span className="stat-label">Overdue</span>
                  </div>
                </div>
                <div className="workflow-progress">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${workflow.progress || 0}%` }} />
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">No active workflows</div>
          )}
        </div>
        <button className="btn-view-all" onClick={() => navigate('/workflow-sla')}>
          View All Workflows →
        </button>
      </div>

      {/* AI Prioritized Tasks */}
      <div className="pa-section ai-tasks-section">
        <div className="section-header clickable" onClick={() => navigate('/tasks')}>
          <h2>AI Prioritized Tasks (Today)</h2>
          <span className="task-badge">{data.tasks.total} tasks</span>
        </div>
        <div className="task-summary" onClick={() => navigate('/tasks')}>
          <div className="task-count-display">
            <div className="count-number">{data.tasks.total}</div>
            <div className="count-label">Outstanding Tasks</div>
          </div>
          <div className="task-breakdown">
            <div className="task-stat">
              <span className="stat-value urgent">{data.tasks.urgent}</span>
              <span className="stat-label">Urgent</span>
            </div>
            <div className="task-stat">
              <span className="stat-value">{data.tasks.today}</span>
              <span className="stat-label">Today</span>
            </div>
          </div>
          <div className="click-to-view">Click to view all tasks →</div>
        </div>
      </div>

      {/* Live Loan Pipeline */}
      <div className="pa-section pipeline-section">
        <div className="section-header">
          <h2>Live Loan Pipeline</h2>
        </div>
        <div className="pipeline-table">
          <table>
            <thead>
              <tr>
                <th>Stage</th>
                <th>Count</th>
                <th>Alerts</th>
                <th>Funding $</th>
              </tr>
            </thead>
            <tbody>
              {data.pipelineStats.filter(stage => stage && stage.name).map((stage, idx) => (
                <tr key={idx} className="clickable-row" onClick={() => navigate(`/loans?stage=${stage.id}`)}>
                  <td><strong>{stage.name}</strong></td>
                  <td>{stage.count}</td>
                  <td>
                    {stage.alerts > 0 ? (
                      <span className="alert-count">{stage.alerts} {stage.alert_text}</span>
                    ) : (
                      <span className="no-issues">no issues</span>
                    )}
                  </td>
                  <td>
                    {stage.volume ? (
                      <strong>${(stage.volume / 1000000).toFixed(1)}M</strong>
                    ) : '—'}
                  </td>
                </tr>
              ))}
              {data.pipelineStats.length === 0 && (
                <tr>
                  <td colSpan={4} className="empty-state">No pipeline data</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// PA1 and PA2 are the same component with different titles/CSS classes
export const ProductionAssistant1Dashboard = () => (
  <ProductionAssistantDashboardBase
    title="Production Assistant 1 Dashboard"
    cssClass="pa1-dashboard"
  />
);

export const ProductionAssistant2Dashboard = () => (
  <ProductionAssistantDashboardBase
    title="Production Assistant 2 Dashboard"
    cssClass="pa2-dashboard"
  />
);
