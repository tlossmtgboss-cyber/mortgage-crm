import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
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
  const [communicationMethod, setCommunicationMethod] = useState('Email');
  const [aiInstructions, setAiInstructions] = useState('');
  const [showDelegateModal, setShowDelegateModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [snoozedTasks, setSnoozedTasks] = useState(new Set());
  const [teamMembers, setTeamMembers] = useState([]);

  // Dashboard data states
  const [prioritizedTasks, setPrioritizedTasks] = useState([]);
  const [loanIssues, setLoanIssues] = useState([]);
  const [aiTasks, setAiTasks] = useState({ pending: [], waiting: [] });
  const [mumAlerts, setMumAlerts] = useState([]);
  const [leadMetrics, setLeadMetrics] = useState({});
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    loadTasks();
    loadTeamMembers();
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
      setCommunicationMethod(selectedTask.preferred_contact_method || 'Email');
      setAiInstructions('');
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

  const loadTeamMembers = async () => {
    try {
      const data = await teamAPI.getMembers();
      setTeamMembers(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load team members:', error);
      setTeamMembers([]);
    }
  };

  // Handler functions
  const handleSend = (taskId) => {
    // TODO: Implement actual send logic based on communicationMethod
    alert(`Task sent via ${communicationMethod}!`);
    handleComplete(taskId);
  };

  const handleDelete = (taskId) => {
    setShowDeleteConfirm(false);
    setCompletedTasks(prev => {
      const newCompleted = new Set(prev);
      newCompleted.add(taskId);
      return newCompleted;
    });

    // Select next task
    if (selectedTask && selectedTask.id === taskId) {
      const allTasks = getAggregatedTasks();
      const currentIndex = allTasks.findIndex(t => t.id === taskId);
      const nextTask = allTasks[currentIndex + 1] || allTasks[currentIndex - 1] || null;
      setSelectedTask(nextTask);
    }
  };

  const handleSnooze = (taskId) => {
    setSnoozedTasks(prev => {
      const newSnoozed = new Set(prev);
      newSnoozed.add(taskId);
      return newSnoozed;
    });

    // Remove from snoozed after 24 hours
    setTimeout(() => {
      setSnoozedTasks(prev => {
        const newSnoozed = new Set(prev);
        newSnoozed.delete(taskId);
        return newSnoozed;
      });
    }, 24 * 60 * 60 * 1000); // 24 hours

    // Select next task
    if (selectedTask && selectedTask.id === taskId) {
      const allTasks = getAggregatedTasks();
      const currentIndex = allTasks.findIndex(t => t.id === taskId);
      const nextTask = allTasks[currentIndex + 1] || allTasks[currentIndex - 1] || null;
      setSelectedTask(nextTask);
    }
  };

  const handleDelegate = (teamMember) => {
    alert(`Task delegated to ${teamMember}`);
    setShowDelegateModal(false);
    handleComplete(selectedTask.id);
  };

  // Get tasks filtered by active tab
  const getTasksForTab = () => {
    const allTasks = getAggregatedTasks();

    switch (activeTab) {
      case 'outstanding':
        return allTasks.filter(task => !snoozedTasks.has(task.id));
      case 'ai-approval':
        return allTasks.filter(task => task.source === 'AI Engine' && !snoozedTasks.has(task.id));
      case 'reconciliation':
        return allTasks.filter(task => task.source === 'Milestone Risk' && !snoozedTasks.has(task.id));
      case 'messages':
        return allTasks.filter(task => task.source === 'Messages' && !snoozedTasks.has(task.id));
      case 'mum':
        return allTasks.filter(task => task.source === 'Client for Life' && !snoozedTasks.has(task.id));
      default:
        return allTasks.filter(task => !snoozedTasks.has(task.id));
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
          ...issue,
          title: issue.issue,
          stage: 'Milestone Alert',
          urgency: 'critical',
          source: 'Milestone Risk',
          sourceIcon: '🔥'
        });
      }
    });

    // Add AI pending tasks
    aiTasks.pending.forEach((task, idx) => {
      if (!completedTasks.has(`ai-pending-${idx}`)) {
        tasks.push({
          id: `ai-pending-${idx}`,
          ...task,
          title: task.task,
          stage: 'AI Suggested',
          urgency: task.urgency || 'medium',
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
          ...task,
          title: task.task,
          stage: 'Needs Approval',
          urgency: task.urgency || 'low',
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
          ...alert,
          borrower: alert.client,
          stage: 'Client Retention',
          urgency: alert.urgency || 'medium',
          source: 'Client for Life',
          sourceIcon: '💎'
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
          ...msg,
          title: `Message from ${msg.from}`,
          borrower: msg.from,
          stage: 'Communication',
          urgency: msg.urgency || 'medium',
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
                  <span className="detail-value">{taskOwner}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">Date Created</span>
                  <span className="detail-value">
                    {selectedTask.date_created ? new Date(selectedTask.date_created).toLocaleString() : 'N/A'}
                  </span>
                </div>
                <div className="detail-info-item detail-comm-method-item">
                  <span className="detail-label">Send Via</span>
                  <div className="comm-method-selector">
                    <button
                      className={`comm-method-btn ${communicationMethod === 'Email' ? 'active' : ''}`}
                      onClick={() => setCommunicationMethod('Email')}
                    >
                      📧 Email
                    </button>
                    <button
                      className={`comm-method-btn ${communicationMethod === 'Text' ? 'active' : ''}`}
                      onClick={() => setCommunicationMethod('Text')}
                    >
                      💬 Text
                    </button>
                    <button
                      className={`comm-method-btn ${communicationMethod === 'Phone' ? 'active' : ''}`}
                      onClick={() => setCommunicationMethod('Phone')}
                    >
                      📞 Phone
                    </button>
                    <button
                      className={`comm-method-btn ${communicationMethod === 'Voicemail' ? 'active' : ''}`}
                      onClick={() => setCommunicationMethod('Voicemail')}
                    >
                      🎙️ Voicemail
                    </button>
                  </div>
                </div>
              </div>

              {selectedTask.missing_documents && selectedTask.missing_documents.length > 0 && (
                <div className="detail-missing-docs-section">
                  <div className="missing-docs-header">
                    <span className="docs-icon">📄</span>
                    <h3>Missing Documents Detected by AI</h3>
                  </div>
                  <div className="missing-docs-list">
                    {selectedTask.missing_documents.map((doc, idx) => (
                      <div key={idx} className="missing-doc-item">
                        <span className="doc-bullet">•</span>
                        <span className="doc-name">{doc}</span>
                      </div>
                    ))}
                  </div>
                  <div className="missing-docs-note">
                    <span className="ai-badge">🤖 AI Analysis</span>
                    <span className="analysis-text">Detected from email thread analysis</span>
                  </div>
                </div>
              )}

              {selectedTask.ai_message && (
                <>
                  {/* AI Training Instructions Section */}
                  <div className="detail-ai-training-section">
                    <div className="ai-training-header">
                      <span className="training-icon">🎓</span>
                      <span className="training-title">Train AI (Optional)</span>
                    </div>
                    <textarea
                      className="ai-training-input"
                      placeholder="Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                      value={aiInstructions}
                      onChange={(e) => setAiInstructions(e.target.value)}
                      rows={3}
                    />
                  </div>

                  {/* AI-Drafted Message Section */}
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
                </>
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
                className="btn-detail-send"
                onClick={() => handleSend(selectedTask.id)}
              >
                📤 Send via {communicationMethod}
              </button>
              {selectedTask.ai_action && (
                <button
                  className="btn-detail-approve"
                  onClick={() => handleApproveAiTask(selectedTask.id)}
                >
                  Approve AI Action
                </button>
              )}
              <button
                className="btn-detail-secondary"
                onClick={() => handleSnooze(selectedTask.id)}
              >
                💤 Snooze
              </button>
              <button
                className="btn-detail-secondary"
                onClick={() => setShowDelegateModal(true)}
              >
                👥 Delegate
              </button>
              <button
                className="btn-detail-danger"
                onClick={() => setShowDeleteConfirm(true)}
              >
                🗑️ Delete
              </button>
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

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Delete Task</h2>
            <p>Are you sure you want to delete this task? This action cannot be undone.</p>
            <div className="modal-buttons">
              <button
                className="btn-modal-danger"
                onClick={() => handleDelete(selectedTask.id)}
              >
                Yes, Delete
              </button>
              <button
                className="btn-modal-cancel"
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delegate Modal */}
      {showDelegateModal && (
        <div className="modal-overlay" onClick={() => setShowDelegateModal(false)}>
          <div className="modal-content delegate-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Delegate Task</h2>
            <p>Select a team member to delegate this task to:</p>
            <div className="team-member-list">
              {teamMembers.length > 0 ? (
                teamMembers.map((member) => (
                  <button
                    key={member.id}
                    className="team-member-btn"
                    onClick={() => handleDelegate(`${member.first_name} ${member.last_name}`)}
                  >
                    👤 {member.first_name} {member.last_name}
                    {member.role && <span style={{ fontSize: '12px', color: '#666', marginLeft: '8px' }}>({member.role})</span>}
                  </button>
                ))
              ) : (
                <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                  <p>No team members available.</p>
                  <p style={{ fontSize: '14px', marginTop: '8px' }}>
                    Add team members in Settings → Team Members
                  </p>
                </div>
              )}
            </div>
            <button
              className="btn-modal-cancel"
              onClick={() => setShowDelegateModal(false)}
            >
              Cancel
            </button>
          </div>
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
    ai_action: 'AI detected missing documents from email analysis',
    owner: 'Loan Processor',
    date_created: '2025-11-10T14:20:00',
    preferred_contact_method: 'Text',
    missing_documents: [
      '2024 W-2 forms (both employers)',
      'Last 2 pay stubs from current job',
      '2 months recent bank statements (checking account)'
    ],
    ai_message: `Hi Mike,

Hope you're doing well! I've been reviewing your loan file and noticed we're still missing a few documents to move forward with processing:

📄 Still Needed:
• 2024 W-2 forms (both employers)
• Last 2 pay stubs from current job
• 2 months recent bank statements (checking)

Can you upload these through the portal? Or you can reply with photos and I'll handle the upload for you.

Once we have these, we can move to the next stage! Let me know if you have any questions.

Thanks!
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-10', type: 'Email', subject: 'Re: Document checklist', status: 'Received', message: 'Mike replied: "I uploaded the tax returns and my W-2 from my main job. Will send the other W-2 tomorrow."' },
      { date: '2025-11-09', type: 'Text', subject: 'Quick check-in', status: 'Sent', message: 'Asked Mike about document upload progress' },
      { date: '2025-11-08', type: 'Email', subject: 'Document checklist', status: 'Sent', message: 'Sent comprehensive list of all required documents for loan processing' },
      { date: '2025-11-07', type: 'Email', subject: 'Welcome to processing', status: 'Sent', message: 'Introduced loan processing phase and set expectations' }
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
    action: 'Follow up with appraiser',
    owner: 'Loan Officer',
    stage: 'Underwriting',
    urgency: 'high',
    date_created: '2025-11-12T09:15:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi John,

I wanted to give you a quick update on your loan application. We're currently waiting on the appraisal, which has been slightly delayed by 2 days.

I've reached out to the appraiser this morning and they confirmed they'll complete the inspection by end of day Thursday. Once we receive the appraisal report, we can move forward to final underwriting approval.

I know waiting can be frustrating, but we're doing everything we can to keep things moving quickly. I'll keep you posted on any updates.

If you have any questions in the meantime, please don't hesitate to reach out!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-12', type: 'Phone', subject: 'Appraisal status update', status: 'Completed', message: 'Called appraiser to check on timeline' },
      { date: '2025-11-10', type: 'Email', subject: 'Appraisal scheduled', status: 'Sent', message: 'Sent confirmation of appraisal appointment' },
      { date: '2025-11-08', type: 'Email', subject: 'Moving to underwriting', status: 'Sent', message: 'Notified client that file is being sent to underwriting' }
    ]
  },
  {
    borrower: 'Jane Doe',
    issue: 'Insurance missing',
    time_remaining: '5 hours',
    time_color: '#dc2626',
    action: 'Send urgent reminder',
    owner: 'Loan Processor',
    stage: 'Clear to Close',
    urgency: 'critical',
    date_created: '2025-11-13T08:00:00',
    preferred_contact_method: 'Text',
    ai_message: `Hi Jane,

URGENT: We need your homeowner's insurance binder by 5 PM today to close on schedule tomorrow.

📋 What we need:
• Homeowner's insurance binder
• Proof of paid first year premium
• Lender named as mortgagee

Your insurance agent can email this directly to us at docs@mortgagecrm.com or you can upload it to the portal.

This is the last item we need before closing! Please let me know if you need help contacting your insurance agent.

Thanks!
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-13', type: 'Text', subject: 'Insurance reminder', status: 'Sent', message: 'Sent text reminder about insurance deadline' },
      { date: '2025-11-12', type: 'Email', subject: 'Closing checklist', status: 'Sent', message: 'Sent final items needed for closing' },
      { date: '2025-11-11', type: 'Phone', subject: 'Closing date confirmed', status: 'Completed', message: '15-minute call confirming closing details' }
    ]
  }
];

const mockAiTasks = () => ({
  pending: [
    {
      id: 1,
      task: 'Draft follow-up email to Sarah Johnson',
      borrower: 'Sarah Johnson',
      confidence: 94,
      what_ai_did: 'Composed personalized email based on last conversation',
      owner: 'Loan Officer',
      stage: 'Pre-Approved',
      urgency: 'medium',
      date_created: '2025-11-13T11:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi Sarah,

I hope you're doing well! I wanted to reach out and see how your property search is going.

Your pre-approval is still active for another 75 days. If you've found a property you're interested in or have any questions about the home buying process, I'm here to help.

Also, if your financial situation has changed at all (new income, credit changes, etc.), please let me know so we can make sure your pre-approval stays accurate.

Looking forward to helping you find your dream home!

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and congratulations' },
        { date: '2025-11-05', type: 'Phone', subject: 'Pre-approval interview', status: 'Completed', message: 'Discussed loan options and gathered documentation' }
      ]
    },
    {
      id: 2,
      task: 'Schedule appointment with Mike Chen',
      borrower: 'Mike Chen',
      confidence: 87,
      what_ai_did: 'Found mutual availability on calendar for Thursday 2pm',
      owner: 'Loan Officer',
      stage: 'Processing',
      urgency: 'medium',
      date_created: '2025-11-13T13:30:00',
      preferred_contact_method: 'Phone',
      ai_message: `Hi Mike,

I wanted to schedule a quick check-in call to review your loan application progress and answer any questions you might have.

I have the following times available this week:
• Thursday, Nov 14 at 2:00 PM
• Thursday, Nov 14 at 4:00 PM
• Friday, Nov 15 at 10:00 AM

The call should only take about 15-20 minutes. We'll review your current status, discuss next steps, and I can answer any questions.

Which time works best for you?

Thanks!
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-10', type: 'Email', subject: 'Document status update', status: 'Sent', message: 'Confirmed receipt of W-2s and requested bank statements' },
        { date: '2025-11-08', type: 'Text', subject: 'Quick question', status: 'Received', message: 'Mike asked about processing timeline' }
      ]
    }
  ],
  waiting: [
    {
      task: 'Approve rate lock for Emily Davis file',
      borrower: 'Emily Davis',
      owner: 'Loan Officer',
      stage: 'Application Complete',
      urgency: 'high',
      date_created: '2025-11-12T16:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi Emily,

Good news! Interest rates have dropped slightly since we started your application.

Current Rate Options:
• 30-year fixed: 6.875% (down from 7.00%)
• 15-year fixed: 6.125% (down from 6.25%)

I recommend locking your rate today to secure this lower rate. The lock is good for 45 days, which gives us plenty of time to close.

Would you like me to proceed with the rate lock? Please confirm and I'll lock it in right away.

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-11', type: 'Email', subject: 'Application received', status: 'Sent', message: 'Confirmed application submission' },
        { date: '2025-11-09', type: 'Phone', subject: 'Rate options discussion', status: 'Completed', message: 'Discussed rate lock strategy' }
      ]
    },
    {
      task: 'Review updated credit report for John Smith',
      borrower: 'John Smith',
      owner: 'Underwriter',
      stage: 'Underwriting',
      urgency: 'medium',
      date_created: '2025-11-13T10:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi John,

I noticed your credit score has improved by 15 points since we pulled your initial credit report! This is great news.

Your new score (735) may qualify you for a better interest rate. I'd like to re-run the numbers to see if we can save you money.

Would you authorize me to pull an updated credit report? This will be a soft pull and won't affect your score.

Let me know and I can have updated numbers for you within an hour!

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-12', type: 'Email', subject: 'Credit report received', status: 'Sent', message: 'Sent initial credit report results' },
        { date: '2025-11-10', type: 'Phone', subject: 'Credit discussion', status: 'Completed', message: 'Reviewed credit history and tradelines' }
      ]
    }
  ]
});

const mockMumAlerts = () => [
  {
    icon: '📅',
    title: 'Annual review due',
    client: 'Tom Wilson',
    borrower: 'Tom Wilson',
    action: 'Schedule annual mortgage review',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'medium',
    date_created: '2025-11-13T09:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Tom,

It's been a year since we closed on your home - congratulations on your home anniversary!

I'd love to schedule a quick 15-minute call to review your mortgage and see if there are any opportunities to save you money:

✅ Current interest rates (they may be lower now!)
✅ Your home equity position
✅ Refinance opportunities
✅ Any questions you have

I have the following times available:
• Tuesday, Nov 19 at 10:00 AM
• Wednesday, Nov 20 at 2:00 PM
• Thursday, Nov 21 at 11:00 AM

Which works best for you?

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2024-11-13', type: 'Email', subject: 'Closing completed!', status: 'Sent', message: 'Sent congratulations on successful closing' },
      { date: '2024-11-01', type: 'Phone', subject: 'Final walkthrough', status: 'Completed', message: 'Confirmed closing date and details' }
    ]
  },
  {
    icon: '📉',
    title: 'Rate drop opportunity',
    client: 'Lisa Brown',
    borrower: 'Lisa Brown',
    action: 'Send rate drop alert',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'high',
    date_created: '2025-11-13T14:00:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Lisa,

Great news! Interest rates have dropped significantly since you closed on your mortgage.

Your Current Loan:
• Current Rate: 7.25%
• Current Payment: $2,850/month

Refinance Opportunity:
• New Rate: 6.50%
• New Payment: $2,540/month
• Potential Savings: $310/month ($3,720/year!)

You could break even on closing costs in just 18 months and start saving immediately.

Would you like me to run the detailed numbers for you? I can have a full analysis ready within 24 hours.

Let me know!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-06-15', type: 'Email', subject: '6-month check-in', status: 'Sent', message: 'Checked in on how home ownership is going' },
      { date: '2025-01-10', type: 'Email', subject: 'First payment reminder', status: 'Sent', message: 'Reminded about first mortgage payment' }
    ]
  },
  {
    icon: '🎂',
    title: 'Home anniversary',
    client: 'Mark Taylor',
    borrower: 'Mark Taylor',
    action: 'Send anniversary message',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'low',
    date_created: '2025-11-13T08:30:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Mark,

Happy Home Anniversary! 🎉

It's been exactly one year since you got the keys to your new home. I hope this past year has been filled with wonderful memories!

As your mortgage professional, I wanted to check in and see how everything is going:

• How's the home treating you?
• Any questions about your mortgage?
• Any friends or family looking to buy a home?

Also, you've built up some equity this year! If you're curious about your current home value or have any questions, I'm always here to help.

Wishing you many more happy years in your home!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2024-11-13', type: 'Email', subject: 'Welcome home!', status: 'Sent', message: 'Sent closing congratulations and next steps' },
      { date: '2024-11-12', type: 'Phone', subject: 'Closing day!', status: 'Completed', message: 'Closing call and final documents review' }
    ]
  }
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
    borrower: 'Sarah Johnson',
    client_type: 'Pre-Approved',
    source: 'Outlook',
    timestamp: '2 hours ago',
    preview: 'Quick question about my pre-approval...',
    ai_summary: 'Asking about pre-approval expiration date',
    read: false,
    requires_response: true,
    owner: 'Loan Officer',
    stage: 'Pre-Approved',
    urgency: 'medium',
    date_created: '2025-11-13T14:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Sarah,

Great question! Your pre-approval is valid for 90 days from the date we completed it.

Here are the details:
• Approved Date: November 8, 2025
• Expiration Date: February 8, 2026
• Days Remaining: 87 days

This gives you plenty of time to find the right home! If you need more time or if your financial situation changes, we can update or extend your pre-approval.

Are you actively looking at properties? I'd love to hear how the search is going!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and congratulations' },
      { date: '2025-11-05', type: 'Phone', subject: 'Pre-approval interview', status: 'Completed', message: '45-minute call gathering financial information' }
    ]
  },
  {
    id: 2,
    type: 'text',
    type_icon: '💬',
    from: 'Mike Chen',
    borrower: 'Mike Chen',
    client_type: 'Processing',
    source: 'Teams',
    timestamp: '5 hours ago',
    preview: 'Thanks for the update!',
    ai_summary: 'Acknowledged document receipt',
    read: true,
    requires_response: false,
    owner: 'Loan Processor',
    stage: 'Processing',
    urgency: 'low',
    date_created: '2025-11-13T09:00:00',
    preferred_contact_method: 'Text',
    ai_message: `Hi Mike,

You're very welcome! I'm glad we received your documents.

Quick update on your loan:
✅ W-2s received
✅ Tax returns verified
⏳ Waiting on final bank statement (due Thursday)

We're on track for your target closing date of December 5th. I'll keep you posted on next steps!

Let me know if you have any questions.

Best,
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-13', type: 'Text', subject: 'Document confirmation', status: 'Sent', message: 'Confirmed receipt of W-2s' },
      { date: '2025-11-10', type: 'Email', subject: 'Document checklist', status: 'Sent', message: 'Sent list of required documents' }
    ]
  },
  {
    id: 3,
    type: 'voicemail',
    type_icon: '🎙️',
    from: 'Emily Davis',
    borrower: 'Emily Davis',
    client_type: 'Application Started',
    source: 'Voicemail',
    timestamp: '1 day ago',
    preview: 'Left voicemail about appraisal timing',
    ai_summary: 'Wants to know when appraisal will be scheduled',
    duration: '1:23',
    read: false,
    requires_response: true,
    owner: 'Loan Officer',
    stage: 'Application Complete',
    urgency: 'high',
    date_created: '2025-11-12T10:30:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Emily,

I got your voicemail about the appraisal timing - thanks for reaching out!

Good news: The appraisal has been scheduled for this Thursday, November 14th at 2:00 PM. The appraiser will call you 30 minutes before arriving.

What to expect:
• The inspection takes about 30-45 minutes
• You don't need to be home, but it's helpful if you are
• Make sure they can access all areas (attic, basement, garage)
• We should have the report within 2-3 business days

I'll call you this afternoon to confirm you got this message and answer any questions!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-12', type: 'Voicemail', subject: 'Appraisal question', status: 'Received', message: 'Emily asked about appraisal timing' },
      { date: '2025-11-10', type: 'Email', subject: 'Application received', status: 'Sent', message: 'Confirmed receipt of completed application' },
      { date: '2025-11-08', type: 'Phone', subject: 'Initial consultation', status: 'Completed', message: 'Discussed loan options and process timeline' }
    ]
  },
  {
    id: 4,
    type: 'email',
    type_icon: '📧',
    from: 'John Smith',
    borrower: 'John Smith',
    client_type: 'Prospect',
    source: 'Outlook',
    timestamp: '3 days ago',
    preview: 'Following up on our conversation...',
    ai_summary: 'Requesting rate quote for $450k loan',
    read: true,
    requires_response: false,
    task_created: true,
    task_id: 'TASK-123',
    owner: 'Loan Officer',
    stage: 'Lead',
    urgency: 'medium',
    date_created: '2025-11-10T11:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi John,

Thanks for your email! I'd be happy to provide you with rate quotes for your $450,000 home purchase.

Based on today's rates, here are your options:

**30-Year Fixed:**
• Rate: 6.875%
• Monthly Payment: $2,960
• Total Interest: $615,600

**15-Year Fixed:**
• Rate: 6.125%
• Monthly Payment: $3,850
• Total Interest: $243,000

**5/1 ARM:**
• Rate: 6.250% (initial 5 years)
• Monthly Payment: $2,770
• Potential savings in first 5 years

These rates assume 20% down ($90,000) and excellent credit (740+). Rates can change daily, so I'd recommend locking in soon if you're ready.

Would you like to schedule a call to discuss which option is best for your situation?

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-10', type: 'Email', subject: 'Rate quote request', status: 'Received', message: 'John requested rate information for $450k purchase' },
      { date: '2025-11-05', type: 'Phone', subject: 'Initial inquiry', status: 'Completed', message: '20-minute call about home buying process' }
    ]
  }
];

export default Tasks;
