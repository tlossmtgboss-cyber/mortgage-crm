import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth } from './utils';

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
          <div className="kpi-icon">&#x1F4C1;</div>
          <div className="kpi-content">
            <div className="kpi-label">Files Assigned</div>
            <div className="kpi-value">{data.queue.assigned}</div>
            <div className="kpi-subtext">{data.queue.inProgress} in progress</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">&#x1F4C4;</div>
          <div className="kpi-content">
            <div className="kpi-label">Pending Documents</div>
            <div className="kpi-value">{data.documents.pending}</div>
            <div className="kpi-subtext">{data.documents.received} received today</div>
          </div>
        </div>

        <div className="kpi-card alert" onClick={() => navigate('/tasks')}>
          <div className="kpi-icon">&#x26A0;&#xFE0F;</div>
          <div className="kpi-content">
            <div className="kpi-label">Open Conditions</div>
            <div className="kpi-value">{data.conditions.open}</div>
            <div className="kpi-subtext">{data.conditions.pastDue} past due</div>
          </div>
        </div>

        <div className="kpi-card success">
          <div className="kpi-icon">&#x2705;</div>
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
                {stage.alerts > 0 && <span className="workload-alert">&#x26A0;&#xFE0F; {stage.alerts}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
