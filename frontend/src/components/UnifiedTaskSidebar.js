import { useState, useEffect, useCallback } from 'react';
import './UnifiedTaskSidebar.css';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const UnifiedTaskSidebar = ({ isOpen, onClose, onTaskCountChange }) => {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState('all');
  const [feedbackText, setFeedbackText] = useState('');
  const [editedResponse, setEditedResponse] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Fetch unified tasks from all sources
  const fetchUnifiedTasks = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/unified-tasks`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setTasks(data.tasks || []);
        if (onTaskCountChange) {
          onTaskCountChange(data.total_count || 0);
        }
      }
    } catch (error) {
      console.error('Error fetching unified tasks:', error);
    } finally {
      setLoading(false);
    }
  }, [onTaskCountChange]);

  useEffect(() => {
    if (isOpen) {
      fetchUnifiedTasks();
    }
  }, [isOpen, fetchUnifiedTasks]);

  // Filter tasks by source
  const filteredTasks = tasks.filter(task => {
    if (activeFilter === 'all') return true;
    return task.source === activeFilter;
  });

  // Get source icon
  const getSourceIcon = (source) => {
    switch (source) {
      case 'task': return '📋';
      case 'workflow': return '⚙️';
      case 'reconciliation': return '📧';
      default: return '📌';
    }
  };

  // Get source label
  const getSourceLabel = (source) => {
    switch (source) {
      case 'task': return 'Task';
      case 'workflow': return 'Workflow';
      case 'reconciliation': return 'Email';
      default: return 'Other';
    }
  };

  // Get confidence color
  const getConfidenceColor = (confidence) => {
    if (confidence >= 90) return '#10b981'; // green
    if (confidence >= 70) return '#f59e0b'; // orange
    if (confidence >= 50) return '#f97316'; // dark orange
    return '#ef4444'; // red
  };

  // Get confidence label
  const getConfidenceLabel = (confidence) => {
    if (confidence >= 90) return 'High Confidence';
    if (confidence >= 70) return 'Medium Confidence';
    if (confidence >= 50) return 'Low Confidence';
    return 'Needs Training';
  };

  // Handle task selection
  const handleSelectTask = (task) => {
    setSelectedTask(task);
    setEditedResponse(task.ai_suggested_response || '');
    setFeedbackText('');
    setIsEditing(false);
  };

  // Handle approve action
  const handleApprove = async () => {
    if (!selectedTask) return;

    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/unified-tasks/${selectedTask.id}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source: selectedTask.source,
          approved_response: isEditing ? editedResponse : selectedTask.ai_suggested_response,
          feedback: feedbackText || null
        })
      });

      if (response.ok) {
        // Remove from list and clear selection
        setTasks(prev => prev.filter(t => t.id !== selectedTask.id || t.source !== selectedTask.source));
        setSelectedTask(null);
        setFeedbackText('');
        setEditedResponse('');
        // Refresh to get updated counts
        fetchUnifiedTasks();
      }
    } catch (error) {
      console.error('Error approving task:', error);
    } finally {
      setSubmitting(false);
    }
  };

  // Handle reject/skip action
  const handleReject = async () => {
    if (!selectedTask) return;

    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/unified-tasks/${selectedTask.id}/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source: selectedTask.source,
          feedback: feedbackText || 'Rejected by user'
        })
      });

      if (response.ok) {
        setTasks(prev => prev.filter(t => t.id !== selectedTask.id || t.source !== selectedTask.source));
        setSelectedTask(null);
        setFeedbackText('');
        fetchUnifiedTasks();
      }
    } catch (error) {
      console.error('Error rejecting task:', error);
    } finally {
      setSubmitting(false);
    }
  };

  // Count by source
  const countBySource = (source) => {
    if (source === 'all') return tasks.length;
    return tasks.filter(t => t.source === source).length;
  };

  if (!isOpen) return null;

  return (
    <div className="unified-task-sidebar">
      <div className="sidebar-header">
        <div className="header-title">
          <span className="header-icon">🎯</span>
          <h2>Action Items</h2>
          <span className="task-count-badge">{tasks.length}</span>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      {/* Filter tabs */}
      <div className="filter-tabs">
        <button
          className={`filter-tab ${activeFilter === 'all' ? 'active' : ''}`}
          onClick={() => setActiveFilter('all')}
        >
          All ({countBySource('all')})
        </button>
        <button
          className={`filter-tab ${activeFilter === 'task' ? 'active' : ''}`}
          onClick={() => setActiveFilter('task')}
        >
          📋 Tasks ({countBySource('task')})
        </button>
        <button
          className={`filter-tab ${activeFilter === 'workflow' ? 'active' : ''}`}
          onClick={() => setActiveFilter('workflow')}
        >
          ⚙️ Workflow ({countBySource('workflow')})
        </button>
        <button
          className={`filter-tab ${activeFilter === 'reconciliation' ? 'active' : ''}`}
          onClick={() => setActiveFilter('reconciliation')}
        >
          📧 Emails ({countBySource('reconciliation')})
        </button>
      </div>

      <div className="sidebar-content">
        {/* Task list */}
        <div className={`task-list ${selectedTask ? 'with-detail' : ''}`}>
          {loading ? (
            <div className="loading-state">Loading tasks...</div>
          ) : filteredTasks.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">✅</span>
              <p>No pending action items</p>
            </div>
          ) : (
            filteredTasks.map((task) => (
              <div
                key={`${task.source}-${task.id}`}
                className={`task-item ${selectedTask?.id === task.id && selectedTask?.source === task.source ? 'selected' : ''}`}
                onClick={() => handleSelectTask(task)}
              >
                <div className="task-item-header">
                  <span className="source-badge" data-source={task.source}>
                    {getSourceIcon(task.source)} {getSourceLabel(task.source)}
                  </span>
                  <div
                    className="confidence-indicator"
                    style={{ '--confidence-color': getConfidenceColor(task.ai_confidence) }}
                    title={`AI Confidence: ${task.ai_confidence}%`}
                  >
                    <div
                      className="confidence-fill"
                      style={{ width: `${task.ai_confidence}%` }}
                    />
                    <span className="confidence-text">{task.ai_confidence}%</span>
                  </div>
                </div>
                <div className="task-item-title">{task.title}</div>
                <div className="task-item-meta">
                  {task.client_name && <span className="client-name">{task.client_name}</span>}
                  {task.due_date && <span className="due-date">{new Date(task.due_date).toLocaleDateString()}</span>}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Task detail panel */}
        {selectedTask && (
          <div className="task-detail-panel">
            <div className="detail-header">
              <div className="detail-source">
                <span className="source-icon-large">{getSourceIcon(selectedTask.source)}</span>
                <span className="source-name">{getSourceLabel(selectedTask.source).toUpperCase()}</span>
              </div>
              <button className="close-detail" onClick={() => setSelectedTask(null)}>×</button>
            </div>

            <div className="detail-body">
              <h3 className="detail-title">{selectedTask.title}</h3>

              {selectedTask.client_name && (
                <div className="detail-client">
                  <span className="label">Client:</span>
                  <span className="value">{selectedTask.client_name}</span>
                </div>
              )}

              {selectedTask.description && (
                <div className="detail-description">
                  <span className="label">Details:</span>
                  <p>{selectedTask.description}</p>
                </div>
              )}

              {/* AI Confidence meter */}
              <div className="confidence-section">
                <div className="confidence-header">
                  <span className="label">AI Confidence</span>
                  <span
                    className="confidence-value"
                    style={{ color: getConfidenceColor(selectedTask.ai_confidence) }}
                  >
                    {selectedTask.ai_confidence}% - {getConfidenceLabel(selectedTask.ai_confidence)}
                  </span>
                </div>
                <div className="confidence-meter">
                  <div
                    className="confidence-bar"
                    style={{
                      width: `${selectedTask.ai_confidence}%`,
                      backgroundColor: getConfidenceColor(selectedTask.ai_confidence)
                    }}
                  />
                </div>
                <p className="confidence-hint">
                  {selectedTask.ai_confidence < 70
                    ? 'This task type needs more training. Your feedback helps AI improve!'
                    : selectedTask.ai_confidence < 90
                    ? 'AI is learning this pattern. Review and adjust as needed.'
                    : 'AI is confident in this response based on your previous approvals.'}
                </p>
              </div>

              {/* AI Suggested Response */}
              <div className="ai-response-section">
                <div className="response-header">
                  <span className="label">🤖 AI Suggested Response</span>
                  <button
                    className="edit-btn"
                    onClick={() => setIsEditing(!isEditing)}
                  >
                    {isEditing ? '✓ Done Editing' : '✏️ Edit'}
                  </button>
                </div>
                {isEditing ? (
                  <textarea
                    className="response-editor"
                    value={editedResponse}
                    onChange={(e) => setEditedResponse(e.target.value)}
                    placeholder="Edit the AI response..."
                  />
                ) : (
                  <div className="response-preview">
                    {selectedTask.ai_suggested_response || 'No AI suggestion available'}
                  </div>
                )}
              </div>

              {/* Feedback section */}
              <div className="feedback-section">
                <span className="label">🎓 Train AI (Optional)</span>
                <textarea
                  className="feedback-input"
                  value={feedbackText}
                  onChange={(e) => setFeedbackText(e.target.value)}
                  placeholder="Provide feedback to help AI improve... (e.g., 'Always mention our competitive rates' or 'Use more formal language')"
                />
              </div>

              {/* Action buttons */}
              <div className="action-buttons">
                <button
                  className="btn-approve"
                  onClick={handleApprove}
                  disabled={submitting}
                >
                  {submitting ? 'Processing...' : '✓ Approve & Complete'}
                </button>
                <button
                  className="btn-reject"
                  onClick={handleReject}
                  disabled={submitting}
                >
                  ✗ Reject / Skip
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default UnifiedTaskSidebar;
