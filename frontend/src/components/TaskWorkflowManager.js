import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import './TaskWorkflowManager.css';

function TaskWorkflowManager() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [activeStage] = useState(null);
  const [viewMode, setViewMode] = useState('team'); // 'team' or 'edit'
  const [editingTask, setEditingTask] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    auto_trigger: 'after_previous',
    days_offset: 0,
    owner_id: '',
    activation_time: ''
  });

  // Team members with their workflow progress (will be loaded from API)
  const [teamMembers, setTeamMembers] = useState([]);

  // Users list for owner dropdown
  const [users, setUsers] = useState([]);

  // Workflow stages with their tasks
  const [workflowStages, setWorkflowStages] = useState({
    lead: {
      name: 'Lead',
      description: 'Initial contact and qualification workflow',
      color: '#3b82f6',
      tasks: [
        { id: 1, title: 'Initial Contact', description: 'Make first contact with lead', order: 1, auto_trigger: 'on_lead_create', days_offset: 0 },
        { id: 2, title: 'Send Introduction Email', description: 'Send welcome email with information', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 3, title: 'Schedule Discovery Call', description: 'Set up initial consultation', order: 3, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 4, title: 'Pre-Qualification Check', description: 'Verify basic qualification criteria', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 5, title: 'Collect Documents', description: 'Request income, assets, and ID documents', order: 5, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 6, title: 'Credit Pull Authorization', description: 'Get authorization for credit check', order: 6, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 7, title: 'Generate Pre-Approval Letter', description: 'Create pre-approval documentation', order: 7, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 8, title: 'Convert to Active Loan', description: 'Move to active loan processing', order: 8, auto_trigger: 'manual', days_offset: 0 }
      ]
    },
    active_loan: {
      name: 'Active Loan',
      description: 'Loan processing and underwriting workflow',
      color: '#10b981',
      tasks: [
        { id: 9, title: 'Application Submitted', description: 'Formal loan application received', order: 1, auto_trigger: 'on_conversion', days_offset: 0 },
        { id: 10, title: 'Order Appraisal', description: 'Request property appraisal', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 11, title: 'Title Search', description: 'Order title search and insurance', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 12, title: 'Submit to Underwriting', description: 'Package file for underwriter review', order: 4, auto_trigger: 'after_previous', days_offset: 2 },
        { id: 13, title: 'Address Conditions', description: 'Clear underwriting conditions', order: 5, auto_trigger: 'on_conditions', days_offset: 0 },
        { id: 14, title: 'Final Approval', description: 'Obtain clear to close', order: 6, auto_trigger: 'after_previous', days_offset: 3 },
        { id: 15, title: 'Schedule Closing', description: 'Coordinate closing date and location', order: 7, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 16, title: 'Closing Day', description: 'Execute closing documents', order: 8, auto_trigger: 'on_closing_date', days_offset: 0 },
        { id: 17, title: 'Fund Loan', description: 'Wire funds and record documents', order: 9, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 18, title: 'Move to Portfolio', description: 'Transfer to servicing/portfolio', order: 10, auto_trigger: 'after_previous', days_offset: 3 }
      ]
    },
    portfolio: {
      name: 'Portfolio',
      description: 'Post-closing servicing and retention workflow',
      color: '#8b5cf6',
      tasks: [
        { id: 19, title: 'Welcome to Portfolio', description: 'Send post-closing welcome package', order: 1, auto_trigger: 'on_portfolio_add', days_offset: 0 },
        { id: 20, title: '30-Day Check-In', description: 'First payment follow-up call', order: 2, auto_trigger: 'scheduled', days_offset: 30 },
        { id: 21, title: '90-Day Review', description: 'Ensure smooth servicing transition', order: 3, auto_trigger: 'scheduled', days_offset: 90 },
        { id: 22, title: 'Annual Review', description: 'Yearly financial checkup', order: 4, auto_trigger: 'annual', days_offset: 365 },
        { id: 23, title: 'Refinance Opportunity Check', description: 'Review for refinance potential', order: 5, auto_trigger: 'rate_trigger', days_offset: 0 },
        { id: 24, title: 'Birthday Outreach', description: 'Send birthday greeting', order: 6, auto_trigger: 'birthday', days_offset: 0 },
        { id: 25, title: 'Loan Anniversary', description: 'Celebrate loan anniversary', order: 7, auto_trigger: 'anniversary', days_offset: 0 },
        { id: 26, title: 'Referral Request', description: 'Ask for referrals at key moments', order: 8, auto_trigger: 'milestone', days_offset: 0 }
      ]
    }
  });

  useEffect(() => {
    loadWorkflowStages();
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/users`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data.users || data || []);
      }
    } catch (error) {
      console.error('Error loading users:', error);
    }
  };

  useEffect(() => {
    if (activeStage && viewMode === 'team') {
      loadTeamMembersForStage(activeStage);
    }
  }, [activeStage, viewMode]);

  const loadTeamMembersForStage = async (stageKey) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stageKey}/team-members`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || []);
      } else {
        setTeamMembers([]);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
      setTeamMembers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadWorkflowStages = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        if (data.stages) {
          setWorkflowStages(data.stages);
        }
      }
    } catch (error) {
      console.error('Error loading workflow stages:', error);
    }
  };

  const handleAddTask = (stageKey) => {
    if (!newTask.title.trim()) return;

    const stage = workflowStages[stageKey];
    const maxId = Math.max(...Object.values(workflowStages).flatMap(s => s.tasks.map(t => t.id)), 0);
    const newTaskObj = {
      id: maxId + 1,
      title: newTask.title,
      description: newTask.description,
      order: stage.tasks.length + 1,
      auto_trigger: newTask.auto_trigger,
      days_offset: parseInt(newTask.days_offset) || 0,
      owner_id: newTask.owner_id || null,
      activation_time: newTask.activation_time || null
    };

    setWorkflowStages(prev => ({
      ...prev,
      [stageKey]: {
        ...prev[stageKey],
        tasks: [...prev[stageKey].tasks, newTaskObj]
      }
    }));

    setNewTask({ title: '', description: '', auto_trigger: 'after_previous', days_offset: 0, owner_id: '', activation_time: '' });
    setShowAddForm(false);
    setMessage({ type: 'success', text: 'Task added successfully' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleDeleteTask = (stageKey, taskId) => {
    setWorkflowStages(prev => ({
      ...prev,
      [stageKey]: {
        ...prev[stageKey],
        tasks: prev[stageKey].tasks
          .filter(t => t.id !== taskId)
          .map((t, idx) => ({ ...t, order: idx + 1 }))
      }
    }));
    setMessage({ type: 'success', text: 'Task deleted' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleMoveTask = (stageKey, taskId, direction) => {
    const stage = workflowStages[stageKey];
    const taskIndex = stage.tasks.findIndex(t => t.id === taskId);
    if (
      (direction === 'up' && taskIndex === 0) ||
      (direction === 'down' && taskIndex === stage.tasks.length - 1)
    ) return;

    const newTasks = [...stage.tasks];
    const swapIndex = direction === 'up' ? taskIndex - 1 : taskIndex + 1;
    [newTasks[taskIndex], newTasks[swapIndex]] = [newTasks[swapIndex], newTasks[taskIndex]];

    // Update order numbers
    const reorderedTasks = newTasks.map((t, idx) => ({ ...t, order: idx + 1 }));

    setWorkflowStages(prev => ({
      ...prev,
      [stageKey]: {
        ...prev[stageKey],
        tasks: reorderedTasks
      }
    }));
  };

  const handleEditTask = (stageKey, taskId, field, value) => {
    setWorkflowStages(prev => ({
      ...prev,
      [stageKey]: {
        ...prev[stageKey],
        tasks: prev[stageKey].tasks.map(t =>
          t.id === taskId ? { ...t, [field]: value } : t
        )
      }
    }));
  };

  const handleSaveWorkflow = async (stageKey) => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stageKey}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tasks: workflowStages[stageKey].tasks
        })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: `${workflowStages[stageKey].name} workflow saved successfully!` });
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

  const triggerOptions = [
    { value: 'on_lead_create', label: 'On Lead Create' },
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

  return (
    <div className="task-workflow-manager">
      <div className="manager-header">
        <h2>Workflow Management</h2>
        <p>Configure automated workflows for each stage of the client lifecycle</p>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      {/* Stage Overview Cards */}
      <div className="workflow-stages-grid">
        {Object.entries(workflowStages).map(([key, stage]) => (
          <div
            key={key}
            className={`stage-card ${activeStage === key ? 'active' : ''}`}
            style={{ '--stage-color': stage.color }}
          >
            <div className="stage-header" onClick={() => navigate(`/workflow/${key}`)}>
              <div className="stage-title">
                <h3>{stage.name}</h3>
              </div>
              <div className="stage-meta">
                <span className="task-count">{stage.tasks.length} tasks</span>
                <span className="expand-icon">▶</span>
              </div>
            </div>
            <p className="stage-description">{stage.description}</p>

            {/* Collapsed Preview */}
            {activeStage !== key && (
              <div className="stage-preview">
                <div className="preview-tasks">
                  {stage.tasks.slice(0, 3).map((task, idx) => (
                    <div key={task.id} className="preview-task">
                      <span className="task-number">{idx + 1}</span>
                      <span className="task-name">{task.title}</span>
                    </div>
                  ))}
                  {stage.tasks.length > 3 && (
                    <div className="preview-more">+{stage.tasks.length - 3} more tasks</div>
                  )}
                </div>
              </div>
            )}

            {/* Expanded View */}
            {activeStage === key && (
              <div className="stage-tasks-expanded">
                {/* View Mode Toggle */}
                <div className="view-mode-toggle">
                  <button
                    className={viewMode === 'team' ? 'active' : ''}
                    onClick={() => setViewMode('team')}
                  >
                    Team Progress
                  </button>
                  <button
                    className={viewMode === 'edit' ? 'active' : ''}
                    onClick={() => setViewMode('edit')}
                  >
                    Edit Tasks
                  </button>
                </div>

                {/* Team View */}
                {viewMode === 'team' && (
                  <>
                    {loading ? (
                      <div className="loading-state">Loading team members...</div>
                    ) : teamMembers.length === 0 ? (
                      <div className="empty-state">No team members with {stage.name.toLowerCase()}s</div>
                    ) : (
                      <div className="team-members-list">
                        {teamMembers.map((member) => (
                          <div key={member.id} className="team-member-card">
                            <div className="member-header">
                              <div className="member-info">
                                <div className="member-avatar">
                                  {member.avatar ? (
                                    <img src={member.avatar} alt={member.name} />
                                  ) : (
                                    <span>{(member.name || '?').split(' ').map(n => n[0]).join('')}</span>
                                  )}
                                </div>
                                <div className="member-details">
                                  <strong>{member.name}</strong>
                                  <span className="member-role">{member.role}</span>
                                </div>
                              </div>
                              <div className="member-count">
                                <span className="count-value">{member.count}</span>
                                <span className="count-label">{stage.name.toLowerCase()}s</span>
                              </div>
                            </div>
                            <div className="member-workflow">
                              <div className="workflow-progress">
                                {member.tasks.map((task) => (
                                  <div
                                    key={task.id}
                                    className={`workflow-step ${task.status}`}
                                    title={`${task.title} - ${task.status}`}
                                  >
                                    <div className="step-indicator">
                                      {task.status === 'completed' ? '✓' : task.status === 'in_progress' ? '●' : '○'}
                                    </div>
                                  </div>
                                ))}
                              </div>
                              <div className="workflow-summary">
                                <span className="completed-count">
                                  {member.tasks.filter(t => t.status === 'completed').length}/{member.tasks.length} completed
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}

                {/* Edit View */}
                {viewMode === 'edit' && (
                  <>
                    <div className="tasks-list">
                      {stage.tasks.map((task, idx) => (
                        <div key={task.id} className="task-item">
                          <div className="task-order">
                            <button
                              className="move-btn"
                              onClick={() => handleMoveTask(key, task.id, 'up')}
                              disabled={idx === 0}
                            >
                              ▲
                            </button>
                            <span>{task.order}</span>
                            <button
                              className="move-btn"
                              onClick={() => handleMoveTask(key, task.id, 'down')}
                              disabled={idx === stage.tasks.length - 1}
                            >
                              ▼
                            </button>
                          </div>
                          <div className="task-content">
                            {editingTask === task.id ? (
                              <div className="task-edit-form expanded-popup">
                                <div className="form-group">
                                  <label>Owner</label>
                                  <select
                                    value={task.owner_id || ''}
                                    onChange={(e) => handleEditTask(key, task.id, 'owner_id', e.target.value || null)}
                                  >
                                    <option value="">Select Owner</option>
                                    {users.map(user => (
                                      <option key={user.id} value={user.id}>
                                        {user.name || user.email}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <div className="form-group">
                                  <label>Task Name</label>
                                  <input
                                    type="text"
                                    value={task.title}
                                    onChange={(e) => handleEditTask(key, task.id, 'title', e.target.value)}
                                    placeholder="Task title"
                                  />
                                </div>
                                <div className="form-group">
                                  <label>Description</label>
                                  <textarea
                                    value={task.description}
                                    onChange={(e) => handleEditTask(key, task.id, 'description', e.target.value)}
                                    placeholder="Describe the task in detail..."
                                    rows={3}
                                  />
                                </div>
                                <div className="form-row">
                                  <div className="form-group">
                                    <label>Trigger</label>
                                    <select
                                      value={task.auto_trigger}
                                      onChange={(e) => handleEditTask(key, task.id, 'auto_trigger', e.target.value)}
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
                                      value={task.days_offset}
                                      onChange={(e) => handleEditTask(key, task.id, 'days_offset', parseInt(e.target.value) || 0)}
                                      min="0"
                                      placeholder="Days"
                                    />
                                  </div>
                                </div>
                                <div className="form-group">
                                  <label>Activation Time</label>
                                  <input
                                    type="time"
                                    value={task.activation_time || ''}
                                    onChange={(e) => handleEditTask(key, task.id, 'activation_time', e.target.value)}
                                    placeholder="When task activates"
                                  />
                                </div>
                                <button className="done-edit-btn" onClick={() => setEditingTask(null)}>
                                  Done
                                </button>
                              </div>
                            ) : (
                              <>
                                <div className="task-title-row">
                                  <strong>{task.title}</strong>
                                  <span className="trigger-badge">{task.auto_trigger}</span>
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
                              className="remove-task-btn"
                              onClick={() => handleDeleteTask(key, task.id)}
                              title="Delete task"
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Add Task Form */}
                    {showAddForm ? (
                      <div className="add-task-form expanded-popup">
                        <h4>Add New Task</h4>
                        <div className="form-group">
                          <label>Owner</label>
                          <select
                            value={newTask.owner_id}
                            onChange={(e) => setNewTask(prev => ({ ...prev, owner_id: e.target.value }))}
                          >
                            <option value="">Select Owner</option>
                            {users.map(user => (
                              <option key={user.id} value={user.id}>
                                {user.name || user.email}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="form-group">
                          <label>Task Name</label>
                          <input
                            type="text"
                            value={newTask.title}
                            onChange={(e) => setNewTask(prev => ({ ...prev, title: e.target.value }))}
                            placeholder="Task title"
                          />
                        </div>
                        <div className="form-group">
                          <label>Description</label>
                          <textarea
                            value={newTask.description}
                            onChange={(e) => setNewTask(prev => ({ ...prev, description: e.target.value }))}
                            placeholder="Describe the task in detail..."
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
                        <div className="form-group">
                          <label>Activation Time</label>
                          <input
                            type="time"
                            value={newTask.activation_time}
                            onChange={(e) => setNewTask(prev => ({ ...prev, activation_time: e.target.value }))}
                            placeholder="When task activates"
                          />
                        </div>
                        <div className="form-actions">
                          <button className="cancel-btn" onClick={() => setShowAddForm(false)}>Cancel</button>
                          <button
                            className="add-btn"
                            onClick={() => handleAddTask(key)}
                            disabled={!newTask.title.trim()}
                          >
                            Add Task
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button className="add-task-btn" onClick={() => setShowAddForm(true)}>
                        + Add Task
                      </button>
                    )}

                    {/* Save Button */}
                    <div className="stage-actions">
                      <button
                        className="save-workflow-btn"
                        onClick={() => handleSaveWorkflow(key)}
                        disabled={saving}
                      >
                        {saving ? 'Saving...' : 'Save Workflow'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Workflow Flow Visualization */}
      <div className="workflow-flow-section">
        <h3>Client Lifecycle Flow</h3>
        <div className="flow-visualization">
          <div className="flow-stage" style={{ '--stage-color': workflowStages.lead.color }}>
            <span>Lead</span>
            <small>{workflowStages.lead.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.active_loan.color }}>
            <span>Active Loan</span>
            <small>{workflowStages.active_loan.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.portfolio.color }}>
            <span>Portfolio</span>
            <small>{workflowStages.portfolio.tasks.length} tasks</small>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="workflow-stats">
        <div className="stat-card">
          <span className="stat-value">
            {Object.values(workflowStages).reduce((sum, stage) => sum + stage.tasks.length, 0)}
          </span>
          <span className="stat-label">Total Tasks</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">3</span>
          <span className="stat-label">Workflow Stages</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {Object.values(workflowStages).reduce((sum, stage) =>
              sum + stage.tasks.filter(t => t.auto_trigger !== 'manual').length, 0
            )}
          </span>
          <span className="stat-label">Automated Tasks</span>
        </div>
      </div>
    </div>
  );
}

export default TaskWorkflowManager;
