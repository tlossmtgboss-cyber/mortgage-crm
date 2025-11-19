import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './TaskWorkflowManager.css';

function TaskWorkflowManager() {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState('');
  const [taskTemplates, setTaskTemplates] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [activeTab, setActiveTab] = useState('bulk-upload'); // 'bulk-upload', 'workflow-assign', 'templates'
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  // Bulk upload state
  const [csvFile, setCsvFile] = useState(null);
  const [csvPreview, setCsvPreview] = useState([]);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Manual task creation
  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    priority: 'medium',
    due_date: '',
    category: 'general',
    assigned_to: ''
  });

  // Workflow assignment state
  const [selectedWorkflow, setSelectedWorkflow] = useState('');
  const [workflowDetails, setWorkflowDetails] = useState(null);

  useEffect(() => {
    loadUsers();
    loadTaskTemplates();
    loadWorkflows();
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
        setUsers(data.users || []);
      }
    } catch (error) {
      console.error('Error loading users:', error);
    }
  };

  const loadTaskTemplates = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/tasks/templates`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setTaskTemplates(data.templates || []);
      }
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const loadWorkflows = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflows`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setWorkflows(data.workflows || []);
      }
    } catch (error) {
      console.error('Error loading workflows:', error);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'text/csv') {
      setCsvFile(file);
      parseCSVPreview(file);
    } else {
      setMessage({ type: 'error', text: 'Please select a valid CSV file' });
    }
  };

  const parseCSVPreview = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const lines = text.split('\n');
      const headers = lines[0].split(',').map(h => h.trim());
      const preview = lines.slice(1, 6).map(line => {
        const values = line.split(',').map(v => v.trim());
        const row = {};
        headers.forEach((header, index) => {
          row[header] = values[index];
        });
        return row;
      });
      setCsvPreview(preview);
    };
    reader.readAsText(file);
  };

  const handleBulkUpload = async () => {
    if (!csvFile) {
      setMessage({ type: 'error', text: 'Please select a CSV file first' });
      return;
    }

    if (!selectedUser) {
      setMessage({ type: 'error', text: 'Please select a user to assign tasks to' });
      return;
    }

    setLoading(true);
    setUploadProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', csvFile);
      formData.append('assigned_to', selectedUser);

      const response = await fetch(`${API_BASE_URL}/api/v1/tasks/bulk-upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setMessage({
          type: 'success',
          text: `Successfully created ${data.created_count} tasks for the user`
        });
        setCsvFile(null);
        setCsvPreview([]);
        setUploadProgress(100);
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Upload failed' });
      }
    } catch (error) {
      console.error('Error uploading tasks:', error);
      setMessage({ type: 'error', text: 'Failed to upload tasks' });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSingleTask = async () => {
    if (!newTask.title || !newTask.assigned_to) {
      setMessage({ type: 'error', text: 'Title and assigned user are required' });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/tasks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newTask)
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Task created successfully' });
        setNewTask({
          title: '',
          description: '',
          priority: 'medium',
          due_date: '',
          category: 'general',
          assigned_to: ''
        });
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to create task' });
      }
    } catch (error) {
      console.error('Error creating task:', error);
      setMessage({ type: 'error', text: 'Failed to create task' });
    } finally {
      setLoading(false);
    }
  };

  const handleAssignWorkflow = async () => {
    if (!selectedWorkflow || !selectedUser) {
      setMessage({ type: 'error', text: 'Please select both a workflow and a user' });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflows/${selectedWorkflow}/assign`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ user_id: selectedUser })
      });

      if (response.ok) {
        const data = await response.json();
        setMessage({
          type: 'success',
          text: `Workflow assigned successfully. ${data.tasks_created} tasks created.`
        });
        setSelectedWorkflow('');
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to assign workflow' });
      }
    } catch (error) {
      console.error('Error assigning workflow:', error);
      setMessage({ type: 'error', text: 'Failed to assign workflow' });
    } finally {
      setLoading(false);
    }
  };

  const loadWorkflowDetails = async (workflowId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setWorkflowDetails(data);
      }
    } catch (error) {
      console.error('Error loading workflow details:', error);
    }
  };

  return (
    <div className="task-workflow-manager">
      <div className="manager-header">
        <h2>Task & Workflow Management</h2>
        <p>Upload tasks in bulk, assign workflows, and manage task templates for your team</p>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      <div className="manager-tabs">
        <button
          className={`tab-btn ${activeTab === 'bulk-upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('bulk-upload')}
        >
          📤 Bulk Upload
        </button>
        <button
          className={`tab-btn ${activeTab === 'workflow-assign' ? 'active' : ''}`}
          onClick={() => setActiveTab('workflow-assign')}
        >
          🔄 Assign Workflow
        </button>
        <button
          className={`tab-btn ${activeTab === 'single-task' ? 'active' : ''}`}
          onClick={() => setActiveTab('single-task')}
        >
          ➕ Create Single Task
        </button>
      </div>

      <div className="manager-content">
        {/* Bulk Upload Tab */}
        {activeTab === 'bulk-upload' && (
          <div className="bulk-upload-section">
            <div className="upload-instructions">
              <h3>📋 CSV Format Instructions</h3>
              <p>Your CSV file should have the following columns:</p>
              <code>title,description,priority,due_date,category,status</code>
              <div className="example-box">
                <strong>Example:</strong>
                <pre>
{`title,description,priority,due_date,category,status
Complete onboarding checklist,Review all onboarding materials,high,2025-12-01,onboarding,pending
Set up email signature,Configure professional email signature,medium,2025-11-25,setup,pending
Schedule 1-on-1 with manager,Initial check-in meeting,high,2025-11-22,meeting,pending`}
                </pre>
              </div>
            </div>

            <div className="upload-form">
              <div className="form-group">
                <label>Select User</label>
                <select
                  value={selectedUser}
                  onChange={(e) => setSelectedUser(e.target.value)}
                  className="user-select"
                >
                  <option value="">Choose a user...</option>
                  {users.map(user => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Upload CSV File</label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleFileSelect}
                  className="file-input"
                />
              </div>

              {csvPreview.length > 0 && (
                <div className="csv-preview">
                  <h4>Preview (first 5 rows)</h4>
                  <table className="preview-table">
                    <thead>
                      <tr>
                        {Object.keys(csvPreview[0]).map(key => (
                          <th key={key}>{key}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {csvPreview.map((row, idx) => (
                        <tr key={idx}>
                          {Object.values(row).map((val, i) => (
                            <td key={i}>{val}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <button
                onClick={handleBulkUpload}
                disabled={loading || !csvFile || !selectedUser}
                className="upload-btn"
              >
                {loading ? 'Uploading...' : 'Upload Tasks'}
              </button>

              {uploadProgress > 0 && uploadProgress < 100 && (
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${uploadProgress}%` }}></div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Workflow Assignment Tab */}
        {activeTab === 'workflow-assign' && (
          <div className="workflow-assign-section">
            <h3>🔄 Assign Process Workflow</h3>
            <p>Assign a pre-configured workflow to a new team member. This will automatically create all tasks in the workflow.</p>

            <div className="assign-form">
              <div className="form-group">
                <label>Select User</label>
                <select
                  value={selectedUser}
                  onChange={(e) => setSelectedUser(e.target.value)}
                  className="user-select"
                >
                  <option value="">Choose a user...</option>
                  {users.map(user => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Select Workflow</label>
                <select
                  value={selectedWorkflow}
                  onChange={(e) => {
                    setSelectedWorkflow(e.target.value);
                    if (e.target.value) loadWorkflowDetails(e.target.value);
                  }}
                  className="workflow-select"
                >
                  <option value="">Choose a workflow...</option>
                  <option value="new-employee-onboarding">New Employee Onboarding</option>
                  <option value="loan-officer-setup">Loan Officer Setup</option>
                  <option value="processor-training">Processor Training</option>
                  <option value="underwriter-onboarding">Underwriter Onboarding</option>
                  {workflows.map(workflow => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.name}
                    </option>
                  ))}
                </select>
              </div>

              {workflowDetails && (
                <div className="workflow-preview">
                  <h4>📋 Workflow Preview: {workflowDetails.name}</h4>
                  <p>{workflowDetails.description}</p>
                  <div className="workflow-tasks">
                    <strong>Tasks that will be created:</strong>
                    <ul>
                      {workflowDetails.tasks?.map((task, idx) => (
                        <li key={idx}>
                          <span className="task-title">{task.title}</span>
                          <span className={`priority-badge ${task.priority}`}>{task.priority}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <button
                onClick={handleAssignWorkflow}
                disabled={loading || !selectedWorkflow || !selectedUser}
                className="assign-btn"
              >
                {loading ? 'Assigning...' : 'Assign Workflow'}
              </button>
            </div>
          </div>
        )}

        {/* Single Task Creation Tab */}
        {activeTab === 'single-task' && (
          <div className="single-task-section">
            <h3>➕ Create Single Task</h3>

            <div className="task-form">
              <div className="form-group">
                <label>Assign To</label>
                <select
                  value={newTask.assigned_to}
                  onChange={(e) => setNewTask({...newTask, assigned_to: e.target.value})}
                  className="user-select"
                >
                  <option value="">Choose a user...</option>
                  {users.map(user => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Task Title *</label>
                <input
                  type="text"
                  value={newTask.title}
                  onChange={(e) => setNewTask({...newTask, title: e.target.value})}
                  placeholder="Enter task title..."
                  className="text-input"
                />
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={newTask.description}
                  onChange={(e) => setNewTask({...newTask, description: e.target.value})}
                  placeholder="Enter task description..."
                  rows="4"
                  className="textarea-input"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Priority</label>
                  <select
                    value={newTask.priority}
                    onChange={(e) => setNewTask({...newTask, priority: e.target.value})}
                    className="select-input"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Category</label>
                  <select
                    value={newTask.category}
                    onChange={(e) => setNewTask({...newTask, category: e.target.value})}
                    className="select-input"
                  >
                    <option value="general">General</option>
                    <option value="onboarding">Onboarding</option>
                    <option value="training">Training</option>
                    <option value="setup">Setup</option>
                    <option value="meeting">Meeting</option>
                    <option value="review">Review</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Due Date</label>
                  <input
                    type="date"
                    value={newTask.due_date}
                    onChange={(e) => setNewTask({...newTask, due_date: e.target.value})}
                    className="date-input"
                  />
                </div>
              </div>

              <button
                onClick={handleCreateSingleTask}
                disabled={loading || !newTask.title || !newTask.assigned_to}
                className="create-btn"
              >
                {loading ? 'Creating...' : 'Create Task'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TaskWorkflowManager;
