import React, { useState, useEffect } from 'react';
import './Tasks.css';

function Tasks() {
  const [loading, setLoading] = useState(true);
  const [completedTasks, setCompletedTasks] = useState(new Set());

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
    type_icon: '📧',
    from: 'Sarah Johnson',
    preview: 'Quick question about my pre-approval...',
    ai_summary: 'Asking about pre-approval expiration date',
    read: false
  },
  {
    type_icon: '💬',
    from: 'Mike Chen',
    preview: 'Thanks for the update!',
    ai_summary: null,
    read: true
  }
];

export default Tasks;
