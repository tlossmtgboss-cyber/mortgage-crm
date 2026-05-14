import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth, formatCurrency } from './utils';

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
          <div className="kpi-icon">&#x1F4C5;</div>
          <div className="kpi-content">
            <div className="kpi-label">Closings This Week</div>
            <div className="kpi-value">{data.closing.thisWeek}</div>
            <div className="kpi-subtext">{data.closing.scheduled} total scheduled</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans?stage=docs-out')}>
          <div className="kpi-icon">&#x1F4DD;</div>
          <div className="kpi-content">
            <div className="kpi-label">Docs Out</div>
            <div className="kpi-value">{data.documents.docsOut}</div>
            <div className="kpi-subtext">{data.documents.docsBack} docs back</div>
          </div>
        </div>

        <div className="kpi-card success" onClick={() => navigate('/loans?stage=funding')}>
          <div className="kpi-icon">&#x1F4B0;</div>
          <div className="kpi-content">
            <div className="kpi-label">Ready to Fund</div>
            <div className="kpi-value">{data.documents.readyToFund}</div>
            <div className="kpi-subtext">{formatCurrency(data.volume.mtd)} MTD</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">&#x1F6A8;</div>
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
              <span className="issue-icon">&#x1F4CB;</span>
              <span className="issue-label">Title Issues</span>
              <span className="issue-count">{data.issues.titleIssues}</span>
            </div>
            <div className="issue-item">
              <span className="issue-icon">&#x270D;&#xFE0F;</span>
              <span className="issue-label">Signing Issues</span>
              <span className="issue-count">{data.issues.signingIssues}</span>
            </div>
            <div className="issue-item">
              <span className="issue-icon">&#x1F3E6;</span>
              <span className="issue-label">Funding Holds</span>
              <span className="issue-count">{data.issues.fundingHolds}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
