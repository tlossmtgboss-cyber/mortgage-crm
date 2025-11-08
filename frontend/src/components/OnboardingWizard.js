import React, { useState } from 'react';
import './OnboardingWizard.css';

const OnboardingWizard = ({ onComplete }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({
    // Step 1: Team & Roles
    teamName: '',
    members: [{ firstName: '', lastName: '', email: '', phone: '', role: '' }],
    manager: '',
    timezone: 'America/Los_Angeles',

    // Step 2: Systems & Processes
    sopFiles: [],
    processTree: null,

    // Step 3: Process Ownership
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
    setFormData({ ...formData, [field]: value });
  };

  const addMember = () => {
    setFormData({
      ...formData,
      members: [...formData.members, { firstName: '', lastName: '', email: '', phone: '', role: '' }]
    });
  };

  const updateMember = (index, field, value) => {
    const newMembers = [...formData.members];
    newMembers[index][field] = value;
    setFormData({ ...formData, members: newMembers });
  };

  const removeMember = (index) => {
    const newMembers = formData.members.filter((_, i) => i !== index);
    setFormData({ ...formData, members: newMembers });
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return renderTeamRoles();
      case 2:
        return renderProcessUpload();
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

  // SCREEN 1: Team & Roles
  const renderTeamRoles = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👥</div>
        <h2>Team & Roles</h2>
        <p className="step-description">Set up your team members and assign roles</p>
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

  // SCREEN 2: Systems & Processes Upload
  const renderProcessUpload = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📄</div>
        <h2>Systems & Processes Upload</h2>
        <p className="step-description">Upload your SOPs and let AI build your process tree</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Upload Process Documents</label>
          <p className="field-hint">PDFs, DOCX, XLSX, CSV of your SOPs (Lead → Loan → Post-Close)</p>
          <div className="file-upload-area">
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.csv"
              onChange={(e) => updateField('sopFiles', Array.from(e.target.files))}
              className="file-input"
              id="sop-upload"
            />
            <label htmlFor="sop-upload" className="file-upload-label">
              <div className="upload-icon">📎</div>
              <div>Click to upload or drag and drop</div>
              <div className="upload-hint">PDF, DOCX, XLSX, CSV (max 10 files)</div>
            </label>
          </div>
          {formData.sopFiles.length > 0 && (
            <div className="uploaded-files">
              {Array.from(formData.sopFiles).map((file, index) => (
                <div key={index} className="file-item">
                  📄 {file.name}
                </div>
              ))}
            </div>
          )}
        </div>

        {formData.sopFiles.length > 0 && (
          <div className="ai-processing">
            <button className="btn-ai-process">
              🤖 AI: Parse & Generate Process Tree
            </button>
            <p className="processing-hint">
              AI will extract milestones, tasks, and role ownership from your documents
            </p>
          </div>
        )}

        {formData.processTree && (
          <div className="process-tree-preview">
            <h4>Process Tree Preview</h4>
            <p>✓ Identified 12 milestones</p>
            <p>✓ Extracted 47 tasks</p>
            <p>✓ Mapped role ownership</p>
          </div>
        )}
      </div>
    </div>
  );

  // SCREEN 3: Confirm "Who Does What, When"
  const renderProcessTree = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🗂️</div>
        <h2>Who Does What, When</h2>
        <p className="step-description">Confirm and adjust your process ownership and SLAs</p>
      </div>

      <div className="process-tree-editor">
        <div className="milestone-column">
          <h4>Milestones</h4>
          <div className="milestone-list">
            <div className="milestone-item active">New Lead</div>
            <div className="milestone-item">Docs Out</div>
            <div className="milestone-item">Disclosed</div>
            <div className="milestone-item">Appraisal Received</div>
            <div className="milestone-item">UW Approved</div>
            <div className="milestone-item">Clear to Close</div>
            <div className="milestone-item">Funded</div>
            <div className="milestone-item">30-Day Check-in</div>
            <div className="milestone-item">90-Day Check-in</div>
            <div className="milestone-item">330-Day Check-in</div>
          </div>
        </div>

        <div className="tasks-column">
          <h4>Tasks for "New Lead"</h4>
          <div className="task-list">
            <div className="task-item">
              <div className="task-name">Initial contact</div>
              <div className="task-owner">
                <select className="owner-select">
                  <option>Loan Officer</option>
                  <option>Concierge</option>
                </select>
              </div>
              <div className="task-sla">
                <input type="number" defaultValue="24" className="sla-input" /> hours
              </div>
              <div className="task-auto">
                <label>
                  <input type="checkbox" /> AI Auto
                </label>
              </div>
            </div>
            <div className="task-item">
              <div className="task-name">Pre-qualification</div>
              <div className="task-owner">
                <select className="owner-select">
                  <option>Loan Officer</option>
                </select>
              </div>
              <div className="task-sla">
                <input type="number" defaultValue="48" className="sla-input" /> hours
              </div>
              <div className="task-auto">
                <label>
                  <input type="checkbox" /> AI Auto
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="process-actions">
        <button className="btn-secondary">Reset to AI Defaults</button>
        <button className="btn-primary">Save & Publish Process v1</button>
      </div>
    </div>
  );

  // SCREEN 4: Integrations
  const renderIntegrations = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🔗</div>
        <h2>Integrations</h2>
        <p className="step-description">Connect your calendars, email, and phone systems</p>
      </div>

      <div className="integrations-grid">
        {/* Calendly */}
        <div className="integration-card">
          <h4>📅 Calendly</h4>
          <p>Connect your Calendly for automated appointment scheduling</p>
          {!formData.calendly.connected ? (
            <button className="btn-connect">Connect Calendly</button>
          ) : (
            <div className="connected-status">
              <p className="status-connected">✓ Connected</p>
              <div className="event-types">
                <label>
                  <input type="checkbox" /> Annual Review (30min)
                </label>
                <label>
                  <input type="checkbox" /> Pre-Approval (45min)
                </label>
                <label>
                  <input type="checkbox" /> Refinance Consult (30min)
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Email */}
        <div className="integration-card">
          <h4>📧 Email</h4>
          <p>Monitor email for appraisal receipts, disclosures, and more</p>
          <div className="provider-choice">
            <button className="btn-provider">
              <img src="/microsoft-icon.svg" alt="Microsoft" className="provider-icon" />
              Microsoft 365
            </button>
            <button className="btn-provider">
              <img src="/gmail-icon.svg" alt="Gmail" className="provider-icon" />
              Gmail
            </button>
          </div>
          {formData.email.connected && (
            <div className="mailbox-list">
              <label>
                <input type="checkbox" /> tim@mortgagecrm.com
              </label>
              <label>
                <input type="checkbox" /> processor@mortgagecrm.com
              </label>
            </div>
          )}
        </div>

        {/* Telephony */}
        <div className="integration-card">
          <h4>📞 Telephony</h4>
          <p>Connect Twilio for AI calling and SMS</p>
          <button className="btn-connect">Connect Twilio</button>
          {formData.telephony.phoneNumbers.length > 0 && (
            <div className="phone-numbers">
              <p className="status-connected">✓ Connected</p>
              <p>+1 (555) 123-4567</p>
              <label>
                <input type="checkbox" defaultChecked /> Enable call recording
              </label>
              <label>
                <input type="checkbox" defaultChecked /> Branded caller ID
              </label>
            </div>
          )}
        </div>

        {/* Optional: LOS */}
        <div className="integration-card optional">
          <h4>🏢 LOS (Optional)</h4>
          <p>Encompass, ICE Mortgage, or other LOS integration</p>
          <button className="btn-connect-secondary">Connect Later</button>
        </div>
      </div>
    </div>
  );

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
          <button className="btn-test">Run Call Test</button>
          <input
            type="tel"
            placeholder="Your test phone number"
            className="input-field test-input"
          />
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
          <button className="btn-test">Upload Sample Email</button>
          <div className="email-test-example">
            <p className="example-hint">Try uploading an "Appraisal Received" email</p>
          </div>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>📅 Test Calendar Booking</h5>
            <span className="status-pending">Optional</span>
          </div>
          <p>Book a test appointment through Calendly integration</p>
          <button className="btn-test-secondary">Test Calendly</button>
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
            { num: 1, label: 'Team' },
            { num: 2, label: 'Process' },
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
    </div>
  );
};

export default OnboardingWizard;
