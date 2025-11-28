import React, { useState, useEffect } from 'react';
import WorkflowConfigEditor from '../components/WorkflowConfigEditor';
import WorkflowScorecard from '../components/WorkflowScorecard';
import './WorkflowDashboard.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

// The 10 workflow definitions matching backend
const WORKFLOW_TABS = [
  { key: 'prospect', name: 'Prospect', color: '#3b82f6' },
  { key: 'prequal', name: 'PreQual', color: '#8b5cf6' },
  { key: 'pre_approved', name: 'Pre-Approval', color: '#10b981' },
  { key: 'under_contract', name: 'Under Contract', color: '#f59e0b' },
  { key: 'lead_purchase', name: 'Lead Purchase', color: '#ec4899' },
  { key: 'theme_day', name: 'Theme Day', color: '#06b6d4' },
  { key: 'last_mile', name: 'Last Mile', color: '#14b8a6' },
  { key: 'post_close', name: 'Post Close', color: '#22c55e' },
  { key: 'credit_repair', name: 'Credit Repair', color: '#f97316' },
  { key: 'nurture', name: 'Nurture', color: '#6366f1' }
];

// View mode tabs
const VIEW_MODES = [
  { key: 'configuration', name: 'Configuration', icon: '⚙️' },
  { key: 'scorecard', name: 'Scorecard', icon: '📊' }
];

function WorkflowDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [activeTab, setActiveTab] = useState('prospect');
  const [viewMode, setViewMode] = useState('configuration');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
    fetchWorkflowDefinitions();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const dashRes = await fetch(`${API_BASE}/api/v1/workflow/dashboard/summary?organization_id=1`, { headers });
      const dashData = await dashRes.json();
      setDashboard(dashData);
    } catch (error) {
      console.error('Error fetching dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkflowDefinitions = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/v1/workflow/definitions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.workflows) {
        setWorkflows(data.workflows);
      }
    } catch (error) {
      console.error('Error fetching workflow definitions:', error);
    }
  };

  const getWorkflowTaskCount = (workflowKey) => {
    const workflow = workflows.find(w => w.name === workflowKey);
    return workflow?.task_count || 0;
  };

  if (loading) {
    return <div className="workflow-loading">Loading workflow dashboard...</div>;
  }

  const activeWorkflow = WORKFLOW_TABS.find(w => w.key === activeTab);

  return (
    <div className="workflow-dashboard">
      <div className="workflow-header">
        <h1>Active Loan Workflow</h1>
        <div className="theme-day-badge">
          {dashboard?.theme_day?.name || 'Today'}
        </div>
      </div>

      {/* Metrics Cards */}
      <div className="workflow-metrics">
        <div className="metric-card">
          <div className="metric-value">{dashboard?.pending_tasks || 0}</div>
          <div className="metric-label">Pending Tasks</div>
        </div>
        <div className="metric-card warning">
          <div className="metric-value">{dashboard?.overdue_tasks || 0}</div>
          <div className="metric-label">Overdue</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{dashboard?.unacknowledged_alerts || 0}</div>
          <div className="metric-label">Alerts</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{dashboard?.last_mile_today || 0}</div>
          <div className="metric-label">Last Mile Today</div>
        </div>
        <div className="metric-card danger">
          <div className="metric-value">{dashboard?.high_risk_loans || 0}</div>
          <div className="metric-label">High Risk</div>
        </div>
      </div>

      {/* Workflow Tab Navigation - 10 Tabs */}
      <div className="workflow-tabs">
        {WORKFLOW_TABS.map(tab => (
          <button
            key={tab.key}
            className={activeTab === tab.key ? 'active' : ''}
            onClick={() => setActiveTab(tab.key)}
            style={{
              '--tab-color': tab.color,
              borderBottom: activeTab === tab.key ? `3px solid ${tab.color}` : 'none'
            }}
          >
            {tab.name}
            <span className="tab-count">({getWorkflowTaskCount(tab.key)})</span>
          </button>
        ))}
      </div>

      {/* View Mode Toggle - Configuration / Scorecard */}
      <div className="view-mode-tabs">
        {VIEW_MODES.map(mode => (
          <button
            key={mode.key}
            className={`view-mode-tab ${viewMode === mode.key ? 'active' : ''}`}
            onClick={() => setViewMode(mode.key)}
          >
            <span className="mode-icon">{mode.icon}</span>
            {mode.name}
          </button>
        ))}
      </div>

      {/* Content Area - Configuration or Scorecard */}
      <div className="workflow-content embedded-config">
        {viewMode === 'configuration' ? (
          <WorkflowConfigEditor
            key={activeTab}
            workflowKey={activeWorkflow.key}
            workflowName={activeWorkflow.name}
            workflowColor={activeWorkflow.color}
            embedded={true}
          />
        ) : (
          <WorkflowScorecard
            key={`${activeTab}-scorecard`}
            workflowKey={activeWorkflow.key}
            workflowName={activeWorkflow.name}
            workflowColor={activeWorkflow.color}
          />
        )}
      </div>
    </div>
  );
}

export default WorkflowDashboard;
