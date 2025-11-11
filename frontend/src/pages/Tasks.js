import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Tasks.css';

function Tasks() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [completedTasks, setCompletedTasks] = useState(new Set());
  const [activeTab, setActiveTab] = useState('outstanding');
  const [selectedTask, setSelectedTask] = useState(null);
  const [editingMessage, setEditingMessage] = useState(false);
  const [draftMessage, setDraftMessage] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [taskOwner, setTaskOwner] = useState('');
  const [commModal, setCommModal] = useState(null);

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

  // Auto-select first task when tasks load or tab changes
  useEffect(() => {
    if (!loading) {
      const tasksForTab = getTasksForTab();
      if (tasksForTab.length > 0) {
        setSelectedTask(tasksForTab[0]);
      } else {
        setSelectedTask(null);
      }
    }
  }, [loading, activeTab]);

  // Update draft message and owner when task changes
  useEffect(() => {
    if (selectedTask) {
      setDraftMessage(selectedTask.ai_message || '');
      setTaskOwner(selectedTask.owner || 'Loan Officer');
      setEditingMessage(false);
      setShowHistory(false);
    }
  }, [selectedTask]);

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

  // Get tasks filtered by active tab
  const getTasksForTab = () => {
    const allTasks = getAggregatedTasks();

    switch (activeTab) {
      case 'outstanding':
        return allTasks;
      case 'ai-approval':
        return allTasks.filter(task => task.source === 'AI Engine');
      case 'reconciliation':
        return allTasks.filter(task => task.source === 'Milestone Risk');
      case 'messages':
        return allTasks.filter(task => task.source === 'Messages');
      case 'mum':
        return allTasks.filter(task => task.source === 'Client for Life');
      default:
        return allTasks;
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

    // If the completed task is the selected one, select the next task
    if (selectedTask && selectedTask.id === taskId) {
      const allTasks = getAggregatedTasks();
      const currentIndex = allTasks.findIndex(t => t.id === taskId);
      const nextTask = allTasks[currentIndex + 1] || allTasks[currentIndex - 1] || null;
      setSelectedTask(nextTask);
    }
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

  const handleCommClick = (comm) => {
    // Generate detailed content based on type
    let detailedContent = null;

    if (comm.type === 'Email') {
      detailedContent = {
        type: 'Email',
        subject: comm.subject,
        thread: [
          {
            from: 'You',
            to: selectedTask?.borrower || 'Client',
            date: comm.date,
            body: comm.message
          },
          {
            from: selectedTask?.borrower || 'Client',
            to: 'You',
            date: comm.date,
            body: 'Thank you for reaching out! I appreciate the information. I have a few questions about the next steps...'
          }
        ]
      };
    } else if (comm.type === 'Phone') {
      detailedContent = {
        type: 'Phone',
        subject: comm.subject,
        duration: '30 minutes',
        date: comm.date,
        summary: comm.message,
        details: `Call started at 2:30 PM and lasted 30 minutes.

Key Discussion Points:
• Reviewed loan options and interest rates
• Discussed pre-qualification requirements
• Explained the application process timeline
• Answered questions about documentation needed
• Scheduled follow-up for next week

Next Steps:
• Client will gather employment verification documents
• Send detailed loan comparison email
• Schedule property search consultation

Client seemed very engaged and interested in moving forward with the pre-qualification process.`
      };
    } else if (comm.type === 'Text') {
      detailedContent = {
        type: 'Text',
        subject: comm.subject,
        messages: [
          { from: 'You', text: comm.message, time: '10:30 AM' },
          { from: selectedTask?.borrower || 'Client', text: 'Thanks for the reminder! I\'ll upload them today.', time: '10:45 AM' },
          { from: 'You', text: 'Perfect! Let me know if you need any help.', time: '10:46 AM' },
          { from: selectedTask?.borrower || 'Client', text: 'Will do 👍', time: '10:47 AM' }
        ]
      };
    }

    setCommModal(detailedContent);
  };

  if (loading) return <div className="loading">Loading tasks...</div>;

  const allTasks = getAggregatedTasks();
  const tabTasks = getTasksForTab();

  // Reusable Email Layout Component
  const TaskEmailLayout = ({ tasks, emptyMessage = "No tasks" }) => (
    <div className="email-layout">
      {/* Task List (Left Side) */}
      <div className="task-inbox">
        <div className="inbox-header">
          <h3>Tasks</h3>
          <span className="task-count">{tasks.length}</span>
        </div>
        <div className="inbox-list">
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`inbox-item ${selectedTask && selectedTask.id === task.id ? 'selected' : ''}`}
              onClick={() => setSelectedTask(task)}
            >
              <div className="inbox-item-header">
                <span className="source-icon">{task.sourceIcon}</span>
                <span className="task-title-compact">{task.title}</span>
              </div>
              <div className="inbox-item-meta">
                <span className="task-client-compact">{task.borrower || task.source}</span>
                <span
                  className="urgency-dot"
                  style={{ backgroundColor: getUrgencyColor(task.urgency) }}
                  title={task.urgency}
                ></span>
              </div>
              <div className="task-preview">{task.stage}</div>
            </div>
          ))}
          {tasks.length === 0 && (
            <div className="empty-inbox">
              <p>{emptyMessage}</p>
            </div>
          )}
        </div>
      </div>

      {/* Task Detail (Right Side) */}
      <div className="task-detail-pane">
        {selectedTask ? (
          <>
            <div className="detail-header">
              <div className="detail-title-section">
                <div className="detail-source">
                  <span className="source-icon-large">{selectedTask.sourceIcon}</span>
                  <span className="source-name">{selectedTask.source}</span>
                </div>
                <h2 className="detail-title">{selectedTask.title}</h2>
              </div>
            </div>

            <div className="detail-body">
              <div className="detail-info-grid">
                {selectedTask.borrower && (
                  <div className="detail-info-item">
                    <span className="detail-label">Client</span>
                    <span className="detail-value">{selectedTask.borrower}</span>
                  </div>
                )}
                <div className="detail-info-item">
                  <span className="detail-label">Stage</span>
                  <span className="detail-value">{selectedTask.stage}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">Priority</span>
                  <span
                    className="detail-urgency-badge"
                    style={{ backgroundColor: getUrgencyColor(selectedTask.urgency) }}
                  >
                    {selectedTask.urgency}
                  </span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">Source</span>
                  <span className="detail-value">{selectedTask.source}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">Owner</span>
                  <select
                    className="detail-owner-select"
                    value={taskOwner}
                    onChange={(e) => setTaskOwner(e.target.value)}
                  >
                    <option value="Loan Officer">Loan Officer</option>
                    <option value="Loan Processor">Loan Processor</option>
                    <option value="Executive Assistant">Executive Assistant</option>
                    <option value="Underwriter">Underwriter</option>
                    <option value="Closer">Closer</option>
                  </select>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">Date Created</span>
                  <span className="detail-value">
                    {selectedTask.date_created ? new Date(selectedTask.date_created).toLocaleString() : 'N/A'}
                  </span>
                </div>
                {selectedTask.preferred_contact_method && (
                  <div className="detail-info-item">
                    <span className="detail-label">Preferred Contact</span>
                    <span className="detail-contact-badge">
                      {selectedTask.preferred_contact_method === 'Email' && '📧'}
                      {selectedTask.preferred_contact_method === 'Phone' && '📞'}
                      {selectedTask.preferred_contact_method === 'Text' && '💬'}
                      {' '}
                      {selectedTask.preferred_contact_method}
                    </span>
                  </div>
                )}
              </div>

              {selectedTask.ai_message && (
                <div className="detail-ai-message-section">
                  <div className="ai-message-header">
                    <div className="ai-message-title-row">
                      <span className="ai-icon-large">🤖</span>
                      <span className="ai-message-title">AI-Drafted Message</span>
                    </div>
                    <button
                      className="btn-edit-message"
                      onClick={() => setEditingMessage(!editingMessage)}
                    >
                      {editingMessage ? '✓ Done Editing' : '✏️ Edit Message'}
                    </button>
                  </div>
                  <div className="ai-message-body">
                    {editingMessage ? (
                      <textarea
                        className="message-editor"
                        value={draftMessage}
                        onChange={(e) => setDraftMessage(e.target.value)}
                        rows={12}
                      />
                    ) : (
                      <div className="message-preview">
                        {draftMessage.split('\n').map((line, idx) => (
                          <p key={idx}>{line || '\u00A0'}</p>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedTask.action && (
                <div className="detail-action-section">
                  <h3>Recommended Action</h3>
                  <p>{selectedTask.action}</p>
                </div>
              )}

              {selectedTask.communication_history && selectedTask.communication_history.length > 0 && (
                <div className="communication-history-section">
                  <button
                    className="history-accordion-button"
                    onClick={() => setShowHistory(!showHistory)}
                  >
                    <span className="history-icon">📋</span>
                    <span className="history-title">Communication History ({selectedTask.communication_history.length})</span>
                    <span className="history-toggle">{showHistory ? '▼' : '▶'}</span>
                  </button>
                  {showHistory && (
                    <div className="history-content">
                      {selectedTask.communication_history.map((comm, idx) => (
                        <div key={idx} className="history-item clickable" onClick={() => handleCommClick(comm)}>
                          <div className="history-item-header">
                            <div className="history-type-date">
                              <span className="history-type-icon">
                                {comm.type === 'Email' && '📧'}
                                {comm.type === 'Phone' && '📞'}
                                {comm.type === 'Text' && '💬'}
                              </span>
                              <span className="history-type">{comm.type}</span>
                              <span className="history-date">{new Date(comm.date).toLocaleDateString()}</span>
                            </div>
                            <span className={`history-status ${comm.status.toLowerCase()}`}>
                              {comm.status}
                            </span>
                          </div>
                          <div className="history-item-body">
                            <div className="history-subject">{comm.subject}</div>
                            <div className="history-message">{comm.message}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="detail-footer">
              <button
                className="btn-detail-complete"
                onClick={() => handleComplete(selectedTask.id)}
              >
                ✓ Mark Complete
              </button>
              {selectedTask.ai_action && (
                <button
                  className="btn-detail-approve"
                  onClick={() => handleApproveAiTask(selectedTask.id)}
                >
                  Approve AI Action
                </button>
              )}
              {selectedTask.action && (
                <button className="btn-detail-action">
                  {selectedTask.action}
                </button>
              )}
              <button className="btn-detail-secondary">Snooze</button>
              <button className="btn-detail-secondary">Delegate</button>
            </div>
          </>
        ) : (
          <div className="detail-empty">
            <p>Select a task to view details</p>
          </div>
        )}
      </div>
    </div>
  );

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
          className={`tab-button ${activeTab === 'ai-approval' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai-approval')}
        >
          🤖 Pending Your Approval
          <span className="tab-badge">{aiTasks.pending.length + aiTasks.waiting.length}</span>
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
          <TaskEmailLayout tasks={tabTasks} emptyMessage="No outstanding tasks" />
        </div>
      )}

      {/* AI Task Engine Tab - Pending Your Approval */}
      {activeTab === 'ai-approval' && (
        <div className="tab-content">
          <TaskEmailLayout tasks={tabTasks} emptyMessage="No AI tasks pending approval" />
        </div>
      )}

      {/* Reconciliation Tab */}
      {activeTab === 'reconciliation' && (
        <div className="tab-content">
          <TaskEmailLayout tasks={tabTasks} emptyMessage="No reconciliation tasks" />
        </div>
      )}

      {/* Unified Messages Tab */}
      {activeTab === 'messages' && (
        <div className="tab-content">
          <TaskEmailLayout tasks={tabTasks} emptyMessage="No unread messages" />
        </div>
      )}

      {/* Client for Life Engine (MUM) Tab */}
      {activeTab === 'mum' && (
        <div className="tab-content">
          <TaskEmailLayout tasks={tabTasks} emptyMessage="No client retention actions needed" />
        </div>
      )}

      {/* Communication Detail Modal */}
      {commModal && (
        <div className="comm-modal-overlay" onClick={() => setCommModal(null)}>
          <div className="comm-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-comm-modal" onClick={() => setCommModal(null)}>×</button>

            <div className="comm-modal-header">
              <span className="comm-modal-icon">
                {commModal.type === 'Email' && '📧'}
                {commModal.type === 'Phone' && '📞'}
                {commModal.type === 'Text' && '💬'}
              </span>
              <h2>{commModal.subject}</h2>
            </div>

            <div className="comm-modal-body">
              {commModal.type === 'Email' && (
                <div className="email-thread">
                  {commModal.thread.map((email, idx) => (
                    <div key={idx} className="email-message">
                      <div className="email-message-header">
                        <div className="email-from-to">
                          <strong>From:</strong> {email.from}<br />
                          <strong>To:</strong> {email.to}
                        </div>
                        <div className="email-date">{new Date(email.date).toLocaleString()}</div>
                      </div>
                      <div className="email-message-body">{email.body}</div>
                    </div>
                  ))}
                </div>
              )}

              {commModal.type === 'Phone' && (
                <div className="phone-summary">
                  <div className="call-meta">
                    <div className="call-info-item">
                      <strong>Duration:</strong> {commModal.duration}
                    </div>
                    <div className="call-info-item">
                      <strong>Date:</strong> {new Date(commModal.date).toLocaleString()}
                    </div>
                  </div>
                  <div className="call-summary-section">
                    <h3>Summary</h3>
                    <p>{commModal.summary}</p>
                  </div>
                  <div className="call-details-section">
                    <h3>Call Notes</h3>
                    <pre className="call-notes">{commModal.details}</pre>
                  </div>
                </div>
              )}

              {commModal.type === 'Text' && (
                <div className="text-thread">
                  {commModal.messages.map((msg, idx) => (
                    <div key={idx} className={`text-message ${msg.from === 'You' ? 'sent' : 'received'}`}>
                      <div className="text-message-bubble">
                        <div className="text-message-sender">{msg.from}</div>
                        <div className="text-message-text">{msg.text}</div>
                        <div className="text-message-time">{msg.time}</div>
                      </div>
                    </div>
                  ))}
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
    ai_action: 'AI can send follow-up email — approve?',
    owner: 'Loan Officer',
    date_created: '2025-11-09T10:30:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Sarah,

I hope this message finds you well! I wanted to follow up on your pre-approval that we completed last week.

Your pre-approval is valid for 90 days, expiring on February 8, 2025. I wanted to check in and see if you've had a chance to view any properties or if you have any questions about next steps.

If you'd like to discuss your home search or need any assistance, I'm here to help. Feel free to reply to this email or give me a call at (555) 123-4567.

Looking forward to hearing from you!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and next steps' },
      { date: '2025-11-05', type: 'Phone', subject: 'Initial consultation', status: 'Completed', message: '30-minute call discussing loan options and requirements' },
      { date: '2025-11-03', type: 'Email', subject: 'Welcome email', status: 'Sent', message: 'Introduced myself and requested initial documents' }
    ]
  },
  {
    title: 'Upload missing documents',
    borrower: 'Mike Chen',
    stage: 'Processing',
    urgency: 'critical',
    ai_action: null,
    owner: 'Loan Processor',
    date_created: '2025-11-10T14:20:00',
    preferred_contact_method: 'Text',
    ai_message: null,
    communication_history: [
      { date: '2025-11-10', type: 'Text', subject: 'Document reminder', status: 'Sent', message: 'Reminded about missing W2s' },
      { date: '2025-11-08', type: 'Email', subject: 'Document checklist', status: 'Sent', message: 'Sent list of required documents' }
    ]
  },
  {
    title: 'Schedule appraisal',
    borrower: 'Emily Davis',
    stage: 'Application Complete',
    urgency: 'medium',
    ai_action: 'AI can schedule appraisal — approve?',
    owner: 'Loan Officer',
    date_created: '2025-11-10T09:15:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Emily,

Great news! Your loan application has been approved and we're ready to move forward with the appraisal.

I have availability with our preferred appraiser for the following dates:
- Thursday, November 14th at 10:00 AM
- Friday, November 15th at 2:00 PM
- Monday, November 18th at 9:00 AM

The appraisal typically takes 45-60 minutes. Please let me know which time works best for you, and I'll get it scheduled right away.

Thanks!
[Your Name]`,
    communication_history: [
      { date: '2025-11-09', type: 'Email', subject: 'Application approved', status: 'Sent', message: 'Congratulations email sent with next steps' },
      { date: '2025-11-07', type: 'Phone', subject: 'Application review', status: 'Completed', message: 'Reviewed application details' }
    ]
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
