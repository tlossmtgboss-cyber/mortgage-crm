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

  // Auto-select first task when tasks load
  useEffect(() => {
    if (!loading && !selectedTask) {
      const allTasks = getAggregatedTasks();
      if (allTasks.length > 0) {
        setSelectedTask(allTasks[0]);
      }
    }
  }, [loading]);

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
          <div className="email-layout">
            {/* Task List (Left Side) */}
            <div className="task-inbox">
              <div className="inbox-header">
                <h3>Tasks</h3>
                <span className="task-count">{outstandingTasks.length}</span>
              </div>
              <div className="inbox-list">
                {outstandingTasks.map((task) => (
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
                {outstandingTasks.length === 0 && (
                  <div className="empty-inbox">
                    <p>No tasks</p>
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
                              <div key={idx} className="history-item">
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
        </div>
      )}

      {/* AI Task Engine Tab - Pending Your Approval */}
      {activeTab === 'ai-approval' && (
        <div className="tab-content">
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
