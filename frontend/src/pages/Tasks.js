import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Tasks.css';

function Tasks() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [completedTasks, setCompletedTasks] = useState(new Set());
  const [activeTab, setActiveTab] = useState('outstanding');

  // Dashboard data states
  const [prioritizedTasks, setPrioritizedTasks] = useState([]);
  const [loanIssues, setLoanIssues] = useState([]);
  const [aiTasks, setAiTasks] = useState({ pending: [], waiting: [] });
  const [mumAlerts, setMumAlerts] = useState([]);
  const [leadMetrics, setLeadMetrics] = useState({});
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    try {
      setLoading(true);

      // Load mock data (same as dashboard)
      setPrioritizedTasks(mockPrioritizedTasks());
      setLoanIssues(mockLoanIssues());
      setAiTasks(mockAiTasks());
      setMumAlerts(mockMumAlerts());
      setLeadMetrics(mockLeadMetrics());
      setMessages(mockMessages());

    } catch (error) {
      console.error('Failed to load tasks:', error);
      // Use mock data on error
      setPrioritizedTasks(mockPrioritizedTasks());
      setLoanIssues(mockLoanIssues());
      setAiTasks(mockAiTasks());
      setMumAlerts(mockMumAlerts());
      setLeadMetrics(mockLeadMetrics());
      setMessages(mockMessages());
    } finally {
      setLoading(false);
    }
  };

  // Aggregate all tasks from different containers (same logic as dashboard)
  const getAggregatedTasks = () => {
    const tasks = [];

    // Add manual prioritized tasks
    prioritizedTasks.forEach((task, idx) => {
      if (!completedTasks.has(`priority-${idx}`)) {
        tasks.push({
          id: `priority-${idx}`,
          ...task,
          source: 'Manual Priority',
          sourceIcon: '🎯'
        });
      }
    });

    // Add loan issues as critical tasks
    loanIssues.forEach((issue, idx) => {
      if (!completedTasks.has(`issue-${idx}`)) {
        tasks.push({
          id: `issue-${idx}`,
          title: issue.issue,
          borrower: issue.borrower,
          stage: 'Milestone Alert',
          urgency: 'critical',
          ai_action: null,
          source: 'Milestone Risk',
          sourceIcon: '🔥',
          action: issue.action
        });
      }
    });

    // Add AI pending tasks
    aiTasks.pending.forEach((task, idx) => {
      if (!completedTasks.has(`ai-pending-${idx}`)) {
        tasks.push({
          id: `ai-pending-${idx}`,
          title: task.task,
          borrower: '',
          stage: 'AI Suggested',
          urgency: 'medium',
          ai_action: `AI confidence: ${task.confidence}%`,
          source: 'AI Engine',
          sourceIcon: '🤖'
        });
      }
    });

    // Add AI waiting tasks
    aiTasks.waiting.forEach((task, idx) => {
      if (!completedTasks.has(`ai-waiting-${idx}`)) {
        tasks.push({
          id: `ai-waiting-${idx}`,
          title: task.task,
          borrower: '',
          stage: 'Needs Approval',
          urgency: 'low',
          ai_action: null,
          source: 'AI Engine',
          sourceIcon: '🤖'
        });
      }
    });

    // Add MUM alerts
    mumAlerts.forEach((alert, idx) => {
      if (!completedTasks.has(`mum-${idx}`)) {
        tasks.push({
          id: `mum-${idx}`,
          title: alert.title,
          borrower: alert.client,
          stage: 'Client Retention',
          urgency: 'medium',
          ai_action: null,
          source: 'Client for Life',
          sourceIcon: '💎',
          action: alert.action
        });
      }
    });

    // Add lead alerts as tasks
    if (leadMetrics.alerts) {
      leadMetrics.alerts.forEach((alert, idx) => {
        if (alert && !completedTasks.has(`lead-${idx}`)) {
          tasks.push({
            id: `lead-${idx}`,
            title: alert,
            borrower: '',
            stage: 'Leads',
            urgency: 'high',
            ai_action: null,
            source: 'Leads Engine',
            sourceIcon: '🚀'
          });
        }
      });
    }

    // Add unread messages as tasks
    messages.filter(m => !m.read).forEach((msg, idx) => {
      if (!completedTasks.has(`message-${idx}`)) {
        tasks.push({
          id: `message-${idx}`,
          title: `Message from ${msg.from}`,
          borrower: msg.from,
          stage: 'Communication',
          urgency: 'medium',
          ai_action: msg.ai_summary ? `AI Summary: ${msg.ai_summary}` : null,
          source: 'Messages',
          sourceIcon: '💬'
        });
      }
    });

    return tasks;
  };

  const handleComplete = (taskId) => {
    setCompletedTasks(prev => {
      const newCompleted = new Set(prev);
      newCompleted.add(taskId);
      return newCompleted;
    });
  };

  const handleApproveAiTask = async (taskId) => {
    // TODO: Implement AI task approval
    alert(`Approved task ${taskId}`);
  };

  const getUrgencyColor = (urgency) => {
    const colors = {
      critical: '#dc2626',
      high: '#f59e0b',
      medium: '#3b82f6',
      low: '#6b7280'
    };
    return colors[urgency] || '#6b7280';
  };

  if (loading) return <div className="loading">Loading tasks...</div>;

  const allTasks = getAggregatedTasks();
  const outstandingTasks = allTasks;
  const completedTasksList = Array.from(completedTasks).map(id => {
    // Return placeholder completed task data
    return { id, title: 'Completed task', completed: true };
  });

  return (
    <div className="tasks-page">
      <div className="page-header">
        <h1>Tasks</h1>
        <p>{allTasks.length} total tasks</p>
      </div>

      {/* Tab Navigation */}
      <div className="task-tabs">
        <button
          className={`tab-button ${activeTab === 'outstanding' ? 'active' : ''}`}
          onClick={() => setActiveTab('outstanding')}
        >
          Outstanding Tasks
          <span className="tab-badge">{allTasks.length}</span>
        </button>
        <button
          className={`tab-button ${activeTab === 'reconciliation' ? 'active' : ''}`}
          onClick={() => setActiveTab('reconciliation')}
        >
          🔄 Reconciliation
        </button>
        <button
          className={`tab-button ${activeTab === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveTab('messages')}
        >
          📬 Unified Messages
          <span className="tab-badge">{messages.filter(m => !m.read).length}</span>
        </button>
        <button
          className={`tab-button ${activeTab === 'mum' ? 'active' : ''}`}
          onClick={() => setActiveTab('mum')}
        >
          ♻️ Client for Life Engine (MUM)
          <span className="tab-badge">{mumAlerts.length}</span>
        </button>
      </div>

      {/* Outstanding Tasks Tab */}
      {activeTab === 'outstanding' && (
        <div className="tab-content">
          <div className="tasks-sections">
        <div className="task-section">
          <div className="section-header">
            <h2>Outstanding Tasks</h2>
            <span className="task-count">{outstandingTasks.length}</span>
          </div>
          <div className="task-list">
            {outstandingTasks.map((task) => (
              <div key={task.id} className="task-item">
                <div className="task-source-badge">
                  <span className="source-icon">{task.sourceIcon}</span>
                  <span className="source-text">{task.source}</span>
                </div>
                <div className="task-main">
                  <div className="task-info">
                    <h4 className="task-title">{task.title}</h4>
                    {task.borrower && (
                      <p className="task-client">Client: {task.borrower}</p>
                    )}
                    <div className="task-meta">
                      <span className="task-stage">{task.stage}</span>
                      <span
                        className="urgency-badge"
                        style={{ backgroundColor: getUrgencyColor(task.urgency) }}
                      >
                        {task.urgency}
                      </span>
                    </div>
                  </div>
                </div>
                {task.ai_action && (
                  <div className="ai-suggestion">
                    <span className="ai-icon">🤖</span>
                    <span className="ai-text">{task.ai_action}</span>
                    <button className="btn-approve-sm">Approve</button>
                  </div>
                )}
                <div className="task-actions">
                  <button
                    className="btn-complete"
                    onClick={() => handleComplete(task.id)}
                  >
                    ✓ Complete
                  </button>
                  {task.action && (
                    <button className="btn-task-action">{task.action}</button>
                  )}
                </div>
              </div>
            ))}
            {outstandingTasks.length === 0 && (
              <div className="empty-state">
                <p>No outstanding tasks</p>
              </div>
            )}
          </div>
        </div>

        <div className="task-section">
          <div className="section-header">
            <h2>Completed Tasks</h2>
            <span className="task-count">{completedTasksList.length}</span>
          </div>
          <div className="task-list">
            {completedTasksList.map((task) => (
              <div key={task.id} className="task-item completed">
                <div className="task-main">
                  <h4>{task.title}</h4>
                  <div className="task-meta">
                    <span className="completed-date">
                      Completed: {new Date().toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>
            ))}
            {completedTasksList.length === 0 && (
              <div className="empty-state">
                <p>No completed tasks</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* AI TASK ENGINE SECTION */}
      <div className="ai-engine-section">
        <h2 className="section-title">🤖 AI Task Engine</h2>
        <div className="ai-engine-grid">
          <div className="ai-engine-column">
            <div className="ai-column-header">
              <h3>Pending Your Approval</h3>
              <span className="ai-count-badge">{aiTasks.pending.length}</span>
            </div>
            <div className="ai-tasks-list">
              {aiTasks.pending.filter(task => task && task.task).map((task, idx) => (
                <div key={idx} className="ai-task-card">
                  <div className="ai-task-header">
                    <span className="task-name">{task.task}</span>
                    <span className="confidence-badge">{task.confidence}% confident</span>
                  </div>
                  <div className="ai-task-description">{task.what_ai_did}</div>
                  <div className="ai-task-actions">
                    <button className="btn-approve" onClick={() => handleApproveAiTask(task.id)}>
                      ✓ Approve
                    </button>
                    <button className="btn-fix">Fix</button>
                    <button className="btn-coach" onClick={() => navigate('/coach')}>Nick Saban Performance Coach</button>
                  </div>
                </div>
              ))}
              {aiTasks.pending.length === 0 && (
                <div className="empty-state">
                  <p>No tasks pending approval</p>
                </div>
              )}
            </div>
          </div>

          <div className="ai-engine-column">
            <div className="ai-column-header">
              <h3>Waiting for Your Input</h3>
              <span className="ai-count-badge">{aiTasks.waiting.length}</span>
            </div>
            <div className="ai-tasks-list">
              {aiTasks.waiting.filter(task => task && task.task).map((task, idx) => (
                <div key={idx} className="ai-task-simple">
                  <span className="task-text">{task.task}</span>
                  <div className="quick-actions">
                    <button className="btn-quick-approve" title="Approve">✓</button>
                    <button className="btn-quick-deny" title="Deny">✗</button>
                    <button className="btn-quick-delegate" title="Delegate">→</button>
                  </div>
                </div>
              ))}
              {aiTasks.waiting.length === 0 && (
                <div className="empty-state">
                  <p>No tasks waiting for input</p>
                </div>
              )}
            </div>
          </div>
        </div>
          </div>
        </div>
      )}

      {/* Reconciliation Tab */}
      {activeTab === 'reconciliation' && (
        <div className="tab-content">
          <div className="reconciliation-content">
            <div className="reconciliation-section">
              <h3>Reconciliation Center</h3>
              <p className="section-description">
                Reconcile your loan pipeline data, verify accuracy, and resolve discrepancies.
              </p>
              <div className="reconciliation-actions">
                <button className="btn-reconcile">
                  Run Monthly Reconciliation
                </button>
                <button className="btn-reconcile">
                  View Past Reconciliations
                </button>
                <button className="btn-reconcile">
                  Export Reconciliation Report
                </button>
              </div>
              <div className="reconciliation-placeholder">
                <p>Reconciliation features coming soon...</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Unified Messages Tab */}
      {activeTab === 'messages' && (
        <div className="tab-content">
          <div className="unified-messages-section">
            <div className="messages-header">
              <h2>📬 Unified Messages</h2>
              <span className="unread-count">{messages.filter(m => !m.read).length} unread</span>
            </div>
            <div className="messages-list">
              {messages.filter(msg => msg && msg.from).map((msg, idx) => (
                <div key={msg.id || idx} className={`message-item ${!msg.read ? 'unread' : ''} ${msg.requires_response ? 'needs-response' : ''}`}>
                  <div className="message-left">
                    <div className="message-type-icon">{msg.type_icon}</div>
                    <div className="message-content">
                      <div className="message-header">
                        <div className="message-from-line">
                          <span className="message-from">{msg.from}</span>
                          <span className="message-client-type">{msg.client_type}</span>
                        </div>
                        <div className="message-meta">
                          <span className="message-source">{msg.source}</span>
                          <span className="message-timestamp">{msg.timestamp}</span>
                        </div>
                      </div>
                      <div className="message-preview">{msg.preview}</div>
                      {msg.ai_summary && (
                        <div className="ai-summary">
                          <span className="ai-icon">🤖</span>
                          <span className="ai-text">{msg.ai_summary}</span>
                        </div>
                      )}
                      {msg.task_created && (
                        <div className="task-status">
                          <span className="task-badge">✓ Task Created: {msg.task_id}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="message-actions">
                    {msg.type === 'voicemail' && (
                      <button className="btn-icon-sm" title="Play Voicemail">
                        <span className="voicemail-duration">{msg.duration}</span> ▶️
                      </button>
                    )}
                    {msg.type === 'email' && (
                      <button className="btn-icon-sm" title="View in Outlook">📧</button>
                    )}
                    {msg.type === 'text' && (
                      <button className="btn-icon-sm" title="View in Teams">💬</button>
                    )}
                    <button className="btn-icon-sm btn-reply" title="Reply">↩️</button>
                    <button className="btn-icon-sm" title="AI Suggested Response">🤖</button>
                  </div>
                </div>
              ))}
            </div>
            <button className="btn-view-all" onClick={() => navigate('/assistant')}>
              View All Messages →
            </button>
          </div>
        </div>
      )}

      {/* Client for Life Engine (MUM) Tab */}
      {activeTab === 'mum' && (
        <div className="tab-content">
          <div className="mum-section">
            <div className="mum-header">
              <h2>♻️ Client for Life Engine (MUM)</h2>
              <span className="actions-badge">{mumAlerts.length} actions</span>
            </div>
            <div className="mum-alerts-list">
              {mumAlerts.map((alert, idx) => (
                <div key={idx} className="mum-alert-card">
                  <div className="mum-alert-icon">{alert.icon}</div>
                  <div className="mum-alert-content">
                    <h4 className="mum-alert-title">{alert.title}</h4>
                    <p className="mum-alert-client">{alert.client}</p>
                  </div>
                  <div className="mum-alert-action">
                    <button className="btn-mum-action">{alert.action}</button>
                  </div>
                </div>
              ))}
              {mumAlerts.length === 0 && (
                <div className="empty-state">
                  <p>No client retention actions needed</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Mock data functions (same as Dashboard)
const mockPrioritizedTasks = () => [
  {
    title: 'Follow up on pre-approval',
    borrower: 'Sarah Johnson',
    stage: 'Pre-Approved',
    urgency: 'high',
    ai_action: 'AI can send follow-up email — approve?'
  },
  {
    title: 'Upload missing documents',
    borrower: 'Mike Chen',
    stage: 'Processing',
    urgency: 'critical',
    ai_action: null
  },
  {
    title: 'Schedule appraisal',
    borrower: 'Emily Davis',
    stage: 'Application Complete',
    urgency: 'medium',
    ai_action: 'AI can schedule appraisal — approve?'
  }
];

const mockLoanIssues = () => [
  {
    borrower: 'John Smith',
    issue: 'Appraisal delay',
    time_remaining: '2 days',
    time_color: '#f59e0b',
    action: 'Follow up'
  },
  {
    borrower: 'Jane Doe',
    issue: 'Insurance missing',
    time_remaining: '5 hours',
    time_color: '#dc2626',
    action: 'Send reminder'
  }
];

const mockAiTasks = () => ({
  pending: [
    {
      id: 1,
      task: 'Draft follow-up email to Sarah Johnson',
      confidence: 94,
      what_ai_did: 'Composed personalized email based on last conversation'
    },
    {
      id: 2,
      task: 'Schedule appointment with Mike Chen',
      confidence: 87,
      what_ai_did: 'Found mutual availability on calendar for Thursday 2pm'
    }
  ],
  waiting: [
    { task: 'Approve rate lock for Emily Davis file' },
    { task: 'Review updated credit report for John Smith' }
  ]
});

const mockMumAlerts = () => [
  { icon: '📅', title: 'Annual review due', client: 'Tom Wilson', action: 'Schedule' },
  { icon: '📉', title: 'Rate drop opportunity', client: 'Lisa Brown', action: 'Send alert' },
  { icon: '🎂', title: 'Home anniversary', client: 'Mark Taylor', action: 'Send card' }
];

const mockLeadMetrics = () => ({
  new_today: 3,
  avg_contact_time: 1.2,
  conversion_rate: 23,
  hot_leads: 5,
  alerts: [
    '3 leads haven\'t been contacted in 24 hours.',
    '2 leads showed high buying intent in email.',
    'A referral partner sent you a lead and you haven\'t responded.'
  ]
});

const mockMessages = () => [
  {
    id: 1,
    type: 'email',
    type_icon: '📧',
    from: 'Sarah Johnson',
    client_type: 'Pre-Approved',
    source: 'Outlook',
    timestamp: '2 hours ago',
    preview: 'Quick question about my pre-approval...',
    ai_summary: 'Asking about pre-approval expiration date',
    read: false,
    requires_response: true
  },
  {
    id: 2,
    type: 'text',
    type_icon: '💬',
    from: 'Mike Chen',
    client_type: 'Processing',
    source: 'Teams',
    timestamp: '5 hours ago',
    preview: 'Thanks for the update!',
    ai_summary: null,
    read: true,
    requires_response: false
  },
  {
    id: 3,
    type: 'voicemail',
    type_icon: '🎙️',
    from: 'Emily Davis',
    client_type: 'Application Started',
    source: 'Voicemail',
    timestamp: '1 day ago',
    preview: 'Left voicemail about appraisal timing',
    ai_summary: 'Wants to know when appraisal will be scheduled',
    duration: '1:23',
    read: false,
    requires_response: true
  },
  {
    id: 4,
    type: 'email',
    type_icon: '📧',
    from: 'John Smith',
    client_type: 'Prospect',
    source: 'Outlook',
    timestamp: '3 days ago',
    preview: 'Following up on our conversation...',
    ai_summary: 'Requesting rate quote for $450k loan',
    read: true,
    requires_response: false,
    task_created: true,
    task_id: 'TASK-123'
  }
];

export default Tasks;
