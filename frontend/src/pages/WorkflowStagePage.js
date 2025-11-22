import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import './WorkflowStagePage.css';

// Status configurations for each stage
const LEAD_STATUSES = {
  new: { name: 'New', color: '#6b7280' },
  contacted: { name: 'Contacted', color: '#3b82f6' },
  qualified: { name: 'Qualified', color: '#8b5cf6' },
  pre_approved: { name: 'Pre-Approved', color: '#10b981' },
  nurturing: { name: 'Nurturing', color: '#f59e0b' }
};

const ACTIVE_LOAN_STATUSES = {
  application: { name: 'Application', color: '#6b7280' },
  processing: { name: 'Processing', color: '#3b82f6' },
  underwriting: { name: 'Underwriting', color: '#8b5cf6' },
  approved: { name: 'Approved', color: '#10b981' },
  closing: { name: 'Closing', color: '#f59e0b' }
};

const PORTFOLIO_STATUSES = {
  onboarding: { name: 'Onboarding', color: '#6b7280' },
  active: { name: 'Active', color: '#10b981' },
  review: { name: 'Review', color: '#f59e0b' },
  refinance: { name: 'Refinance Opportunity', color: '#8b5cf6' }
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
      contacted: [
        { id: 3, title: 'Schedule Discovery Call', description: 'Set up initial consultation', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 4, title: 'Send Follow-up', description: 'Follow up if no response', order: 2, auto_trigger: 'scheduled', days_offset: 2 }
      ],
      qualified: [
        { id: 5, title: 'Pre-Qualification Check', description: 'Verify qualification criteria', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 6, title: 'Collect Documents', description: 'Request income and assets docs', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 7, title: 'Credit Authorization', description: 'Get credit check authorization', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      pre_approved: [
        { id: 8, title: 'Generate Pre-Approval', description: 'Create pre-approval letter', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 9, title: 'Send Pre-Approval', description: 'Email pre-approval to client', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 10, title: 'Convert to Active Loan', description: 'Move to loan processing', order: 3, auto_trigger: 'manual', days_offset: 0 }
      ],
      nurturing: [
        { id: 11, title: 'Add to Drip Campaign', description: 'Start nurture sequence', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 12, title: 'Monthly Check-in', description: 'Periodic follow-up call', order: 2, auto_trigger: 'scheduled', days_offset: 30 },
        { id: 13, title: 'Rate Alert', description: 'Notify when rates favorable', order: 3, auto_trigger: 'rate_trigger', days_offset: 0 }
      ]
    }
  },
  active_loan: {
    name: 'Active Loan',
    description: 'Loan processing and underwriting workflow',
    color: '#10b981',
    statuses: ACTIVE_LOAN_STATUSES,
    defaultTasksByStatus: {
      application: [
        { id: 14, title: 'Application Received', description: 'Formal application submitted', order: 1, auto_trigger: 'on_conversion', days_offset: 0 },
        { id: 15, title: 'Order Appraisal', description: 'Request property appraisal', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 16, title: 'Title Search', description: 'Order title search', order: 3, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      processing: [
        { id: 17, title: 'Document Review', description: 'Review all submitted docs', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 18, title: 'Request Missing Docs', description: 'Send conditions letter', order: 2, auto_trigger: 'after_previous', days_offset: 1 }
      ],
      underwriting: [
        { id: 19, title: 'Submit to UW', description: 'Package file for review', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 20, title: 'Address Conditions', description: 'Clear UW conditions', order: 2, auto_trigger: 'on_conditions', days_offset: 0 }
      ],
      approved: [
        { id: 21, title: 'Clear to Close', description: 'Final approval obtained', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 22, title: 'Final CD Review', description: 'Review closing disclosure', order: 2, auto_trigger: 'after_previous', days_offset: 0 }
      ],
      closing: [
        { id: 23, title: 'Schedule Closing', description: 'Coordinate date/location', order: 1, auto_trigger: 'on_status_change', days_offset: 0 },
        { id: 24, title: 'Closing Day', description: 'Execute documents', order: 2, auto_trigger: 'on_closing_date', days_offset: 0 },
        { id: 25, title: 'Fund & Record', description: 'Wire funds', order: 3, auto_trigger: 'after_previous', days_offset: 1 }
      ]
    }
  },
  portfolio: {
    name: 'Portfolio',
    description: 'Post-closing servicing and retention workflow',
    color: '#8b5cf6',
    statuses: PORTFOLIO_STATUSES,
    defaultTasksByStatus: {
      onboarding: [
        { id: 26, title: 'Welcome Package', description: 'Send welcome materials', order: 1, auto_trigger: 'on_portfolio_add', days_offset: 0 },
        { id: 27, title: '30-Day Check-In', description: 'First payment follow-up', order: 2, auto_trigger: 'scheduled', days_offset: 30 }
      ],
      active: [
        { id: 28, title: '90-Day Review', description: 'Servicing transition check', order: 1, auto_trigger: 'scheduled', days_offset: 90 },
        { id: 29, title: 'Annual Review', description: 'Yearly checkup', order: 2, auto_trigger: 'annual', days_offset: 365 },
        { id: 30, title: 'Birthday Outreach', description: 'Send greeting', order: 3, auto_trigger: 'birthday', days_offset: 0 }
      ],
      review: [
        { id: 31, title: 'Loan Anniversary', description: 'Celebrate anniversary', order: 1, auto_trigger: 'anniversary', days_offset: 0 },
        { id: 32, title: 'Referral Request', description: 'Ask for referrals', order: 2, auto_trigger: 'milestone', days_offset: 0 }
      ],
      refinance: [
        { id: 33, title: 'Rate Check', description: 'Review rates', order: 1, auto_trigger: 'rate_trigger', days_offset: 0 },
        { id: 34, title: 'Refinance Proposal', description: 'Send savings analysis', order: 2, auto_trigger: 'after_previous', days_offset: 1 }
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

        <div className="tasks-list">
          {tasks.map((task, idx) => (
            <div key={task.id} className="task-item">
              <div className="task-order">
                <button
                  className="move-btn"
                  onClick={() => handleMoveTask(task.id, 'up')}
                  disabled={idx === 0}
                >
                  ▲
                </button>
                <span className="order-number">{task.order}</span>
                <button
                  className="move-btn"
                  onClick={() => handleMoveTask(task.id, 'down')}
                  disabled={idx === tasks.length - 1}
                >
                  ▼
                </button>
              </div>

              <div className="task-content">
                {editingTask === task.id ? (
                  <div className="task-edit-form">
                    <input
                      type="text"
                      value={task.title}
                      onChange={(e) => handleEditTask(task.id, 'title', e.target.value)}
                      placeholder="Task title"
                    />
                    <textarea
                      value={task.description}
                      onChange={(e) => handleEditTask(task.id, 'description', e.target.value)}
                      placeholder="Description"
                      rows={2}
                    />
                    <div className="form-row">
                      <select
                        value={task.auto_trigger}
                        onChange={(e) => handleEditTask(task.id, 'auto_trigger', e.target.value)}
                      >
                        {triggerOptions.map(opt => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                      <input
                        type="number"
                        value={task.days_offset}
                        onChange={(e) => handleEditTask(task.id, 'days_offset', parseInt(e.target.value) || 0)}
                        min="0"
                        placeholder="Days"
                      />
                    </div>
                    <button className="done-edit-btn" onClick={() => setEditingTask(null)}>
                      Done Editing
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="task-title-row">
                      <strong>{task.title}</strong>
                      <span className="trigger-badge" data-trigger={task.auto_trigger}>
                        {task.auto_trigger.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="task-desc">{task.description}</p>
                    {task.days_offset > 0 && (
                      <span className="days-offset">+{task.days_offset} days</span>
                    )}
                  </>
                )}
              </div>

              <div className="task-actions">
                <button
                  className="edit-task-btn"
                  onClick={() => setEditingTask(editingTask === task.id ? null : task.id)}
                  title="Edit task"
                >
                  ✎
                </button>
                <button
                  className="delete-task-btn"
                  onClick={() => handleDeleteTask(task.id)}
                  title="Delete task"
                >
                  ×
                </button>
              </div>
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
