import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ClickablePhone } from '../ClickableContact';
import './CallDetailPanel.css';

const CallDetailPanel = ({
  task,
  callStatus = 'idle',
  powerDialActive = false,
  powerDialIndex = 0,
  powerDialTotal = 0,
  onClickToDial,
  onEndCall,
  onNextContact,
  onSkipContact,
  onStopPowerDial,
  onViewEntity,
  onComplete,
  onClose,
  completing = false,
  compact = false
}) => {
  const navigate = useNavigate();

  const handleViewEntity = () => {
    if (onViewEntity) {
      onViewEntity(task);
    } else if (task.lead_id) {
      navigate(`/leads/${task.lead_id}`);
    } else if (task.loan_id) {
      navigate(`/loans/${task.loan_id}`);
    }
  };

  const getPriorityColor = (priority) => {
    const colors = {
      critical: '#dc2626',
      high: '#f59e0b',
      medium: '#ca8a04',
      normal: '#6b7280',
      low: '#10b981'
    };
    return colors[priority] || colors.normal;
  };

  if (!task) {
    return (
      <div className={`call-detail-panel ${compact ? 'compact' : ''}`}>
        <div className="detail-empty">
          <span className="empty-icon">📞</span>
          <p>Select a call task to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`call-detail-panel ${compact ? 'compact' : ''}`}>
      {/* Header */}
      <div className="detail-header">
        <div className="detail-title-section">
          <div className="detail-source">
            <span className="source-icon-large">📞</span>
            <span className="source-name">{task.task_type === 'workflow' ? 'Workflow' : 'Call Task'}</span>
            {task.priority && task.priority !== 'normal' && (
              <span
                className="priority-badge"
                style={{ backgroundColor: getPriorityColor(task.priority) }}
              >
                {task.priority}
              </span>
            )}
          </div>
          <h2 className="detail-title">{task.title}</h2>
        </div>
        {onClose && (
          <button className="close-btn" onClick={onClose}>×</button>
        )}
      </div>

      {/* Body */}
      <div className="detail-body">
        {/* Info Grid */}
        <div className="detail-info-grid">
          <div className="detail-info-item">
            <span className="detail-label">Contact</span>
            <span className="detail-value client-link" onClick={handleViewEntity}>
              {task.contact_name}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Phone</span>
            <span className="detail-value phone-number">
              <ClickablePhone phone={task.contact_phone} />
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Type</span>
            <span className="detail-value">{task.entity_type === 'lead' ? 'Lead' : 'Loan'}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Priority</span>
            <span
              className="detail-value priority-text"
              style={{ color: getPriorityColor(task.priority) }}
            >
              {task.priority || 'Normal'}
            </span>
          </div>
          {task.workflow_name && (
            <div className="detail-info-item">
              <span className="detail-label">Workflow</span>
              <span className="detail-value">{task.workflow_name}</span>
            </div>
          )}
          {task.due_date && (
            <div className="detail-info-item">
              <span className="detail-label">Due Date</span>
              <span className="detail-value">{new Date(task.due_date).toLocaleDateString()}</span>
            </div>
          )}
          {task.stage && (
            <div className="detail-info-item">
              <span className="detail-label">Stage</span>
              <span className="detail-value">{task.stage}</span>
            </div>
          )}
        </div>

        {/* Task Description */}
        {task.description && (
          <div className="task-details-section">
            <div className="section-header">
              <span className="section-icon">📝</span>
              <span className="section-title">Task Details</span>
            </div>
            <div className="section-content">
              <p>{task.description}</p>
            </div>
          </div>
        )}

        {/* Call Script / Notes */}
        {task.call_script && (
          <div className="call-script-section">
            <div className="section-header">
              <span className="section-icon">📋</span>
              <span className="section-title">Call Script</span>
            </div>
            <div className="section-content">
              <pre>{task.call_script}</pre>
            </div>
          </div>
        )}

        {/* Call Status */}
        <div className="call-status-section">
          <div className="section-header">
            <span className="section-icon">📞</span>
            <span className="section-title">Call Status</span>
          </div>
          <div className="section-content call-status-display">
            {callStatus === 'idle' && (
              <div className="status-idle">
                <span className="status-icon">⚪</span>
                <span className="status-text">Ready to dial</span>
              </div>
            )}
            {callStatus === 'dialing' && (
              <div className="status-dialing">
                <span className="status-icon">⏳</span>
                <span className="status-text">Dialing...</span>
              </div>
            )}
            {callStatus === 'in-progress' && (
              <div className="status-in-progress">
                <span className="status-icon">🔴</span>
                <span className="status-text">Call in progress</span>
              </div>
            )}
            {callStatus === 'completed' && (
              <div className="status-completed">
                <span className="status-icon">✅</span>
                <span className="status-text">Call completed</span>
              </div>
            )}
          </div>
        </div>

        {/* Power Dial Progress (when active) */}
        {powerDialActive && (
          <div className="power-dial-progress-section">
            <div className="section-header">
              <span className="section-icon">🚀</span>
              <span className="section-title">Power Dial Progress</span>
            </div>
            <div className="section-content">
              <div className="progress-info">
                <span>Contact {powerDialIndex + 1} of {powerDialTotal}</span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${((powerDialIndex + 1) / powerDialTotal) * 100}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Action Bar */}
      <div className="detail-actions">
        {callStatus === 'idle' && !powerDialActive && (
          <button
            className="btn-dial"
            onClick={() => onClickToDial && onClickToDial(task)}
          >
            📞 Click to Dial
          </button>
        )}

        {callStatus === 'in-progress' && (
          <button
            className="btn-end-call"
            onClick={() => onEndCall && onEndCall(task)}
          >
            📴 End Call
          </button>
        )}

        {/* Power Dial Controls */}
        {powerDialActive && (
          <>
            <button
              className="btn-next"
              onClick={() => onNextContact && onNextContact()}
              disabled={powerDialIndex >= powerDialTotal - 1}
            >
              ➡️ Next ({powerDialIndex + 1}/{powerDialTotal})
            </button>
            <button
              className="btn-skip"
              onClick={() => onSkipContact && onSkipContact()}
            >
              ⏭️ Skip
            </button>
            <button
              className="btn-stop"
              onClick={() => onStopPowerDial && onStopPowerDial()}
            >
              ⏹️ Stop
            </button>
          </>
        )}

        <button className="btn-view-entity" onClick={handleViewEntity}>
          👤 View {task.entity_type === 'lead' ? 'Lead' : 'Loan'}
        </button>

        <button
          className="btn-complete"
          onClick={() => onComplete && onComplete(task.id)}
          disabled={completing}
        >
          {completing ? '⏳ Completing...' : '✓ Complete Task'}
        </button>
      </div>
    </div>
  );
};

export default CallDetailPanel;
