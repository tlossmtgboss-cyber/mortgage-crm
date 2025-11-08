import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './OnboardingWizard.css';

function OnboardingWizard() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  // eslint-disable-next-line no-unused-vars
  const [user, setUser] = useState(null);

  // Step 2: Document uploads
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  // Step 3: Team members
  const [teamMembers, setTeamMembers] = useState([]);
  const [newMember, setNewMember] = useState({
    name: '',
    role: '',
    responsibilities: '',
    email: ''
  });

  // Step 4: AI generated workflows
  const [workflows, setWorkflows] = useState([]);
  const [generatingWorkflows, setGeneratingWorkflows] = useState(false);

  useEffect(() => {
    // Get user from localStorage
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
  }, []);

  const handleFileUpload = (event) => {
    const files = Array.from(event.target.files);

    setUploading(true);
    // Simulate file upload
    setTimeout(() => {
      const newFiles = files.map(file => ({
        name: file.name,
        size: file.size,
        type: file.type,
        uploadedAt: new Date()
      }));

      setUploadedFiles(prev => [...prev, ...newFiles]);
      setUploading(false);
    }, 1000);
  };

  const removeFile = (index) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleAddTeamMember = () => {
    if (!newMember.name || !newMember.role) {
      alert('Please fill in name and role');
      return;
    }

    setTeamMembers(prev => [...prev, { ...newMember, id: Date.now() }]);
    setNewMember({ name: '', role: '', responsibilities: '', email: '' });
  };

  const removeTeamMember = (id) => {
    setTeamMembers(prev => prev.filter(m => m.id !== id));
  };

  const generateWorkflows = async () => {
    setGeneratingWorkflows(true);

    try {
      // Simulate AI workflow generation
      await new Promise(resolve => setTimeout(resolve, 3000));

      // Mock generated workflows
      const mockWorkflows = [
        {
          id: 1,
          name: 'Lead to Application Pipeline',
          description: 'Automated workflow for converting leads to applications',
          steps: [
            { order: 1, name: 'Initial Contact', assignedTo: teamMembers[0]?.name || 'Loan Officer', automated: false },
            { order: 2, name: 'Send Pre-qualification Form', assignedTo: 'AI Assistant', automated: true },
            { order: 3, name: 'Credit Pull Request', assignedTo: teamMembers[0]?.name || 'Loan Officer', automated: false },
            { order: 4, name: 'Application Submission', assignedTo: 'Processor', automated: false },
            { order: 5, name: 'Document Collection', assignedTo: 'AI Assistant', automated: true }
          ]
        },
        {
          id: 2,
          name: 'Document Management Workflow',
          description: 'Automated document collection and verification',
          steps: [
            { order: 1, name: 'Send Document Checklist', assignedTo: 'AI Assistant', automated: true },
            { order: 2, name: 'Monitor Document Uploads', assignedTo: 'AI Assistant', automated: true },
            { order: 3, name: 'Send Reminder for Missing Docs', assignedTo: 'AI Assistant', automated: true },
            { order: 4, name: 'Review and Verify Documents', assignedTo: 'Processor', automated: false }
          ]
        },
        {
          id: 3,
          name: 'Client Communication Workflow',
          description: 'Automated client updates and engagement',
          steps: [
            { order: 1, name: 'Send Welcome Email', assignedTo: 'AI Assistant', automated: true },
            { order: 2, name: 'Schedule Initial Call', assignedTo: teamMembers[0]?.name || 'Loan Officer', automated: false },
            { order: 3, name: 'Send Status Updates', assignedTo: 'AI Assistant', automated: true },
            { order: 4, name: 'Request Feedback', assignedTo: 'AI Assistant', automated: true }
          ]
        }
      ];

      setWorkflows(mockWorkflows);
    } catch (error) {
      console.error('Failed to generate workflows:', error);
      alert('Failed to generate workflows. Please try again.');
    } finally {
      setGeneratingWorkflows(false);
    }
  };

  const handleNext = async () => {
    if (currentStep === 2 && uploadedFiles.length === 0) {
      alert('Please upload at least one document');
      return;
    }

    if (currentStep === 3 && teamMembers.length === 0) {
      alert('Please add at least one team member');
      return;
    }

    if (currentStep === 3) {
      // Generate workflows after team members are added
      await generateWorkflows();
    }

    setCurrentStep(prev => prev + 1);
  };

  const handleBack = () => {
    setCurrentStep(prev => prev - 1);
  };

  const completeOnboarding = async () => {
    setLoading(true);

    try {
      // Save onboarding data
      // In production, this would save to backend
      await new Promise(resolve => setTimeout(resolve, 1500));

      localStorage.setItem('onboarding_complete', 'true');
      navigate('/dashboard');
    } catch (error) {
      console.error('Failed to complete onboarding:', error);
      alert('Failed to complete onboarding. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="onboarding-wizard">
      {/* Progress Bar */}
      <div className="onboarding-progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${(currentStep / 5) * 100}%` }}
        />
      </div>

      <div className="onboarding-container">
        {/* Step 1: Welcome */}
        {currentStep === 1 && (
          <div className="onboarding-step welcome-step">
            <div className="step-icon">👋</div>
            <h1>Welcome to Mortgage CRM!</h1>
            <p className="step-subtitle">
              Let's get your AI-powered CRM set up in just 5 minutes
            </p>

            <div className="welcome-features">
              <div className="welcome-feature">
                <div className="feature-icon">📄</div>
                <h3>Upload Your Processes</h3>
                <p>Share your existing workflows, team structure, and processes</p>
              </div>
              <div className="welcome-feature">
                <div className="feature-icon">🤖</div>
                <h3>AI Analysis</h3>
                <p>Our AI will analyze and understand your business operations</p>
              </div>
              <div className="welcome-feature">
                <div className="feature-icon">⚡</div>
                <h3>Custom Workflows</h3>
                <p>Get tailored workflows and automation for your team</p>
              </div>
            </div>

            <button className="btn-primary-large" onClick={handleNext}>
              Get Started
            </button>
          </div>
        )}

        {/* Step 2: Document Upload */}
        {currentStep === 2 && (
          <div className="onboarding-step upload-step">
            <h2>Upload Your Documents</h2>
            <p className="step-description">
              Upload documents about your processes, team roles, and workflows.
              The AI will analyze these to create custom automation for you.
            </p>

            <div className="upload-area">
              <input
                type="file"
                id="file-upload"
                multiple
                onChange={handleFileUpload}
                accept=".pdf,.doc,.docx,.txt,.xlsx,.xls"
                style={{ display: 'none' }}
              />
              <label htmlFor="file-upload" className="upload-label">
                <div className="upload-icon">📁</div>
                <h3>Click to upload or drag and drop</h3>
                <p>PDF, DOC, DOCX, TXT, XLS, XLSX (max 10MB each)</p>
              </label>
            </div>

            {uploading && (
              <div className="uploading-indicator">
                <div className="spinner"></div>
                <p>Uploading files...</p>
              </div>
            )}

            {uploadedFiles.length > 0 && (
              <div className="uploaded-files-list">
                <h3>Uploaded Files ({uploadedFiles.length})</h3>
                {uploadedFiles.map((file, index) => (
                  <div key={index} className="file-item">
                    <div className="file-info">
                      <span className="file-icon">📄</span>
                      <div>
                        <div className="file-name">{file.name}</div>
                        <div className="file-size">
                          {(file.size / 1024).toFixed(2)} KB
                        </div>
                      </div>
                    </div>
                    <button
                      className="btn-remove"
                      onClick={() => removeFile(index)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="step-buttons">
              <button className="btn-back" onClick={handleBack}>
                Back
              </button>
              <button className="btn-next" onClick={handleNext}>
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Team Members */}
        {currentStep === 3 && (
          <div className="onboarding-step team-step">
            <h2>Add Your Team Members</h2>
            <p className="step-description">
              Tell us about your team structure so we can assign workflows appropriately
            </p>

            <div className="add-member-form">
              <div className="form-row">
                <input
                  type="text"
                  placeholder="Name *"
                  value={newMember.name}
                  onChange={(e) => setNewMember({...newMember, name: e.target.value})}
                />
                <input
                  type="text"
                  placeholder="Role *"
                  value={newMember.role}
                  onChange={(e) => setNewMember({...newMember, role: e.target.value})}
                />
              </div>
              <textarea
                placeholder="Responsibilities (optional)"
                value={newMember.responsibilities}
                onChange={(e) => setNewMember({...newMember, responsibilities: e.target.value})}
                rows={3}
              />
              <input
                type="email"
                placeholder="Email (optional)"
                value={newMember.email}
                onChange={(e) => setNewMember({...newMember, email: e.target.value})}
              />
              <button className="btn-add-member" onClick={handleAddTeamMember}>
                + Add Team Member
              </button>
            </div>

            {teamMembers.length > 0 && (
              <div className="team-members-list">
                <h3>Team Members ({teamMembers.length})</h3>
                {teamMembers.map((member) => (
                  <div key={member.id} className="team-member-card">
                    <div className="member-info">
                      <div className="member-avatar">
                        {member.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="member-name">{member.name}</div>
                        <div className="member-role">{member.role}</div>
                        {member.responsibilities && (
                          <div className="member-responsibilities">
                            {member.responsibilities}
                          </div>
                        )}
                      </div>
                    </div>
                    <button
                      className="btn-remove"
                      onClick={() => removeTeamMember(member.id)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="step-buttons">
              <button className="btn-back" onClick={handleBack}>
                Back
              </button>
              <button className="btn-next" onClick={handleNext}>
                Generate Workflows
              </button>
            </div>
          </div>
        )}

        {/* Step 4: AI Analysis & Workflow Generation */}
        {currentStep === 4 && (
          <div className="onboarding-step analysis-step">
            {generatingWorkflows ? (
              <div className="ai-generating">
                <div className="ai-icon-animated">🤖</div>
                <h2>AI is Analyzing Your Data...</h2>
                <p>Generating custom workflows based on your documents and team structure</p>
                <div className="progress-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            ) : (
              <>
                <h2>Your Custom Workflows</h2>
                <p className="step-description">
                  Based on your documents and team, we've created these automated workflows
                </p>

                <div className="workflows-list">
                  {workflows.map((workflow) => (
                    <div key={workflow.id} className="workflow-card">
                      <h3>{workflow.name}</h3>
                      <p className="workflow-description">{workflow.description}</p>

                      <div className="workflow-steps">
                        {workflow.steps.map((step, index) => (
                          <div key={index} className="workflow-step-item">
                            <div className="step-number">{step.order}</div>
                            <div className="step-details">
                              <div className="step-name">{step.name}</div>
                              <div className="step-assigned">
                                Assigned to: {step.assignedTo}
                                {step.automated && (
                                  <span className="automated-badge">Automated</span>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="step-buttons">
                  <button className="btn-back" onClick={handleBack}>
                    Back
                  </button>
                  <button className="btn-next" onClick={handleNext}>
                    Looks Good!
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Step 5: Confirmation */}
        {currentStep === 5 && (
          <div className="onboarding-step confirmation-step">
            <div className="success-icon-large">🎉</div>
            <h1>You're All Set!</h1>
            <p className="step-subtitle">
              Your AI-powered CRM is ready to transform your business
            </p>

            <div className="onboarding-summary">
              <div className="summary-item">
                <div className="summary-icon">📄</div>
                <div>
                  <strong>{uploadedFiles.length}</strong>
                  <span>Documents Analyzed</span>
                </div>
              </div>
              <div className="summary-item">
                <div className="summary-icon">👥</div>
                <div>
                  <strong>{teamMembers.length}</strong>
                  <span>Team Members</span>
                </div>
              </div>
              <div className="summary-item">
                <div className="summary-icon">⚡</div>
                <div>
                  <strong>{workflows.length}</strong>
                  <span>Workflows Created</span>
                </div>
              </div>
            </div>

            <div className="next-steps-box">
              <h3>What's Next?</h3>
              <ul>
                <li>Start adding your leads and clients</li>
                <li>Connect your email and calendar</li>
                <li>Explore the AI assistant features</li>
                <li>Invite your team members</li>
              </ul>
            </div>

            <button
              className="btn-primary-large"
              onClick={completeOnboarding}
              disabled={loading}
            >
              {loading ? 'Setting up...' : 'Go to Dashboard'}
            </button>
          </div>
        )}
      </div>

      {/* Step indicator */}
      <div className="step-indicator">
        Step {currentStep} of 5
      </div>
    </div>
  );
}

export default OnboardingWizard;
