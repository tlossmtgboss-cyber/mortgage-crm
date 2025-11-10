import { useState, useEffect } from 'react';
import { processTemplatesAPI } from '../services/api';
import './ProcessTemplates.css';

function ProcessTemplates() {
  const [roles, setRoles] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedRole, setSelectedRole] = useState('');
  const [loading, setLoading] = useState(true);
  const [editingTask, setEditingTask] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [efficiencyAnalysis, setEfficiencyAnalysis] = useState(null);
  const [analyzingEfficiency, setAnalyzingEfficiency] = useState(false);

  const [newTask, setNewTask] = useState({
    role_name: '',
    task_title: '',
    task_description: '',
    sequence_order: 0,
    estimated_duration: 30,
    is_required: true
  });

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedRole) {
      loadTemplates(selectedRole);
    }
  }, [selectedRole]);

  const loadData = async () => {
    try {
      setLoading(true);
      const rolesData = await processTemplatesAPI.getRoles();

      if (rolesData.length === 0) {
        // Seed default templates if none exist
        await processTemplatesAPI.seedDefaults();
        const newRoles = await processTemplatesAPI.getRoles();
        setRoles(newRoles);
        if (newRoles.length > 0) {
          setSelectedRole(newRoles[0]);
        }
      } else {
        setRoles(rolesData);
        if (rolesData.length > 0) {
          setSelectedRole(rolesData[0]);
        }
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadTemplates = async (role) => {
    try {
      const data = await processTemplatesAPI.getByRole(role);
      setTemplates(data);
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const handleAnalyzeEfficiency = async () => {
    try {
      setAnalyzingEfficiency(true);
      const analysis = await processTemplatesAPI.analyzeEfficiency(selectedRole);
      setEfficiencyAnalysis(analysis);
    } catch (error) {
      console.error('Error analyzing efficiency:', error);
    } finally {
      setAnalyzingEfficiency(false);
    }
  };

  const handleSaveTask = async (taskId, updates) => {
    try {
      await processTemplatesAPI.update(taskId, updates);
      await loadTemplates(selectedRole);
      setEditingTask(null);
    } catch (error) {
      console.error('Error updating task:', error);
      alert('Failed to update task');
    }
  };

  const handleAddTask = async () => {
    try {
      await processTemplatesAPI.create({ ...newTask, role_name: selectedRole });
      await loadData();
      await loadTemplates(selectedRole);
      setShowAddForm(false);
      setNewTask({
        role_name: '',
        task_title: '',
        task_description: '',
        sequence_order: 0,
        estimated_duration: 30,
        is_required: true
      });
    } catch (error) {
      console.error('Error adding task:', error);
      alert('Failed to add task');
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!window.confirm('Are you sure you want to delete this task?')) {
      return;
    }

    try {
      await processTemplatesAPI.delete(taskId);
      await loadTemplates(selectedRole);
    } catch (error) {
      console.error('Error deleting task:', error);
      alert('Failed to delete task');
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'high': return '#ef4444';
      case 'medium': return '#f59e0b';
      case 'low': return '#3b82f6';
      case 'info': return '#10b981';
      default: return '#6b7280';
    }
  };

  if (loading) {
    return <div className="process-templates-container">Loading...</div>;
  }

  return (
    <div className="process-templates-container">
      <div className="page-header">
        <div>
          <h1>Process Templates</h1>
          <p>Manage role-based tasks and optimize your workflow</p>
        </div>
        <div className="header-actions">
          <button
            className="btn-analyze"
            onClick={handleAnalyzeEfficiency}
            disabled={analyzingEfficiency}
          >
            {analyzingEfficiency ? 'Analyzing...' : '🤖 AI Efficiency Analysis'}
          </button>
          <button
            className="btn-add"
            onClick={() => setShowAddForm(true)}
          >
            + Add Task
          </button>
        </div>
      </div>

      {/* Role Tabs */}
      <div className="role-tabs">
        {roles.map(role => (
          <button
            key={role}
            className={`role-tab ${selectedRole === role ? 'active' : ''}`}
            onClick={() => setSelectedRole(role)}
          >
            {role}
          </button>
        ))}
      </div>

      {/* Efficiency Analysis Results */}
      {efficiencyAnalysis && (
        <div className="efficiency-analysis">
          <div className="analysis-header">
            <h3>AI Efficiency Analysis</h3>
            <button onClick={() => setEfficiencyAnalysis(null)}>×</button>
          </div>

          <div className="analysis-summary">
            <div className="summary-stat">
              <span className="label">Total Tasks:</span>
              <span className="value">{efficiencyAnalysis.total_templates}</span>
            </div>
            <div className="summary-stat">
              <span className="label">Roles Analyzed:</span>
              <span className="value">{efficiencyAnalysis.roles_analyzed.length}</span>
            </div>
          </div>

          <div className="suggestions-list">
            {efficiencyAnalysis.suggestions.map((suggestion, index) => (
              <div
                key={index}
                className={`suggestion-card ${suggestion.type}`}
                style={{ borderLeftColor: getSeverityColor(suggestion.severity) }}
              >
                <div className="suggestion-header">
                  <h4>{suggestion.title}</h4>
                  <span className={`severity-badge ${suggestion.severity}`}>
                    {suggestion.severity}
                  </span>
                </div>
                <p className="suggestion-description">{suggestion.description}</p>
                <p className="suggestion-impact">
                  <strong>Impact:</strong> {suggestion.impact}
                </p>
                {suggestion.tasks_affected && suggestion.tasks_affected.length > 0 && (
                  <div className="affected-tasks">
                    <strong>Affected Tasks:</strong>
                    <ul>
                      {suggestion.tasks_affected.map((task, idx) => (
                        <li key={idx}>{task}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {suggestion.efficiency_score && (
                  <div className="efficiency-score">
                    <div className="score-bar">
                      <div
                        className="score-fill"
                        style={{
                          width: `${suggestion.efficiency_score}%`,
                          backgroundColor: suggestion.efficiency_score >= 70 ? '#10b981' : '#f59e0b'
                        }}
                      />
                    </div>
                    <span className="score-text">{suggestion.efficiency_score}%</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Task Form */}
      {showAddForm && (
        <div className="modal-overlay" onClick={() => setShowAddForm(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Add New Task for {selectedRole}</h3>
            <div className="form-group">
              <label>Task Title *</label>
              <input
                type="text"
                value={newTask.task_title}
                onChange={(e) => setNewTask({ ...newTask, task_title: e.target.value })}
                placeholder="Enter task title"
              />
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={newTask.task_description}
                onChange={(e) => setNewTask({ ...newTask, task_description: e.target.value })}
                placeholder="Enter task description"
                rows="3"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Sequence Order</label>
                <input
                  type="number"
                  value={newTask.sequence_order}
                  onChange={(e) => setNewTask({ ...newTask, sequence_order: parseInt(e.target.value) })}
                />
              </div>
              <div className="form-group">
                <label>Est. Duration (min)</label>
                <input
                  type="number"
                  value={newTask.estimated_duration}
                  onChange={(e) => setNewTask({ ...newTask, estimated_duration: parseInt(e.target.value) })}
                />
              </div>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={newTask.is_required}
                  onChange={(e) => setNewTask({ ...newTask, is_required: e.target.checked })}
                />
                Required Task
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowAddForm(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleAddTask}>
                Add Task
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tasks List */}
      <div className="tasks-container">
        <div className="tasks-header">
          <h2>{selectedRole} Tasks</h2>
          <div className="tasks-summary">
            <span>{templates.length} tasks</span>
            <span>·</span>
            <span>
              {templates.reduce((sum, t) => sum + (t.estimated_duration || 0), 0)} min total
            </span>
          </div>
        </div>

        <div className="tasks-list">
          {templates.map((task) => (
            <div key={task.id} className="task-card">
              {editingTask === task.id ? (
                <div className="task-edit-form">
                  <input
                    type="text"
                    defaultValue={task.task_title}
                    onBlur={(e) => handleSaveTask(task.id, { task_title: e.target.value })}
                    autoFocus
                  />
                  <textarea
                    defaultValue={task.task_description || ''}
                    onBlur={(e) => handleSaveTask(task.id, { task_description: e.target.value })}
                    rows="2"
                  />
                  <div className="edit-actions">
                    <button
                      className="btn-save"
                      onClick={() => setEditingTask(null)}
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="task-number">{task.sequence_order}</div>
                  <div className="task-content">
                    <div className="task-header">
                      <h3>{task.task_title}</h3>
                      {task.is_required && <span className="required-badge">Required</span>}
                    </div>
                    {task.task_description && (
                      <p className="task-description">{task.task_description}</p>
                    )}
                    <div className="task-meta">
                      {task.estimated_duration && (
                        <span className="meta-item">
                          ⏱️ {task.estimated_duration} min
                        </span>
                      )}
                      {task.automation_potential && (
                        <span className="meta-item">
                          🤖 {task.automation_potential} automation
                        </span>
                      )}
                    </div>
                    {task.efficiency_notes && (
                      <div className="efficiency-notes">
                        💡 {task.efficiency_notes}
                      </div>
                    )}
                  </div>
                  <div className="task-actions">
                    <button
                      className="btn-icon"
                      onClick={() => setEditingTask(task.id)}
                      title="Edit task"
                    >
                      ✏️
                    </button>
                    <button
                      className="btn-icon delete"
                      onClick={() => handleDeleteTask(task.id)}
                      title="Delete task"
                    >
                      🗑️
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}

          {templates.length === 0 && (
            <div className="no-tasks">
              <p>No tasks defined for this role yet.</p>
              <button className="btn-add" onClick={() => setShowAddForm(true)}>
                Add First Task
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ProcessTemplates;
