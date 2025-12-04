import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { aiAPI, tasksAPI } from '../../services/api';
import './TaskDetailPanel.css';

/**
 * Shared TaskDetailPanel Component
 * Used by: Tasks page, AI Landing Page Action Center, and anywhere task details are shown
 *
 * Props:
 * - task: The selected task object
 * - onComplete: Function to handle task completion
 * - onDelete: Function to handle task deletion
 * - onSnooze: Function to handle snoozing
 * - onDelegate: Function to handle delegation (receives team member)
 * - onSend: Function to handle sending message (id, method, message)
 * - onApproveAi: Function to handle AI action approval
 * - onChangeStatus: Function to handle status change (newStatus)
 * - onClose: Function to close the panel
 * - completing: Boolean indicating if completion is in progress
 * - updatingStatus: Boolean indicating if status update is in progress
 * - compact: Boolean for compact mode (sidebar)
 * - showActionBar: Boolean to show/hide bottom action bar (default true)
 * - teamMembers: Array of team members for delegation
 * - statusOptions: Array of status options for status change modal
 */

// Default status options if none provided
const DEFAULT_STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: '#6366f1' },
  { value: 'attempted_contact', label: 'Attempted Contact', color: '#8b5cf6' },
  { value: 'contact_made', label: 'Contact Made', color: '#06b6d4' },
  { value: 'needs_analysis', label: 'Needs Analysis', color: '#0ea5e9' },
  { value: 'pre_approved', label: 'Pre-Approved', color: '#10b981' },
  { value: 'application', label: 'Application', color: '#f59e0b' },
  { value: 'processing', label: 'Processing', color: '#f97316' },
  { value: 'closing', label: 'Closing', color: '#22c55e' },
  { value: 'funded', label: 'Funded', color: '#16a34a' },
  { value: 'not_qualified', label: 'Does Not Qualify', color: '#ef4444' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' }
];

const TaskDetailPanel = ({
  task,
  onComplete,
  onDelete,
  onSnooze,
  onDelegate,
  onSend,
  onApproveAi,
  onChangeStatus,
  onClose,
  completing = false,
  updatingStatus = false,
  compact = false,
  showActionBar = true,
  teamMembers = [],
  statusOptions = DEFAULT_STATUS_OPTIONS
}) => {
  const navigate = useNavigate();

  // Local state
  const [editingMessage, setEditingMessage] = useState(false);
  const [draftMessage, setDraftMessage] = useState('');
  const [aiInstructions, setAiInstructions] = useState('');
  const [aiAcknowledgment, setAiAcknowledgment] = useState(null);
  const [sendingInstruction, setSendingInstruction] = useState(false);
  const [communicationMethod, setCommunicationMethod] = useState('Email');
  const [taskOwner, setTaskOwner] = useState('Loan Officer');
  const [showHistory, setShowHistory] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showDelegateModal, setShowDelegateModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  // SLA task state
  const [slaMilestoneDate, setSlaMilestoneDate] = useState('');
  const [completingSla, setCompletingSla] = useState(false);

  // Reset state when task changes
  useEffect(() => {
    if (task) {
      setDraftMessage(task.ai_message || '');
      setTaskOwner(task.owner || 'Loan Officer');
      setCommunicationMethod(task.preferred_contact_method || 'Email');
      setAiInstructions('');
      setAiAcknowledgment(null);
      setEditingMessage(false);
      setShowHistory(false);
      // Reset SLA date - use existing milestone_date if available
      setSlaMilestoneDate(task.milestone_date ? task.milestone_date.split('T')[0] : '');
    }
  }, [task?.id]);

  if (!task) {
    return (
      <div className={`task-detail-panel ${compact ? 'compact' : ''}`}>
        <div className="detail-empty">
          <span className="empty-icon">📋</span>
          <p>Select a task to view details</p>
        </div>
      </div>
    );
  }

  const getUrgencyColor = (urgency) => {
    switch (urgency?.toLowerCase()) {
      case 'critical': return '#dc2626';
      case 'high': return '#f97316';
      case 'medium': return '#eab308';
      case 'low': return '#22c55e';
      default: return '#6b7280';
    }
  };

  const getSourceIcon = (source) => {
    switch (source?.toLowerCase()) {
      case 'workflow': return '⚙️';
      case 'ai engine': return '🤖';
      case 'manual priority': return '⭐';
      case 'leads engine': return '👤';
      case 'milestone risk': return '⚠️';
      case 'client for life':
      case 'mum': return '👋';
      case 'messages': return '💬';
      default: return '📋';
    }
  };

  const handleNavigateToEntity = () => {
    const loanId = task.loan_id || task.loanId;
    const leadId = task.lead_id || task.leadId;

    // Prioritize navigating to the client profile (loan or lead page)
    if (loanId) {
      navigate(`/loans/${loanId}`);
    } else if (leadId) {
      navigate(`/leads/${leadId}`);
    } else if (task.entity_type === 'loan' && task.entity_id) {
      navigate(`/loans/${task.entity_id}`);
    } else if (task.entity_type === 'lead' && task.entity_id) {
      navigate(`/leads/${task.entity_id}`);
    }
  };

  const handleNavigateToSource = () => {
    if (task.source === 'Workflow') {
      navigate('/workflow-dashboard');
    } else if (task.source === 'AI Engine') {
      navigate('/ai-landing');
    } else if (task.source === 'Messages') {
      navigate('/messages');
    } else if (task.source === 'Client for Life' || task.source === 'MUM') {
      navigate('/mum');
    } else if (task.source === 'Milestone Risk') {
      const loanId = task.loan_id || task.loanId || task.entity_id;
      if (loanId) navigate(`/loans/${loanId}`);
    }
  };

  const handleSendToAi = async () => {
    if (!aiInstructions.trim()) return;
    setSendingInstruction(true);
    try {
      const response = await aiAPI.submitTrainingInstruction(
        aiInstructions,
        {
          task_type: task.source || 'general',
          borrower_name: task.borrower || '',
          task_title: task.title || '',
          stage: task.stage || ''
        }
      );
      setAiAcknowledgment(response.acknowledgment);
      setAiInstructions('');
    } catch (error) {
      console.error('Failed to send instruction:', error);
      setAiAcknowledgment('Failed to send instruction. Please try again.');
    } finally {
      setSendingInstruction(false);
    }
  };

  const handleDeleteClick = () => {
    if (localStorage.getItem('skipDeleteConfirmation') === 'true') {
      onDelete && onDelete(task.id);
    } else {
      setShowDeleteConfirm(true);
    }
  };

  // Handle SLA task completion with date
  const handleCompleteSlaTask = async () => {
    if (!slaMilestoneDate) {
      alert('Please enter the milestone completion date');
      return;
    }

    setCompletingSla(true);
    try {
      // Extract numeric task ID if it's a string like "workflow-123"
      let taskId = task.id;
      if (typeof taskId === 'string' && taskId.includes('-')) {
        taskId = taskId.split('-').pop();
      }

      const response = await fetch(`/api/v1/tasks/${taskId}/complete-sla`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          milestone_date: slaMilestoneDate
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to complete SLA task');
      }

      const result = await response.json();

      // Show success message with details
      let message = 'SLA task completed!';
      if (result.loan_field_updated) {
        message += ` Updated ${result.loan_field_updated.replace(/_/g, ' ')} on the loan.`;
      }
      if (result.milestone_completed) {
        message += ' SLA milestone marked as complete.';
      }
      alert(message);

      // Call parent's onComplete to remove from list
      onComplete && onComplete(task.id);
    } catch (error) {
      console.error('Error completing SLA task:', error);
      alert(error.message || 'Failed to complete SLA task');
    } finally {
      setCompletingSla(false);
    }
  };

  const hasEntityLink = task.loan_id || task.loanId || task.lead_id || task.leadId || task.entity_id;
  const isSlaTask = task.sla_milestone_id || task.sla_milestone_type || task.related_type === 'sla_milestone';

  return (
    <div className={`task-detail-panel ${compact ? 'compact' : ''}`}>
      {/* Header with source badge */}
      <div className="detail-header">
        <div className="detail-source">
          <span className="source-icon-large">{task.sourceIcon || getSourceIcon(task.source)}</span>
          <span className="source-name">{task.source || 'Task'}</span>
        </div>
        {onClose && (
          <button className="detail-close-btn" onClick={onClose}>×</button>
        )}
      </div>

      {/* Title */}
      <h2 className="detail-title">{task.title}</h2>

      {/* Info Grid */}
      <div className="detail-body">
        <div className="detail-info-grid">
          {task.borrower && (
            <div className="detail-info-item">
              <span className="detail-label">Client</span>
              <span
                className={`detail-value ${hasEntityLink ? 'client-link' : ''}`}
                onClick={hasEntityLink ? handleNavigateToEntity : undefined}
                style={{
                  cursor: hasEntityLink ? 'pointer' : 'default',
                  color: hasEntityLink ? '#218D8D' : 'inherit',
                  textDecoration: hasEntityLink ? 'underline' : 'none'
                }}
              >
                {task.borrower}
              </span>
            </div>
          )}
          <div className="detail-info-item">
            <span className="detail-label">Stage</span>
            <span
              className="detail-value clickable-link"
              onClick={handleNavigateToEntity}
            >
              {task.stage || task.status || 'N/A'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Priority</span>
            <span
              className="detail-urgency-badge"
              style={{ backgroundColor: getUrgencyColor(task.urgency || task.priority) }}
            >
              {task.urgency || task.priority || 'Medium'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Source</span>
            <span
              className="detail-value clickable-link"
              onClick={handleNavigateToSource}
            >
              {task.source || 'Manual'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Owner</span>
            <span className="detail-value">{taskOwner}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">{task.source === 'Workflow' ? 'Due Date' : 'Date Created'}</span>
            <span className="detail-value">
              {task.due_date
                ? new Date(task.due_date).toLocaleDateString()
                : task.date_created || task.created_at
                  ? new Date(task.date_created || task.created_at).toLocaleString()
                  : 'N/A'}
              {task.days_until_due !== undefined && (
                <span className={`due-badge ${task.days_until_due === 0 ? 'due-today' : task.days_until_due === 1 ? 'due-tomorrow' : 'due-upcoming'}`}>
                  {task.days_until_due === 0 ? 'Today' : task.days_until_due === 1 ? 'Tomorrow' : `In ${task.days_until_due} days`}
                </span>
              )}
            </span>
          </div>

          {/* Send Via Options */}
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

        {/* Task Description - What needs to be accomplished */}
        {(task.description || task.ai_action || task.workflow_name) && (
          <div className="task-description-section">
            <div className="task-description-header">
              <span className="description-icon">📋</span>
              <span className="description-title">What to Accomplish</span>
            </div>
            <div className="task-description-content">
              {task.description && (
                <p className="task-description-text">{task.description}</p>
              )}
              {task.ai_action && !task.description && (
                <p className="task-description-text">{task.ai_action}</p>
              )}
              {task.workflow_name && (
                <p className="task-workflow-info">
                  <span className="workflow-badge" style={{ backgroundColor: task.workflow_color || '#218D8D' }}>
                    {task.workflow_name}
                  </span>
                  {task.days_until_due !== undefined && (
                    <span className="days-info">
                      {task.days_until_due === 0 ? 'Due today' :
                       task.days_until_due === 1 ? 'Due tomorrow' :
                       `Due in ${task.days_until_due} days`}
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
        )}

        {/* SLA Milestone Date Input Section */}
        {isSlaTask && (
          <div className="detail-sla-section">
            <div className="sla-section-header">
              <span className="sla-icon">⚠️</span>
              <span className="sla-title">SLA Milestone Completion</span>
            </div>
            <div className="sla-section-content">
              <p className="sla-instruction">
                Enter the date this milestone was completed to update the loan's Important Dates:
              </p>
              {task.sla_milestone_type && (
                <p className="sla-milestone-type">
                  <strong>Milestone:</strong> {task.sla_milestone_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </p>
              )}
              {task.sla_date_field && (
                <p className="sla-date-field">
                  <strong>Updates:</strong> {task.sla_date_field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </p>
              )}
              <div className="sla-date-input-container">
                <label htmlFor="sla-milestone-date">Milestone Date:</label>
                <input
                  id="sla-milestone-date"
                  type="date"
                  className="sla-date-input"
                  value={slaMilestoneDate}
                  onChange={(e) => setSlaMilestoneDate(e.target.value)}
                  max={new Date().toISOString().split('T')[0]}
                />
              </div>
              <button
                className="btn-complete-sla"
                onClick={handleCompleteSlaTask}
                disabled={completingSla || !slaMilestoneDate}
              >
                {completingSla ? '⏳ Completing...' : '✓ Complete SLA Milestone'}
              </button>
            </div>
          </div>
        )}

        {/* Missing Documents Section */}
        {task.missing_documents && task.missing_documents.length > 0 && (
          <div className="detail-missing-docs-section">
            <div className="missing-docs-header">
              <span className="docs-icon">📄</span>
              <h3>Missing Documents Detected by AI</h3>
            </div>
            <div className="missing-docs-list">
              {task.missing_documents.map((doc, idx) => (
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

        {/* AI Training + AI Drafted Message Sections */}
        {task.ai_message && (
          <>
            {/* AI Training Instructions Section */}
            <div className="detail-ai-training-section">
              <div className="ai-training-header">
                <span className="training-icon">🎓</span>
                <span className="training-title">Train AI (Optional)</span>
              </div>

              {/* Inline AI Response */}
              {aiAcknowledgment && (
                <div className="ai-conversation-response">
                  <div className="ai-response-header">
                    <span className="ai-response-icon">🤖</span>
                    <span className="ai-response-label">AI Response</span>
                    <button
                      className="btn-clear-response"
                      onClick={() => setAiAcknowledgment(null)}
                    >
                      ✕
                    </button>
                  </div>
                  <div
                    className="ai-response-content"
                    dangerouslySetInnerHTML={{
                      __html: aiAcknowledgment
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                        .replace(/\n/g, '<br />')
                    }}
                  />
                </div>
              )}

              <div className="ai-training-input-container">
                <textarea
                  className="ai-training-input"
                  placeholder={aiAcknowledgment
                    ? "Continue the conversation or provide additional instructions..."
                    : "Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                  }
                  value={aiInstructions}
                  onChange={(e) => setAiInstructions(e.target.value)}
                  rows={3}
                  autoComplete="off"
                />
                <button
                  className="btn-send-to-ai"
                  disabled={sendingInstruction || !aiInstructions.trim()}
                  onClick={handleSendToAi}
                >
                  {sendingInstruction ? 'Sending...' : aiAcknowledgment ? 'Continue' : 'Send to AI'}
                </button>
              </div>
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
                  <div
                    className="message-preview"
                    dangerouslySetInnerHTML={{
                      __html: draftMessage.replace(/\n/g, '<br />')
                    }}
                  />
                )}
              </div>
            </div>
          </>
        )}

        {/* Recommended Action */}
        {task.action && (
          <div className="detail-action-section">
            <h3>Recommended Action</h3>
            <p>{task.action}</p>
          </div>
        )}

        {/* Communication History */}
        {task.communication_history && task.communication_history.length > 0 && (
          <div className="communication-history-section">
            <button
              className="history-accordion-button"
              onClick={() => setShowHistory(!showHistory)}
            >
              <span className="history-icon">📋</span>
              <span className="history-title">Communication History ({task.communication_history.length})</span>
              <span className="history-toggle">{showHistory ? '▼' : '▶'}</span>
            </button>
            {showHistory && (
              <div className="history-content">
                {task.communication_history.map((comm, idx) => (
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
                      <span className={`history-status ${comm.status?.toLowerCase()}`}>
                        {comm.status}
                      </span>
                    </div>
                    <div className="history-item-body">
                      {comm.subject && <div className="history-subject">{comm.subject}</div>}
                      <div className="history-message">{comm.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Action Bar */}
      {showActionBar && (
        <div className="detail-footer">
          <button
            className="btn-detail-send"
            onClick={() => onSend && onSend(task.id, communicationMethod, draftMessage)}
          >
            📤 Send via {communicationMethod}
          </button>
          {task.ai_action && (
            <button
              className="btn-detail-approve"
              onClick={() => onApproveAi && onApproveAi(task.id)}
            >
              Approve AI Action
            </button>
          )}
          <button
            className="btn-detail-status"
            onClick={() => setShowStatusModal(true)}
          >
            📊 Change Status
          </button>
          <button
            className="btn-detail-secondary"
            onClick={() => onSnooze && onSnooze(task.id)}
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
            className="btn-detail-complete"
            onClick={() => onComplete && onComplete(task.id)}
            disabled={completing}
          >
            {completing ? '⏳ Completing...' : '✓ Complete Task'}
          </button>
          <button
            className="btn-detail-danger"
            onClick={handleDeleteClick}
          >
            🗑️ Delete
          </button>
        </div>
      )}

      {/* Change Status Modal */}
      {showStatusModal && (
        <div className="modal-overlay" onClick={() => setShowStatusModal(false)}>
          <div className="status-modal" onClick={(e) => e.stopPropagation()}>
            <div className="status-modal-header">
              <h3>Change Lead/Loan Status</h3>
              <button className="modal-close" onClick={() => setShowStatusModal(false)}>×</button>
            </div>
            <div className="status-modal-content">
              <p className="status-current">
                Current: <strong>{task.stage || task.status || 'Unknown'}</strong>
              </p>
              <div className="status-options">
                {statusOptions.map((stage) => (
                  <button
                    key={stage.value}
                    className={`status-option ${task.stage?.toLowerCase().replace(/\s+/g, '_') === stage.value ? 'current' : ''}`}
                    style={{ borderLeftColor: stage.color }}
                    onClick={() => {
                      onChangeStatus && onChangeStatus(stage.value);
                      setShowStatusModal(false);
                    }}
                    disabled={updatingStatus}
                  >
                    <span className="status-dot" style={{ backgroundColor: stage.color }}></span>
                    {stage.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delegate Modal */}
      {showDelegateModal && (
        <div className="modal-overlay" onClick={() => setShowDelegateModal(false)}>
          <div className="delegate-modal" onClick={(e) => e.stopPropagation()}>
            <div className="delegate-modal-header">
              <h3>Delegate Task</h3>
              <button className="modal-close" onClick={() => setShowDelegateModal(false)}>×</button>
            </div>
            <div className="delegate-modal-content">
              <p>Select a team member to delegate this task to:</p>
              <div className="team-member-list">
                {teamMembers.length > 0 ? (
                  teamMembers.map((member) => (
                    <button
                      key={member.id}
                      className="team-member-option"
                      onClick={() => {
                        onDelegate && onDelegate(member);
                        setShowDelegateModal(false);
                      }}
                    >
                      <span className="member-avatar">
                        {member.first_name?.[0]}{member.last_name?.[0]}
                      </span>
                      <span className="member-name">
                        {member.first_name} {member.last_name}
                      </span>
                      <span className="member-role">{member.role || 'Team Member'}</span>
                    </button>
                  ))
                ) : (
                  <p className="no-team-members">No team members available</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="delete-confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="delete-modal-header">
              <h3>Delete Task?</h3>
              <button className="modal-close" onClick={() => setShowDeleteConfirm(false)}>×</button>
            </div>
            <div className="delete-modal-content">
              <p>Are you sure you want to delete this task?</p>
              <p className="task-title-preview">"{task.title}"</p>
              <label className="dont-ask-again">
                <input
                  type="checkbox"
                  onChange={(e) => {
                    if (e.target.checked) {
                      localStorage.setItem('skipDeleteConfirmation', 'true');
                    }
                  }}
                />
                Don't ask me again
              </label>
            </div>
            <div className="delete-modal-actions">
              <button
                className="btn-modal-cancel"
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancel
              </button>
              <button
                className="btn-modal-danger"
                onClick={() => {
                  onDelete && onDelete(task.id);
                  setShowDeleteConfirm(false);
                }}
              >
                Yes, Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TaskDetailPanel;
