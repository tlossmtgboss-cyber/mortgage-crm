import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth } from './utils';

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
        decisions: { approved: 12, denied: 2, conditioned: 8 },
        turnaround: { avg: 36, target: 48, compliance: 92 },
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

  const totalDecisions = data.decisions.approved + data.decisions.denied + data.decisions.conditioned;

  return (
    <div className="role-dashboard underwriter-dashboard">
      <div className="dashboard-header">
        <h1>Underwriter Dashboard</h1>
        <p className="subtitle">Loan review queue and decision tracking</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/loans?stage=underwriting')}>
          <div className="kpi-icon">&#x1F50D;</div>
          <div className="kpi-content">
            <div className="kpi-label">Review Queue</div>
            <div className="kpi-value">{data.queue.pending}</div>
            <div className="kpi-subtext">{data.queue.inReview} in review</div>
          </div>
        </div>

        <div className="kpi-card success">
          <div className="kpi-icon">&#x2705;</div>
          <div className="kpi-content">
            <div className="kpi-label">Approved Today</div>
            <div className="kpi-value">{data.decisions.approved}</div>
            <div className="kpi-subtext">{data.decisions.conditioned} w/ conditions</div>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon">&#x23F1;&#xFE0F;</div>
          <div className="kpi-content">
            <div className="kpi-label">Avg Turnaround</div>
            <div className="kpi-value">{data.turnaround.avg}h</div>
            <div className="kpi-subtext">Target: {data.turnaround.target}h</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">&#x26A0;&#xFE0F;</div>
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
            <div className="decision-bar approved" style={{ width: `${(data.decisions.approved / totalDecisions) * 100}%` }}>
              <span>Approved: {data.decisions.approved}</span>
            </div>
            <div className="decision-bar conditioned" style={{ width: `${(data.decisions.conditioned / totalDecisions) * 100}%` }}>
              <span>Conditioned: {data.decisions.conditioned}</span>
            </div>
            <div className="decision-bar denied" style={{ width: `${(data.decisions.denied / totalDecisions) * 100}%` }}>
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
