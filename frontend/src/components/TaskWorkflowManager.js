import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './TaskWorkflowManager.css';

function TaskWorkflowManager() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [activeStage, setActiveStage] = useState(null); // For editing a stage
  const [showAddTask, setShowAddTask] = useState(false);

  // Workflow stages with their tasks
  const [workflowStages, setWorkflowStages] = useState({
    lead: {
      name: 'Lead',
      description: 'Initial contact and qualification workflow',
      color: '#3b82f6',
      icon: '🎯',
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
      icon: '📋',
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
      icon: '💼',
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

  // New task form state
  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    order: 1,
    auto_trigger: 'after_previous',
    days_offset: 0
  });

  useEffect(() => {
    loadWorkflowStages();
  }, []);

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
      // Keep default stages if API fails
    }
  };

  const saveWorkflowStage = async (stageKey) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stageKey}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(workflowStages[stageKey])
      });
      if (response.ok) {
        setMessage({ type: 'success', text: `${workflowStages[stageKey].name} workflow saved successfully` });
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to save workflow' });
      }
    } catch (error) {
      console.error('Error saving workflow:', error);
      setMessage({ type: 'error', text: 'Failed to save workflow' });
    } finally {
      setLoading(false);
    }
  };

  const addTaskToStage = (stageKey) => {
    const stage = workflowStages[stageKey];
    const newTaskId = Math.max(...stage.tasks.map(t => t.id), 0) + 1;
    const newOrder = stage.tasks.length + 1;

    const taskToAdd = {
      ...newTask,
      id: newTaskId,
      order: newOrder
    };

    setWorkflowStages({
      ...workflowStages,
      [stageKey]: {
        ...stage,
        tasks: [...stage.tasks, taskToAdd]
      }
    });

    setNewTask({
      title: '',
      description: '',
      order: 1,
      auto_trigger: 'after_previous',
      days_offset: 0
    });
    setShowAddTask(false);
    setMessage({ type: 'success', text: 'Task added to workflow' });
  };

  const removeTaskFromStage = (stageKey, taskId) => {
    const stage = workflowStages[stageKey];
    const updatedTasks = stage.tasks
      .filter(t => t.id !== taskId)
      .map((t, idx) => ({ ...t, order: idx + 1 }));

    setWorkflowStages({
      ...workflowStages,
      [stageKey]: {
        ...stage,
        tasks: updatedTasks
      }
    });
  };

  const moveTask = (stageKey, taskId, direction) => {
    const stage = workflowStages[stageKey];
    const taskIndex = stage.tasks.findIndex(t => t.id === taskId);

    if (
      (direction === 'up' && taskIndex === 0) ||
      (direction === 'down' && taskIndex === stage.tasks.length - 1)
    ) {
      return;
    }

    const newTasks = [...stage.tasks];
    const swapIndex = direction === 'up' ? taskIndex - 1 : taskIndex + 1;
    [newTasks[taskIndex], newTasks[swapIndex]] = [newTasks[swapIndex], newTasks[taskIndex]];

    // Update order numbers
    const reorderedTasks = newTasks.map((t, idx) => ({ ...t, order: idx + 1 }));

    setWorkflowStages({
      ...workflowStages,
      [stageKey]: {
        ...stage,
        tasks: reorderedTasks
      }
    });
  };

  const getTriggerLabel = (trigger) => {
    const labels = {
      'on_lead_create': 'On Lead Create',
      'on_conversion': 'On Conversion',
      'on_portfolio_add': 'On Portfolio Add',
      'after_previous': 'After Previous',
      'manual': 'Manual',
      'scheduled': 'Scheduled',
      'annual': 'Annual',
      'rate_trigger': 'Rate Trigger',
      'birthday': 'Birthday',
      'anniversary': 'Anniversary',
      'milestone': 'Milestone',
      'on_conditions': 'On Conditions',
      'on_closing_date': 'On Closing Date'
    };
    return labels[trigger] || trigger;
  };

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
            <div className="stage-header" onClick={() => setActiveStage(activeStage === key ? null : key)}>
              <div className="stage-title">
                <span className="stage-icon">{stage.icon}</span>
                <h3>{stage.name}</h3>
              </div>
              <div className="stage-meta">
                <span className="task-count">{stage.tasks.length} tasks</span>
                <span className="expand-icon">{activeStage === key ? '▼' : '▶'}</span>
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

            {/* Expanded Task List */}
            {activeStage === key && (
              <div className="stage-tasks-expanded">
                <div className="tasks-list">
                  {stage.tasks.map((task, idx) => (
                    <div key={task.id} className="task-item">
                      <div className="task-order">
                        <button
                          className="move-btn"
                          onClick={() => moveTask(key, task.id, 'up')}
                          disabled={idx === 0}
                        >
                          ↑
                        </button>
                        <span>{task.order}</span>
                        <button
                          className="move-btn"
                          onClick={() => moveTask(key, task.id, 'down')}
                          disabled={idx === stage.tasks.length - 1}
                        >
                          ↓
                        </button>
                      </div>
                      <div className="task-content">
                        <div className="task-title-row">
                          <strong>{task.title}</strong>
                          <span className="trigger-badge">{getTriggerLabel(task.auto_trigger)}</span>
                        </div>
                        <p className="task-desc">{task.description}</p>
                        {task.days_offset > 0 && (
                          <span className="days-offset">+{task.days_offset} days</span>
                        )}
                      </div>
                      <button
                        className="remove-task-btn"
                        onClick={() => removeTaskFromStage(key, task.id)}
                        title="Remove task"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add Task Form */}
                {showAddTask && activeStage === key ? (
                  <div className="add-task-form">
                    <h4>Add New Task</h4>
                    <div className="form-group">
                      <label>Task Title</label>
                      <input
                        type="text"
                        value={newTask.title}
                        onChange={(e) => setNewTask({...newTask, title: e.target.value})}
                        placeholder="Enter task title..."
                      />
                    </div>
                    <div className="form-group">
                      <label>Description</label>
                      <textarea
                        value={newTask.description}
                        onChange={(e) => setNewTask({...newTask, description: e.target.value})}
                        placeholder="Enter task description..."
                        rows="2"
                      />
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label>Trigger</label>
                        <select
                          value={newTask.auto_trigger}
                          onChange={(e) => setNewTask({...newTask, auto_trigger: e.target.value})}
                        >
                          <option value="after_previous">After Previous</option>
                          <option value="manual">Manual</option>
                          <option value="scheduled">Scheduled</option>
                          <option value="on_lead_create">On Lead Create</option>
                          <option value="on_conversion">On Conversion</option>
                          <option value="on_portfolio_add">On Portfolio Add</option>
                          <option value="on_conditions">On Conditions</option>
                          <option value="on_closing_date">On Closing Date</option>
                          <option value="annual">Annual</option>
                          <option value="birthday">Birthday</option>
                          <option value="anniversary">Anniversary</option>
                          <option value="milestone">Milestone</option>
                          <option value="rate_trigger">Rate Trigger</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Days Offset</label>
                        <input
                          type="number"
                          value={newTask.days_offset}
                          onChange={(e) => setNewTask({...newTask, days_offset: parseInt(e.target.value) || 0})}
                          min="0"
                        />
                      </div>
                    </div>
                    <div className="form-actions">
                      <button
                        className="cancel-btn"
                        onClick={() => setShowAddTask(false)}
                      >
                        Cancel
                      </button>
                      <button
                        className="add-btn"
                        onClick={() => addTaskToStage(key)}
                        disabled={!newTask.title}
                      >
                        Add Task
                      </button>
                    </div>
                  </div>
                ) : (
                  activeStage === key && (
                    <button
                      className="add-task-btn"
                      onClick={() => setShowAddTask(true)}
                    >
                      + Add Task
                    </button>
                  )
                )}

                {/* Stage Actions */}
                <div className="stage-actions">
                  <button
                    className="save-workflow-btn"
                    onClick={() => saveWorkflowStage(key)}
                    disabled={loading}
                  >
                    {loading ? 'Saving...' : 'Save Workflow'}
                  </button>
                </div>
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
            <div className="flow-icon">{workflowStages.lead.icon}</div>
            <span>Lead</span>
            <small>{workflowStages.lead.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.active_loan.color }}>
            <div className="flow-icon">{workflowStages.active_loan.icon}</div>
            <span>Active Loan</span>
            <small>{workflowStages.active_loan.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.portfolio.color }}>
            <div className="flow-icon">{workflowStages.portfolio.icon}</div>
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
