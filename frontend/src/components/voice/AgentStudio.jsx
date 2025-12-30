/**
 * Agent Studio Component
 *
 * Create, configure, and manage Voice OS agents.
 * Provides UI for:
 * - Agent creation and editing
 * - System prompt configuration
 * - Tool selection and enablement
 * - Voice and model settings
 * - Agent testing and deployment
 */

import React, { useState, useEffect, useCallback } from 'react';
import './AgentStudio.css';

const AVAILABLE_VOICES = [
  { id: 'alloy', name: 'Alloy', description: 'Balanced and neutral' },
  { id: 'echo', name: 'Echo', description: 'Deep and resonant' },
  { id: 'fable', name: 'Fable', description: 'Warm and expressive' },
  { id: 'onyx', name: 'Onyx', description: 'Authoritative and clear' },
  { id: 'nova', name: 'Nova', description: 'Youthful and energetic' },
  { id: 'shimmer', name: 'Shimmer', description: 'Soft and friendly' },
];

const AVAILABLE_MODELS = [
  { id: 'gpt-4o', name: 'GPT-4o', description: 'Most capable, higher cost' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', description: 'Fast and cost-effective' },
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', description: 'Fast and economical' },
];

const AVAILABLE_TOOLS = [
  { id: 'lookup_caller', name: 'Lookup Caller', category: 'Contact', description: 'Find contact by phone number' },
  { id: 'create_lead', name: 'Create Lead', category: 'Lead', description: 'Create a new lead' },
  { id: 'update_lead_stage', name: 'Update Lead Stage', category: 'Lead', description: 'Move lead to next stage' },
  { id: 'qualify_lead', name: 'Qualify Lead', category: 'Lead', description: 'Qualify a lead based on criteria' },
  { id: 'get_lo_availability', name: 'Get LO Availability', category: 'Scheduling', description: 'Check loan officer availability' },
  { id: 'schedule_appointment', name: 'Schedule Appointment', category: 'Scheduling', description: 'Book an appointment' },
  { id: 'create_callback_request', name: 'Create Callback', category: 'Scheduling', description: 'Schedule a callback' },
  { id: 'get_loan_status', name: 'Get Loan Status', category: 'Loan', description: 'Check loan application status' },
  { id: 'request_documents', name: 'Request Documents', category: 'Loan', description: 'Request documents from borrower' },
  { id: 'log_call_note', name: 'Log Call Note', category: 'Communication', description: 'Add notes to call record' },
  { id: 'create_task', name: 'Create Task', category: 'Communication', description: 'Create a follow-up task' },
  { id: 'leave_message', name: 'Leave Message', category: 'Communication', description: 'Leave a message for contact' },
  { id: 'escalate_to_human', name: 'Escalate to Human', category: 'Call', description: 'Transfer to human operator' },
  { id: 'transfer_call', name: 'Transfer Call', category: 'Call', description: 'Transfer call to another party' },
  { id: 'find_available_lo', name: 'Find Available LO', category: 'Call', description: 'Find available loan officer' },
  { id: 'get_current_rates', name: 'Get Rates', category: 'Info', description: 'Get current mortgage rates' },
];

const DEFAULT_AGENT = {
  name: '',
  displayName: '',
  description: '',
  role: 'receptionist',
  voice: 'nova',
  model: 'gpt-4o-mini',
  systemPrompt: `You are a friendly and professional AI receptionist for a mortgage company.

Your goals:
- Greet callers warmly and identify their needs
- Help existing borrowers check loan status
- Qualify and capture new leads
- Schedule appointments with loan officers
- Answer common questions about rates and processes

Guidelines:
- Be concise but helpful
- Always verify caller identity before sharing sensitive info
- If unsure, offer to connect with a human representative
- Log important information from every call`,
  enabledTools: ['lookup_caller', 'get_loan_status', 'schedule_appointment', 'log_call_note', 'escalate_to_human'],
  isActive: true,
  settings: {
    maxTurns: 20,
    timeoutSeconds: 30,
    silenceTimeoutMs: 3000,
    interruptionHandling: 'graceful',
    transferOnFail: true,
  },
};

const AgentStudio = () => {
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [editingAgent, setEditingAgent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('config');

  // Fetch agents on mount
  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/voice/agents');
      if (response.ok) {
        const data = await response.json();
        setAgents(data.agents || []);
      } else {
        // Mock data if API not available
        setAgents([
          {
            id: '1',
            ...DEFAULT_AGENT,
            name: 'receptionist',
            displayName: 'Main Receptionist',
            description: 'Primary inbound call handler',
          },
        ]);
      }
    } catch (err) {
      console.error('Failed to fetch agents:', err);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAgent = () => {
    setEditingAgent({
      ...DEFAULT_AGENT,
      id: null,
    });
    setSelectedAgent(null);
    setActiveTab('config');
  };

  const handleEditAgent = (agent) => {
    setEditingAgent({ ...agent });
    setSelectedAgent(agent);
    setActiveTab('config');
  };

  const handleSaveAgent = async () => {
    if (!editingAgent.name) {
      setError('Agent name is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const url = editingAgent.id
        ? `/api/voice/agents/${editingAgent.id}`
        : '/api/voice/agents';
      const method = editingAgent.id ? 'PUT' : 'POST';

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingAgent),
      });

      if (response.ok) {
        const savedAgent = await response.json();
        if (editingAgent.id) {
          setAgents(agents.map(a => a.id === savedAgent.id ? savedAgent : a));
        } else {
          setAgents([...agents, savedAgent]);
        }
        setEditingAgent(savedAgent);
        setSelectedAgent(savedAgent);
      } else {
        throw new Error('Failed to save agent');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAgent = async (agentId) => {
    if (!window.confirm('Are you sure you want to delete this agent?')) return;

    try {
      const response = await fetch(`/api/voice/agents/${agentId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setAgents(agents.filter(a => a.id !== agentId));
        if (selectedAgent?.id === agentId) {
          setSelectedAgent(null);
          setEditingAgent(null);
        }
      }
    } catch (err) {
      setError('Failed to delete agent');
    }
  };

  const handleTestAgent = async () => {
    if (!editingAgent) return;

    setTesting(true);
    setTestResult(null);

    try {
      const response = await fetch('/api/voice/agents/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agentConfig: editingAgent,
          testPrompt: 'Hello, I want to check the status of my loan application.',
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setTestResult(result);
      } else {
        setTestResult({
          success: false,
          error: 'Test failed',
          response: 'Unable to test agent configuration',
        });
      }
    } catch (err) {
      setTestResult({
        success: false,
        error: err.message,
        response: 'Test connection failed',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleToggleTool = (toolId) => {
    if (!editingAgent) return;

    const enabledTools = editingAgent.enabledTools || [];
    const newTools = enabledTools.includes(toolId)
      ? enabledTools.filter(t => t !== toolId)
      : [...enabledTools, toolId];

    setEditingAgent({ ...editingAgent, enabledTools: newTools });
  };

  const updateField = useCallback((field, value) => {
    setEditingAgent(prev => ({ ...prev, [field]: value }));
  }, []);

  const updateSetting = useCallback((field, value) => {
    setEditingAgent(prev => ({
      ...prev,
      settings: { ...prev.settings, [field]: value },
    }));
  }, []);

  const toolsByCategory = AVAILABLE_TOOLS.reduce((acc, tool) => {
    if (!acc[tool.category]) acc[tool.category] = [];
    acc[tool.category].push(tool);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="agent-studio loading">
        <div className="loading-spinner">Loading agents...</div>
      </div>
    );
  }

  return (
    <div className="agent-studio">
      {/* Agent List Sidebar */}
      <div className="agent-sidebar">
        <div className="sidebar-header">
          <h2>Voice Agents</h2>
          <button className="btn-create" onClick={handleCreateAgent}>
            + New Agent
          </button>
        </div>

        <div className="agent-list">
          {agents.map(agent => (
            <div
              key={agent.id}
              className={`agent-item ${selectedAgent?.id === agent.id ? 'active' : ''}`}
              onClick={() => handleEditAgent(agent)}
            >
              <div className="agent-info">
                <span className="agent-name">{agent.displayName || agent.name}</span>
                <span className="agent-role">{agent.role}</span>
              </div>
              <span className={`status-badge ${agent.isActive ? 'active' : 'inactive'}`}>
                {agent.isActive ? 'Active' : 'Inactive'}
              </span>
            </div>
          ))}

          {agents.length === 0 && (
            <div className="no-agents">
              <p>No agents configured</p>
              <button onClick={handleCreateAgent}>Create your first agent</button>
            </div>
          )}
        </div>
      </div>

      {/* Main Editor */}
      <div className="agent-editor">
        {editingAgent ? (
          <>
            <div className="editor-header">
              <h2>{editingAgent.id ? 'Edit Agent' : 'Create Agent'}</h2>
              <div className="editor-actions">
                <button
                  className="btn-test"
                  onClick={handleTestAgent}
                  disabled={testing}
                >
                  {testing ? 'Testing...' : 'Test Agent'}
                </button>
                <button
                  className="btn-save"
                  onClick={handleSaveAgent}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Agent'}
                </button>
                {editingAgent.id && (
                  <button
                    className="btn-delete"
                    onClick={() => handleDeleteAgent(editingAgent.id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {testResult && (
              <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
                <h4>Test Result</h4>
                <p>{testResult.response}</p>
                {testResult.toolsUsed && (
                  <div className="tools-used">
                    <span>Tools used:</span>
                    {testResult.toolsUsed.map(t => (
                      <span key={t} className="tool-badge">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Tabs */}
            <div className="editor-tabs">
              <button
                className={activeTab === 'config' ? 'active' : ''}
                onClick={() => setActiveTab('config')}
              >
                Configuration
              </button>
              <button
                className={activeTab === 'prompt' ? 'active' : ''}
                onClick={() => setActiveTab('prompt')}
              >
                System Prompt
              </button>
              <button
                className={activeTab === 'tools' ? 'active' : ''}
                onClick={() => setActiveTab('tools')}
              >
                Tools ({editingAgent.enabledTools?.length || 0})
              </button>
              <button
                className={activeTab === 'settings' ? 'active' : ''}
                onClick={() => setActiveTab('settings')}
              >
                Advanced
              </button>
            </div>

            {/* Tab Content */}
            <div className="tab-content">
              {activeTab === 'config' && (
                <div className="config-tab">
                  <div className="form-group">
                    <label>Agent ID</label>
                    <input
                      type="text"
                      value={editingAgent.name}
                      onChange={e => updateField('name', e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                      placeholder="e.g., main_receptionist"
                    />
                    <span className="help-text">Unique identifier (lowercase, no spaces)</span>
                  </div>

                  <div className="form-group">
                    <label>Display Name</label>
                    <input
                      type="text"
                      value={editingAgent.displayName}
                      onChange={e => updateField('displayName', e.target.value)}
                      placeholder="e.g., Main Receptionist"
                    />
                  </div>

                  <div className="form-group">
                    <label>Description</label>
                    <textarea
                      value={editingAgent.description}
                      onChange={e => updateField('description', e.target.value)}
                      placeholder="Describe what this agent does..."
                      rows={2}
                    />
                  </div>

                  <div className="form-group">
                    <label>Role</label>
                    <select
                      value={editingAgent.role}
                      onChange={e => updateField('role', e.target.value)}
                    >
                      <option value="receptionist">Receptionist</option>
                      <option value="lead_qualifier">Lead Qualifier</option>
                      <option value="appointment_scheduler">Appointment Scheduler</option>
                      <option value="status_checker">Status Checker</option>
                      <option value="outbound_caller">Outbound Caller</option>
                    </select>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Voice</label>
                      <select
                        value={editingAgent.voice}
                        onChange={e => updateField('voice', e.target.value)}
                      >
                        {AVAILABLE_VOICES.map(v => (
                          <option key={v.id} value={v.id}>
                            {v.name} - {v.description}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>AI Model</label>
                      <select
                        value={editingAgent.model}
                        onChange={e => updateField('model', e.target.value)}
                      >
                        {AVAILABLE_MODELS.map(m => (
                          <option key={m.id} value={m.id}>
                            {m.name} - {m.description}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={editingAgent.isActive}
                        onChange={e => updateField('isActive', e.target.checked)}
                      />
                      Agent is active and can handle calls
                    </label>
                  </div>
                </div>
              )}

              {activeTab === 'prompt' && (
                <div className="prompt-tab">
                  <div className="form-group">
                    <label>System Prompt</label>
                    <textarea
                      className="system-prompt-editor"
                      value={editingAgent.systemPrompt}
                      onChange={e => updateField('systemPrompt', e.target.value)}
                      placeholder="Define how the agent should behave..."
                      rows={20}
                    />
                    <span className="help-text">
                      This prompt defines the agent's personality, goals, and behavior guidelines.
                      Be specific about what the agent should and shouldn't do.
                    </span>
                  </div>

                  <div className="prompt-templates">
                    <h4>Quick Templates</h4>
                    <button onClick={() => updateField('systemPrompt', DEFAULT_AGENT.systemPrompt)}>
                      Default Receptionist
                    </button>
                    <button onClick={() => updateField('systemPrompt', `You are a mortgage lead qualification specialist.

Your goal is to determine if callers are qualified leads by gathering:
- Their timeline for purchasing/refinancing
- Estimated credit score range
- Down payment availability
- Property type and location
- Employment status

Be friendly but efficient. If they're a good fit, schedule them with a loan officer.
If they're not ready, offer to add them to our newsletter.`)}>
                      Lead Qualifier
                    </button>
                  </div>
                </div>
              )}

              {activeTab === 'tools' && (
                <div className="tools-tab">
                  <p className="tools-intro">
                    Select which CRM tools this agent can use during calls.
                    Only enable tools the agent actually needs.
                  </p>

                  {Object.entries(toolsByCategory).map(([category, tools]) => (
                    <div key={category} className="tool-category">
                      <h4>{category}</h4>
                      <div className="tool-list">
                        {tools.map(tool => (
                          <label key={tool.id} className="tool-item">
                            <input
                              type="checkbox"
                              checked={editingAgent.enabledTools?.includes(tool.id)}
                              onChange={() => handleToggleTool(tool.id)}
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
              )}

              {activeTab === 'settings' && (
                <div className="settings-tab">
                  <div className="form-group">
                    <label>Maximum Conversation Turns</label>
                    <input
                      type="number"
                      value={editingAgent.settings?.maxTurns || 20}
                      onChange={e => updateSetting('maxTurns', parseInt(e.target.value))}
                      min={5}
                      max={100}
                    />
                    <span className="help-text">End call after this many back-and-forth exchanges</span>
                  </div>

                  <div className="form-group">
                    <label>Response Timeout (seconds)</label>
                    <input
                      type="number"
                      value={editingAgent.settings?.timeoutSeconds || 30}
                      onChange={e => updateSetting('timeoutSeconds', parseInt(e.target.value))}
                      min={5}
                      max={120}
                    />
                    <span className="help-text">Time to wait for AI response before timeout</span>
                  </div>

                  <div className="form-group">
                    <label>Silence Timeout (ms)</label>
                    <input
                      type="number"
                      value={editingAgent.settings?.silenceTimeoutMs || 3000}
                      onChange={e => updateSetting('silenceTimeoutMs', parseInt(e.target.value))}
                      min={1000}
                      max={10000}
                      step={500}
                    />
                    <span className="help-text">Time to wait before assuming speaker is done</span>
                  </div>

                  <div className="form-group">
                    <label>Interruption Handling</label>
                    <select
                      value={editingAgent.settings?.interruptionHandling || 'graceful'}
                      onChange={e => updateSetting('interruptionHandling', e.target.value)}
                    >
                      <option value="ignore">Ignore - Continue speaking</option>
                      <option value="graceful">Graceful - Finish sentence then listen</option>
                      <option value="immediate">Immediate - Stop and listen</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={editingAgent.settings?.transferOnFail !== false}
                        onChange={e => updateSetting('transferOnFail', e.target.checked)}
                      />
                      Transfer to human operator on failure
                    </label>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="no-selection">
            <div className="empty-state">
              <h3>No Agent Selected</h3>
              <p>Select an agent from the list or create a new one to get started.</p>
              <button onClick={handleCreateAgent}>Create New Agent</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentStudio;
