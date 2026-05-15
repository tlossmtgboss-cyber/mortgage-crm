// Voice OS Agent Builder - Agent creation and editing wizard
import React, { useState, useEffect } from 'react';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';





const AgentBuilder = ({
  existingAgent,
  onSave,
  onCancel
}) => {
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState({
    name: '',
    description: '',
    voice_id: 'alloy',
    voice_stability: 0.5,
    voice_similarity: 0.75,
    voice_style: 0.5,
    system_prompt: '',
    temperature: 0.7,
    max_tokens: 150,
    interrupt_enabled: true,
    filler_words_enabled: true,
    backchanneling_enabled: true,
    emotion_detection_enabled: true,
    tools_allowed: ['get_contact_by_phone', 'create_lead', 'schedule_appointment'],
    ...existingAgent
  });

  const voiceOptions = [
    { id: 'alloy', name: 'Alloy', description: 'Neutral and balanced', personality: 'Professional, Clear' },
    { id: 'echo', name: 'Echo', description: 'Professional and clear', personality: 'Confident, Articulate' },
    { id: 'fable', name: 'Fable', description: 'Warm and friendly', personality: 'Warm, Approachable' },
    { id: 'onyx', name: 'Onyx', description: 'Deep and authoritative', personality: 'Authoritative, Deep' },
    { id: 'nova', name: 'Nova', description: 'Energetic and upbeat', personality: 'Energetic, Enthusiastic' },
    { id: 'shimmer', name: 'Shimmer', description: 'Soft and gentle', personality: 'Gentle, Calm' }
  ];

  const toolOptions = [
    // Contact tools
    { id: 'get_contact_by_phone', name: 'Get Contact by Phone', description: 'Look up contacts by phone number', category: 'Contact' },
    { id: 'get_contact_details', name: 'Get Contact Details', description: 'Get full contact information', category: 'Contact' },
    // Lead tools
    { id: 'create_lead', name: 'Create Lead', description: 'Create new leads in CRM', category: 'Lead' },
    { id: 'update_lead_stage', name: 'Update Lead Stage', description: 'Move leads through pipeline', category: 'Lead' },
    { id: 'qualify_lead', name: 'Qualify Lead', description: 'Assess lead qualification', category: 'Lead' },
    // Appointment tools
    { id: 'schedule_appointment', name: 'Schedule Appointment', description: 'Book appointments', category: 'Appointment' },
    { id: 'check_availability', name: 'Check Availability', description: 'View available time slots', category: 'Appointment' },
    { id: 'reschedule_appointment', name: 'Reschedule Appointment', description: 'Change appointment times', category: 'Appointment' },
    { id: 'cancel_appointment', name: 'Cancel Appointment', description: 'Cancel bookings', category: 'Appointment' },
    // Task tools
    { id: 'create_task', name: 'Create Task', description: 'Create follow-up tasks', category: 'Task' },
    { id: 'log_call_note', name: 'Log Call Note', description: 'Save call notes to CRM', category: 'Task' },
    // Loan tools
    { id: 'get_loan_status', name: 'Get Loan Status', description: 'Check loan application status', category: 'Loan' },
    { id: 'get_loan_conditions', name: 'Get Loan Conditions', description: 'View outstanding conditions', category: 'Loan' },
    { id: 'request_documents', name: 'Request Documents', description: 'Send document requests', category: 'Loan' },
    { id: 'get_rate_quote', name: 'Get Rate Quote', description: 'Calculate rate estimates', category: 'Loan' },
    // Communication tools
    { id: 'send_sms', name: 'Send SMS', description: 'Send text messages', category: 'Communication' },
    { id: 'send_email', name: 'Send Email', description: 'Send emails', category: 'Communication' },
    { id: 'send_calendar_invite', name: 'Send Calendar Invite', description: 'Send meeting invites', category: 'Communication' },
    // Escalation tools
    { id: 'escalate_to_human', name: 'Escalate to Human', description: 'Transfer to human agent', category: 'Escalation' },
    { id: 'transfer_call', name: 'Transfer Call', description: 'Transfer to department', category: 'Escalation' }
  ];

  const promptTemplates = [
    {
      name: 'AI Receptionist',
      prompt: `You are a friendly and professional AI receptionist for a mortgage company. Your role is to:
- Greet callers warmly and professionally
- Identify if they are existing clients or new prospects
- Understand their needs (new loan, refinance, loan status, etc.)
- Schedule appointments with loan officers
- Answer basic questions about the mortgage process
- Create leads for new prospects

Guidelines:
- Keep responses concise (under 3 sentences when possible)
- Be empathetic and patient
- If you can't help, offer to transfer to a human
- Never provide specific rate quotes without proper qualification`
    },
    {
      name: 'LO Assistant',
      prompt: `You are Aria, an AI assistant for mortgage loan officers. You help them:
- Check on loan statuses and pipeline
- Create follow-up tasks and reminders
- Log notes from client conversations
- Review conditions and document requirements

Guidelines:
- Be efficient and to-the-point
- Proactively suggest actions when helpful
- Provide summaries rather than long explanations
- Use mortgage industry terminology appropriately`
    },
    {
      name: 'Customer Service',
      prompt: `You are a customer service AI for mortgage servicing. You help borrowers with:
- Payment information and due dates
- Escrow account questions
- Document requests
- General account inquiries

Guidelines:
- Be patient and clear with explanations
- Verify caller identity before sharing account details
- Offer to escalate complex issues
- Follow up to ensure the customer's needs are met`
    }
  ];

  const updateConfig = (updates) => {
    setConfig(prev => ({ ...prev, ...updates }));
  };

  const toggleTool = (toolId) => {
    setConfig(prev => ({
      ...prev,
      tools_allowed: prev.tools_allowed.includes(toolId)
        ? prev.tools_allowed.filter(t => t !== toolId)
        : [...prev.tools_allowed, toolId]
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const API_BASE_URL = typeof window !== 'undefined' &&
        (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
        ? 'https://api.perenniaai.com'
        : 'http://localhost:8000';

      const token = getToken();

      const response = await fetch(`${API_BASE_URL}/api/v1/voice/agents`, {
        method: existingAgent?.name ? 'PUT' : 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });

      if (!response.ok) {
        throw new Error('Failed to save agent');
      }

      onSave?.(config);
    } catch (err) {
      console.error('Error saving agent:', err);
      toast.error('Failed to save agent. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const isStepValid = (stepNum) => {
    switch (stepNum) {
      case 1:
        return config.name.trim().length > 0;
      case 2:
        return config.voice_id.length > 0;
      case 3:
        return config.system_prompt.trim().length > 0;
      case 4:
        return config.tools_allowed.length > 0;
      default:
        return true;
    }
  };

  const toolsByCategory = toolOptions.reduce((acc, tool) => {
    if (!acc[tool.category]) acc[tool.category] = [];
    acc[tool.category].push(tool);
    return acc;
  }, {});

  return (
    <div className="agent-builder">
      <div className="builder-header">
        <h1>{existingAgent?.name ? 'Edit Agent' : 'Create New Agent'}</h1>
        <div className="step-indicator">
          {[1, 2, 3, 4, 5].map(s => (
            <div
              key={s}
              className={`step ${step === s ? 'active' : ''} ${step > s ? 'completed' : ''}`}
              onClick={() => isStepValid(s - 1) && setStep(s)}
            >
              <span className="step-number">{s}</span>
              <span className="step-label">
                {s === 1 && 'Basics'}
                {s === 2 && 'Voice'}
                {s === 3 && 'Personality'}
                {s === 4 && 'Tools'}
                {s === 5 && 'Review'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="builder-content">
        {/* Step 1: Basic Info */}
        {step === 1 && (
          <div className="step-content">
            <h2>Basic Information</h2>
            <p>Give your agent a name and description</p>

            <div className="form-group">
              <label>Agent Name</label>
              <input
                type="text"
                value={config.name}
                onChange={(e) => updateConfig({ name: e.target.value })}
                placeholder="e.g., Sam - AI Receptionist"
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={config.description}
                onChange={(e) => updateConfig({ description: e.target.value })}
                placeholder="What does this agent do?"
                rows={3}
              />
            </div>
          </div>
        )}

        {/* Step 2: Voice Selection */}
        {step === 2 && (
          <div className="step-content">
            <h2>Select Voice</h2>
            <p>Choose the voice that best represents your brand</p>

            <div className="voice-grid">
              {voiceOptions.map(voice => (
                <div
                  key={voice.id}
                  className={`voice-option ${config.voice_id === voice.id ? 'selected' : ''}`}
                  onClick={() => updateConfig({ voice_id: voice.id })}
                >
                  <h4>{voice.name}</h4>
                  <p>{voice.description}</p>
                  <span className="personality">{voice.personality}</span>
                </div>
              ))}
            </div>

            <div className="voice-settings">
              <h3>Voice Settings</h3>
              <div className="slider-group">
                <label>
                  Stability: {config.voice_stability.toFixed(2)}
                  <span className="hint">Lower = more expressive</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={config.voice_stability}
                  onChange={(e) => updateConfig({ voice_stability: parseFloat(e.target.value) })}
                />
              </div>
              <div className="slider-group">
                <label>
                  Similarity: {config.voice_similarity.toFixed(2)}
                  <span className="hint">Higher = more consistent</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={config.voice_similarity}
                  onChange={(e) => updateConfig({ voice_similarity: parseFloat(e.target.value) })}
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Personality & Prompt */}
        {step === 3 && (
          <div className="step-content">
            <h2>Personality & Behavior</h2>
            <p>Define how your agent communicates</p>

            <div className="templates-section">
              <h3>Start from a template</h3>
              <div className="template-buttons">
                {promptTemplates.map(template => (
                  <button
                    key={template.name}
                    className="btn-template"
                    onClick={() => updateConfig({ system_prompt: template.prompt })}
                  >
                    {template.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>System Prompt</label>
              <textarea
                value={config.system_prompt}
                onChange={(e) => updateConfig({ system_prompt: e.target.value })}
                placeholder="Define your agent's personality, role, and behavior..."
                rows={10}
              />
            </div>

            <div className="behavior-toggles">
              <h3>Conversation Features</h3>
              <div className="toggle-grid">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.interrupt_enabled}
                    onChange={(e) => updateConfig({ interrupt_enabled: e.target.checked })}
                  />
                  <span>Allow Interruptions</span>
                  <span className="toggle-hint">Let callers interrupt the agent</span>
                </label>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.filler_words_enabled}
                    onChange={(e) => updateConfig({ filler_words_enabled: e.target.checked })}
                  />
                  <span>Natural Fillers</span>
                  <span className="toggle-hint">Add "um", "let me check" etc.</span>
                </label>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.backchanneling_enabled}
                    onChange={(e) => updateConfig({ backchanneling_enabled: e.target.checked })}
                  />
                  <span>Backchanneling</span>
                  <span className="toggle-hint">Add "mm-hmm", "I see" responses</span>
                </label>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.emotion_detection_enabled}
                    onChange={(e) => updateConfig({ emotion_detection_enabled: e.target.checked })}
                  />
                  <span>Emotion Detection</span>
                  <span className="toggle-hint">Detect caller emotions</span>
                </label>
              </div>
            </div>

            <div className="llm-settings">
              <h3>AI Settings</h3>
              <div className="settings-row">
                <div className="form-group">
                  <label>Temperature: {config.temperature}</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={config.temperature}
                    onChange={(e) => updateConfig({ temperature: parseFloat(e.target.value) })}
                  />
                  <span className="hint">Lower = more focused, Higher = more creative</span>
                </div>
                <div className="form-group">
                  <label>Max Response Tokens</label>
                  <input
                    type="number"
                    min="50"
                    max="500"
                    value={config.max_tokens}
                    onChange={(e) => updateConfig({ max_tokens: parseInt(e.target.value) })}
                  />
                  <span className="hint">Keep low for concise responses</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Tools */}
        {step === 4 && (
          <div className="step-content">
            <h2>CRM Tools</h2>
            <p>Select which tools your agent can use</p>

            <div className="tools-by-category">
              {Object.entries(toolsByCategory).map(([category, tools]) => (
                <div key={category} className="tool-category">
                  <h3>{category}</h3>
                  <div className="tools-list">
                    {tools.map(tool => (
                      <label
                        key={tool.id}
                        className={`tool-option ${config.tools_allowed.includes(tool.id) ? 'selected' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={config.tools_allowed.includes(tool.id)}
                          onChange={() => toggleTool(tool.id)}
                        />
                        <div className="tool-info">
                          <span className="tool-name">{tool.name}</span>
                          <span className="tool-desc">{tool.description}</span>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="selected-tools-summary">
              <strong>{config.tools_allowed.length}</strong> tools selected
            </div>
          </div>
        )}

        {/* Step 5: Review */}
        {step === 5 && (
          <div className="step-content">
            <h2>Review & Create</h2>
            <p>Review your agent configuration</p>

            <div className="review-section">
              <h3>Basic Info</h3>
              <div className="review-item">
                <span className="label">Name:</span>
                <span className="value">{config.name}</span>
              </div>
              <div className="review-item">
                <span className="label">Description:</span>
                <span className="value">{config.description || 'Not set'}</span>
              </div>
            </div>

            <div className="review-section">
              <h3>Voice</h3>
              <div className="review-item">
                <span className="label">Voice:</span>
                <span className="value">{voiceOptions.find(v => v.id === config.voice_id)?.name}</span>
              </div>
              <div className="review-item">
                <span className="label">Stability:</span>
                <span className="value">{config.voice_stability}</span>
              </div>
            </div>

            <div className="review-section">
              <h3>Behavior</h3>
              <div className="review-item">
                <span className="label">Features:</span>
                <span className="value">
                  {[
                    config.interrupt_enabled && 'Interrupts',
                    config.filler_words_enabled && 'Natural Fillers',
                    config.emotion_detection_enabled && 'Emotion Detection'
                  ].filter(Boolean).join(', ')}
                </span>
              </div>
            </div>

            <div className="review-section">
              <h3>Tools ({config.tools_allowed.length})</h3>
              <div className="tools-preview">
                {config.tools_allowed.map(tool => (
                  <span key={tool} className="tool-tag">{tool}</span>
                ))}
              </div>
            </div>

            <div className="review-section">
              <h3>System Prompt</h3>
              <pre className="prompt-preview">{config.system_prompt}</pre>
            </div>
          </div>
        )}
      </div>

      <div className="builder-footer">
        <button
          className="btn-cancel"
          onClick={onCancel}
        >
          Cancel
        </button>
        <div className="nav-buttons">
          {step > 1 && (
            <button
              className="btn-back"
              onClick={() => setStep(step - 1)}
            >
              Back
            </button>
          )}
          {step < 5 ? (
            <button
              className="btn-next"
              onClick={() => setStep(step + 1)}
              disabled={!isStepValid(step)}
            >
              Next
            </button>
          ) : (
            <button
              className="btn-save"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Creating...' : 'Create Agent'}
            </button>
          )}
        </div>
      </div>

      <style>{`
        .agent-builder {
          max-width: 900px;
          margin: 0 auto;
          padding: 24px;
        }

        .builder-header {
          margin-bottom: 32px;
        }

        .builder-header h1 {
          margin: 0 0 24px 0;
          font-size: 28px;
        }

        .step-indicator {
          display: flex;
          gap: 8px;
        }

        .step {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          background: #f3f4f6;
          border-radius: 8px;
          cursor: pointer;
        }

        .step.active {
          background: #2563eb;
          color: white;
        }

        .step.completed {
          background: #dcfce7;
          color: #16a34a;
        }

        .step-number {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: rgba(0,0,0,0.1);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 600;
        }

        .step.active .step-number {
          background: rgba(255,255,255,0.2);
        }

        .step-label {
          font-size: 14px;
        }

        .builder-content {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 32px;
          min-height: 500px;
        }

        .step-content h2 {
          margin: 0 0 8px 0;
          font-size: 24px;
        }

        .step-content > p {
          color: #666;
          margin: 0 0 24px 0;
        }

        .form-group {
          margin-bottom: 20px;
        }

        .form-group label {
          display: block;
          font-weight: 500;
          margin-bottom: 8px;
        }

        .form-group input[type="text"],
        .form-group input[type="number"],
        .form-group textarea {
          width: 100%;
          padding: 12px;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          font-size: 14px;
        }

        .form-group textarea {
          resize: vertical;
          font-family: inherit;
        }

        .hint {
          display: block;
          font-size: 12px;
          color: #666;
          margin-top: 4px;
        }

        .voice-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          margin-bottom: 32px;
        }

        .voice-option {
          border: 2px solid #e5e7eb;
          border-radius: 12px;
          padding: 16px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .voice-option:hover {
          border-color: #2563eb;
        }

        .voice-option.selected {
          border-color: #2563eb;
          background: #f0f7ff;
        }

        .voice-option h4 {
          margin: 0 0 4px 0;
        }

        .voice-option p {
          margin: 0 0 8px 0;
          color: #666;
          font-size: 14px;
        }

        .personality {
          font-size: 12px;
          color: #2563eb;
        }

        .voice-settings h3 {
          margin: 0 0 16px 0;
          font-size: 16px;
        }

        .slider-group {
          margin-bottom: 16px;
        }

        .slider-group label {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .slider-group input[type="range"] {
          width: 100%;
        }

        .templates-section {
          margin-bottom: 24px;
        }

        .templates-section h3 {
          margin: 0 0 12px 0;
          font-size: 16px;
        }

        .template-buttons {
          display: flex;
          gap: 12px;
        }

        .btn-template {
          padding: 10px 16px;
          border: 1px solid #d1d5db;
          background: white;
          border-radius: 8px;
          cursor: pointer;
        }

        .btn-template:hover {
          background: #f3f4f6;
        }

        .behavior-toggles {
          margin-top: 24px;
        }

        .behavior-toggles h3 {
          margin: 0 0 16px 0;
          font-size: 16px;
        }

        .toggle-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
        }

        .toggle {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          cursor: pointer;
        }

        .toggle input {
          margin-top: 2px;
        }

        .toggle span:first-of-type {
          font-weight: 500;
        }

        .toggle-hint {
          display: block;
          font-size: 12px;
          color: #666;
        }

        .llm-settings {
          margin-top: 24px;
        }

        .llm-settings h3 {
          margin: 0 0 16px 0;
          font-size: 16px;
        }

        .settings-row {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
        }

        .tools-by-category {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .tool-category h3 {
          margin: 0 0 12px 0;
          font-size: 16px;
          color: #666;
        }

        .tools-list {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
        }

        .tool-option {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          cursor: pointer;
        }

        .tool-option.selected {
          background: #f0f7ff;
          border-color: #2563eb;
        }

        .tool-info {
          display: flex;
          flex-direction: column;
        }

        .tool-name {
          font-weight: 500;
        }

        .tool-desc {
          font-size: 12px;
          color: #666;
        }

        .selected-tools-summary {
          margin-top: 16px;
          padding: 12px;
          background: #f3f4f6;
          border-radius: 8px;
          text-align: center;
        }

        .review-section {
          margin-bottom: 24px;
          padding-bottom: 24px;
          border-bottom: 1px solid #e5e7eb;
        }

        .review-section h3 {
          margin: 0 0 12px 0;
          font-size: 14px;
          color: #666;
          text-transform: uppercase;
        }

        .review-item {
          display: flex;
          margin-bottom: 8px;
        }

        .review-item .label {
          width: 120px;
          color: #666;
        }

        .review-item .value {
          font-weight: 500;
        }

        .tools-preview {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .tool-tag {
          background: #F5EDD9;
          color: #6B5424;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
        }

        .prompt-preview {
          background: #f9fafb;
          padding: 16px;
          border-radius: 8px;
          font-size: 13px;
          white-space: pre-wrap;
          max-height: 200px;
          overflow-y: auto;
        }

        .builder-footer {
          display: flex;
          justify-content: space-between;
          margin-top: 24px;
        }

        .nav-buttons {
          display: flex;
          gap: 12px;
        }

        .btn-cancel {
          background: none;
          border: 1px solid #d1d5db;
          padding: 12px 24px;
          border-radius: 8px;
          cursor: pointer;
        }

        .btn-back {
          background: #f3f4f6;
          border: none;
          padding: 12px 24px;
          border-radius: 8px;
          cursor: pointer;
        }

        .btn-next,
        .btn-save {
          background: #2563eb;
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
        }

        .btn-next:disabled,
        .btn-save:disabled {
          background: #93c5fd;
          cursor: not-allowed;
        }

        .btn-save {
          background: #16a34a;
        }
      `}</style>
    </div>
  );
};

export default AgentBuilder;
