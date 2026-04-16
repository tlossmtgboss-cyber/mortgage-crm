/**
 * Retell AI Settings Component
 *
 * Configuration UI for Retell AI voice platform.
 * Replaces ElevenLabs with unified voice solution via Telnyx.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './RetellSettings.css';
import TelnyxRetellBridge from './TelnyxRetellBridge';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const RetellSettings = () => {
  // Connection state
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Configuration
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  // Data
  const [agents, setAgents] = useState([]);
  const [phoneNumbers, setPhoneNumbers] = useState([]);
  const [voices, setVoices] = useState([]);
  const [analytics, setAnalytics] = useState(null);

  // UI State
  const [activeTab, setActiveTab] = useState('overview');
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [showAddPhone, setShowAddPhone] = useState(false);
  const [testingVoice, setTestingVoice] = useState(null);

  // New agent form
  const [newAgent, setNewAgent] = useState({
    agent_name: '',
    agent_type: 'receptionist',
    voice_id: '11labs-Emma',
    company_name: '',
    business_hours: 'Monday-Friday, 9 AM - 6 PM',
  });

  // New phone form
  const [newPhone, setNewPhone] = useState({
    agent_id: '',
    area_code: '',
  });

  const getAuthHeaders = useCallback(() => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }, []);

  // Check connection status
  const checkStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/status`, {
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      setConnected(data.connected);
      return data.connected;
    } catch (err) {
      setConnected(false);
      return false;
    }
  }, [getAuthHeaders]);

  // Load all data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const isConnected = await checkStatus();

      if (isConnected) {
        // Load agents
        const agentsRes = await fetch(`${API_BASE}/api/v1/retell/agents`, {
          headers: getAuthHeaders(),
        });
        if (agentsRes.ok) {
          const agentsData = await agentsRes.json();
          setAgents(agentsData.agents || []);
        }

        // Load phone numbers
        const phonesRes = await fetch(`${API_BASE}/api/v1/retell/phone-numbers`, {
          headers: getAuthHeaders(),
        });
        if (phonesRes.ok) {
          const phonesData = await phonesRes.json();
          setPhoneNumbers(phonesData.phone_numbers || []);
        }

        // Load voices
        const voicesRes = await fetch(`${API_BASE}/api/v1/retell/voices`, {
          headers: getAuthHeaders(),
        });
        if (voicesRes.ok) {
          const voicesData = await voicesRes.json();
          setVoices(voicesData.voices || []);
        }

        // Load analytics
        const analyticsRes = await fetch(`${API_BASE}/api/v1/retell/analytics/calls?days=30`, {
          headers: getAuthHeaders(),
        });
        if (analyticsRes.ok) {
          const analyticsData = await analyticsRes.json();
          setAnalytics(analyticsData);
        }
      }
    } catch (err) {
      console.error('Failed to load Retell data:', err);
    } finally {
      setLoading(false);
    }
  }, [checkStatus, getAuthHeaders]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Connect to Retell
  const handleConnect = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/connect`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ api_key: apiKey }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to connect');
      }

      setSuccess('Successfully connected to Retell AI!');
      setApiKey('');
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Create agent
  const handleCreateAgent = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/agents`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(newAgent),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create agent');
      }

      setSuccess('Agent created successfully!');
      setShowCreateAgent(false);
      setNewAgent({
        agent_name: '',
        agent_type: 'receptionist',
        voice_id: '11labs-Emma',
        company_name: '',
        business_hours: 'Monday-Friday, 9 AM - 6 PM',
      });
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Delete agent
  const handleDeleteAgent = async (agentId) => {
    if (!window.confirm('Are you sure you want to delete this agent?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/agents/${agentId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Failed to delete agent');
      }

      setSuccess('Agent deleted');
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  // Create phone number
  const handleCreatePhone = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/phone-numbers`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          agent_id: newPhone.agent_id,
          area_code: newPhone.area_code ? parseInt(newPhone.area_code) : undefined,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create phone number');
      }

      setSuccess('Phone number purchased successfully!');
      setShowAddPhone(false);
      setNewPhone({ agent_id: '', area_code: '' });
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Delete phone number
  const handleDeletePhone = async (phoneNumber) => {
    if (!window.confirm('Are you sure you want to release this phone number?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/retell/phone-numbers/${encodeURIComponent(phoneNumber)}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Failed to release phone number');
      }

      setSuccess('Phone number released');
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  // Clear messages after timeout
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  // Render connection form
  const renderConnectionForm = () => (
    <div className="retell-connection-card">
      <div className="retell-logo">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </div>
      <h2>Connect Retell AI</h2>
      <p>Enter your Retell AI API key to enable voice agents</p>

      <form onSubmit={handleConnect} className="retell-connect-form">
        <div className="retell-input-group">
          <label>API Key</label>
          <div className="retell-password-input">
            <input
              type={showApiKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="ret_..."
              required
            />
            <button
              type="button"
              className="retell-toggle-visibility"
              onClick={() => setShowApiKey(!showApiKey)}
            >
              {showApiKey ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>

        <button type="submit" className="retell-btn-primary" disabled={loading || !apiKey}>
          {loading ? 'Connecting...' : 'Connect'}
        </button>
      </form>

      <p className="retell-help-text">
        Get your API key from{' '}
        <a href="https://dashboard.retellai.com" target="_blank" rel="noopener noreferrer">
          dashboard.retellai.com
        </a>
      </p>
    </div>
  );

  // Render overview tab
  const renderOverview = () => (
    <div className="retell-overview">
      <div className="retell-stats-grid">
        <div className="retell-stat-card">
          <div className="retell-stat-icon agents">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div className="retell-stat-content">
            <span className="retell-stat-value">{agents.length}</span>
            <span className="retell-stat-label">Voice Agents</span>
          </div>
        </div>

        <div className="retell-stat-card">
          <div className="retell-stat-icon phones">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
          </div>
          <div className="retell-stat-content">
            <span className="retell-stat-value">{phoneNumbers.length}</span>
            <span className="retell-stat-label">Phone Numbers</span>
          </div>
        </div>

        <div className="retell-stat-card">
          <div className="retell-stat-icon calls">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
          </div>
          <div className="retell-stat-content">
            <span className="retell-stat-value">{analytics?.summary?.total_calls || 0}</span>
            <span className="retell-stat-label">Calls (30 days)</span>
          </div>
        </div>

        <div className="retell-stat-card">
          <div className="retell-stat-icon success">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div className="retell-stat-content">
            <span className="retell-stat-value">{analytics?.summary?.success_rate || 0}%</span>
            <span className="retell-stat-label">Success Rate</span>
          </div>
        </div>
      </div>

      {analytics && (
        <div className="retell-analytics-summary">
          <h3>Last 30 Days</h3>
          <div className="retell-analytics-metrics">
            <div className="retell-metric">
              <span className="retell-metric-label">Completed Calls</span>
              <span className="retell-metric-value">{analytics.summary.completed_calls}</span>
            </div>
            <div className="retell-metric">
              <span className="retell-metric-label">Avg Duration</span>
              <span className="retell-metric-value">{Math.round(analytics.summary.avg_duration_seconds)}s</span>
            </div>
            <div className="retell-metric">
              <span className="retell-metric-label">Successful Calls</span>
              <span className="retell-metric-value">{analytics.summary.successful_calls}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // Render agents tab
  const renderAgents = () => (
    <div className="retell-agents">
      <div className="retell-section-header">
        <h3>Voice Agents</h3>
        <button className="retell-btn-primary" onClick={() => setShowCreateAgent(true)}>
          + Create Agent
        </button>
      </div>

      {agents.length === 0 ? (
        <div className="retell-empty-state">
          <p>No agents created yet. Create your first AI voice agent to get started.</p>
        </div>
      ) : (
        <div className="retell-agents-list">
          {agents.map((agent) => (
            <div key={agent.agent_id} className="retell-agent-card">
              <div className="retell-agent-avatar">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </div>
              <div className="retell-agent-info">
                <h4>{agent.agent_name}</h4>
                <span className="retell-agent-voice">{agent.voice_id}</span>
              </div>
              <div className="retell-agent-actions">
                <button
                  className="retell-btn-icon"
                  onClick={() => handleDeleteAgent(agent.agent_id)}
                  title="Delete agent"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Agent Modal */}
      {showCreateAgent && (
        <div className="retell-modal-overlay" onClick={() => setShowCreateAgent(false)}>
          <div className="retell-modal" onClick={(e) => e.stopPropagation()}>
            <div className="retell-modal-header">
              <h3>Create Voice Agent</h3>
              <button className="retell-modal-close" onClick={() => setShowCreateAgent(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateAgent}>
              <div className="retell-modal-body">
                <div className="retell-form-group">
                  <label>Agent Name</label>
                  <input
                    type="text"
                    value={newAgent.agent_name}
                    onChange={(e) => setNewAgent({ ...newAgent, agent_name: e.target.value })}
                    placeholder="e.g., Sam - AI Receptionist"
                    required
                  />
                </div>

                <div className="retell-form-group">
                  <label>Agent Type</label>
                  <select
                    value={newAgent.agent_type}
                    onChange={(e) => setNewAgent({ ...newAgent, agent_type: e.target.value })}
                  >
                    <option value="receptionist">AI Receptionist</option>
                    <option value="marketing">Marketing Assistant</option>
                    <option value="custom">Custom Agent</option>
                  </select>
                </div>

                <div className="retell-form-group">
                  <label>Voice</label>
                  <select
                    value={newAgent.voice_id}
                    onChange={(e) => setNewAgent({ ...newAgent, voice_id: e.target.value })}
                  >
                    <optgroup label="ElevenLabs Voices">
                      <option value="11labs-Emma">Emma (Female, Professional)</option>
                      <option value="11labs-Dorothy">Dorothy (Female, Warm)</option>
                      <option value="11labs-Matilda">Matilda (Female, Friendly)</option>
                      <option value="11labs-Rachel">Rachel (Female, Clear)</option>
                      <option value="11labs-Adam">Adam (Male, Professional)</option>
                      <option value="11labs-Josh">Josh (Male, Casual)</option>
                      <option value="11labs-Michael">Michael (Male, Authoritative)</option>
                      <option value="11labs-Chris">Chris (Male, Friendly)</option>
                    </optgroup>
                    <optgroup label="OpenAI Voices">
                      <option value="openai-Alloy">Alloy (Neutral)</option>
                      <option value="openai-Echo">Echo (Clear)</option>
                      <option value="openai-Nova">Nova (Energetic)</option>
                      <option value="openai-Shimmer">Shimmer (Soft)</option>
                    </optgroup>
                  </select>
                </div>

                <div className="retell-form-group">
                  <label>Company Name</label>
                  <input
                    type="text"
                    value={newAgent.company_name}
                    onChange={(e) => setNewAgent({ ...newAgent, company_name: e.target.value })}
                    placeholder="Your Company Name"
                  />
                </div>

                <div className="retell-form-group">
                  <label>Business Hours</label>
                  <input
                    type="text"
                    value={newAgent.business_hours}
                    onChange={(e) => setNewAgent({ ...newAgent, business_hours: e.target.value })}
                    placeholder="Monday-Friday, 9 AM - 6 PM"
                  />
                </div>
              </div>
              <div className="retell-modal-footer">
                <button type="button" className="retell-btn-secondary" onClick={() => setShowCreateAgent(false)}>
                  Cancel
                </button>
                <button type="submit" className="retell-btn-primary" disabled={loading}>
                  {loading ? 'Creating...' : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );

  // Render phone numbers tab
  const renderPhoneNumbers = () => (
    <div className="retell-phones">
      <div className="retell-section-header">
        <h3>Phone Numbers</h3>
        <button
          className="retell-btn-primary"
          onClick={() => setShowAddPhone(true)}
          disabled={agents.length === 0}
        >
          + Add Number
        </button>
      </div>

      {phoneNumbers.length === 0 ? (
        <div className="retell-empty-state">
          <p>No phone numbers configured. Add a number to enable inbound and outbound calls.</p>
        </div>
      ) : (
        <div className="retell-phones-list">
          {phoneNumbers.map((phone) => (
            <div key={phone.phone_number} className="retell-phone-card">
              <div className="retell-phone-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
              </div>
              <div className="retell-phone-info">
                <h4>{phone.phone_number}</h4>
                <span className="retell-phone-agent">
                  Agent: {agents.find(a => a.agent_id === phone.agent_id)?.agent_name || 'Unassigned'}
                </span>
              </div>
              <div className="retell-phone-actions">
                <button
                  className="retell-btn-icon danger"
                  onClick={() => handleDeletePhone(phone.phone_number)}
                  title="Release number"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Phone Modal */}
      {showAddPhone && (
        <div className="retell-modal-overlay" onClick={() => setShowAddPhone(false)}>
          <div className="retell-modal" onClick={(e) => e.stopPropagation()}>
            <div className="retell-modal-header">
              <h3>Add Phone Number</h3>
              <button className="retell-modal-close" onClick={() => setShowAddPhone(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreatePhone}>
              <div className="retell-modal-body">
                <div className="retell-form-group">
                  <label>Assign to Agent</label>
                  <select
                    value={newPhone.agent_id}
                    onChange={(e) => setNewPhone({ ...newPhone, agent_id: e.target.value })}
                    required
                  >
                    <option value="">Select an agent...</option>
                    {agents.map((agent) => (
                      <option key={agent.agent_id} value={agent.agent_id}>
                        {agent.agent_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="retell-form-group">
                  <label>Preferred Area Code (Optional)</label>
                  <input
                    type="text"
                    value={newPhone.area_code}
                    onChange={(e) => setNewPhone({ ...newPhone, area_code: e.target.value })}
                    placeholder="e.g., 415"
                    maxLength={3}
                  />
                </div>

                <p className="retell-form-note">
                  A new phone number will be purchased and assigned to the selected agent.
                  Standard Retell telephony rates apply.
                </p>
              </div>
              <div className="retell-modal-footer">
                <button type="button" className="retell-btn-secondary" onClick={() => setShowAddPhone(false)}>
                  Cancel
                </button>
                <button type="submit" className="retell-btn-primary" disabled={loading || !newPhone.agent_id}>
                  {loading ? 'Adding...' : 'Add Number'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );

  // Render voices tab
  const renderVoices = () => (
    <div className="retell-voices">
      <h3>Available Voices</h3>
      <p className="retell-voices-intro">
        Preview and select from a variety of high-quality AI voices for your agents.
      </p>

      <div className="retell-voices-grid">
        {[
          { id: '11labs-Emma', name: 'Emma', provider: 'ElevenLabs', gender: 'Female', style: 'Professional' },
          { id: '11labs-Dorothy', name: 'Dorothy', provider: 'ElevenLabs', gender: 'Female', style: 'Warm' },
          { id: '11labs-Matilda', name: 'Matilda', provider: 'ElevenLabs', gender: 'Female', style: 'Friendly' },
          { id: '11labs-Rachel', name: 'Rachel', provider: 'ElevenLabs', gender: 'Female', style: 'Clear' },
          { id: '11labs-Adam', name: 'Adam', provider: 'ElevenLabs', gender: 'Male', style: 'Professional' },
          { id: '11labs-Josh', name: 'Josh', provider: 'ElevenLabs', gender: 'Male', style: 'Casual' },
          { id: '11labs-Michael', name: 'Michael', provider: 'ElevenLabs', gender: 'Male', style: 'Authoritative' },
          { id: '11labs-Chris', name: 'Chris', provider: 'ElevenLabs', gender: 'Male', style: 'Friendly' },
          { id: 'openai-Alloy', name: 'Alloy', provider: 'OpenAI', gender: 'Neutral', style: 'Professional' },
          { id: 'openai-Echo', name: 'Echo', provider: 'OpenAI', gender: 'Neutral', style: 'Clear' },
          { id: 'openai-Nova', name: 'Nova', provider: 'OpenAI', gender: 'Neutral', style: 'Energetic' },
          { id: 'openai-Shimmer', name: 'Shimmer', provider: 'OpenAI', gender: 'Neutral', style: 'Soft' },
        ].map((voice) => (
          <div key={voice.id} className="retell-voice-card">
            <div className="retell-voice-avatar">
              {voice.gender === 'Female' ? '👩' : voice.gender === 'Male' ? '👨' : '🤖'}
            </div>
            <div className="retell-voice-info">
              <h4>{voice.name}</h4>
              <span className="retell-voice-provider">{voice.provider}</span>
              <span className="retell-voice-style">{voice.style}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  // Main render
  if (loading && !connected) {
    return (
      <div className="retell-settings">
        <div className="retell-loading">
          <div className="retell-spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="retell-settings">
      {/* Messages */}
      {error && <div className="retell-message error">{error}</div>}
      {success && <div className="retell-message success">{success}</div>}

      {!connected ? (
        renderConnectionForm()
      ) : (
        <>
          {/* Header */}
          <div className="retell-header">
            <div className="retell-header-info">
              <h2>Retell AI Voice Platform</h2>
              <span className="retell-status connected">Connected</span>
            </div>
          </div>

          {/* Tabs */}
          <div className="retell-tabs">
            <button
              className={`retell-tab ${activeTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveTab('overview')}
            >
              Overview
            </button>
            <button
              className={`retell-tab ${activeTab === 'agents' ? 'active' : ''}`}
              onClick={() => setActiveTab('agents')}
            >
              Agents
            </button>
            <button
              className={`retell-tab ${activeTab === 'phones' ? 'active' : ''}`}
              onClick={() => setActiveTab('phones')}
            >
              Phone Numbers
            </button>
            <button
              className={`retell-tab ${activeTab === 'voices' ? 'active' : ''}`}
              onClick={() => setActiveTab('voices')}
            >
              Voices
            </button>
            <button
              className={`retell-tab ${activeTab === 'telnyx' ? 'active' : ''}`}
              onClick={() => setActiveTab('telnyx')}
            >
              Telnyx Bridge
            </button>
          </div>

          {/* Tab Content */}
          <div className="retell-tab-content">
            {activeTab === 'overview' && renderOverview()}
            {activeTab === 'agents' && renderAgents()}
            {activeTab === 'phones' && renderPhoneNumbers()}
            {activeTab === 'voices' && renderVoices()}
            {activeTab === 'telnyx' && <TelnyxRetellBridge />}
          </div>
        </>
      )}
    </div>
  );
};

export default RetellSettings;
