import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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

function WorkflowDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [activeTab, setActiveTab] = useState('prospect');
  const [workflowData, setWorkflowData] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);

  useEffect(() => {
    fetchDashboardData();
    fetchWorkflowDefinitions();
  }, []);

  useEffect(() => {
    fetchWorkflowTasks(activeTab);
  }, [activeTab]);

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

  const fetchWorkflowTasks = async (workflowKey) => {
    setTabLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch workflow definition with tasks
      const [defRes, tasksRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/workflow/definitions/${workflowKey}`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/definitions/${workflowKey}/tasks?status=pending&limit=50`, { headers })
      ]);

      const [defData, tasksData] = await Promise.all([
        defRes.json(),
        tasksRes.json()
      ]);

      setWorkflowData(defData);
      setTasks(tasksData.tasks || []);
    } catch (error) {
      console.error('Error fetching workflow tasks:', error);
      setWorkflowData(null);
      setTasks([]);
    } finally {
      setTabLoading(false);
    }
  };

  const completeTask = async (taskId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE}/api/v1/workflow/tasks/${taskId}/complete`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchWorkflowTasks(activeTab);
    } catch (error) {
      console.error('Error completing task:', error);
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

      {/* Tab Content */}
      <div className="workflow-content">
        {tabLoading ? (
          <div className="tab-loading">Loading {activeWorkflow?.name} workflow...</div>
        ) : (
          <WorkflowTabContent
            workflow={workflowData}
            tasks={tasks}
            activeWorkflow={activeWorkflow}
            onComplete={completeTask}
            onRefresh={() => fetchWorkflowTasks(activeTab)}
            navigate={navigate}
          />
        )}
      </div>
    </div>
  );
}

// Workflow Tab Content Component
function WorkflowTabContent({ workflow, tasks, activeWorkflow, onComplete, onRefresh, navigate }) {
  if (!workflow) {
    return (
      <div className="workflow-tab-section">
        <div className="workflow-header-section">
          <div className="workflow-info">
            <h3 style={{ color: activeWorkflow?.color }}>{activeWorkflow?.name} Workflow</h3>
            <p className="workflow-description">Loading workflow details...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="workflow-tab-section">
      {/* Workflow Info Header */}
      <div className="workflow-header-section">
        <div className="workflow-info">
          <h3 style={{ color: workflow.color || activeWorkflow?.color }}>
            {workflow.display_name || activeWorkflow?.name} Workflow
          </h3>
          <p className="workflow-description">{workflow.description}</p>
          <p className="workflow-objective">
            <strong>Objective:</strong> {workflow.objective}
          </p>
        </div>
        <div className="workflow-stats">
          <div className="stat-item">
            <span className="stat-number" style={{ color: workflow.color }}>{workflow.task_count || 0}</span>
            <span className="stat-label">Total Tasks</span>
          </div>
          <div className="stat-item">
            <span className="stat-number">{tasks.length}</span>
            <span className="stat-label">Pending</span>
          </div>
        </div>
      </div>

      {/* Task Templates (from workflow definition) */}
      {workflow.tasks && workflow.tasks.length > 0 && (
        <div className="task-templates-section">
          <div className="section-header">
            <h4>Task Templates</h4>
            <span className="template-count">{workflow.tasks.length} tasks in sequence</span>
          </div>
          <div className="task-templates-grid">
            {workflow.tasks.map((task, idx) => (
              <div key={task.id || idx} className="task-template-card">
                <div className="template-sequence">{task.sequence || idx + 1}</div>
                <div className="template-info">
                  <div className="template-name">{task.name}</div>
                  <div className="template-timing">{task.timing_label || `${task.timing_type}: ${task.timing_value}`}</div>
                  <div className="template-channels">
                    {task.requires_phone && <span className="channel-badge phone">Phone</span>}
                    {task.requires_text && <span className="channel-badge text">Text</span>}
                    {task.requires_email && <span className="channel-badge email">Email</span>}
                    {task.requires_partner_contact && <span className="channel-badge partner">Partner</span>}
                  </div>
                  {task.assigned_to && (
                    <div className="template-assigned">Assigned to: {task.assigned_to}</div>
                  )}
                </div>
                {task.is_automated && <span className="auto-badge">Auto</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Task Instances */}
      <div className="active-tasks-section">
        <div className="section-header">
          <h4>Active Tasks</h4>
          <button onClick={onRefresh} className="btn-refresh">Refresh</button>
        </div>

        {tasks.length === 0 ? (
          <div className="empty-state">
            <p>No pending tasks in this workflow</p>
            <p className="empty-hint">Tasks will appear here when workflows are triggered for leads/loans</p>
          </div>
        ) : (
          <table className="workflow-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Borrower</th>
                <th>Scheduled</th>
                <th>Assigned To</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr key={task.id}>
                  <td>
                    <strong>{task.task_name}</strong>
                  </td>
                  <td>{task.borrower_name}</td>
                  <td>{task.scheduled_date ? new Date(task.scheduled_date).toLocaleDateString() : '-'}</td>
                  <td>{task.assigned_to || '-'}</td>
                  <td>
                    <div className="action-buttons">
                      {task.lead_id && (
                        <button
                          onClick={() => navigate(`/leads/${task.lead_id}`)}
                          className="btn-view"
                        >
                          View Lead
                        </button>
                      )}
                      {task.loan_id && (
                        <button
                          onClick={() => navigate(`/loans/${task.loan_id}`)}
                          className="btn-view"
                        >
                          View Loan
                        </button>
                      )}
                      <button onClick={() => onComplete(task.id)} className="btn-complete">
                        Complete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default WorkflowDashboard;
