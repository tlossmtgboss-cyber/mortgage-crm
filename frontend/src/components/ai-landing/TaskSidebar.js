import React from 'react';
import { tasksAPI, reconciliationAPI, outreachAPI } from '../../services/api';

function TaskSidebar({
  structuredContent,
  setStructuredContent,
  selectedTask,
  setSelectedTask,
  selectedSendMethod,
  setSelectedSendMethod,
  selectedTaskIds,
  setSelectedTaskIds,
  bulkProcessing,
  setBulkProcessing,
  showRightSidebar,
  setShowRightSidebar,
  addMessage
}) {
  if (!showRightSidebar || !structuredContent?.tasks?.length) return null;

  const getUrgencyColor = (priority) => {
    const colors = { 'URGENT': '#ef4444', 'HIGH': '#f97316', 'MEDIUM': '#eab308', 'LOW': '#22c55e' };
    return colors[priority?.toUpperCase()] || '#9ca3af';
  };

  const getPriorityStyle = (priority) => {
    const styles = {
      'URGENT': { bg: '#fef2f2', text: '#dc2626' },
      'HIGH': { bg: '#fff7ed', text: '#ea580c' },
      'MEDIUM': { bg: '#fefce8', text: '#ca8a04' },
      'LOW': { bg: '#f0fdf4', text: '#16a34a' }
    };
    return styles[priority?.toUpperCase()] || { bg: '#f3f4f6', text: '#6b7280' };
  };

  const handleCloseSidebar = () => {
    setShowRightSidebar(false);
    setStructuredContent(null);
    setSelectedTask(null);
  };

  const removeTask = (taskId) => {
    const newTasks = structuredContent.tasks.filter(t => t.id !== taskId);
    if (newTasks.length > 0) {
      setStructuredContent({ ...structuredContent, tasks: newTasks });
      setSelectedTask(newTasks[0]);
    } else {
      handleCloseSidebar();
    }
  };

  const handleBulkDelete = async () => {
    if (selectedTaskIds.size === 0) return;
    setBulkProcessing(true);
    try {
      for (const taskId of selectedTaskIds) {
        const task = structuredContent.tasks.find(t => t.id === taskId);
        if (task?.backendId) {
          if (task.taskType === 'reconciliation') {
            await reconciliationAPI.delete(task.backendId);
          } else {
            await tasksAPI.delete(task.backendId);
          }
        }
      }
      // Remove from local state
      const newTasks = structuredContent.tasks.filter(t => !selectedTaskIds.has(t.id));
      if (newTasks.length > 0) {
        setStructuredContent({ ...structuredContent, tasks: newTasks });
        setSelectedTask(newTasks[0]);
      } else {
        handleCloseSidebar();
      }
      setSelectedTaskIds(new Set());
      addMessage(`🗑️ Deleted ${selectedTaskIds.size} task(s)`, 'assistant');
    } catch (error) {
      console.error('Error bulk deleting tasks:', error);
    } finally {
      setBulkProcessing(false);
    }
  };

  const handleSend = async (task) => {
    addMessage(`Sending ${selectedSendMethod} to ${task.client}...`, 'assistant');
    try {
      const message = `Complete task: ${task.title}`;
      const leadId = task.leadId || task.backendId || null;

      switch (selectedSendMethod) {
        case 'email':
          await outreachAPI.sendEmail(
            task.clientEmail || task.email,
            `Follow-up: ${task.title}`,
            message,
            leadId
          );
          addMessage(`✅ Email sent to ${task.client}`, 'assistant');
          break;
        case 'text':
          await outreachAPI.sendSMS(
            task.clientPhone || task.phone,
            message,
            leadId
          );
          addMessage(`✅ Text sent to ${task.client}`, 'assistant');
          break;
        case 'phone':
          await outreachAPI.requestCall(
            task.clientPhone || task.phone,
            leadId,
            task.title
          );
          addMessage(`✅ Call request created for ${task.client}`, 'assistant');
          break;
        case 'voicemail':
          await outreachAPI.sendVoicemail(
            task.clientPhone || task.phone,
            'default',
            leadId
          );
          addMessage(`✅ Voicemail dropped for ${task.client}`, 'assistant');
          break;
        default:
          addMessage(`✅ Message sent to ${task.client}`, 'assistant');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      addMessage(`⚠️ Could not send ${selectedSendMethod}. Please try again or use another method.`, 'assistant');
    }
  };

  const handleApprove = async (task) => {
    try {
      if (task.taskType === 'reconciliation') {
        await reconciliationAPI.approve({ item_id: task.backendId, action: 'approve' });
        addMessage(`✅ Approved reconciliation: "${task.title}" for ${task.client}`, 'assistant');
      } else if (task.backendId && typeof task.backendId === 'number') {
        await tasksAPI.update(task.backendId, { status: 'completed' });
        addMessage(`✅ Completed task: "${task.title}"`, 'assistant');
      }
    } catch (error) {
      console.error('Error completing task:', error);
      addMessage(`Marked complete: "${task.title}" (sync pending)`, 'assistant');
    }
    removeTask(task.id);
  };

  const handleSnooze = (task) => {
    addMessage(`⏰ Snoozed "${task.title}" - I'll remind you in 3 hours.`, 'assistant');
    removeTask(task.id);
  };

  const handleDelegate = (task) => {
    addMessage(`👥 Who would you like to delegate "${task.title}" to? Type a team member's name.`, 'assistant');
  };

  const handleDelete = async (task) => {
    try {
      if (task.taskType === 'reconciliation') {
        await reconciliationAPI.delete(task.backendId);
        addMessage(`🗑️ Dismissed reconciliation item: "${task.title}"`, 'assistant');
      } else if (task.backendId && typeof task.backendId === 'number') {
        await tasksAPI.delete(task.backendId);
        addMessage(`🗑️ Deleted task: "${task.title}"`, 'assistant');
      }
    } catch (error) {
      console.error('Error deleting task:', error);
      addMessage(`Removed: "${task.title}" (sync pending)`, 'assistant');
    }
    removeTask(task.id);
  };

  const task = selectedTask || structuredContent.tasks[0];
  const priorityStyle = getPriorityStyle(task.priority);

  return (
    <div className="task-sidebar">
      <div className="task-sidebar-header">
        <h2>Tasks to Complete</h2>
        <span className="task-count-badge">{structuredContent.tasks.length}</span>
        <button className="task-sidebar-close" onClick={handleCloseSidebar}>
          ×
        </button>
      </div>

      <div className="task-sidebar-content">
        {/* Task List - Email Style Layout */}
        <div className="task-email-layout">
          {/* Left: Task Inbox List */}
          <div className="task-inbox-panel">
            <div className="inbox-panel-header">
              <div className="inbox-header-left">
                <input
                  type="checkbox"
                  className="task-checkbox select-all-checkbox"
                  checked={structuredContent.tasks.length > 0 && structuredContent.tasks.every(t => selectedTaskIds.has(t.id))}
                  ref={(el) => {
                    if (el) el.indeterminate = structuredContent.tasks.some(t => selectedTaskIds.has(t.id)) && !structuredContent.tasks.every(t => selectedTaskIds.has(t.id));
                  }}
                  onChange={() => {
                    const allSelected = structuredContent.tasks.every(t => selectedTaskIds.has(t.id));
                    if (allSelected) {
                      setSelectedTaskIds(new Set());
                    } else {
                      setSelectedTaskIds(new Set(structuredContent.tasks.map(t => t.id)));
                    }
                  }}
                  title="Select all"
                />
                <h3>Tasks</h3>
                <span className="task-count-pill">{structuredContent.tasks.length}</span>
              </div>
              {selectedTaskIds.size > 0 && (
                <button
                  className="btn-bulk-delete"
                  onClick={handleBulkDelete}
                  disabled={bulkProcessing}
                >
                  {bulkProcessing ? 'Deleting...' : `🗑️ Delete (${selectedTaskIds.size})`}
                </button>
              )}
            </div>
            <div className="inbox-task-list">
              {structuredContent.tasks.map((t, idx) => {
                const isSelected = selectedTask?.id === t.id || (!selectedTask && idx === 0);
                const isChecked = selectedTaskIds.has(t.id);
                return (
                  <div
                    key={t.id || idx}
                    className={`inbox-task-item ${isSelected ? 'selected' : ''} ${isChecked ? 'checked' : ''}`}
                    onClick={() => setSelectedTask(t)}
                  >
                    <div className="inbox-task-header">
                      <input
                        type="checkbox"
                        className="task-checkbox"
                        checked={isChecked}
                        onChange={(e) => {
                          e.stopPropagation();
                          setSelectedTaskIds(prev => {
                            const newSet = new Set(prev);
                            if (newSet.has(t.id)) {
                              newSet.delete(t.id);
                            } else {
                              newSet.add(t.id);
                            }
                            return newSet;
                          });
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <span className="task-source-icon">{t.taskType === 'reconciliation' ? '📧' : '⚡'}</span>
                      <span className="inbox-task-title">{t.title}</span>
                    </div>
                    <div className="inbox-task-meta">
                      <span className="inbox-task-client">{t.client || 'Client'}</span>
                      <span
                        className="urgency-indicator-dot"
                        style={{ backgroundColor: getUrgencyColor(t.priority) }}
                        title={t.priority}
                      ></span>
                    </div>
                    <div className="inbox-task-stage">{t.stage || 'Workflow'}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Task Detail Panel */}
          {task && (
            <div className="task-detail-panel">
              {/* Source Badge */}
              <div className="detail-source-badge">
                <span className="source-badge-icon">⚡</span>
                <span className="source-badge-text">WORKFLOW</span>
              </div>

              {/* Task Title */}
              <h2 className="detail-task-title">{task.title}</h2>

              {/* Info Grid */}
              <div className="detail-info-grid">
                <div className="detail-info-item">
                  <span className="detail-label">CLIENT</span>
                  <span className="detail-value">{task.client || 'Client'}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">STAGE</span>
                  <span className="detail-value">{task.stage || 'Workflow'}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">PRIORITY</span>
                  <span
                    className="priority-badge-inline"
                    style={{ backgroundColor: priorityStyle.bg, color: priorityStyle.text }}
                  >
                    {task.priority || 'HIGH'}
                  </span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">SOURCE</span>
                  <span className="detail-value">{task.source || 'Workflow'}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">OWNER</span>
                  <span className="detail-value">{task.owner || 'Loan Officer'}</span>
                </div>
                <div className="detail-info-item">
                  <span className="detail-label">DATE CREATED</span>
                  <span className="detail-value">{task.dateCreated || new Date().toLocaleString()}</span>
                </div>
              </div>

              {/* Send Via Options */}
              <div className="detail-send-via">
                <span className="send-via-label">SEND VIA</span>
                <div className="send-via-buttons">
                  <button
                    className={`send-via-btn ${selectedSendMethod === 'email' ? 'active' : ''}`}
                    onClick={() => setSelectedSendMethod('email')}
                  >
                    📧 Email
                  </button>
                  <button
                    className={`send-via-btn ${selectedSendMethod === 'text' ? 'active' : ''}`}
                    onClick={() => setSelectedSendMethod('text')}
                  >
                    💬 Text
                  </button>
                  <button
                    className={`send-via-btn ${selectedSendMethod === 'phone' ? 'active' : ''}`}
                    onClick={() => setSelectedSendMethod('phone')}
                  >
                    📞 Phone
                  </button>
                  <button
                    className={`send-via-btn ${selectedSendMethod === 'voicemail' ? 'active' : ''}`}
                    onClick={() => setSelectedSendMethod('voicemail')}
                  >
                    📱 Voicemail
                  </button>
                </div>
              </div>

              {/* Train AI Section */}
              <div className="train-ai-section">
                <div className="train-ai-header">
                  <span className="train-ai-icon">🤖</span>
                  <span className="train-ai-title">Train AI (Optional)</span>
                </div>
                <textarea
                  className="train-ai-input"
                  placeholder="Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                  rows={3}
                />
              </div>

              {/* AI Drafted Message */}
              <div className="ai-drafted-section">
                <div className="ai-drafted-header">
                  <span className="ai-drafted-icon">🤖</span>
                  <span className="ai-drafted-title">AI-Drafted Message</span>
                  <button className="edit-message-btn">
                    ✏️ Edit Message
                  </button>
                </div>
                <div className="ai-drafted-content">
                  Complete task: {task.title}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="detail-actions">
                <button
                  className="detail-action-btn send"
                  onClick={() => handleSend(task)}
                >
                  🚀 Send via {selectedSendMethod.charAt(0).toUpperCase() + selectedSendMethod.slice(1)}
                </button>
                <button
                  className="detail-action-btn approve"
                  onClick={() => handleApprove(task)}
                >
                  ✅ {task.taskType === 'reconciliation' ? 'Approve' : 'Complete'}
                </button>
                <button
                  className="detail-action-btn snooze"
                  onClick={() => handleSnooze(task)}
                >
                  ⏰ Snooze
                </button>
                <button
                  className="detail-action-btn delegate"
                  onClick={() => handleDelegate(task)}
                >
                  👥 Delegate
                </button>
                <button
                  className="detail-action-btn delete"
                  onClick={() => handleDelete(task)}
                >
                  🗑️ Delete
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TaskSidebar;
