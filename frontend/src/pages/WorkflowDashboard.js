import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import TaskWorkflowManager from '../components/TaskWorkflowManager';
import './WorkflowDashboard.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

function WorkflowDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [leads, setLeads] = useState([]);
  const [loans, setLoans] = useState([]);
  const [portfolio, setPortfolio] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const [dashRes, tasksRes, alertsRes, leadsRes, loansRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/workflow/dashboard/summary?organization_id=1`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/tasks?status=pending&limit=10`, { headers }),
        fetch(`${API_BASE}/api/v1/workflow/alerts?limit=10`, { headers }),
        fetch(`${API_BASE}/api/v1/leads`, { headers }).catch(() => ({ json: () => [] })),
        fetch(`${API_BASE}/api/v1/loans`, { headers }).catch(() => ({ json: () => [] }))
      ]);

      const [dashData, tasksData, alertsData, leadsData, loansData] = await Promise.all([
        dashRes.json(),
        tasksRes.json(),
        alertsRes.json(),
        leadsRes.json ? leadsRes.json() : [],
        loansRes.json ? loansRes.json() : []
      ]);

      setDashboard(dashData);
      setTasks(tasksData.tasks || []);
      setAlerts(alertsData.alerts || []);
      setLeads(Array.isArray(leadsData) ? leadsData : []);

      // Separate active loans and portfolio (closed loans)
      const allLoans = Array.isArray(loansData) ? loansData : [];
      setLoans(allLoans.filter(loan => loan.status !== 'Closed' && loan.status !== 'Funded'));
      setPortfolio(allLoans.filter(loan => loan.status === 'Closed' || loan.status === 'Funded'));
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
          className={activeTab === 'leads' ? 'active' : ''}
          onClick={() => setActiveTab('leads')}
        >
          Leads ({leads.length})
        </button>
        <button
          className={activeTab === 'active-loans' ? 'active' : ''}
          onClick={() => setActiveTab('active-loans')}
        >
          Active Loans ({loans.length})
        </button>
        <button
          className={activeTab === 'portfolio' ? 'active' : ''}
          onClick={() => setActiveTab('portfolio')}
        >
          Portfolio ({portfolio.length})
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
        <button
          className={activeTab === 'configure' ? 'active' : ''}
          onClick={() => setActiveTab('configure')}
        >
          Configure
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

        {activeTab === 'leads' && (
          <LeadsTab leads={leads} navigate={navigate} onRefresh={fetchDashboardData} />
        )}

        {activeTab === 'active-loans' && (
          <ActiveLoansTab loans={loans} navigate={navigate} onRefresh={fetchDashboardData} />
        )}

        {activeTab === 'portfolio' && (
          <PortfolioTab portfolio={portfolio} navigate={navigate} onRefresh={fetchDashboardData} />
        )}

        {activeTab === 'theme-days' && (
          <ThemeDayManager />
        )}

        {activeTab === 'last-mile' && (
          <LastMileTracker />
        )}

        {activeTab === 'configure' && (
          <TaskWorkflowManager />
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
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState(null);

  // Weekly marketing theme schedule
  const weeklyThemes = [
    {
      day: 'Monday',
      dayNum: 1,
      name: 'Motivation Monday',
      icon: '💪',
      focus: 'inspiration',
      color: '#4CAF50',
      description: 'Start the week with motivational content about homeownership dreams',
      suggestedContent: [
        'Share homeownership success stories',
        'Post motivational quotes about achieving dreams',
        'Highlight first-time homebuyer victories'
      ]
    },
    {
      day: 'Tuesday',
      dayNum: 2,
      name: 'Tip Tuesday',
      icon: '💡',
      focus: 'education',
      color: '#2196F3',
      description: 'Educational tips about mortgages, credit, and homebuying',
      suggestedContent: [
        'Credit score improvement tips',
        'Down payment saving strategies',
        'First-time homebuyer program info'
      ]
    },
    {
      day: 'Wednesday',
      dayNum: 3,
      name: 'Wisdom Wednesday',
      icon: '🧠',
      focus: 'advice',
      color: '#9C27B0',
      description: 'Share expert advice and market insights',
      suggestedContent: [
        'Market update analysis',
        'Rate trend predictions',
        'Expert Q&A responses'
      ]
    },
    {
      day: 'Thursday',
      dayNum: 4,
      name: 'Throwback Thursday',
      icon: '📸',
      focus: 'testimonials',
      color: '#FF9800',
      description: 'Feature past client success stories and closings',
      suggestedContent: [
        'Client testimonial videos',
        'Before/after home photos',
        'Anniversary check-ins with past clients'
      ]
    },
    {
      day: 'Friday',
      dayNum: 5,
      name: 'Feature Friday',
      icon: '🏠',
      focus: 'listings',
      color: '#E91E63',
      description: 'Highlight featured properties and new listings',
      suggestedContent: [
        'New listing announcements',
        'Open house reminders',
        'Property highlight videos'
      ]
    },
    {
      day: 'Saturday',
      dayNum: 6,
      name: 'Saturday Showcase',
      icon: '🎬',
      focus: 'lifestyle',
      color: '#00BCD4',
      description: 'Showcase lifestyle content and community events',
      suggestedContent: [
        'Local community events',
        'Home improvement ideas',
        'Weekend open house tours'
      ]
    },
    {
      day: 'Sunday',
      dayNum: 0,
      name: 'Sunday Planning',
      icon: '📅',
      focus: 'planning',
      color: '#607D8B',
      description: 'Help clients plan their week ahead',
      suggestedContent: [
        'Week ahead preview',
        'Rate watch updates',
        'Schedule appointment reminders'
      ]
    }
  ];

  const today = new Date().getDay();
  const todayTheme = weeklyThemes.find(t => t.dayNum === today) || weeklyThemes[2];

  useEffect(() => {
    fetchThemeData();
  }, []);

  const fetchThemeData = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const messagesRes = await fetch(`${API_BASE}/api/v1/workflow/theme-days/scheduled?limit=20`, { headers });
      const messagesData = await messagesRes.json();
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
      alert('Messages scheduled for today\'s theme!');
    } catch (error) {
      console.error('Error scheduling messages:', error);
      alert('Failed to schedule messages');
    }
  };

  if (loading) return <p>Loading theme days...</p>;

  return (
    <div className="theme-day-section">
      <div className="section-header">
        <h3>Theme Days - Weekly Marketing Calendar</h3>
        <button onClick={scheduleMessages} className="btn-primary">
          Schedule Today's Messages
        </button>
      </div>

      {/* Today's Theme Highlight */}
      <div className="theme-today-highlight" style={{ marginBottom: '24px' }}>
        <h4>Today's Theme</h4>
        <div
          className="theme-card-large"
          style={{
            backgroundColor: todayTheme.color,
            color: 'white',
            padding: '20px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '16px'
          }}
        >
          <span style={{ fontSize: '48px' }}>{todayTheme.icon}</span>
          <div>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{todayTheme.name}</div>
            <div style={{ opacity: 0.9, marginTop: '4px' }}>{todayTheme.description}</div>
            <div style={{ marginTop: '12px', fontSize: '14px', opacity: 0.8 }}>
              Focus: {todayTheme.focus}
            </div>
          </div>
        </div>
      </div>

      {/* Weekly Theme Grid */}
      <h4 style={{ marginBottom: '16px' }}>Weekly Theme Schedule</h4>
      <div className="theme-week-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '12px',
        marginBottom: '24px'
      }}>
        {weeklyThemes.map(theme => (
          <div
            key={theme.day}
            onClick={() => setSelectedDay(selectedDay === theme.day ? null : theme.day)}
            style={{
              backgroundColor: theme.dayNum === today ? theme.color : '#f5f5f5',
              color: theme.dayNum === today ? 'white' : '#333',
              padding: '16px 12px',
              borderRadius: '8px',
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'transform 0.2s, box-shadow 0.2s',
              border: selectedDay === theme.day ? `3px solid ${theme.color}` : '3px solid transparent',
              boxShadow: theme.dayNum === today ? '0 4px 12px rgba(0,0,0,0.2)' : 'none'
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = theme.dayNum === today ? '0 4px 12px rgba(0,0,0,0.2)' : 'none';
            }}
          >
            <div style={{ fontSize: '24px', marginBottom: '8px' }}>{theme.icon}</div>
            <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '4px' }}>{theme.day}</div>
            <div style={{ fontSize: '11px', opacity: 0.8 }}>{theme.name.split(' ')[0]}</div>
          </div>
        ))}
      </div>

      {/* Selected Day Details */}
      {selectedDay && (
        <div style={{
          backgroundColor: '#f8f9fa',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '24px',
          borderLeft: `4px solid ${weeklyThemes.find(t => t.day === selectedDay)?.color}`
        }}>
          {(() => {
            const theme = weeklyThemes.find(t => t.day === selectedDay);
            return (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                  <span style={{ fontSize: '32px' }}>{theme.icon}</span>
                  <div>
                    <h4 style={{ margin: 0 }}>{theme.name}</h4>
                    <p style={{ margin: '4px 0 0 0', color: '#666' }}>{theme.description}</p>
                  </div>
                </div>
                <div>
                  <strong>Suggested Content Ideas:</strong>
                  <ul style={{ marginTop: '8px', paddingLeft: '20px' }}>
                    {theme.suggestedContent.map((content, idx) => (
                      <li key={idx} style={{ marginBottom: '4px' }}>{content}</li>
                    ))}
                  </ul>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* Scheduled Messages */}
      <h4>Scheduled Messages</h4>
      {messages.length === 0 ? (
        <p className="empty-state">No scheduled messages. Click "Schedule Today's Messages" to create theme-based outreach.</p>
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

// Leads Tab Component
function LeadsTab({ leads, navigate, onRefresh }) {
  const formatCurrency = (amount) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getStatusColor = (status) => {
    const colors = {
      'New': '#3b82f6',
      'Contacted': '#8b5cf6',
      'Qualified': '#22c55e',
      'Nurturing': '#f59e0b',
      'Lost': '#ef4444'
    };
    return colors[status] || '#6b7280';
  };

  return (
    <div className="leads-tab-section">
      <div className="section-header">
        <h3>Leads Pipeline</h3>
        <div className="header-actions">
          <button onClick={onRefresh} className="btn-refresh">Refresh</button>
          <button onClick={() => navigate('/leads')} className="btn-primary">View All Leads</button>
        </div>
      </div>
      {leads.length === 0 ? (
        <p className="empty-state">No leads found</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Source</th>
              <th>Status</th>
              <th>Est. Loan Amount</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {leads.slice(0, 20).map(lead => (
              <tr key={lead.id} className="clickable-row" onClick={() => navigate(`/leads/${lead.id}`)}>
                <td><strong>{lead.first_name} {lead.last_name}</strong></td>
                <td>{lead.email || '-'}</td>
                <td>{lead.phone || '-'}</td>
                <td>{lead.source || '-'}</td>
                <td>
                  <span
                    className="status-badge"
                    style={{ backgroundColor: getStatusColor(lead.status), color: 'white' }}
                  >
                    {lead.status || 'New'}
                  </span>
                </td>
                <td>{formatCurrency(lead.estimated_loan_amount)}</td>
                <td>
                  <button
                    onClick={(e) => { e.stopPropagation(); navigate(`/leads/${lead.id}`); }}
                    className="btn-view"
                  >
                    View
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

// Active Loans Tab Component
function ActiveLoansTab({ loans, navigate, onRefresh }) {
  const formatCurrency = (amount) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getStageColor = (stage) => {
    const colors = {
      'Pre-Qualification': '#3b82f6',
      'Application': '#8b5cf6',
      'Processing': '#f59e0b',
      'Underwriting': '#ec4899',
      'Conditional Approval': '#14b8a6',
      'Clear to Close': '#22c55e',
      'Closing': '#10b981'
    };
    return colors[stage] || '#6b7280';
  };

  return (
    <div className="active-loans-tab-section">
      <div className="section-header">
        <h3>Active Loans</h3>
        <div className="header-actions">
          <button onClick={onRefresh} className="btn-refresh">Refresh</button>
          <button onClick={() => navigate('/loans')} className="btn-primary">View All Loans</button>
        </div>
      </div>
      {loans.length === 0 ? (
        <p className="empty-state">No active loans</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Loan #</th>
              <th>Borrower</th>
              <th>Stage</th>
              <th>Loan Amount</th>
              <th>Rate</th>
              <th>Est. Close Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loans.slice(0, 20).map(loan => (
              <tr key={loan.id} className="clickable-row" onClick={() => navigate(`/loans/${loan.loan_number || loan.id}`)}>
                <td><strong>{loan.loan_number || `LOAN-${loan.id}`}</strong></td>
                <td>{loan.borrower_name || '-'}</td>
                <td>
                  <span
                    className="status-badge"
                    style={{ backgroundColor: getStageColor(loan.stage || loan.status), color: 'white' }}
                  >
                    {loan.stage || loan.status || 'Processing'}
                  </span>
                </td>
                <td>{formatCurrency(loan.loan_amount)}</td>
                <td>{loan.interest_rate ? `${loan.interest_rate}%` : '-'}</td>
                <td>{loan.estimated_close_date ? new Date(loan.estimated_close_date).toLocaleDateString() : '-'}</td>
                <td>
                  <button
                    onClick={(e) => { e.stopPropagation(); navigate(`/loans/${loan.loan_number || loan.id}`); }}
                    className="btn-view"
                  >
                    View
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

// Portfolio Tab Component
function PortfolioTab({ portfolio, navigate, onRefresh }) {
  const formatCurrency = (amount) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  // Calculate portfolio stats
  const totalVolume = portfolio.reduce((sum, loan) => sum + (loan.loan_amount || 0), 0);
  const avgLoanSize = portfolio.length > 0 ? totalVolume / portfolio.length : 0;

  return (
    <div className="portfolio-tab-section">
      <div className="section-header">
        <h3>Closed Loan Portfolio</h3>
        <div className="header-actions">
          <button onClick={onRefresh} className="btn-refresh">Refresh</button>
        </div>
      </div>

      {/* Portfolio Stats */}
      <div className="portfolio-stats" style={{ display: 'flex', gap: '20px', marginBottom: '24px' }}>
        <div className="stat-card" style={{ background: '#f0fdf4', padding: '16px 24px', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
          <div style={{ fontSize: '24px', fontWeight: '700', color: '#166534' }}>{portfolio.length}</div>
          <div style={{ fontSize: '13px', color: '#15803d' }}>Closed Loans</div>
        </div>
        <div className="stat-card" style={{ background: '#eff6ff', padding: '16px 24px', borderRadius: '8px', border: '1px solid #bfdbfe' }}>
          <div style={{ fontSize: '24px', fontWeight: '700', color: '#1e40af' }}>{formatCurrency(totalVolume)}</div>
          <div style={{ fontSize: '13px', color: '#1d4ed8' }}>Total Volume</div>
        </div>
        <div className="stat-card" style={{ background: '#faf5ff', padding: '16px 24px', borderRadius: '8px', border: '1px solid #e9d5ff' }}>
          <div style={{ fontSize: '24px', fontWeight: '700', color: '#6b21a8' }}>{formatCurrency(avgLoanSize)}</div>
          <div style={{ fontSize: '13px', color: '#7c3aed' }}>Avg. Loan Size</div>
        </div>
      </div>

      {portfolio.length === 0 ? (
        <p className="empty-state">No closed loans in portfolio</p>
      ) : (
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Loan #</th>
              <th>Borrower</th>
              <th>Loan Amount</th>
              <th>Rate</th>
              <th>Close Date</th>
              <th>Loan Type</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.slice(0, 20).map(loan => (
              <tr key={loan.id} className="clickable-row" onClick={() => navigate(`/loans/${loan.loan_number || loan.id}`)}>
                <td><strong>{loan.loan_number || `LOAN-${loan.id}`}</strong></td>
                <td>{loan.borrower_name || '-'}</td>
                <td>{formatCurrency(loan.loan_amount)}</td>
                <td>{loan.interest_rate ? `${loan.interest_rate}%` : '-'}</td>
                <td>{loan.close_date ? new Date(loan.close_date).toLocaleDateString() : '-'}</td>
                <td>{loan.loan_type || '-'}</td>
                <td>
                  <button
                    onClick={(e) => { e.stopPropagation(); navigate(`/loans/${loan.loan_number || loan.id}`); }}
                    className="btn-view"
                  >
                    View
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
