import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './WorkflowDashboard.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

function WorkflowDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const [dashRes, tasksRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/workflow/dashboard/summary?organization_id=1`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/tasks?status=pending&limit=10`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/alerts?limit=10`, { headers })
      ]);

      const [dashData, tasksData, alertsData] = await Promise.all([
        dashRes.json(),
        tasksRes.json(),
        alertsRes.json()
      ]);

      setDashboard(dashData);
      setTasks(tasksData.tasks || []);
      setAlerts(alertsData.alerts || []);
    } catch (error) {
      console.error('Error fetching dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const completeTask = async (taskId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE}/api/v1/workflow/tasks/${taskId}/complete`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchDashboardData();
    } catch (error) {
      console.error('Error completing task:', error);
    }
  };

  const acknowledgeAlert = async (alertId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE}/api/v1/workflow/alerts/${alertId}/acknowledge`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchDashboardData();
    } catch (error) {
      console.error('Error acknowledging alert:', error);
    }
  };

  if (loading) {
    return <div className="workflow-loading">Loading workflow dashboard...</div>;
  }

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

      {/* Tab Navigation */}
      <div className="workflow-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'tasks' ? 'active' : ''}
          onClick={() => setActiveTab('tasks')}
        >
          Tasks ({tasks.length})
        </button>
        <button
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alerts.length})
        </button>
        <button
          className={activeTab === 'theme-days' ? 'active' : ''}
          onClick={() => setActiveTab('theme-days')}
        >
          Theme Days
        </button>
        <button
          className={activeTab === 'last-mile' ? 'active' : ''}
          onClick={() => setActiveTab('last-mile')}
        >
          Last Mile
        </button>
      </div>

      {/* Tab Content */}
      <div className="workflow-content">
        {activeTab === 'overview' && (
          <div className="overview-grid">
            <div className="overview-section">
              <h3>Recent Tasks</h3>
              {tasks.length === 0 ? (
                <p className="empty-state">No pending tasks</p>
              ) : (
                <ul className="task-list">
                  {tasks.slice(0, 5).map(task => (
                    <li key={task.id} className={`task-item priority-${task.priority}`}>
                      <div className="task-info">
                        <strong>{task.title}</strong>
                        <span className="task-borrower">{task.borrower}</span>
                        {task.due_date && (
                          <span className="task-due">Due: {new Date(task.due_date).toLocaleDateString()}</span>
                        )}
                      </div>
                      <button onClick={() => completeTask(task.id)} className="btn-complete">
                        Complete
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="overview-section">
              <h3>Active Alerts</h3>
              {alerts.length === 0 ? (
                <p className="empty-state">No active alerts</p>
              ) : (
                <ul className="alert-list">
                  {alerts.slice(0, 5).map(alert => (
                    <li key={alert.id} className={`alert-item severity-${alert.severity}`}>
                      <div className="alert-info">
                        <strong>{alert.alert_type}</strong>
                        <p>{alert.message}</p>
                        <span className="alert-borrower">{alert.borrower}</span>
                      </div>
                      <button onClick={() => acknowledgeAlert(alert.id)} className="btn-acknowledge">
                        Acknowledge
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {activeTab === 'tasks' && (
          <WorkflowTasks tasks={tasks} onComplete={completeTask} onRefresh={fetchDashboardData} />
        )}

        {activeTab === 'alerts' && (
          <WorkflowAlerts alerts={alerts} onAcknowledge={acknowledgeAlert} onRefresh={fetchDashboardData} />
        )}

        {activeTab === 'theme-days' && (
          <ThemeDayManager />
        )}

        {activeTab === 'last-mile' && (
          <LastMileTracker />
        )}
      </div>
    </div>
  );
}

// Tasks Component
function WorkflowTasks({ tasks, onComplete, onRefresh }) {
  return (
    <div className="tasks-section">
      <div className="section-header">
        <h3>Workflow Tasks</h3>
        <button onClick={onRefresh} className="btn-refresh">Refresh</button>
      </div>
      {tasks.length === 0 ? (
        <p className="empty-state">No pending tasks</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Borrower</th>
              <th>Priority</th>
              <th>Due Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(task => (
              <tr key={task.id} className={`priority-${task.priority}`}>
                <td>
                  <strong>{task.title}</strong>
                  {task.description && <p className="task-desc">{task.description}</p>}
                </td>
                <td>{task.borrower}</td>
                <td><span className={`priority-badge ${task.priority}`}>{task.priority}</span></td>
                <td>{task.due_date ? new Date(task.due_date).toLocaleDateString() : '-'}</td>
                <td>
                  <button onClick={() => onComplete(task.id)} className="btn-complete">
                    Complete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Alerts Component
function WorkflowAlerts({ alerts, onAcknowledge, onRefresh }) {
  return (
    <div className="alerts-section">
      <div className="section-header">
        <h3>Workflow Alerts</h3>
        <button onClick={onRefresh} className="btn-refresh">Refresh</button>
      </div>
      {alerts.length === 0 ? (
        <p className="empty-state">No active alerts</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Message</th>
              <th>Borrower</th>
              <th>Severity</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(alert => (
              <tr key={alert.id} className={`severity-${alert.severity}`}>
                <td>{alert.alert_type}</td>
                <td>{alert.message}</td>
                <td>{alert.borrower}</td>
                <td><span className={`severity-badge ${alert.severity}`}>{alert.severity}</span></td>
                <td>
                  <button onClick={() => onAcknowledge(alert.id)} className="btn-acknowledge">
                    Acknowledge
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Theme Day Manager Component
function ThemeDayManager() {
  const [theme, setTheme] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchThemeData();
  }, []);

  const fetchThemeData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const [themeRes, messagesRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/workflow/theme-days/today`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/theme-days/scheduled?limit=20`, { headers })
      ]);

      const [themeData, messagesData] = await Promise.all([
        themeRes.json(),
        messagesRes.json()
      ]);

      setTheme(themeData);
      setMessages(messagesData.messages || []);
    } catch (error) {
      console.error('Error fetching theme data:', error);
    } finally {
      setLoading(false);
    }
  };

  const scheduleMessages = async () => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE}/api/v1/workflow/theme-days/schedule?organization_id=1`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchThemeData();
    } catch (error) {
      console.error('Error scheduling messages:', error);
    }
  };

  if (loading) return <p>Loading theme days...</p>;

  return (
    <div className="theme-day-section">
      <div className="section-header">
        <h3>Theme Days</h3>
        <button onClick={scheduleMessages} className="btn-primary">
          Schedule Today's Messages
        </button>
      </div>

      <div className="theme-today">
        <h4>Today's Theme</h4>
        <div className="theme-card">
          <div className="theme-name">{theme?.name || 'No theme'}</div>
          <div className="theme-focus">Focus: {theme?.focus || 'general'}</div>
        </div>
      </div>

      <h4>Scheduled Messages</h4>
      {messages.length === 0 ? (
        <p className="empty-state">No scheduled messages</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Borrower</th>
              <th>Theme</th>
              <th>Date</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {messages.map(msg => (
              <tr key={msg.id}>
                <td>{msg.borrower}</td>
                <td>{msg.theme_name}</td>
                <td>{msg.scheduled_date ? new Date(msg.scheduled_date).toLocaleDateString() : '-'}</td>
                <td><span className={`status-badge ${msg.status}`}>{msg.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Last Mile Tracker Component
function LastMileTracker() {
  const [todayTasks, setTodayTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLastMileData();
  }, []);

  const fetchLastMileData = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/v1/workflow/last-mile/today`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setTodayTasks(data.tasks || []);
    } catch (error) {
      console.error('Error fetching last mile data:', error);
    } finally {
      setLoading(false);
    }
  };

  const completeTask = async (taskId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE}/api/v1/workflow/last-mile/tasks/${taskId}/complete`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchLastMileData();
    } catch (error) {
      console.error('Error completing task:', error);
    }
  };

  if (loading) return <p>Loading last mile data...</p>;

  return (
    <div className="last-mile-section">
      <div className="section-header">
        <h3>Last Mile - 7 Day Pre-Closing</h3>
      </div>

      <h4>Today's Tasks</h4>
      {todayTasks.length === 0 ? (
        <p className="empty-state">No Last Mile tasks scheduled for today</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Borrower</th>
              <th>Contact</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {todayTasks.map(task => (
              <tr key={task.task_id}>
                <td>{task.task_name}</td>
                <td>{task.borrower_name}</td>
                <td>
                  {task.phone && <div>{task.phone}</div>}
                  {task.email && <div>{task.email}</div>}
                </td>
                <td>
                  <button onClick={() => completeTask(task.task_id)} className="btn-complete">
                    Complete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default WorkflowDashboard;
