import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import './WorkflowStagePage.css';

// Status configurations for each stage
const LEAD_STATUSES = {
  new: { name: 'New', color: '#6b7280' },
  attempted_contact: { name: 'Attempted Contact', color: '#f59e0b' },
  prospect: { name: 'Prospect', color: '#3b82f6' },
  application: { name: 'Application', color: '#8b5cf6' },
  pre_qualified: { name: 'Pre-Qualified', color: '#06b6d4' },
  pre_approved: { name: 'Pre-Approved', color: '#10b981' },
  withdrawn: { name: 'Withdrawn', color: '#ef4444' },
  does_not_qualify: { name: 'Does Not Qualify', color: '#dc2626' }
};

const ACTIVE_LOAN_STATUSES = {
  in_processing: { name: 'In Processing', color: '#3b82f6' },
  in_underwriting: { name: 'In Underwriting', color: '#8b5cf6' },
  approved: { name: 'Approved', color: '#10b981' },
  cleared_to_close: { name: 'Cleared to Close', color: '#f59e0b' },
  suspended: { name: 'Suspended', color: '#ef4444' }
};

const PORTFOLIO_STATUSES = {
  closed_funded: { name: 'Closed and Funded', color: '#10b981' }
};

const STAGE_CONFIG = {
  lead: {
    name: 'Lead',
    description: 'Initial contact and qualification workflow',
    color: '#3b82f6',
    statuses: LEAD_STATUSES,
    defaultTasksByStatus: {
      new: [
        { id: 1, title: 'Initial Contact', description: 'Make first contact with lead', order: 1, auto_trigger: 'on_lead_create', days_offset: 0 },
        { id: 2, title: 'Send Introduction Email', description: 'Send welcome email', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      attempted_contact: [
        { id: 3, title: 'Follow-up Call', description: 'Attempt to reach lead again', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 4, title: 'Send Follow-up Email', description: 'Email if no phone response', order: 2, auto_trigger: 'scheduled', days_offset: 1 },
        { id: 5, title: 'Final Attempt', description: 'Last contact attempt', order: 3, auto_trigger: 'scheduled', days_offset: 3 }
      ],
      prospect: [
        { id: 6, title: 'Schedule Discovery Call', description: 'Set up initial consultation', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 7, title: 'Send Loan Options', description: 'Email loan product info', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      application: [
        { id: 8, title: 'Send Application Link', description: 'Email application portal', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 9, title: 'Collect Documents', description: 'Request income and assets', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 10, title: 'Credit Authorization', description: 'Get credit check consent', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      pre_qualified: [
        { id: 11, title: 'Run Credit Check', description: 'Pull credit report', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 12, title: 'Verify Income', description: 'Review income documents', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 13, title: 'Send Pre-Qual Letter', description: 'Email pre-qualification', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      pre_approved: [
        { id: 14, title: 'Generate Pre-Approval', description: 'Create pre-approval letter', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 15, title: 'Send Pre-Approval', description: 'Email to client', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 16, title: 'Convert to Active Loan', description: 'Move to processing', order: 3, auto_trigger: 'manual', days_offset: 0 }
      ],
      withdrawn: [
        { id: 17, title: 'Send Exit Survey', description: 'Request feedback', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 18, title: 'Add to Nurture List', description: 'Future follow-up', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      does_not_qualify: [
        { id: 19, title: 'Send DNQ Letter', description: 'Explain reasons', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 20, title: 'Refer to Resources', description: 'Credit repair/savings tips', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 21, title: 'Schedule Follow-up', description: 'Check back in 6 months', order: 3, auto_trigger: 'scheduled', days_offset: 180 }
      ]
    }
  },
  active_loan: {
    name: 'Active Loan',
    description: 'Loan processing and underwriting workflow',
    color: '#10b981',
    statuses: ACTIVE_LOAN_STATUSES,
    defaultTasksByStatus: {
      in_processing: [
        { id: 22, title: 'Order Appraisal', description: 'Request property appraisal', order: 1, auto_trigger: 'on_conversion', days_offset: 0 },
        { id: 23, title: 'Order Title Search', description: 'Request title work', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 24, title: 'Document Review', description: 'Review all submitted docs', order: 3, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 25, title: 'Request Missing Docs', description: 'Send conditions letter', order: 4, auto_trigger: 'after_previous', days_offset: 1 }
      ],
      in_underwriting: [
        { id: 26, title: 'Submit to UW', description: 'Package file for review', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 27, title: 'Address Conditions', description: 'Clear UW conditions', order: 2, auto_trigger: 'on_conditions', days_offset: 0 },
        { id: 28, title: 'Resubmit to UW', description: 'Send cleared conditions', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      approved: [
        { id: 29, title: 'Final Approval Notice', description: 'Notify client of approval', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 30, title: 'Order Final CD', description: 'Request closing disclosure', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      cleared_to_close: [
        { id: 31, title: 'Schedule Closing', description: 'Coordinate date/location', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 32, title: 'Send Closing Package', description: 'Email final documents', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 33, title: 'Closing Day', description: 'Execute documents', order: 3, auto_trigger: 'on_closing_date', days_offset: 0 },
        { id: 34, title: 'Fund & Record', description: 'Wire funds and record', order: 4, auto_trigger: 'after_previous', days_offset: 1 }
      ],
      suspended: [
        { id: 35, title: 'Notify Client', description: 'Explain suspension reason', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 36, title: 'Create Action Plan', description: 'Steps to resolve issues', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 37, title: 'Weekly Check-in', description: 'Monitor progress', order: 3, auto_trigger: 'scheduled', days_offset: 7 }
      ]
    }
  },
  portfolio: {
    name: 'Portfolio',
    description: 'Post-closing servicing and retention workflow',
    color: '#8b5cf6',
    statuses: PORTFOLIO_STATUSES,
    defaultTasksByStatus: {
      closed_funded: [
        { id: 38, title: 'Welcome Package', description: 'Send welcome materials', order: 1, auto_trigger: 'on_portfolio_add', days_offset: 0 },
        { id: 39, title: '30-Day Check-In', description: 'First payment follow-up', order: 2, auto_trigger: 'scheduled', days_offset: 30 },
        { id: 40, title: '90-Day Review', description: 'Servicing transition check', order: 3, auto_trigger: 'scheduled', days_offset: 90 },
        { id: 41, title: 'Annual Review', description: 'Yearly financial checkup', order: 4, auto_trigger: 'annual', days_offset: 365 },
        { id: 42, title: 'Birthday Outreach', description: 'Send birthday greeting', order: 5, auto_trigger: 'birthday', days_offset: 0 },
        { id: 43, title: 'Loan Anniversary', description: 'Celebrate anniversary', order: 6, auto_trigger: 'anniversary', days_offset: 0 },
        { id: 44, title: 'Refinance Check', description: 'Review for refi opportunity', order: 7, auto_trigger: 'rate_trigger', days_offset: 0 },
        { id: 45, title: 'Referral Request', description: 'Ask for referrals', order: 8, auto_trigger: 'milestone', days_offset: 0 }
      ]
    }
  }
};

const triggerOptions = [
  { value: 'on_lead_create', label: 'On Lead Create' },
  { value: 'on_status_change', label: 'On Status Change' },
  { value: 'after_previous', label: 'After Previous Task' },
  { value: 'manual', label: 'Manual' },
  { value: 'on_conversion', label: 'On Conversion' },
  { value: 'on_conditions', label: 'On Conditions' },
  { value: 'on_closing_date', label: 'On Closing Date' },
  { value: 'on_portfolio_add', label: 'On Portfolio Add' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'annual', label: 'Annual' },
  { value: 'rate_trigger', label: 'Rate Trigger' },
  { value: 'birthday', label: 'Birthday' },
  { value: 'anniversary', label: 'Anniversary' },
  { value: 'milestone', label: 'Milestone' }
];

function WorkflowStagePage() {
  const { stage } = useParams();
  const navigate = useNavigate();
  const [tasksByStatus, setTasksByStatus] = useState({});
  const [selectedStatus, setSelectedStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [editingTask, setEditingTask] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    auto_trigger: 'after_previous',
    days_offset: 0
  });
  const [draggedTask, setDraggedTask] = useState(null);

  const stageConfig = STAGE_CONFIG[stage];
  const statuses = stageConfig?.statuses || {};
  const statusKeys = Object.keys(statuses);
  const tasks = selectedStatus ? (tasksByStatus[selectedStatus] || []) : [];

  useEffect(() => {
    if (!stageConfig) {
      navigate('/settings');
      return;
    }
    // Set default selected status to first one
    if (statusKeys.length > 0 && !selectedStatus) {
      setSelectedStatus(statusKeys[0]);
    }
    loadTasks();
  }, [stage, stageConfig, navigate]);

  const loadTasks = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stage}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setTasksByStatus(data.tasksByStatus || stageConfig.defaultTasksByStatus);
      } else {
        setTasksByStatus(stageConfig.defaultTasksByStatus);
      }
    } catch (error) {
      console.error('Error loading tasks:', error);
      setTasksByStatus(stageConfig.defaultTasksByStatus);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTask = () => {
    if (!newTask.title.trim() || !selectedStatus) return;

    const allTasks = Object.values(tasksByStatus).flat();
    const maxId = Math.max(...allTasks.map(t => t.id), 0);
    const currentTasks = tasksByStatus[selectedStatus] || [];
    const newTaskObj = {
      id: maxId + 1,
      title: newTask.title,
      description: newTask.description,
      order: currentTasks.length + 1,
      auto_trigger: newTask.auto_trigger,
      days_offset: parseInt(newTask.days_offset) || 0
    };

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: [...currentTasks, newTaskObj]
    });
    setNewTask({ title: '', description: '', auto_trigger: 'after_previous', days_offset: 0 });
    setShowAddForm(false);
    setMessage({ type: 'success', text: 'Task added successfully' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleDeleteTask = (taskId) => {
    if (!selectedStatus) return;
    const updatedTasks = tasks
      .filter(t => t.id !== taskId)
      .map((t, idx) => ({ ...t, order: idx + 1 }));

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: updatedTasks
    });
    setMessage({ type: 'success', text: 'Task deleted' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleMoveTask = (taskId, direction) => {
    if (!selectedStatus) return;
    const taskIndex = tasks.findIndex(t => t.id === taskId);
    if (
      (direction === 'up' && taskIndex === 0) ||
      (direction === 'down' && taskIndex === tasks.length - 1)
    ) return;

    const newTasks = [...tasks];
    const swapIndex = direction === 'up' ? taskIndex - 1 : taskIndex + 1;
    [newTasks[taskIndex], newTasks[swapIndex]] = [newTasks[swapIndex], newTasks[taskIndex]];

    const reorderedTasks = newTasks.map((t, idx) => ({ ...t, order: idx + 1 }));
    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: reorderedTasks
    });
  };

  const handleEditTask = (taskId, field, value) => {
    if (!selectedStatus) return;
    const updatedTasks = tasks.map(t =>
      t.id === taskId ? { ...t, [field]: value } : t
    );
    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: updatedTasks
    });
  };

  // Drag and drop handlers
  const handleDragStart = (e, task) => {
    setDraggedTask(task);
    e.dataTransfer.effectAllowed = 'move';
    e.target.style.opacity = '0.5';
  };

  const handleDragEnd = (e) => {
    e.target.style.opacity = '1';
    setDraggedTask(null);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e, targetTask) => {
    e.preventDefault();
    if (!draggedTask || !selectedStatus || draggedTask.id === targetTask.id) return;

    const currentTasks = [...tasks];
    const draggedIndex = currentTasks.findIndex(t => t.id === draggedTask.id);
    const targetIndex = currentTasks.findIndex(t => t.id === targetTask.id);

    // Remove dragged task and insert at target position
    currentTasks.splice(draggedIndex, 1);
    currentTasks.splice(targetIndex, 0, draggedTask);

    // Update order numbers
    const reorderedTasks = currentTasks.map((t, idx) => ({ ...t, order: idx + 1 }));

    setTasksByStatus({
      ...tasksByStatus,
      [selectedStatus]: reorderedTasks
    });
    setDraggedTask(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stage}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ tasksByStatus })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: `${stageConfig.name} workflow saved successfully!` });
      } else {
        setMessage({ type: 'error', text: 'Failed to save workflow' });
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      setMessage({ type: 'error', text: 'Error saving workflow' });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    }
  };

  // Calculate total tasks across all statuses
  const totalTasks = Object.values(tasksByStatus).flat().length;

  if (!stageConfig) {
    return null;
  }

  if (loading) {
    return (
      <div className="workflow-stage-page">
        <div className="loading-state">Loading workflow tasks...</div>
      </div>
    );
  }

  return (
    <div className="workflow-stage-page">
      <div className="stage-page-header" style={{ '--stage-color': stageConfig.color }}>
        <button className="back-button" onClick={() => navigate('/settings')}>
          ← Back to Settings
        </button>
        <div className="header-content">
          <h1>{stageConfig.name} Workflow</h1>
          <p>{stageConfig.description}</p>
          <span className="task-count">{totalTasks} tasks total</span>
        </div>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      {/* Status Tabs */}
      <div className="status-tabs">
        {statusKeys.map(statusKey => (
          <button
            key={statusKey}
            className={`status-tab ${selectedStatus === statusKey ? 'active' : ''}`}
            onClick={() => setSelectedStatus(statusKey)}
            style={{ '--status-color': statuses[statusKey].color }}
          >
            <span className="status-name">{statuses[statusKey].name}</span>
            <span className="status-task-count">{(tasksByStatus[statusKey] || []).length}</span>
          </button>
        ))}
      </div>

      <div className="tasks-container" style={{ '--stage-color': selectedStatus ? statuses[selectedStatus]?.color : stageConfig.color }}>
        <div className="tasks-header">
          <h2>{selectedStatus ? statuses[selectedStatus]?.name : ''} Tasks</h2>
          <div className="header-actions">
            <button className="add-task-btn" onClick={() => setShowAddForm(true)}>
              + Add Task
            </button>
            <button
              className="save-workflow-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save All'}
            </button>
          </div>
        </div>

        <div className="tasks-grid">
          {tasks.map((task, idx) => (
            <div
              key={task.id}
              className={`task-card ${editingTask === task.id ? 'editing' : ''} ${draggedTask?.id === task.id ? 'dragging' : ''}`}
              draggable={editingTask !== task.id}
              onDragStart={(e) => handleDragStart(e, task)}
              onDragEnd={handleDragEnd}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, task)}
              onClick={() => editingTask !== task.id && setEditingTask(task.id)}
            >
              <div className="task-card-header">
                <button
                  className="move-btn"
                  onClick={(e) => { e.stopPropagation(); handleMoveTask(task.id, 'up'); }}
                  disabled={idx === 0}
                >
                  ▲
                </button>
                <span className="order-number">{task.order}</span>
                <button
                  className="move-btn"
                  onClick={(e) => { e.stopPropagation(); handleMoveTask(task.id, 'down'); }}
                  disabled={idx === tasks.length - 1}
                >
                  ▼
                </button>
              </div>

              {editingTask === task.id ? (
                <div className="task-edit-form expanded" onClick={(e) => e.stopPropagation()}>
                  <div className="edit-form-group">
                    <label>Owner</label>
                    <select
                      value={task.owner || ''}
                      onChange={(e) => handleEditTask(task.id, 'owner', e.target.value)}
                    >
                      <option value="">Select Owner</option>
                      <option value="loan_officer">Loan Officer</option>
                      <option value="processor">Processor</option>
                      <option value="underwriter">Underwriter</option>
                      <option value="closer">Closer</option>
                      <option value="system">System (Auto)</option>
                    </select>
                  </div>
                  <div className="edit-form-group">
                    <label>Task Name</label>
                    <input
                      type="text"
                      value={task.title}
                      onChange={(e) => handleEditTask(task.id, 'title', e.target.value)}
                      placeholder="Task title"
                    />
                  </div>
                  <div className="edit-form-group">
                    <label>Description</label>
                    <textarea
                      value={task.description}
                      onChange={(e) => handleEditTask(task.id, 'description', e.target.value)}
                      placeholder="Detailed description of the task..."
                      rows={4}
                    />
                  </div>
                  <div className="edit-form-group">
                    <label>Activation Trigger</label>
                    <select
                      value={task.auto_trigger}
                      onChange={(e) => handleEditTask(task.id, 'auto_trigger', e.target.value)}
                    >
                      {triggerOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="edit-form-row">
                    <div className="edit-form-group">
                      <label>Days Offset</label>
                      <input
                        type="number"
                        value={task.days_offset}
                        onChange={(e) => handleEditTask(task.id, 'days_offset', parseInt(e.target.value) || 0)}
                        min="0"
                        placeholder="0"
                      />
                    </div>
                    <div className="edit-form-group">
                      <label>Time of Day</label>
                      <select
                        value={task.activation_time || '09:00'}
                        onChange={(e) => handleEditTask(task.id, 'activation_time', e.target.value)}
                      >
                        <option value="08:00">8:00 AM</option>
                        <option value="09:00">9:00 AM</option>
                        <option value="10:00">10:00 AM</option>
                        <option value="11:00">11:00 AM</option>
                        <option value="12:00">12:00 PM</option>
                        <option value="13:00">1:00 PM</option>
                        <option value="14:00">2:00 PM</option>
                        <option value="15:00">3:00 PM</option>
                        <option value="16:00">4:00 PM</option>
                        <option value="17:00">5:00 PM</option>
                      </select>
                    </div>
                  </div>
                  <div className="edit-form-actions">
                    <button
                      className="delete-task-btn"
                      onClick={() => handleDeleteTask(task.id)}
                    >
                      Delete
                    </button>
                    <button className="done-edit-btn" onClick={() => setEditingTask(null)}>
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                <div className="task-card-title">
                  {task.title}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Add Task Modal */}
        {showAddForm && (
          <div className="modal-overlay" onClick={() => setShowAddForm(false)}>
            <div className="add-task-modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Add New Task</h3>
                <button className="close-modal" onClick={() => setShowAddForm(false)}>×</button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label>Title *</label>
                  <input
                    type="text"
                    value={newTask.title}
                    onChange={(e) => setNewTask(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="Task title"
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    value={newTask.description}
                    onChange={(e) => setNewTask(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Task description"
                    rows={3}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Trigger</label>
                    <select
                      value={newTask.auto_trigger}
                      onChange={(e) => setNewTask(prev => ({ ...prev, auto_trigger: e.target.value }))}
                    >
                      {triggerOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Days Offset</label>
                    <input
                      type="number"
                      value={newTask.days_offset}
                      onChange={(e) => setNewTask(prev => ({ ...prev, days_offset: e.target.value }))}
                      min="0"
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button className="cancel-btn" onClick={() => setShowAddForm(false)}>Cancel</button>
                <button
                  className="add-btn"
                  onClick={handleAddTask}
                  disabled={!newTask.title.trim()}
                >
                  Add Task
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkflowStagePage;
