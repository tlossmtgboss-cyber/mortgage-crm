import React, { useState } from 'react';
import './OnboardingWizard.css';

const OnboardingWizard = ({ onComplete, onSkip }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [activeMilestone, setActiveMilestone] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [connectionModal, setConnectionModal] = useState(null);
  const [helpdeskModal, setHelpdeskModal] = useState(null);
  const [uploadedTestEmail, setUploadedTestEmail] = useState(null);
  const [formData, setFormData] = useState({
    // Step 1: Team & Roles
    teamName: '',
    members: [{ firstName: '', lastName: '', email: '', phone: '', role: '' }],
    manager: '',
    timezone: 'America/Los_Angeles',

    // Step 2: Systems & Processes
    sopFiles: [],
    processTree: null,

    // Step 3: Process Ownership (populated by AI or manually)
    milestones: [],

    // Step 4: Integrations
    calendly: { connected: false, eventTypes: [] },
    email: { provider: null, connected: false, mailboxes: [] },
    telephony: { provider: null, phoneNumbers: [] },

    // Step 5: Compliance
    quietHours: { start: '08:00', end: '20:00' },
    maxRetries: 3,
    maxDailyAttempts: 5,
    dncAccepted: false,
    recordingPolicy: {},

    // Step 6: AI Agent
    agentName: 'Samantha',
    voiceProfile: 'elevenlabs-default',
    identityLine: '',
    purposePrompts: {},
    escalationNumber: '',

    // Step 7: Test & Go-Live
    testsPassed: {
      callTest: false,
      emailTest: false
    }
  });

  const totalSteps = 7;

  const handleNext = () => {
    if (currentStep < totalSteps) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleComplete = async () => {
    try {
      const token = localStorage.getItem('token');
      const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

      await fetch(`${API_BASE_URL}/api/v1/onboarding/complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (onComplete) {
        onComplete();
      }
    } catch (error) {
      console.error('Failed to complete onboarding:', error);
      // Still complete on error for now
      if (onComplete) {
        onComplete();
      }
    }
  };

  const updateField = (field, value) => {
    setFormData(prevData => ({ ...prevData, [field]: value }));
  };

  const addMember = () => {
    setFormData(prevData => ({
      ...prevData,
      members: [...prevData.members, { firstName: '', lastName: '', email: '', phone: '', role: '' }]
    }));
  };

  const updateMember = (index, field, value) => {
    setFormData(prevData => {
      const newMembers = [...prevData.members];
      newMembers[index][field] = value;
      return { ...prevData, members: newMembers };
    });
  };

  const removeMember = (index) => {
    setFormData(prevData => ({
      ...prevData,
      members: prevData.members.filter((_, i) => i !== index)
    }));
  };

  // File upload handlers
  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    addFiles(files);
  };

  const addFiles = (newFiles) => {
    const MAX_FILES = 10;
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB per file

    const validFiles = newFiles.filter(file => {
      // Check file type
      const validTypes = ['.pdf', '.docx', '.xlsx', '.csv', '.doc', '.xls', '.txt'];
      const fileExt = '.' + file.name.split('.').pop().toLowerCase();
      if (!validTypes.includes(fileExt)) {
        alert(`${file.name}: Invalid file type. Please upload PDF, DOCX, XLSX, or CSV files.`);
        return false;
      }

      // Check file size
      if (file.size > MAX_FILE_SIZE) {
        alert(`${file.name}: File too large. Maximum size is 50MB.`);
        return false;
      }

      return true;
    });

    const currentFiles = formData.sopFiles || [];
    const combinedFiles = [...currentFiles, ...validFiles];

    if (combinedFiles.length > MAX_FILES) {
      alert(`Maximum ${MAX_FILES} files allowed. Only adding first ${MAX_FILES - currentFiles.length} files.`);
      updateField('sopFiles', combinedFiles.slice(0, MAX_FILES));
    } else {
      updateField('sopFiles', combinedFiles);
    }
  };

  const removeFile = (index) => {
    const newFiles = formData.sopFiles.filter((_, i) => i !== index);
    updateField('sopFiles', newFiles);
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  };

  // AI Process Tree Generation
  const handleAIProcessing = async () => {
    setIsProcessing(true);

    // Simulate AI processing (replace with actual API call later)
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Sample milestones that would be extracted from documents
    const generatedMilestones = [
      {
        name: 'New Lead',
        tasks: [
          { name: 'Initial contact', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
          { name: 'Pre-qualification', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Credit pull authorization', owner: 'Loan Officer', sla: 48, slaUnit: 'hours', aiAuto: false }
        ]
      },
      {
        name: 'Application',
        tasks: [
          { name: 'Send application link', owner: 'Concierge', sla: 4, slaUnit: 'hours', aiAuto: true },
          { name: 'Review application', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Initial disclosures', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Processing',
        tasks: [
          { name: 'Order appraisal', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Request documentation', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Title order', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Underwriting',
        tasks: [
          { name: 'Submit to underwriter', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Review conditions', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Clear conditions', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Clear to Close',
        tasks: [
          { name: 'Final review', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Schedule closing', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Closing',
        tasks: [
          { name: 'Send closing docs', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Confirm funding', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Post-Close',
        tasks: [
          { name: '7-day check-in', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
          { name: '30-day check-in', owner: 'Loan Officer', sla: 30, slaUnit: 'days', aiAuto: true }
        ]
      },
      {
        name: 'Annual Review',
        tasks: [
          { name: 'Send annual review invite', owner: 'Concierge', sla: 330, slaUnit: 'days', aiAuto: true },
          { name: 'Review financial situation', owner: 'Loan Officer', sla: 365, slaUnit: 'days', aiAuto: false }
        ]
      }
    ];

    // Calculate stats
    const totalTasks = generatedMilestones.reduce((total, m) => total + m.tasks.length, 0);

    // Update BOTH milestones AND processTree in a single atomic update
    setFormData(prevData => ({
      ...prevData,
      milestones: generatedMilestones,
      processTree: {
        generated: true,
        milestones: generatedMilestones.length,
        tasks: totalTasks,
        roles: 5
      }
    }));

    setIsProcessing(false);
  };

  // Milestone and task management
  const addMilestone = () => {
    setFormData(prevData => {
      const newMilestone = {
        name: 'New Milestone',
        tasks: []
      };
      const newMilestones = [...prevData.milestones, newMilestone];
      setActiveMilestone(newMilestones.length - 1);
      return { ...prevData, milestones: newMilestones };
    });
  };

  const updateMilestone = (index, field, value) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[index][field] = value;
      return { ...prevData, milestones: newMilestones };
    });
  };

  const removeMilestone = (index) => {
    setFormData(prevData => {
      const newMilestones = prevData.milestones.filter((_, i) => i !== index);
      if (activeMilestone >= newMilestones.length) {
        setActiveMilestone(Math.max(0, newMilestones.length - 1));
      }
      return { ...prevData, milestones: newMilestones };
    });
  };

  const addTask = (milestoneIndex) => {
    setFormData(prevData => {
      const newTask = {
        name: '',
        owner: 'Loan Officer',
        sla: 24,
        slaUnit: 'hours',
        aiAuto: false
      };
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks = [...newMilestones[milestoneIndex].tasks, newTask];
      return { ...prevData, milestones: newMilestones };
    });
  };

  const updateTask = (milestoneIndex, taskIndex, field, value) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks[taskIndex][field] = value;
      return { ...prevData, milestones: newMilestones };
    });
  };

  const removeTask = (milestoneIndex, taskIndex) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks = newMilestones[milestoneIndex].tasks.filter((_, i) => i !== taskIndex);
      return { ...prevData, milestones: newMilestones };
    });
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return renderProcessUpload();
      case 2:
        return renderTeamRoles();
      case 3:
        return renderProcessTree();
      case 4:
        return renderIntegrations();
      case 5:
        return renderCompliance();
      case 6:
        return renderAIAgent();
      case 7:
        return renderTestGoLive();
      default:
        return null;
    }
  };

  // SCREEN 2: Team & Roles
  const renderTeamRoles = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👥</div>
        <h2>Team & Roles</h2>
        <p className="step-description">
          {formData.processTree
            ? `Set up your team members - you'll assign them to the ${formData.processTree.tasks} generated tasks in the next step`
            : 'Set up your team members and assign roles'}
        </p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Team Name (Branch)</label>
          <input
            type="text"
            value={formData.teamName}
            onChange={(e) => updateField('teamName', e.target.value)}
            placeholder="e.g., West Coast Branch"
            className="input-field"
          />
        </div>

        <div className="form-field">
          <label>Timezone</label>
          <select
            value={formData.timezone}
            onChange={(e) => updateField('timezone', e.target.value)}
            className="input-field"
          >
            <option value="America/Los_Angeles">Pacific Time</option>
            <option value="America/Denver">Mountain Time</option>
            <option value="America/Chicago">Central Time</option>
            <option value="America/New_York">Eastern Time</option>
          </select>
        </div>

        <div className="form-field">
          <label>Team Members</label>
          {formData.members.map((member, index) => (
            <div key={index} className="member-row">
              <input
                type="text"
                placeholder="First Name"
                value={member.firstName}
                onChange={(e) => updateMember(index, 'firstName', e.target.value)}
                className="input-field input-sm"
              />
              <input
                type="text"
                placeholder="Last Name"
                value={member.lastName}
                onChange={(e) => updateMember(index, 'lastName', e.target.value)}
                className="input-field input-sm"
              />
              <input
                type="email"
                placeholder="Email"
                value={member.email}
                onChange={(e) => updateMember(index, 'email', e.target.value)}
                className="input-field input-md"
              />
              <input
                type="tel"
                placeholder="Phone"
                value={member.phone}
                onChange={(e) => updateMember(index, 'phone', e.target.value)}
                className="input-field input-sm"
              />
              <select
                value={member.role}
                onChange={(e) => updateMember(index, 'role', e.target.value)}
                className="input-field input-md"
              >
                <option value="">Select Role</option>
                <option value="loan_officer">Loan Officer</option>
                <option value="processor">Processor</option>
                <option value="analyst">Analyst</option>
                <option value="concierge">Concierge</option>
                <option value="admin">Admin</option>
              </select>
              {index > 0 && (
                <button onClick={() => removeMember(index)} className="btn-remove">×</button>
              )}
            </div>
          ))}
          <button onClick={addMember} className="btn-add-member">+ Add Member</button>
        </div>

        <div className="form-field">
          <label>Manager</label>
          <select
            value={formData.manager}
            onChange={(e) => updateField('manager', e.target.value)}
            className="input-field"
          >
            <option value="">Select Manager</option>
            {formData.members.map((member, index) => (
              member.email && (
                <option key={index} value={member.email}>
                  {member.firstName} {member.lastName} ({member.email})
                </option>
              )
            ))}
          </select>
        </div>
      </div>

      <div className="validation-requirements">
        <p>✓ At least one Loan Officer required</p>
        <p>✓ At least one Admin required</p>
        <p>✓ All emails must be unique and valid</p>
      </div>
    </div>
  );

  // SCREEN 1: Systems & Processes Upload
  const renderProcessUpload = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📄</div>
        <h2>Upload Your Process Documents</h2>
        <p className="step-description">Upload your SOPs first - AI will generate ALL tasks and workflows to assign to your team</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Upload Process Documents</label>
          <p className="field-hint">PDFs, DOCX, XLSX, CSV of your SOPs (Lead → Loan → Post-Close)</p>
          <div
            className="file-upload-area"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt"
              onChange={handleFileSelect}
              className="file-input"
              id="sop-upload"
            />
            <label htmlFor="sop-upload" className="file-upload-label">
              <div className="upload-icon">📎</div>
              <div className="upload-text">Click to upload or drag and drop</div>
              <div className="upload-hint">PDF, DOCX, XLSX, CSV, TXT (max 10 files, 50MB each)</div>
            </label>
          </div>

          {formData.sopFiles && formData.sopFiles.length > 0 && (
            <div className="uploaded-files">
              <div className="files-header">
                <h4>{formData.sopFiles.length} file{formData.sopFiles.length !== 1 ? 's' : ''} uploaded</h4>
                <button
                  className="btn-clear-all"
                  onClick={() => updateField('sopFiles', [])}
                >
                  Clear all
                </button>
              </div>
              {formData.sopFiles.map((file, index) => (
                <div key={index} className="file-item">
                  <div className="file-icon">
                    {file.name.endsWith('.pdf') ? '📕' :
                     file.name.endsWith('.docx') || file.name.endsWith('.doc') ? '📘' :
                     file.name.endsWith('.xlsx') || file.name.endsWith('.xls') ? '📗' :
                     file.name.endsWith('.csv') ? '📊' : '📄'}
                  </div>
                  <div className="file-info">
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">{formatFileSize(file.size)}</div>
                  </div>
                  <button
                    className="btn-remove-file"
                    onClick={() => removeFile(index)}
                    title="Remove file"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {formData.sopFiles && formData.sopFiles.length > 0 && !formData.processTree && (
          <div className="ai-processing">
            <button
              className="btn-ai-process"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <>
                  <span className="spinner"></span>
                  Processing...
                </>
              ) : (
                <>🤖 AI: Parse & Generate Process Tree</>
              )}
            </button>
            <p className="processing-hint">
              AI will extract milestones, tasks, and role ownership from your {formData.sopFiles.length} document{formData.sopFiles.length !== 1 ? 's' : ''}
            </p>
          </div>
        )}

        {formData.processTree && (
          <div className="process-tree-preview">
            <h4>✓ Process Tree Generated</h4>
            <div className="preview-stats">
              <div className="stat-item">
                <span className="stat-number">{formData.processTree.milestones}</span>
                <span className="stat-label">Milestones</span>
              </div>
              <div className="stat-item">
                <span className="stat-number">{formData.processTree.tasks}</span>
                <span className="stat-label">Tasks</span>
              </div>
              <div className="stat-item">
                <span className="stat-number">{formData.processTree.roles}</span>
                <span className="stat-label">Roles</span>
              </div>
            </div>
            <button
              className="btn-regenerate"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              🔄 Regenerate
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // SCREEN 3: Confirm "Who Does What, When"
  const renderProcessTree = () => {
    const currentMilestone = formData.milestones[activeMilestone];
    const availableRoles = ['Loan Officer', 'Processor', 'Analyst', 'Concierge', 'Admin'];

    // Show message if no milestones exist
    if (formData.milestones.length === 0) {
      return (
        <div className="step-content">
          <div className="step-header">
            <div className="step-icon">🗂️</div>
            <h2>Who Does What, When</h2>
            <p className="step-description">No milestones or tasks found</p>
          </div>

          <div className="empty-milestones-state">
            <div className="empty-state-icon">📋</div>
            <h3>No Process Tree Generated</h3>
            <p>
              Go back to <strong>Step 1</strong> to upload your process documents and click
              <strong> "🤖 AI: Parse & Generate Process Tree"</strong> to automatically create
              all your milestones and tasks.
            </p>
            <button className="btn-back-to-upload" onClick={() => setCurrentStep(1)}>
              ← Go Back to Upload Documents
            </button>
            <div className="or-divider">
              <span>OR</span>
            </div>
            <p className="manual-option">Start building your process manually:</p>
            <button className="btn-add-first-milestone" onClick={addMilestone}>
              + Add Your First Milestone
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="step-content">
        <div className="step-header">
          <div className="step-icon">🗂️</div>
          <h2>Who Does What, When</h2>
          <p className="step-description">
            {formData.processTree
              ? `✓ Review ${formData.milestones.reduce((total, m) => total + m.tasks.length, 0)} AI-generated tasks and assign ownership`
              : 'Configure your process ownership and SLAs'}
          </p>
        </div>

        {formData.processTree && (
          <div className="ai-generated-banner">
            <span className="banner-icon">🤖</span>
            <div className="banner-content">
              <strong>AI-Generated Process Tree</strong>
              <p>Review and approve the {formData.milestones.length} milestones and {formData.milestones.reduce((total, m) => total + m.tasks.length, 0)} tasks below. You can edit, add, or remove any milestone or task.</p>
            </div>
          </div>
        )}

        <div className="process-tree-editor">
          <div className="milestone-column">
            <div className="milestone-header">
              <h4>Milestones</h4>
              <button className="btn-add-milestone" onClick={addMilestone} title="Add Milestone">+</button>
            </div>
            <div className="milestone-list">
              {formData.milestones.map((milestone, index) => (
                <div
                  key={index}
                  className={`milestone-item ${index === activeMilestone ? 'active' : ''}`}
                  onClick={() => setActiveMilestone(index)}
                >
                  <input
                    type="text"
                    value={milestone.name}
                    onChange={(e) => updateMilestone(index, 'name', e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="milestone-name-input"
                  />
                  {formData.milestones.length > 1 && (
                    <button
                      className="btn-remove-milestone"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeMilestone(index);
                      }}
                      title="Remove Milestone"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="tasks-column">
            {currentMilestone && (
              <>
                <div className="tasks-header">
                  <h4>Tasks for "{currentMilestone.name}"</h4>
                  <button
                    className="btn-add-task"
                    onClick={() => addTask(activeMilestone)}
                  >
                    + Add Task
                  </button>
                </div>
                <div className="task-list">
                  {currentMilestone.tasks.length === 0 ? (
                    <div className="empty-tasks">
                      <p>No tasks yet. Click "+ Add Task" to create one.</p>
                    </div>
                  ) : (
                    currentMilestone.tasks.map((task, taskIndex) => (
                      <div key={taskIndex} className="task-item">
                        <div className="task-header">
                          <div className="task-name-section">
                            <label className="task-label">Task</label>
                            <input
                              type="text"
                              value={task.name}
                              onChange={(e) => updateTask(activeMilestone, taskIndex, 'name', e.target.value)}
                              placeholder="What needs to be done?"
                              className="task-name-input"
                            />
                          </div>
                          <button
                            className="btn-remove-task"
                            onClick={() => removeTask(activeMilestone, taskIndex)}
                            title="Remove Task"
                          >
                            ×
                          </button>
                        </div>

                        <div className="task-details">
                          <div className="task-detail-group">
                            <label className="detail-label">Assigned To</label>
                            <select
                              value={task.owner}
                              onChange={(e) => updateTask(activeMilestone, taskIndex, 'owner', e.target.value)}
                              className="owner-select"
                            >
                              {availableRoles.map(role => (
                                <option key={role} value={role}>{role}</option>
                              ))}
                            </select>
                          </div>

                          <div className="task-detail-group">
                            <label className="detail-label">Complete Within</label>
                            <div className="task-sla">
                              <input
                                type="number"
                                value={task.sla}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'sla', parseInt(e.target.value) || 0)}
                                className="sla-input"
                                min="1"
                              />
                              <select
                                value={task.slaUnit}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'slaUnit', e.target.value)}
                                className="sla-unit-select"
                              >
                                <option value="hours">hours</option>
                                <option value="days">days</option>
                              </select>
                            </div>
                          </div>

                          <div className="task-detail-group task-ai-section">
                            <label className="ai-auto-label">
                              <input
                                type="checkbox"
                                checked={task.aiAuto}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'aiAuto', e.target.checked)}
                                className="ai-auto-checkbox"
                              />
                              <span className="ai-auto-text">
                                <strong>AI Auto</strong>
                                <span className="ai-auto-hint">AI attempts task, escalates to user if needed, learns for next time</span>
                              </span>
                            </label>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="process-summary">
          <p>
            <strong>{formData.milestones.length}</strong> milestone{formData.milestones.length !== 1 ? 's' : ''} •
            <strong> {formData.milestones.reduce((total, m) => total + m.tasks.length, 0)}</strong> total task{formData.milestones.reduce((total, m) => total + m.tasks.length, 0) !== 1 ? 's' : ''}
          </p>
        </div>
      </div>
    );
  };

  // SCREEN 4: Integrations
  const integrationsList = [
    // Calendar & Scheduling
    { id: 'calendly', name: 'Calendly', icon: '📅', category: 'Calendar', description: 'Automated appointment scheduling' },
    { id: 'google-calendar', name: 'Google Calendar', icon: '📅', category: 'Calendar', description: 'Sync your Google Calendar events' },
    { id: 'outlook-calendar', name: 'Outlook Calendar', icon: '📅', category: 'Calendar', description: 'Microsoft Outlook calendar integration' },

    // Email
    { id: 'gmail', name: 'Gmail', icon: '📧', category: 'Email', description: 'Connect your Gmail account' },
    { id: 'outlook', name: 'Microsoft 365', icon: '📧', category: 'Email', description: 'Outlook and Microsoft 365 email' },
    { id: 'yahoo', name: 'Yahoo Mail', icon: '📧', category: 'Email', description: 'Yahoo email integration' },

    // Phone & SMS
    { id: 'twilio', name: 'Twilio', icon: '📞', category: 'Phone', description: 'AI calling, SMS, and voice' },
    { id: 'ringcentral', name: 'RingCentral', icon: '📞', category: 'Phone', description: 'Business phone system' },
    { id: 'dialpad', name: 'Dialpad', icon: '📞', category: 'Phone', description: 'Cloud-based phone system' },

    // Document Management
    { id: 'docusign', name: 'DocuSign', icon: '📝', category: 'Documents', description: 'Electronic signature platform' },
    { id: 'adobe-sign', name: 'Adobe Sign', icon: '📝', category: 'Documents', description: 'Adobe document signing' },
    { id: 'dropbox', name: 'Dropbox', icon: '📁', category: 'Documents', description: 'Cloud file storage' },
    { id: 'google-drive', name: 'Google Drive', icon: '📁', category: 'Documents', description: 'Google cloud storage' },

    // LOS (Loan Origination Systems)
    { id: 'encompass', name: 'Encompass', icon: '🏢', category: 'LOS', description: 'ICE Mortgage Technology LOS', optional: true },
    { id: 'calyx-point', name: 'Calyx Point', icon: '🏢', category: 'LOS', description: 'Calyx loan origination', optional: true },
    { id: 'bytepro', name: 'BytePro', icon: '🏢', category: 'LOS', description: 'BytePro LOS integration', optional: true },

    // CRM
    { id: 'salesforce', name: 'Salesforce', icon: '☁️', category: 'CRM', description: 'Salesforce CRM integration', optional: true },
    { id: 'hubspot', name: 'HubSpot', icon: '🎯', category: 'CRM', description: 'HubSpot marketing & CRM', optional: true },

    // Credit Bureaus
    { id: 'experian', name: 'Experian', icon: '💳', category: 'Credit', description: 'Experian credit reports', optional: true },
    { id: 'equifax', name: 'Equifax', icon: '💳', category: 'Credit', description: 'Equifax credit data', optional: true },
    { id: 'transunion', name: 'TransUnion', icon: '💳', category: 'Credit', description: 'TransUnion credit services', optional: true },

    // Team Communication
    { id: 'slack', name: 'Slack', icon: '💬', category: 'Communication', description: 'Team messaging and alerts' },
    { id: 'teams', name: 'Microsoft Teams', icon: '💬', category: 'Communication', description: 'Microsoft Teams chat' },

    // Accounting
    { id: 'quickbooks', name: 'QuickBooks', icon: '💰', category: 'Accounting', description: 'QuickBooks accounting', optional: true },
    { id: 'xero', name: 'Xero', icon: '💰', category: 'Accounting', description: 'Xero accounting software', optional: true }
  ];

  const handleConnectIntegration = (integration) => {
    setConnectionModal(integration);
  };

  const handleCloseModal = () => {
    setConnectionModal(null);
  };

  const handleAuthComplete = () => {
    // Simulate successful connection
    console.log(`Connected to ${connectionModal.name}`);
    setConnectionModal(null);
  };

  const renderIntegrations = () => {
    // Group integrations by category
    const categories = [...new Set(integrationsList.map(i => i.category))];

    return (
      <div className="step-content">
        <div className="step-header">
          <div className="step-icon">🔗</div>
          <h2>Integrations</h2>
          <p className="step-description">Connect your tools and services</p>
        </div>

        {categories.map(category => (
          <div key={category} className="integration-category">
            <h3 className="category-title">{category}</h3>
            <div className="integrations-grid">
              {integrationsList
                .filter(integration => integration.category === category)
                .map(integration => (
                  <div key={integration.id} className={`integration-card ${integration.optional ? 'optional' : ''}`}>
                    <div className="integration-header">
                      <span className="integration-icon">{integration.icon}</span>
                      <h4>{integration.name}</h4>
                      {integration.optional && <span className="optional-badge">Optional</span>}
                    </div>
                    <p className="integration-description">{integration.description}</p>
                    <button
                      className="btn-connect"
                      onClick={() => handleConnectIntegration(integration)}
                    >
                      Connect {integration.name}
                    </button>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // SCREEN 5: Compliance & Guardrails
  const renderCompliance = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">⚖️</div>
        <h2>Compliance & Guardrails</h2>
        <p className="step-description">Set calling hours, retry limits, and compliance policies</p>
      </div>

      <div className="form-section">
        <div className="form-row">
          <div className="form-field">
            <label>Quiet Hours (Local Time)</label>
            <div className="time-range">
              <input
                type="time"
                value={formData.quietHours.start}
                onChange={(e) => updateField('quietHours', { ...formData.quietHours, start: e.target.value })}
                className="input-field"
              />
              <span>to</span>
              <input
                type="time"
                value={formData.quietHours.end}
                onChange={(e) => updateField('quietHours', { ...formData.quietHours, end: e.target.value })}
                className="input-field"
              />
            </div>
            <p className="field-hint">AI will only call between these hours</p>
          </div>
        </div>

        <div className="form-row">
          <div className="form-field">
            <label>Max Retries per Contact</label>
            <input
              type="number"
              value={formData.maxRetries}
              onChange={(e) => updateField('maxRetries', parseInt(e.target.value))}
              className="input-field"
              min="1"
              max="10"
            />
            <p className="field-hint">Number of retry attempts with backoff</p>
          </div>

          <div className="form-field">
            <label>Max Daily Attempts</label>
            <input
              type="number"
              value={formData.maxDailyAttempts}
              onChange={(e) => updateField('maxDailyAttempts', parseInt(e.target.value))}
              className="input-field"
              min="1"
              max="20"
            />
            <p className="field-hint">Maximum contact attempts per day</p>
          </div>
        </div>

        <div className="compliance-policies">
          <h4>Policy Acknowledgments</h4>
          <label className="policy-checkbox">
            <input
              type="checkbox"
              checked={formData.dncAccepted}
              onChange={(e) => updateField('dncAccepted', e.target.checked)}
            />
            <span>I acknowledge compliance with Do Not Call (DNC) regulations</span>
          </label>

          <label className="policy-checkbox">
            <input type="checkbox" />
            <span>I will comply with state-specific recording consent laws</span>
          </label>

          <label className="policy-checkbox">
            <input type="checkbox" />
            <span>I will honor customer opt-out requests immediately</span>
          </label>
        </div>

        <div className="recording-states">
          <h4>Recording Policy by State</h4>
          <p className="field-hint">Select states where you do business:</p>
          <div className="state-grid">
            <label><input type="checkbox" /> CA (2-party)</label>
            <label><input type="checkbox" /> TX (1-party)</label>
            <label><input type="checkbox" /> FL (2-party)</label>
            <label><input type="checkbox" /> NY (1-party)</label>
          </div>
        </div>
      </div>
    </div>
  );

  // SCREEN 6: AI Agent Voice & Script
  const renderAIAgent = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🤖</div>
        <h2>AI Agent Voice & Script</h2>
        <p className="step-description">Configure your AI assistant's personality and scripts</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Agent Name</label>
          <input
            type="text"
            value={formData.agentName}
            onChange={(e) => updateField('agentName', e.target.value)}
            className="input-field"
            placeholder="e.g., Samantha, Alex, Jordan"
          />
        </div>

        <div className="form-field">
          <label>Voice Profile</label>
          <select
            value={formData.voiceProfile}
            onChange={(e) => updateField('voiceProfile', e.target.value)}
            className="input-field"
          >
            <option value="elevenlabs-rachel">Rachel (Professional Female)</option>
            <option value="elevenlabs-adam">Adam (Professional Male)</option>
            <option value="elevenlabs-samantha">Samantha (Friendly Female)</option>
            <option value="elevenlabs-josh">Josh (Casual Male)</option>
          </select>
          <button className="btn-preview-voice">▶ Preview Voice</button>
        </div>

        <div className="form-field">
          <label>Identity Line</label>
          <textarea
            value={formData.identityLine || `This is ${formData.agentName}, calling from Tim Loss's office...`}
            onChange={(e) => updateField('identityLine', e.target.value)}
            className="textarea-field"
            rows="3"
            placeholder="This is Samantha, calling from Tim Loss's mortgage office..."
          />
          <p className="field-hint">How the AI introduces itself on calls</p>
        </div>

        <div className="purpose-prompts">
          <h4>Purpose Prompts</h4>

          <div className="prompt-section">
            <label>Annual Review</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="I'm reaching out for your annual mortgage review. We've found potential savings..."
            />
          </div>

          <div className="prompt-section">
            <label>Pre-Approval Follow-up</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="Following up on your pre-approval application. Do you have time to discuss next steps?"
            />
          </div>

          <div className="prompt-section">
            <label>Refinance Opportunity</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="Rates have dropped significantly. I wanted to discuss potential refinance savings..."
            />
          </div>
        </div>

        <div className="form-field">
          <label>Escalation / Warm Transfer Number</label>
          <input
            type="tel"
            value={formData.escalationNumber}
            onChange={(e) => updateField('escalationNumber', e.target.value)}
            className="input-field"
            placeholder="+1 (555) 123-4567"
          />
          <p className="field-hint">Number to transfer to when customer requests human</p>
        </div>
      </div>
    </div>
  );

  // SCREEN 7: Test & Go-Live
  const handleTestCallClick = () => {
    setHelpdeskModal({
      feature: 'AI Calling Test',
      message: 'This feature is not yet configured. Our team will help you set it up.'
    });
  };

  const handleTestCalendarClick = () => {
    setHelpdeskModal({
      feature: 'Calendar Booking Test',
      message: 'This feature requires Calendly integration to be fully configured.'
    });
  };

  const handleEmailUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setUploadedTestEmail(file);
      // Simulate email parsing
      setTimeout(() => {
        setFormData(prevData => ({
          ...prevData,
          testsPassed: { ...prevData.testsPassed, emailTest: true }
        }));
      }, 1000);
    }
  };

  const handleCloseHelpdeskModal = () => {
    setHelpdeskModal(null);
  };

  const handleSubmitTicket = (e) => {
    e.preventDefault();
    console.log('Helpdesk ticket submitted for:', helpdeskModal.feature);
    // In production, this would send to your helpdesk system
    setHelpdeskModal(null);
    alert('Support ticket submitted! Our team will contact you shortly.');
  };

  const renderTestGoLive = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🚀</div>
        <h2>Test & Go-Live</h2>
        <p className="step-description">Verify everything works before activating your account</p>
      </div>

      <div className="test-checklist">
        <h4>Pre-Launch Checklist</h4>

        <div className="test-item">
          <div className="test-header">
            <h5>📞 Test AI Calling</h5>
            {formData.testsPassed.callTest ? (
              <span className="status-pass">✓ Passed</span>
            ) : (
              <span className="status-pending">Pending</span>
            )}
          </div>
          <p>Call your phone number and verify voice quality, script, and transfer</p>
          <input
            type="tel"
            placeholder="Your test phone number"
            className="input-field test-input"
          />
          <button className="btn-test" onClick={handleTestCallClick}>Run Call Test</button>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>📧 Test Email Parsing</h5>
            {formData.testsPassed.emailTest ? (
              <span className="status-pass">✓ Passed</span>
            ) : (
              <span className="status-pending">Pending</span>
            )}
          </div>
          <p>Upload a sample email to verify milestone detection</p>
          {uploadedTestEmail ? (
            <div className="uploaded-test-file">
              <span className="file-icon">📧</span>
              <span className="file-name">{uploadedTestEmail.name}</span>
              <span className="status-pass">✓ Uploaded</span>
            </div>
          ) : (
            <div className="file-upload-area">
              <input
                type="file"
                accept=".eml,.msg,.txt"
                onChange={handleEmailUpload}
                className="file-input"
                id="email-test-upload"
              />
              <label htmlFor="email-test-upload" className="btn-test">
                Upload Sample Email
              </label>
            </div>
          )}
          <div className="email-test-example">
            <p className="example-hint">Try uploading an "Appraisal Received" email (.eml, .msg, or .txt)</p>
          </div>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>📅 Test Calendar Booking</h5>
            <span className="status-pending">Optional</span>
          </div>
          <p>Book a test appointment through Calendly integration</p>
          <button className="btn-test-secondary" onClick={handleTestCalendarClick}>Test Calendly</button>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>👥 Team Invites Sent</h5>
            <span className="status-pass">✓ Ready</span>
          </div>
          <p>{formData.members.length} team members will receive activation emails</p>
        </div>
      </div>

      <div className="go-live-section">
        <div className="requirements-check">
          <h4>Requirements</h4>
          <div className="requirement-item">
            <span className={formData.teamName ? 'check-pass' : 'check-fail'}>
              {formData.teamName ? '✓' : '○'}
            </span>
            Team configured
          </div>
          <div className="requirement-item">
            <span className={formData.dncAccepted ? 'check-pass' : 'check-fail'}>
              {formData.dncAccepted ? '✓' : '○'}
            </span>
            Compliance policies accepted
          </div>
          <div className="requirement-item">
            <span className="check-pass">✓</span>
            AI agent configured
          </div>
        </div>

        <div className="activation-ready">
          <p className="ready-message">
            All systems ready! Click below to activate your account.
          </p>
          <p className="ready-hint">
            Your team will receive login credentials and you'll be redirected to your dashboard.
          </p>
        </div>
      </div>
    </div>
  );

  const progress = (currentStep / totalSteps) * 100;
  const canProceed = true; // Add validation logic per step if needed

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-wizard-v2">
        {/* Close Button */}
        {onSkip && (
          <button className="btn-close-wizard" onClick={onSkip} title="Skip for now">
            ×
          </button>
        )}

        {/* Progress Bar */}
        <div className="wizard-progress">
          <div className="progress-bar-container">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
          <div className="progress-text">
            Step {currentStep} of {totalSteps}
          </div>
        </div>

        {/* Step Indicators */}
        <div className="step-indicators">
          {[
            { num: 1, label: 'Process' },
            { num: 2, label: 'Team' },
            { num: 3, label: 'Ownership' },
            { num: 4, label: 'Integrations' },
            { num: 5, label: 'Compliance' },
            { num: 6, label: 'AI Agent' },
            { num: 7, label: 'Go-Live' }
          ].map((step) => (
            <div
              key={step.num}
              className={`step-indicator ${currentStep >= step.num ? 'active' : ''} ${
                currentStep > step.num ? 'completed' : ''
              }`}
            >
              <div className="indicator-dot">
                {currentStep > step.num ? '✓' : step.num}
              </div>
              <div className="indicator-label">{step.label}</div>
            </div>
          ))}
        </div>

        {/* Step Content */}
        {renderStep()}

        {/* Navigation */}
        <div className="wizard-navigation">
          {currentStep > 1 && (
            <button className="btn-nav btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}

          <div className="nav-spacer"></div>

          <button
            className={`btn-nav btn-next ${!canProceed ? 'disabled' : ''}`}
            onClick={handleNext}
            disabled={!canProceed}
          >
            {currentStep === totalSteps ? (
              <>Activate Account & Go Live! 🚀</>
            ) : (
              <>Next →</>
            )}
          </button>
        </div>
      </div>

      {/* Helpdesk Modal */}
      {helpdeskModal && (
        <div className="connection-modal-overlay" onClick={handleCloseHelpdeskModal}>
          <div className="connection-modal helpdesk-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseHelpdeskModal}>×</button>

            <div className="modal-header">
              <span className="modal-icon">🎫</span>
              <h3>Submit Support Ticket</h3>
              <p className="modal-description">Feature Not Yet Available</p>
            </div>

            <div className="modal-body">
              <div className="helpdesk-notice">
                <div className="notice-icon">ℹ️</div>
                <div className="notice-content">
                  <h4>{helpdeskModal.feature}</h4>
                  <p>{helpdeskModal.message}</p>
                </div>
              </div>

              <form className="helpdesk-form" onSubmit={handleSubmitTicket}>
                <div className="form-field">
                  <label>Your Name</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Full name"
                    required
                    defaultValue={`${formData.members[0]?.firstName || ''} ${formData.members[0]?.lastName || ''}`.trim()}
                  />
                </div>

                <div className="form-field">
                  <label>Email Address</label>
                  <input
                    type="email"
                    className="input-field"
                    placeholder="your@email.com"
                    required
                    defaultValue={formData.members[0]?.email || ''}
                  />
                </div>

                <div className="form-field">
                  <label>Phone Number (Optional)</label>
                  <input
                    type="tel"
                    className="input-field"
                    placeholder="(555) 123-4567"
                    defaultValue={formData.members[0]?.phone || ''}
                  />
                </div>

                <div className="form-field">
                  <label>Issue Type</label>
                  <select className="input-field" required>
                    <option value="setup">Setup Assistance</option>
                    <option value="bug">Report a Bug</option>
                    <option value="feature">Feature Request</option>
                    <option value="integration">Integration Help</option>
                    <option value="other">Other</option>
                  </select>
                </div>

                <div className="form-field">
                  <label>Additional Details</label>
                  <textarea
                    className="textarea-field"
                    placeholder="Please describe what you need help with..."
                    rows="4"
                    defaultValue={`I need help setting up: ${helpdeskModal.feature}`}
                  ></textarea>
                </div>

                <div className="helpdesk-actions">
                  <button type="button" className="btn-cancel" onClick={handleCloseHelpdeskModal}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-submit-ticket">
                    Submit Ticket
                  </button>
                </div>
              </form>

              <div className="support-info">
                <p className="support-note">
                  📧 You can also email us at <strong>support@mortgagecrm.com</strong>
                </p>
                <p className="support-note">
                  ⏱️ Average response time: <strong>2-4 hours</strong>
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Connection Modal */}
      {connectionModal && (
        <div className="connection-modal-overlay" onClick={handleCloseModal}>
          <div className="connection-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseModal}>×</button>

            <div className="modal-header">
              <span className="modal-icon">{connectionModal.icon}</span>
              <h3>Connect to {connectionModal.name}</h3>
              <p className="modal-description">{connectionModal.description}</p>
            </div>

            <div className="modal-body">
              <div className="auth-form">
                <div className="auth-provider-logo">
                  <span className="provider-logo-icon">{connectionModal.icon}</span>
                  <h4>{connectionModal.name}</h4>
                </div>

                <p className="auth-instruction">
                  Sign in to your {connectionModal.name} account to authorize access
                </p>

                <form className="oauth-form" onSubmit={(e) => { e.preventDefault(); handleAuthComplete(); }}>
                  <div className="form-field">
                    <label>Email or Username</label>
                    <input
                      type="text"
                      className="input-field"
                      placeholder={`Your ${connectionModal.name} email`}
                      autoFocus
                    />
                  </div>

                  <div className="form-field">
                    <label>Password</label>
                    <input
                      type="password"
                      className="input-field"
                      placeholder="Password"
                    />
                  </div>

                  <button type="submit" className="btn-authorize">
                    Authorize Connection
                  </button>
                </form>

                <div className="auth-footer">
                  <p className="security-note">
                    🔒 Your credentials are encrypted and securely stored. We only access data necessary for the integration.
                  </p>
                  <div className="permissions-info">
                    <p className="permissions-title">This integration will be able to:</p>
                    <ul className="permissions-list">
                      {connectionModal.category === 'Email' && (
                        <>
                          <li>Read emails and attachments</li>
                          <li>Send emails on your behalf</li>
                          <li>Access contact information</li>
                        </>
                      )}
                      {connectionModal.category === 'Calendar' && (
                        <>
                          <li>View and create calendar events</li>
                          <li>Send meeting invitations</li>
                          <li>Access availability information</li>
                        </>
                      )}
                      {connectionModal.category === 'Phone' && (
                        <>
                          <li>Make and receive calls</li>
                          <li>Send and receive SMS messages</li>
                          <li>Access call history and recordings</li>
                        </>
                      )}
                      {connectionModal.category === 'Documents' && (
                        <>
                          <li>Upload and download documents</li>
                          <li>Create and modify files</li>
                          <li>Share documents with clients</li>
                        </>
                      )}
                      {connectionModal.category === 'LOS' && (
                        <>
                          <li>Read loan application data</li>
                          <li>Update loan statuses</li>
                          <li>Sync borrower information</li>
                        </>
                      )}
                      {connectionModal.category === 'CRM' && (
                        <>
                          <li>Read and write contact data</li>
                          <li>Create and update leads</li>
                          <li>Sync pipeline information</li>
                        </>
                      )}
                      {connectionModal.category === 'Credit' && (
                        <>
                          <li>Pull credit reports</li>
                          <li>View credit scores</li>
                          <li>Access credit history</li>
                        </>
                      )}
                      {connectionModal.category === 'Communication' && (
                        <>
                          <li>Send messages to channels</li>
                          <li>Create notifications</li>
                          <li>Access team information</li>
                        </>
                      )}
                      {connectionModal.category === 'Accounting' && (
                        <>
                          <li>Read transaction data</li>
                          <li>Create invoices</li>
                          <li>Sync financial records</li>
                        </>
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OnboardingWizard;
