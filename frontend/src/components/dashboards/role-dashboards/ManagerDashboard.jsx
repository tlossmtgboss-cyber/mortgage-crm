import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PipelineProbabilityWidget } from '../../PipelineProbability';
import { fetchWithAuth, formatCurrency, formatPercent } from './utils';

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
          <div className="kpi-icon">&#x1F465;</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Members</div>
            <div className="kpi-value">{data.team.total_members || data.team.total || 0}</div>
            <div className="kpi-subtext">{data.team.active_today || data.team.active || 0} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/scorecard')}>
          <div className="kpi-icon">&#x1F4CA;</div>
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
          <div className="kpi-icon">&#x1F3E0;</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">&#x1F4CB;</div>
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
              <span className="action-icon">&#x2705;</span>
              <span className="action-label">Pending Approvals</span>
              <span className="action-count">{data.approvals.pending}</span>
            </div>
            <div className="action-item" onClick={() => navigate('/loans?filter=at-risk')}>
              <span className="action-icon">&#x26A0;&#xFE0F;</span>
              <span className="action-label">At-Risk Loans</span>
              <span className="action-count">{data.pipeline.atRisk}</span>
            </div>
          </div>
        </div>

        <div className="section probability-section">
          <PipelineProbabilityWidget compact={true} />
        </div>
      </div>
    </div>
  );
};
