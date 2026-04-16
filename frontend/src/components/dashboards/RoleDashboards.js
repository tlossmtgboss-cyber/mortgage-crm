import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PipelineProbabilityWidget } from '../PipelineProbability';
import './RoleDashboards.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// Utility function for API calls
const fetchWithAuth = async (endpoint) => {
  const response = await fetch(`${API_URL}${endpoint}`, {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    }
  });
  if (!response.ok) throw new Error('API request failed');
  return response.json();
};

// Format currency
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
};

// Format percentage
const formatPercent = (value) => {
  if (!value) return '0%';
  return `${Math.round(value)}%`;
};

// ============================================================================
// LOAN OFFICER DASHBOARD
// ============================================================================
export const LoanOfficerDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    production: { mtd: 0, ytd: 0, goal: 0, progress: 0 },
    pipeline: { total: 0, volume: 0, avgDaysToClose: 0 },
    pipelineStats: [],
    leads: { new: 0, hot: 0, followUpToday: 0 },
    tasks: { urgent: 0, today: 0, overdue: 0, total: 0 },
    recentActivity: [],
    efficiency: {
      overallScore: 0,
      avgTimeToClose: 0,
      pullThroughRate: 0,
      loansFallingBehind: 0,
      stages: []
    },
    referralStats: { top_partners: [] }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      // Calculate total tasks
      const prioritizedTasks = result.prioritized_tasks || [];
      const loanIssues = result.loan_issues || [];
      const aiTasks = result.ai_tasks || { pending: [], waiting: [] };
      const totalTasks = prioritizedTasks.length + loanIssues.length +
                        (aiTasks.pending?.length || 0) + (aiTasks.waiting?.length || 0);

      setData({
        production: result.production || { mtd: 0, ytd: 0, goal: 0, progress: 0 },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0,
          avgDaysToClose: result.efficiency?.avgTimeToClose || 28
        },
        pipelineStats: result.pipeline_stats || [],
        leads: result.lead_metrics || { new: 0, hot: 0, followUpToday: 0 },
        tasks: {
          urgent: prioritizedTasks.filter(t => t.priority === 'urgent').length,
          today: prioritizedTasks.length,
          overdue: loanIssues.length,
          total: totalTasks
        },
        recentActivity: result.messages || [],
        efficiency: result.efficiency || {
          overallScore: 0,
          avgTimeToClose: 0,
          pullThroughRate: 0,
          loansFallingBehind: 0,
          stages: []
        },
        referralStats: result.referral_stats || { top_partners: [] }
      });
    } catch (error) {
      console.error('Failed to load LO dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  // Format goal number
  const formatGoalNumber = (value) => {
    if (!value) return '0.00';
    return Number(value).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard loan-officer-dashboard">
      {/* Monthly Production Tracker */}
      <div className="lo-section production-tracker-section">
        <div className="section-header clickable" onClick={() => navigate('/goal-tracker')}>
          <h2>Monthly Production Tracker</h2>
        </div>
        <div className="production-kpis">
          <div className="kpi-card">
            <div className="kpi-label">Annual Origination Goal</div>
            <div className="kpi-values">
              <div className="kpi-row">
                <span className="kpi-caption">Goal:</span>
                <span className="kpi-number">{formatGoalNumber(data.production.annualGoal)}</span>
              </div>
              <div className="kpi-row">
                <span className="kpi-caption">Actual:</span>
                <span className="kpi-number highlight">{formatGoalNumber(data.production.annualActual)}</span>
              </div>
              <div className="kpi-progress-bar">
                <div className="kpi-progress-fill" style={{ width: `${Math.min(data.production.annualProgress || 0, 100)}%` }}></div>
              </div>
              <div className="kpi-percentage">{data.production.annualProgress || 0}% of Goal</div>
            </div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Monthly Units Goal</div>
            <div className="kpi-values">
              <div className="kpi-row">
                <span className="kpi-caption">Goal:</span>
                <span className="kpi-number">{formatGoalNumber(data.production.monthlyGoal)}</span>
              </div>
              <div className="kpi-row">
                <span className="kpi-caption">Actual:</span>
                <span className="kpi-number highlight">{formatGoalNumber(data.production.monthlyActual)}</span>
              </div>
              <div className="kpi-progress-bar">
                <div className="kpi-progress-fill" style={{ width: `${Math.min(data.production.monthlyProgress || 0, 100)}%` }}></div>
              </div>
              <div className="kpi-percentage">{data.production.monthlyProgress || 0}% of Goal</div>
            </div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Weekly Units Goal</div>
            <div className="kpi-values">
              <div className="kpi-row">
                <span className="kpi-caption">Goal:</span>
                <span className="kpi-number">{formatGoalNumber(data.production.weeklyGoal)}</span>
              </div>
              <div className="kpi-row">
                <span className="kpi-caption">Actual:</span>
                <span className="kpi-number highlight">{formatGoalNumber(data.production.weeklyActual)}</span>
              </div>
              <div className="kpi-progress-bar">
                <div className="kpi-progress-fill" style={{ width: `${Math.min(data.production.weeklyProgress || 0, 100)}%` }}></div>
              </div>
              <div className="kpi-percentage">{data.production.weeklyProgress || 0}% of Goal</div>
            </div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Daily Units Goal</div>
            <div className="kpi-values">
              <div className="kpi-row">
                <span className="kpi-caption">Goal:</span>
                <span className="kpi-number">{formatGoalNumber(data.production.dailyGoal)}</span>
              </div>
              <div className="kpi-row">
                <span className="kpi-caption">Actual:</span>
                <span className="kpi-number highlight">{formatGoalNumber(data.production.dailyActual)}</span>
              </div>
              <div className="kpi-progress-bar">
                <div className="kpi-progress-fill" style={{ width: `${Math.min(data.production.dailyProgress || 0, 100)}%` }}></div>
              </div>
              <div className="kpi-percentage">{data.production.dailyProgress || 0}% of Goal</div>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Efficiency Report - NEW */}
      <div className="lo-section efficiency-report-section">
        <div className="section-header clickable" onClick={() => navigate('/dashboard/efficiency')}>
          <h2>Pipeline Efficiency Report</h2>
        </div>
        <div className="efficiency-summary">
          <div className="efficiency-score-card">
            <div className="score-circle">
              <span className="score-value">{data.efficiency.overallScore || 0}</span>
              <span className="score-label">Efficiency Score</span>
            </div>
          </div>
          <div className="efficiency-metrics-grid">
            <div className="efficiency-metric">
              <div className="metric-label">Avg. Time to Close</div>
              <div className="metric-value">{data.efficiency.avgTimeToClose || 0} days</div>
              <div className={`metric-indicator ${(data.efficiency.avgTimeToClose || 0) <= 30 ? 'good' : 'warning'}`}>
                {(data.efficiency.avgTimeToClose || 0) <= 30 ? '✓ On Track' : '⚠ Above Target'}
              </div>
            </div>
            <div className="efficiency-metric">
              <div className="metric-label">Pull-Through Rate</div>
              <div className="metric-value">{data.efficiency.pullThroughRate || 0}%</div>
              <div className={`metric-indicator ${(data.efficiency.pullThroughRate || 0) >= 70 ? 'good' : 'warning'}`}>
                {(data.efficiency.pullThroughRate || 0) >= 70 ? '✓ Strong' : '⚠ Needs Improvement'}
              </div>
            </div>
            <div className="efficiency-metric">
              <div className="metric-label">Loans Falling Behind</div>
              <div className="metric-value">{data.efficiency.loansFallingBehind || 0}</div>
              <div className={`metric-indicator ${(data.efficiency.loansFallingBehind || 0) <= 2 ? 'good' : 'warning'}`}>
                {(data.efficiency.loansFallingBehind || 0) <= 2 ? '✓ Healthy' : '⚠ Attention Needed'}
              </div>
            </div>
            <div className="efficiency-metric">
              <div className="metric-label">Conversion Rate</div>
              <div className="metric-value">{data.efficiency.conversionRate || 0}%</div>
              <div className={`metric-indicator ${(data.efficiency.conversionRate || 0) >= 25 ? 'good' : 'warning'}`}>
                {(data.efficiency.conversionRate || 0) >= 25 ? '✓ Above Average' : '⚠ Below Target'}
              </div>
            </div>
          </div>
        </div>
        {/* Stage Performance Bars */}
        <div className="stage-performance">
          <h4>Stage Performance</h4>
          <div className="stage-bars">
            {(data.efficiency.stages || []).slice(0, 5).map((stage, idx) => (
              <div key={idx} className="stage-bar-row">
                <span className="stage-name">{stage.name}</span>
                <div className="stage-bar-container">
                  <div
                    className={`stage-bar ${stage.efficiency >= 80 ? 'good' : stage.efficiency >= 60 ? 'medium' : 'low'}`}
                    style={{ width: `${stage.efficiency || 0}%` }}
                  ></div>
                </div>
                <span className="stage-percent">{stage.efficiency || 0}%</span>
              </div>
            ))}
            {(!data.efficiency.stages || data.efficiency.stages.length === 0) && (
              <div className="empty-state">No stage data available</div>
            )}
          </div>
        </div>
        <button className="btn-view-full" onClick={() => navigate('/dashboard/efficiency')}>
          View Full Efficiency Report →
        </button>
      </div>

      {/* Pipeline Probability Scores */}
      <div className="lo-section probability-section">
        <PipelineProbabilityWidget compact={true} />
      </div>

      {/* AI Prioritized Tasks */}
      <div className="lo-section ai-tasks-section">
        <div className="section-header clickable" onClick={() => navigate('/tasks')}>
          <h2>AI Prioritized Tasks (Today)</h2>
          <span className="task-badge">{data.tasks.total} tasks</span>
        </div>
        <div className="task-summary" onClick={() => navigate('/tasks')}>
          <div className="task-count-display">
            <div className="count-number">{data.tasks.total}</div>
            <div className="count-label">Outstanding Tasks</div>
          </div>
          <div className="click-to-view">Click to view all tasks →</div>
        </div>
      </div>

      {/* Live Loan Pipeline */}
      <div className="lo-section pipeline-section">
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

      {/* Referral Scoreboard */}
      <div className="lo-section referral-section">
        <div className="section-header">
          <h2>Referral Scoreboard</h2>
        </div>
        <div className="referral-list">
          {(data.referralStats.top_partners || []).slice(0, 5).map((partner, idx) => (
            <div
              key={idx}
              className="referral-row clickable"
              onClick={() => navigate(`/referral-partners/${partner.id || idx + 1}`)}
            >
              <span className="rank">{idx + 1}</span>
              <span className="partner-name">{partner.name}</span>
              <span className="partner-score">
                <span className="received">↓{partner.received || 0}</span>
                <span className="sent">↑{partner.sent || 0}</span>
              </span>
            </div>
          ))}
          {(!data.referralStats.top_partners || data.referralStats.top_partners.length === 0) && (
            <div className="empty-state">No referral partners yet</div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// PROCESSOR DASHBOARD
// ============================================================================
export const ProcessorDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    queue: { assigned: 0, inProgress: 0, needsReview: 0 },
    documents: { pending: 0, received: 0, expired: 0 },
    conditions: { open: 0, cleared: 0, pastDue: 0 },
    sla: { onTime: 0, atRisk: 0, late: 0 },
    workload: []
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');
      // Map to processor-specific metrics
      const pipelineData = result.pipeline_stats || [];
      const processingStages = pipelineData.filter(s =>
        ['Processing', 'Submitted', 'Underwriting'].includes(s.name)
      );

      setData({
        queue: {
          assigned: processingStages.reduce((sum, s) => sum + (s.count || 0), 0),
          inProgress: processingStages.find(s => s.name === 'Processing')?.count || 0,
          needsReview: result.loan_issues?.length || 0
        },
        documents: {
          pending: result.ai_tasks?.pending?.length || 0,
          received: result.ai_tasks?.waiting?.length || 0,
          expired: 0
        },
        conditions: {
          open: result.loan_issues?.filter(i => i.type === 'condition').length || 0,
          cleared: 0,
          pastDue: result.loan_issues?.filter(i => i.priority === 'high').length || 0
        },
        sla: {
          onTime: result.efficiency?.onTimePercent || 85,
          atRisk: 10,
          late: 5
        },
        workload: processingStages
      });
    } catch (error) {
      console.error('Failed to load Processor dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard processor-dashboard">
      <div className="dashboard-header">
        <h1>Processor Dashboard</h1>
        <p className="subtitle">Document management and file processing</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/loans?stage=processing')}>
          <div className="kpi-icon">📁</div>
          <div className="kpi-content">
            <div className="kpi-label">Files Assigned</div>
            <div className="kpi-value">{data.queue.assigned}</div>
            <div className="kpi-subtext">{data.queue.inProgress} in progress</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">📄</div>
          <div className="kpi-content">
            <div className="kpi-label">Pending Documents</div>
            <div className="kpi-value">{data.documents.pending}</div>
            <div className="kpi-subtext">{data.documents.received} received today</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">⚠️</div>
          <div className="kpi-content">
            <div className="kpi-label">Open Conditions</div>
            <div className="kpi-value">{data.conditions.open}</div>
            <div className="kpi-subtext">{data.conditions.pastDue} past due</div>
          </div>
        </div>

        <div className="kpi-card success">
          <div className="kpi-icon">✅</div>
          <div className="kpi-content">
            <div className="kpi-label">SLA Compliance</div>
            <div className="kpi-value">{data.sla.onTime}%</div>
            <div className="kpi-subtext">{data.sla.atRisk}% at risk</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section queue-section">
          <div className="section-header">
            <h2>Processing Queue</h2>
            <button className="view-all-btn" onClick={() => navigate('/loans?stage=processing')}>View All →</button>
          </div>
          <div className="queue-stats">
            <div className="queue-item">
              <span className="queue-label">Needs Review</span>
              <span className="queue-count warning">{data.queue.needsReview}</span>
            </div>
            <div className="queue-item">
              <span className="queue-label">Document Expired</span>
              <span className="queue-count danger">{data.documents.expired}</span>
            </div>
            <div className="queue-item">
              <span className="queue-label">Ready to Submit</span>
              <span className="queue-count success">{data.queue.inProgress}</span>
            </div>
          </div>
        </div>

        <div className="section workload-section">
          <div className="section-header">
            <h2>Today's Workload</h2>
          </div>
          <div className="workload-list">
            {data.workload.map((stage, idx) => (
              <div key={idx} className="workload-item" onClick={() => navigate(`/loans?stage=${stage.id}`)}>
                <span className="workload-stage">{stage.name}</span>
                <span className="workload-count">{stage.count} files</span>
                {stage.alerts > 0 && <span className="workload-alert">⚠️ {stage.alerts}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// UNDERWRITER DASHBOARD
// ============================================================================
export const UnderwriterDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    queue: { pending: 0, inReview: 0, suspended: 0 },
    decisions: { approved: 0, denied: 0, conditioned: 0 },
    turnaround: { avg: 0, target: 48, compliance: 0 },
    risk: { high: 0, medium: 0, low: 0 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');
      const pipelineData = result.pipeline_stats || [];
      const uwStage = pipelineData.find(s => s.name === 'Underwriting');

      setData({
        queue: {
          pending: uwStage?.count || 0,
          inReview: Math.floor((uwStage?.count || 0) * 0.6),
          suspended: result.loan_issues?.filter(i => i.status === 'suspended').length || 0
        },
        decisions: {
          approved: 12,
          denied: 2,
          conditioned: 8
        },
        turnaround: {
          avg: 36,
          target: 48,
          compliance: 92
        },
        risk: {
          high: result.loan_issues?.filter(i => i.priority === 'high').length || 0,
          medium: result.loan_issues?.filter(i => i.priority === 'medium').length || 0,
          low: result.loan_issues?.filter(i => i.priority === 'low').length || 0
        }
      });
    } catch (error) {
      console.error('Failed to load Underwriter dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard underwriter-dashboard">
      <div className="dashboard-header">
        <h1>Underwriter Dashboard</h1>
        <p className="subtitle">Loan review queue and decision tracking</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/loans?stage=underwriting')}>
          <div className="kpi-icon">🔍</div>
          <div className="kpi-content">
            <div className="kpi-label">Review Queue</div>
            <div className="kpi-value">{data.queue.pending}</div>
            <div className="kpi-subtext">{data.queue.inReview} in review</div>
          </div>
        </div>

        <div className="kpi-card success">
          <div className="kpi-icon">✅</div>
          <div className="kpi-content">
            <div className="kpi-label">Approved Today</div>
            <div className="kpi-value">{data.decisions.approved}</div>
            <div className="kpi-subtext">{data.decisions.conditioned} w/ conditions</div>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon">⏱️</div>
          <div className="kpi-content">
            <div className="kpi-label">Avg Turnaround</div>
            <div className="kpi-value">{data.turnaround.avg}h</div>
            <div className="kpi-subtext">Target: {data.turnaround.target}h</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">⚠️</div>
          <div className="kpi-content">
            <div className="kpi-label">High Risk Files</div>
            <div className="kpi-value">{data.risk.high}</div>
            <div className="kpi-subtext">{data.queue.suspended} suspended</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section decisions-section">
          <div className="section-header">
            <h2>Today's Decisions</h2>
          </div>
          <div className="decision-chart">
            <div className="decision-bar approved" style={{ width: `${(data.decisions.approved / (data.decisions.approved + data.decisions.denied + data.decisions.conditioned)) * 100}%` }}>
              <span>Approved: {data.decisions.approved}</span>
            </div>
            <div className="decision-bar conditioned" style={{ width: `${(data.decisions.conditioned / (data.decisions.approved + data.decisions.denied + data.decisions.conditioned)) * 100}%` }}>
              <span>Conditioned: {data.decisions.conditioned}</span>
            </div>
            <div className="decision-bar denied" style={{ width: `${(data.decisions.denied / (data.decisions.approved + data.decisions.denied + data.decisions.conditioned)) * 100}%` }}>
              <span>Denied: {data.decisions.denied}</span>
            </div>
          </div>
        </div>

        <div className="section risk-section">
          <div className="section-header">
            <h2>Risk Distribution</h2>
          </div>
          <div className="risk-breakdown">
            <div className="risk-item high">
              <span className="risk-label">High Risk</span>
              <span className="risk-count">{data.risk.high}</span>
            </div>
            <div className="risk-item medium">
              <span className="risk-label">Medium Risk</span>
              <span className="risk-count">{data.risk.medium}</span>
            </div>
            <div className="risk-item low">
              <span className="risk-label">Low Risk</span>
              <span className="risk-count">{data.risk.low}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// CLOSER DASHBOARD
// ============================================================================
export const CloserDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    closing: { scheduled: 0, thisWeek: 0, funding: 0 },
    documents: { docsOut: 0, docsBack: 0, readyToFund: 0 },
    issues: { titleIssues: 0, signingIssues: 0, fundingHolds: 0 },
    volume: { mtd: 0, ytd: 0 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');
      const pipelineData = result.pipeline_stats || [];
      const closingStages = pipelineData.filter(s =>
        ['Clear to Close', 'Docs Out', 'Docs Back', 'Funding'].includes(s.name)
      );

      setData({
        closing: {
          scheduled: closingStages.reduce((sum, s) => sum + (s.count || 0), 0),
          thisWeek: pipelineData.find(s => s.name === 'Clear to Close')?.count || 0,
          funding: pipelineData.find(s => s.name === 'Funding')?.count || 0
        },
        documents: {
          docsOut: pipelineData.find(s => s.name === 'Docs Out')?.count || 0,
          docsBack: pipelineData.find(s => s.name === 'Docs Back')?.count || 0,
          readyToFund: pipelineData.find(s => s.name === 'Funding')?.count || 0
        },
        issues: {
          titleIssues: result.loan_issues?.filter(i => i.type === 'title').length || 0,
          signingIssues: result.loan_issues?.filter(i => i.type === 'signing').length || 0,
          fundingHolds: result.loan_issues?.filter(i => i.type === 'funding').length || 0
        },
        volume: {
          mtd: closingStages.reduce((sum, s) => sum + (s.volume || 0), 0),
          ytd: result.production?.yearToDateVolume || 0
        }
      });
    } catch (error) {
      console.error('Failed to load Closer dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard closer-dashboard">
      <div className="dashboard-header">
        <h1>Closer Dashboard</h1>
        <p className="subtitle">Closing calendar and funding pipeline</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/loans?stage=closing')}>
          <div className="kpi-icon">📅</div>
          <div className="kpi-content">
            <div className="kpi-label">Closings This Week</div>
            <div className="kpi-value">{data.closing.thisWeek}</div>
            <div className="kpi-subtext">{data.closing.scheduled} total scheduled</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans?stage=docs-out')}>
          <div className="kpi-icon">📝</div>
          <div className="kpi-content">
            <div className="kpi-label">Docs Out</div>
            <div className="kpi-value">{data.documents.docsOut}</div>
            <div className="kpi-subtext">{data.documents.docsBack} docs back</div>
          </div>
        </div>

        <div className="kpi-card success" onClick={() => navigate('/loans?stage=funding')}>
          <div className="kpi-icon">💰</div>
          <div className="kpi-content">
            <div className="kpi-label">Ready to Fund</div>
            <div className="kpi-value">{data.documents.readyToFund}</div>
            <div className="kpi-subtext">{formatCurrency(data.volume.mtd)} MTD</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">🚨</div>
          <div className="kpi-content">
            <div className="kpi-label">Funding Holds</div>
            <div className="kpi-value">{data.issues.fundingHolds}</div>
            <div className="kpi-subtext">{data.issues.titleIssues} title issues</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section closing-pipeline">
          <div className="section-header">
            <h2>Closing Pipeline</h2>
            <button className="view-all-btn" onClick={() => navigate('/calendar')}>View Calendar →</button>
          </div>
          <div className="pipeline-flow">
            <div className="flow-stage">
              <span className="stage-name">Clear to Close</span>
              <span className="stage-count">{data.closing.thisWeek}</span>
            </div>
            <span className="flow-arrow">→</span>
            <div className="flow-stage">
              <span className="stage-name">Docs Out</span>
              <span className="stage-count">{data.documents.docsOut}</span>
            </div>
            <span className="flow-arrow">→</span>
            <div className="flow-stage">
              <span className="stage-name">Docs Back</span>
              <span className="stage-count">{data.documents.docsBack}</span>
            </div>
            <span className="flow-arrow">→</span>
            <div className="flow-stage success">
              <span className="stage-name">Funding</span>
              <span className="stage-count">{data.closing.funding}</span>
            </div>
          </div>
        </div>

        <div className="section issues-section">
          <div className="section-header">
            <h2>Open Issues</h2>
          </div>
          <div className="issues-list">
            <div className="issue-item">
              <span className="issue-icon">📋</span>
              <span className="issue-label">Title Issues</span>
              <span className="issue-count">{data.issues.titleIssues}</span>
            </div>
            <div className="issue-item">
              <span className="issue-icon">✍️</span>
              <span className="issue-label">Signing Issues</span>
              <span className="issue-count">{data.issues.signingIssues}</span>
            </div>
            <div className="issue-item">
              <span className="issue-icon">🏦</span>
              <span className="issue-label">Funding Holds</span>
              <span className="issue-count">{data.issues.fundingHolds}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// SITE ADMINISTRATOR DASHBOARD (Company Admin / Account Owner)
// ============================================================================
export const SiteAdminDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    team: { total: 0, active: 0 },
    production: { ytd: 0, volume: 0 },
    pipeline: { total: 0, volume: 0 },
    subscription: { plan: 'Professional', status: 'Active', users: 0, maxUsers: 10 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      setData({
        team: {
          total: result.team_stats?.total_members || 0,
          active: result.team_stats?.active_today || 0
        },
        production: {
          ytd: result.production?.yearlyActual || 0,
          volume: result.production?.yearlyVolume || 0
        },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0
        },
        subscription: {
          plan: 'Professional',
          status: 'Active',
          users: result.team_stats?.total_members || 0,
          maxUsers: 25
        }
      });
    } catch (error) {
      console.error('Failed to load Site Admin dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard site-admin-dashboard">
      <div className="dashboard-header">
        <h1>Site Administrator</h1>
        <p className="subtitle">Company account management and settings</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/team-members')}>
          <div className="kpi-icon">👥</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Members</div>
            <div className="kpi-value">{data.team.total}</div>
            <div className="kpi-subtext">{data.team.active} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/scorecard')}>
          <div className="kpi-icon">📊</div>
          <div className="kpi-content">
            <div className="kpi-label">YTD Production</div>
            <div className="kpi-value">{data.production.ytd} units</div>
            <div className="kpi-subtext">{formatCurrency(data.production.volume)}</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans')}>
          <div className="kpi-icon">🏠</div>
          <div className="kpi-content">
            <div className="kpi-label">Active Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className="kpi-card success" onClick={() => navigate('/settings/subscription')}>
          <div className="kpi-icon">💳</div>
          <div className="kpi-content">
            <div className="kpi-label">Subscription</div>
            <div className="kpi-value">{data.subscription.plan}</div>
            <div className="kpi-subtext">{data.subscription.users}/{data.subscription.maxUsers} users</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section">
          <div className="section-header">
            <h2>Account Management</h2>
          </div>
          <div className="quick-actions-grid">
            <button className="quick-action-card" onClick={() => navigate('/team-members')}>
              <span className="action-icon">👤</span>
              <span className="action-label">Manage Users</span>
              <span className="action-desc">Add, edit, or remove team members</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/subscription')}>
              <span className="action-icon">💳</span>
              <span className="action-label">Subscription & Billing</span>
              <span className="action-desc">Manage your plan and payments</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/company')}>
              <span className="action-icon">🏢</span>
              <span className="action-label">Company Settings</span>
              <span className="action-desc">Logo, branding, and company info</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/integrations')}>
              <span className="action-icon">🔗</span>
              <span className="action-label">Integrations</span>
              <span className="action-desc">Connect external services</span>
            </button>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <h2>Team Overview</h2>
            <button className="view-all-btn" onClick={() => navigate('/team-members')}>View All →</button>
          </div>
          <div className="team-summary">
            <div className="summary-stat">
              <span className="stat-label">Total Users</span>
              <span className="stat-value">{data.team.total}</span>
            </div>
            <div className="summary-stat">
              <span className="stat-label">Active Today</span>
              <span className="stat-value">{data.team.active}</span>
            </div>
            <div className="summary-stat">
              <span className="stat-label">Available Seats</span>
              <span className="stat-value">{data.subscription.maxUsers - data.subscription.users}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// MANAGER DASHBOARD
// ============================================================================
export const ManagerDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    team: { total: 0, active: 0, onLeave: 0 },
    production: { mtd: 0, goal: 0, progress: 0 },
    pipeline: { total: 0, volume: 0, atRisk: 0 },
    performance: { topPerformer: '', avgConversion: 0 },
    approvals: { pending: 0, urgent: 0 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      setData({
        team: result.team_stats || { total: 0, active: 0, onLeave: 0 },
        production: {
          mtd: result.production?.monthlyActual || 0,
          goal: result.production?.monthlyGoal || 0,
          progress: result.production?.monthlyProgress || 0
        },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0,
          atRisk: result.loan_issues?.length || 0
        },
        performance: {
          topPerformer: 'John Smith',
          avgConversion: result.efficiency?.conversionRate || 68
        },
        approvals: {
          pending: result.ai_tasks?.waiting?.length || 0,
          urgent: result.ai_tasks?.pending?.filter(t => t.priority === 'urgent').length || 0
        }
      });
    } catch (error) {
      console.error('Failed to load Manager dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard manager-dashboard">
      <div className="dashboard-header">
        <h1>Manager Dashboard</h1>
        <p className="subtitle">Team performance and operational oversight</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/team-members')}>
          <div className="kpi-icon">👥</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Members</div>
            <div className="kpi-value">{data.team.total_members || data.team.total || 0}</div>
            <div className="kpi-subtext">{data.team.active_today || data.team.active || 0} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/scorecard')}>
          <div className="kpi-icon">📊</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Production</div>
            <div className="kpi-value">{data.production.mtd} units</div>
            <div className="kpi-subtext">{formatPercent(data.production.progress)} of goal</div>
          </div>
          <div className="kpi-progress">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.min(data.production.progress, 100)}%` }} />
            </div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans')}>
          <div className="kpi-icon">🏠</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">📋</div>
          <div className="kpi-content">
            <div className="kpi-label">Pending Approvals</div>
            <div className="kpi-value">{data.approvals.pending}</div>
            <div className="kpi-subtext">{data.approvals.urgent} urgent</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section performance-section">
          <div className="section-header">
            <h2>Team Performance</h2>
            <button className="view-all-btn" onClick={() => navigate('/scorecard')}>View Scorecard →</button>
          </div>
          <div className="performance-stats">
            <div className="perf-stat">
              <span className="perf-label">Conversion Rate</span>
              <span className="perf-value">{data.performance.avgConversion}%</span>
            </div>
            <div className="perf-stat">
              <span className="perf-label">At-Risk Loans</span>
              <span className="perf-value warning">{data.pipeline.atRisk}</span>
            </div>
            <div className="perf-stat">
              <span className="perf-label">Top Performer</span>
              <span className="perf-value">{data.performance.topPerformer}</span>
            </div>
          </div>
        </div>

        <div className="section approvals-section">
          <div className="section-header">
            <h2>Action Required</h2>
          </div>
          <div className="action-items">
            <div className="action-item" onClick={() => navigate('/tasks?filter=approvals')}>
              <span className="action-icon">✅</span>
              <span className="action-label">Pending Approvals</span>
              <span className="action-count">{data.approvals.pending}</span>
            </div>
            <div className="action-item" onClick={() => navigate('/loans?filter=at-risk')}>
              <span className="action-icon">⚠️</span>
              <span className="action-label">At-Risk Loans</span>
              <span className="action-count">{data.pipeline.atRisk}</span>
            </div>
          </div>
        </div>

        {/* Pipeline Probability Scores */}
        <div className="section probability-section">
          <PipelineProbabilityWidget compact={true} />
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// ADMIN/EXECUTIVE DASHBOARD
// ============================================================================
export const AdminDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    company: { totalUsers: 0, activeToday: 0, branches: 0 },
    production: { mtd: 0, ytd: 0, revenue: 0 },
    pipeline: { total: 0, volume: 0 },
    health: { systemStatus: 'healthy', alerts: 0, compliance: 100 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      setData({
        company: {
          totalUsers: result.team_stats?.total_members || 25,
          activeToday: result.team_stats?.active_today || 18,
          branches: 3
        },
        production: {
          mtd: result.production?.monthlyActual || 0,
          ytd: result.production?.annualActual || 0,
          revenue: result.production?.revenue || 0
        },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0
        },
        health: {
          systemStatus: 'healthy',
          alerts: result.loan_issues?.length || 0,
          compliance: 98
        }
      });
    } catch (error) {
      console.error('Failed to load Admin dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard admin-dashboard">
      <div className="dashboard-header">
        <h1>Executive Dashboard</h1>
        <p className="subtitle">Company-wide metrics and system health</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/team-members')}>
          <div className="kpi-icon">🏢</div>
          <div className="kpi-content">
            <div className="kpi-label">Total Users</div>
            <div className="kpi-value">{data.company.totalUsers}</div>
            <div className="kpi-subtext">{data.company.activeToday} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/profitability')}>
          <div className="kpi-icon">💰</div>
          <div className="kpi-content">
            <div className="kpi-label">YTD Production</div>
            <div className="kpi-value">{data.production.ytd} units</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)} pipeline</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans')}>
          <div className="kpi-icon">📈</div>
          <div className="kpi-content">
            <div className="kpi-label">Active Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className={`kpi-card ${data.health.systemStatus === 'healthy' ? 'success' : 'alert'}`}>
          <div className="kpi-icon">{data.health.systemStatus === 'healthy' ? '✅' : '⚠️'}</div>
          <div className="kpi-content">
            <div className="kpi-label">System Health</div>
            <div className="kpi-value">{data.health.systemStatus === 'healthy' ? 'Healthy' : 'Issues'}</div>
            <div className="kpi-subtext">{data.health.compliance}% compliance</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section company-section">
          <div className="section-header">
            <h2>Company Overview</h2>
            <button className="view-all-btn" onClick={() => navigate('/settings/account-management')}>Manage Accounts →</button>
          </div>
          <div className="company-stats">
            <div className="company-stat">
              <span className="stat-label">Branches</span>
              <span className="stat-value">{data.company.branches}</span>
            </div>
            <div className="company-stat">
              <span className="stat-label">MTD Units</span>
              <span className="stat-value">{data.production.mtd}</span>
            </div>
            <div className="company-stat">
              <span className="stat-label">Active Alerts</span>
              <span className="stat-value warning">{data.health.alerts}</span>
            </div>
          </div>
        </div>

        <div className="section quick-links">
          <div className="section-header">
            <h2>Quick Links</h2>
          </div>
          <div className="links-grid">
            <button className="quick-link" onClick={() => navigate('/settings/account-management')}>
              <span className="link-icon">👤</span>
              <span className="link-label">Account Management</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/admin/settings')}>
              <span className="link-icon">⚙️</span>
              <span className="link-label">Admin Settings</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/compliance')}>
              <span className="link-icon">📋</span>
              <span className="link-label">Compliance</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/scorecard')}>
              <span className="link-icon">📊</span>
              <span className="link-label">Scorecards</span>
            </button>
          </div>
        </div>

        {/* Pipeline Probability Scores */}
        <div className="section probability-section">
          <PipelineProbabilityWidget compact={false} />
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// PRODUCTION ASSISTANT 1 DASHBOARD
// ============================================================================
export const ProductionAssistant1Dashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    efficiency: {
      overallScore: 0,
      changeFromLast: 0,
      avgTimeToClose: 0,
      avgTimeChange: 0,
      pullThroughRate: 0,
      pullThroughChange: 0,
      loansFallingBehind: 0,
      fallingBehindChange: 0,
      automationRate: 0,
      automationChange: 0,
      customerSatisfaction: 0,
      satisfactionChange: 0
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

      // Calculate total tasks
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
      console.error('Failed to load PA1 dashboard:', error);
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
    <div className="role-dashboard pa-dashboard pa1-dashboard">
      <div className="dashboard-header">
        <h1>Production Assistant 1 Dashboard</h1>
        <p className="subtitle">Pipeline efficiency and workflow management</p>
      </div>

      {/* Pipeline Efficiency Monitor */}
      <div className="pa-section efficiency-monitor-section">
        <div className="section-header">
          <h2>Pipeline Efficiency Monitor</h2>
        </div>

        {/* Overall Efficiency Banner */}
        <div className="efficiency-banner">
          <div className="efficiency-score-large">
            <span className="score">{data.efficiency.overallScore}</span>
            <span className="label">Overall Efficiency</span>
            <span className={`change ${data.efficiency.changeFromLast >= 0 ? 'positive' : 'negative'}`}>
              {data.efficiency.changeFromLast >= 0 ? '↑' : '↓'} {Math.abs(data.efficiency.changeFromLast)}% vs. last period
            </span>
          </div>
        </div>

        {/* Efficiency Metrics Row */}
        <div className="efficiency-metrics-row">
          <div className="efficiency-metric-card">
            <div className="metric-label">AVG. TIME TO CLOSE</div>
            <div className="metric-value">{data.efficiency.avgTimeToClose} days</div>
            <div className={`metric-change ${data.efficiency.avgTimeChange <= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.avgTimeChange)} days
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">PULL-THROUGH RATE</div>
            <div className="metric-value">{data.efficiency.pullThroughRate}%</div>
            <div className={`metric-change ${data.efficiency.pullThroughChange >= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.pullThroughChange)}%
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">LOANS FALLING BEHIND</div>
            <div className="metric-value">{data.efficiency.loansFallingBehind}</div>
            <div className={`metric-change ${data.efficiency.fallingBehindChange <= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.fallingBehindChange)}
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">AUTOMATION RATE</div>
            <div className="metric-value">{data.efficiency.automationRate}%</div>
            <div className={`metric-change ${data.efficiency.automationChange >= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.automationChange)}%
            </div>
          </div>
        </div>

        {/* Customer Satisfaction */}
        <div className="satisfaction-card">
          <div className="metric-label">CUSTOMER SATISFACTION SCORE</div>
          <div className="metric-value">{data.efficiency.customerSatisfaction}%</div>
          <div className={`metric-change ${data.efficiency.satisfactionChange >= 0 ? 'positive' : 'negative'}`}>
            ↑ {Math.abs(data.efficiency.satisfactionChange)}%
          </div>
        </div>

        {/* Stage and Team Performance */}
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

        {/* Active Bottlenecks */}
        <div className="bottlenecks-section">
          <h4 className="bottlenecks-title">ACTIVE BOTTLENECKS ({data.bottlenecks.length})</h4>
          {data.bottlenecks.length > 0 ? (
            <div className="bottlenecks-list">
              {data.bottlenecks.map((bottleneck, idx) => (
                <div key={idx} className="bottleneck-item">
                  <span className="bottleneck-icon">⚠️</span>
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

// ============================================================================
// PRODUCTION ASSISTANT 2 DASHBOARD
// ============================================================================
export const ProductionAssistant2Dashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    efficiency: {
      overallScore: 0,
      changeFromLast: 0,
      avgTimeToClose: 0,
      avgTimeChange: 0,
      pullThroughRate: 0,
      pullThroughChange: 0,
      loansFallingBehind: 0,
      fallingBehindChange: 0,
      automationRate: 0,
      automationChange: 0,
      customerSatisfaction: 0,
      satisfactionChange: 0
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

      // Calculate total tasks
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
      console.error('Failed to load PA2 dashboard:', error);
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
    <div className="role-dashboard pa-dashboard pa2-dashboard">
      <div className="dashboard-header">
        <h1>Production Assistant 2 Dashboard</h1>
        <p className="subtitle">Pipeline efficiency and workflow management</p>
      </div>

      {/* Pipeline Efficiency Monitor */}
      <div className="pa-section efficiency-monitor-section">
        <div className="section-header">
          <h2>Pipeline Efficiency Monitor</h2>
        </div>

        {/* Overall Efficiency Banner */}
        <div className="efficiency-banner">
          <div className="efficiency-score-large">
            <span className="score">{data.efficiency.overallScore}</span>
            <span className="label">Overall Efficiency</span>
            <span className={`change ${data.efficiency.changeFromLast >= 0 ? 'positive' : 'negative'}`}>
              {data.efficiency.changeFromLast >= 0 ? '↑' : '↓'} {Math.abs(data.efficiency.changeFromLast)}% vs. last period
            </span>
          </div>
        </div>

        {/* Efficiency Metrics Row */}
        <div className="efficiency-metrics-row">
          <div className="efficiency-metric-card">
            <div className="metric-label">AVG. TIME TO CLOSE</div>
            <div className="metric-value">{data.efficiency.avgTimeToClose} days</div>
            <div className={`metric-change ${data.efficiency.avgTimeChange <= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.avgTimeChange)} days
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">PULL-THROUGH RATE</div>
            <div className="metric-value">{data.efficiency.pullThroughRate}%</div>
            <div className={`metric-change ${data.efficiency.pullThroughChange >= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.pullThroughChange)}%
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">LOANS FALLING BEHIND</div>
            <div className="metric-value">{data.efficiency.loansFallingBehind}</div>
            <div className={`metric-change ${data.efficiency.fallingBehindChange <= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.fallingBehindChange)}
            </div>
          </div>
          <div className="efficiency-metric-card">
            <div className="metric-label">AUTOMATION RATE</div>
            <div className="metric-value">{data.efficiency.automationRate}%</div>
            <div className={`metric-change ${data.efficiency.automationChange >= 0 ? 'positive' : 'negative'}`}>
              ↑ {Math.abs(data.efficiency.automationChange)}%
            </div>
          </div>
        </div>

        {/* Customer Satisfaction */}
        <div className="satisfaction-card">
          <div className="metric-label">CUSTOMER SATISFACTION SCORE</div>
          <div className="metric-value">{data.efficiency.customerSatisfaction}%</div>
          <div className={`metric-change ${data.efficiency.satisfactionChange >= 0 ? 'positive' : 'negative'}`}>
            ↑ {Math.abs(data.efficiency.satisfactionChange)}%
          </div>
        </div>

        {/* Stage and Team Performance */}
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

        {/* Active Bottlenecks */}
        <div className="bottlenecks-section">
          <h4 className="bottlenecks-title">ACTIVE BOTTLENECKS ({data.bottlenecks.length})</h4>
          {data.bottlenecks.length > 0 ? (
            <div className="bottlenecks-list">
              {data.bottlenecks.map((bottleneck, idx) => (
                <div key={idx} className="bottleneck-item">
                  <span className="bottleneck-icon">⚠️</span>
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

// ============================================================================
// ROLE DASHBOARD SWITCHER (for Admin users)
// ============================================================================
export const RoleDashboardSwitcher = ({ currentView, onViewChange, isAdmin }) => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);

  const roles = [
    { id: 'admin', label: 'Administrator', icon: '🏢' },
    { id: 'site_admin', label: 'Site Administrator', icon: '🔧' },
    { id: 'loan_officer', label: 'Loan Officer', icon: '👔' },
    { id: 'production_assistant_1', label: 'Production Assistant 1', icon: '📊' },
    { id: 'production_assistant_2', label: 'Production Assistant 2', icon: '📈' },
    { id: 'concierge', label: 'Concierge', icon: '🛎️' },
    { id: 'processor', label: 'Processor', icon: '📁' },
    { id: 'underwriter', label: 'Underwriter', icon: '🔍' },
    { id: 'closer', label: 'Closer', icon: '📅' },
    { id: 'manager', label: 'Manager', icon: '👥' },
    { id: 'executive', label: 'Executive', icon: '🏢' }
  ];

  const currentRole = roles.find(r => r.id === currentView) || roles[0];

  if (!isAdmin) return null;

  return (
    <div className="role-switcher">
      <button
        className="role-switcher-trigger"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="current-role-label">{currentRole.label}</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="role-switcher-dropdown">
          {roles.map(role => (
            <button
              key={role.id}
              className={`role-option ${currentView === role.id ? 'active' : ''}`}
              onClick={() => {
                onViewChange(role.id);
                setIsOpen(false);
              }}
            >
              <span className="role-label">{role.label}</span>
              {currentView === role.id && <span className="check-mark">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// GET DASHBOARD BY ROLE
// ============================================================================
export const getDashboardByRole = (roleId) => {
  switch (roleId) {
    case 'site_admin':
      return SiteAdminDashboard;
    case 'loan_officer':
    case 'sales':
      return LoanOfficerDashboard;
    case 'production_assistant_1':
    case 'pa1':
      return ProductionAssistant1Dashboard;
    case 'production_assistant_2':
    case 'pa2':
      return ProductionAssistant2Dashboard;
    case 'concierge':
      return ProductionAssistant1Dashboard; // Concierge has same permissions as Production Assistants
    case 'processor':
      return ProcessorDashboard;
    case 'underwriter':
      return UnderwriterDashboard;
    case 'closer':
      return CloserDashboard;
    case 'manager':
    case 'management':
      return ManagerDashboard;
    case 'executive':
    case 'admin':
      return AdminDashboard;
    default:
      return null;
  }
};

const RoleDashboards = {
  LoanOfficerDashboard,
  ProductionAssistant1Dashboard,
  ProductionAssistant2Dashboard,
  ProcessorDashboard,
  UnderwriterDashboard,
  CloserDashboard,
  ManagerDashboard,
  SiteAdminDashboard,
  AdminDashboard,
  RoleDashboardSwitcher,
  getDashboardByRole
};

export default RoleDashboards;
