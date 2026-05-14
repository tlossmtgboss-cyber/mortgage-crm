import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PipelineProbabilityWidget } from '../../PipelineProbability';
import { fetchWithAuth } from './utils';

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
      overallScore: 0, avgTimeToClose: 0, pullThroughRate: 0,
      loansFallingBehind: 0, stages: []
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
          overallScore: 0, avgTimeToClose: 0, pullThroughRate: 0,
          loansFallingBehind: 0, stages: []
        },
        referralStats: result.referral_stats || { top_partners: [] }
      });
    } catch (error) {
      console.error('Failed to load LO dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

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
          {[
            { label: 'Annual Origination Goal', goal: data.production.annualGoal, actual: data.production.annualActual, progress: data.production.annualProgress },
            { label: 'Monthly Units Goal', goal: data.production.monthlyGoal, actual: data.production.monthlyActual, progress: data.production.monthlyProgress },
            { label: 'Weekly Units Goal', goal: data.production.weeklyGoal, actual: data.production.weeklyActual, progress: data.production.weeklyProgress },
            { label: 'Daily Units Goal', goal: data.production.dailyGoal, actual: data.production.dailyActual, progress: data.production.dailyProgress }
          ].map((kpi, idx) => (
            <div key={idx} className="kpi-card">
              <div className="kpi-label">{kpi.label}</div>
              <div className="kpi-values">
                <div className="kpi-row">
                  <span className="kpi-caption">Goal:</span>
                  <span className="kpi-number">{formatGoalNumber(kpi.goal)}</span>
                </div>
                <div className="kpi-row">
                  <span className="kpi-caption">Actual:</span>
                  <span className="kpi-number highlight">{formatGoalNumber(kpi.actual)}</span>
                </div>
                <div className="kpi-progress-bar">
                  <div className="kpi-progress-fill" style={{ width: `${Math.min(kpi.progress || 0, 100)}%` }}></div>
                </div>
                <div className="kpi-percentage">{kpi.progress || 0}% of Goal</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Pipeline Efficiency Report */}
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
                <span className="received">{'↓'}{partner.received || 0}</span>
                <span className="sent">{'↑'}{partner.sent || 0}</span>
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
