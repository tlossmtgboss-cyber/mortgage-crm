/**
 * Voice Agent Studio - Retell AI Integration
 *
 * Main agent management dashboard using Retell AI for voice agents.
 */

import React, { useState, useEffect, useCallback } from 'react';
import TalkToAgent from './TalkToAgent';
import { getToken } from '../../utils/tokenStore';

const AgentStudio = ({ onAgentSelect, onEditAgent }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [talkingToAgent, setTalkingToAgent] = useState(null);
  const [retellConnected, setRetellConnected] = useState(false);
  const [analytics, setAnalytics] = useState(null);

  // New agent form
  const [newAgent, setNewAgent] = useState({
    agent_name: '',
    agent_type: 'receptionist',
    voice_id: '11labs-Emma',
    company_name: '',
    business_hours: 'Monday-Friday, 9 AM - 6 PM',
  });

  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${getToken()}`,
    'Content-Type': 'application/json'
  }), []);

  // Check Retell connection status
  const checkRetellStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/retell/status`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setRetellConnected(data.connected);
        return data.connected;
      }
      return false;
    } catch {
      return false;
    }
  }, [API_BASE_URL, getAuthHeaders]);

  // Fetch agents from Retell
  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const isConnected = await checkRetellStatus();

      if (isConnected) {
        // Fetch from Retell AI
        const response = await fetch(`${API_BASE_URL}/api/v1/retell/agents`, {
          headers: getAuthHeaders()
        });

        if (response.ok) {
          const data = await response.json();
          // Transform Retell agents to our format
          const transformedAgents = (data.agents || []).map(agent => ({
            id: agent.agent_id,
            name: agent.agent_name,
            description: agent.metadata?.type === 'ai_receptionist'
              ? 'AI Receptionist - handles inbound calls'
              : agent.metadata?.type === 'marketing_assistant'
                ? 'Marketing Assistant - outbound campaigns'
                : 'Custom voice agent',
            status: 'active',
            voice_id: agent.voice_id,
            voice_temperature: agent.voice_temperature || 0.7,
            voice_speed: agent.voice_speed || 1.0,
            interruption_sensitivity: agent.interruption_sensitivity || 0.5,
            enable_backchannel: agent.enable_backchannel || true,
            agent_type: agent.metadata?.type || 'custom',
            retell_agent_id: agent.agent_id,
            llm_id: agent.llm_id,
          }));
          setAgents(transformedAgents);
        }

        // Fetch analytics
        const analyticsResponse = await fetch(`${API_BASE_URL}/api/v1/retell/analytics/calls?days=30`, {
          headers: getAuthHeaders()
        });
        if (analyticsResponse.ok) {
          setAnalytics(await analyticsResponse.json());
        }
      } else {
        // Show demo agents if not connected
        setAgents([
          {
            id: 'demo-receptionist',
            name: 'Sam - AI Receptionist',
            description: 'Connect Retell AI to activate this agent',
            status: 'inactive',
            voice_id: '11labs-Emma',
            agent_type: 'receptionist',
            isDemo: true,
          },
          {
            id: 'demo-marketing',
            name: 'Alex - Marketing Assistant',
            description: 'Connect Retell AI to activate this agent',
            status: 'inactive',
            voice_id: '11labs-Adam',
            agent_type: 'marketing',
            isDemo: true,
          }
        ]);
      }
    } catch (err) {
      setError(err?.message || 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL, getAuthHeaders, checkRetellStatus]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Create new agent
  const handleCreateAgent = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/retell/agents`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(newAgent)
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create agent');
      }

      setSuccess('Agent created successfully!');
      setShowCreateModal(false);
      setNewAgent({
        agent_name: '',
        agent_type: 'receptionist',
        voice_id: '11labs-Emma',
        company_name: '',
        business_hours: 'Monday-Friday, 9 AM - 6 PM',
      });
      await fetchAgents();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Delete agent
  const handleDeleteAgent = async (agent) => {
    if (!window.confirm(`Delete agent "${agent.name}"?`)) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/retell/agents/${agent.id}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new Error('Failed to delete agent');
      }

      setSuccess('Agent deleted');
      await fetchAgents();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAgentClick = (agent) => {
    if (agent.isDemo) {
      setError('Connect Retell AI to use agents');
      return;
    }
    setSelectedAgent(agent);
    onAgentSelect?.(agent);
  };

  // Clear messages
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  const getVoiceLabel = (voiceId) => {
    const voices = {
      '11labs-Emma': 'Emma (Professional)',
      '11labs-Dorothy': 'Dorothy (Warm)',
      '11labs-Adam': 'Adam (Professional)',
      '11labs-Josh': 'Josh (Casual)',
      'openai-Alloy': 'Alloy (Neutral)',
      'openai-Nova': 'Nova (Energetic)',
    };
    return voices[voiceId] || voiceId;
  };

  const getAgentTypeIcon = (type) => {
    switch (type) {
      case 'receptionist': return '📞';
      case 'marketing': return '📢';
      default: return '🤖';
    }
  };

  if (loading && agents.length === 0) {
    return (
      <div className="agent-studio-loading" style={{ padding: '40px', textAlign: 'center' }}>
        <div className="spinner" style={{
          width: '40px',
          height: '40px',
          margin: '0 auto 16px',
          border: '3px solid #f3f4f6',
          borderTopColor: '#3b82f6',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }}></div>
        <p>Loading agents...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div className="agent-studio">
      {/* Messages */}
      {error && <div className="message error">{error}</div>}
      {success && <div className="message success">{success}</div>}

      {/* Header */}
      <div className="agent-studio-header">
        <div className="header-left">
          <h1>Voice Agents</h1>
          <p>Powered by Retell AI</p>
        </div>
        <div className="header-right">
          <span className={`connection-status ${retellConnected ? 'connected' : 'disconnected'}`}>
            {retellConnected ? '● Connected' : '○ Not Connected'}
          </span>
          <button
            className="btn-primary"
            onClick={() => setShowCreateModal(true)}
            disabled={!retellConnected}
          >
            + Create Agent
          </button>
          <button className="btn-secondary" onClick={fetchAgents}>
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      {analytics && retellConnected && (
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-value">{analytics.summary?.total_calls || 0}</span>
            <span className="stat-label">Total Calls</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{analytics.summary?.completed_calls || 0}</span>
            <span className="stat-label">Completed</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{Math.round(analytics.summary?.avg_duration_seconds || 0)}s</span>
            <span className="stat-label">Avg Duration</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{analytics.summary?.success_rate || 0}%</span>
            <span className="stat-label">Success Rate</span>
          </div>
        </div>
      )}

      {/* Connect Banner */}
      {!retellConnected && (
        <div className="connect-banner">
          <div className="banner-content">
            <h3>Connect Retell AI to get started</h3>
            <p>Add your Retell API key in Settings to create and manage voice agents.</p>
          </div>
          <a href="/settings?tab=integrations" className="btn-primary">
            Go to Settings
          </a>
        </div>
      )}

      {/* Agents Grid */}
      <div className="agents-grid">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className={`agent-card ${selectedAgent?.id === agent.id ? 'selected' : ''} ${agent.isDemo ? 'demo' : ''}`}
            onClick={() => handleAgentClick(agent)}
          >
            <div className="agent-card-header">
              <div className="agent-info">
                <span className="agent-type-icon">{getAgentTypeIcon(agent.agent_type)}</span>
                <div>
                  <h3>{agent.name}</h3>
                  <span className={`status-badge ${agent.status}`}>
                    {agent.status}
                  </span>
                </div>
              </div>
              {!agent.isDemo && (
                <div className="agent-actions">
                  <button
                    className="btn-talk"
                    onClick={(e) => {
                      e.stopPropagation();
                      setTalkingToAgent(agent);
                    }}
                    title="Talk to Agent"
                  >
                    🎙️ Talk
                  </button>
                  <button
                    className="btn-icon danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteAgent(agent);
                    }}
                    title="Delete Agent"
                  >
                    🗑️
                  </button>
                </div>
              )}
            </div>

            <p className="agent-description">{agent.description}</p>

            <div className="agent-details">
              <div className="detail">
                <span className="detail-label">Voice</span>
                <span className="detail-value">{getVoiceLabel(agent.voice_id)}</span>
              </div>
              <div className="detail">
                <span className="detail-label">Type</span>
                <span className="detail-value">{agent.agent_type}</span>
              </div>
            </div>

            {agent.isDemo && (
              <div className="demo-overlay">
                <span>Connect Retell AI to activate</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Create Agent Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create Voice Agent</h2>
              <button onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateAgent}>
              <div className="modal-content">
                <div className="form-group">
                  <label>Agent Name</label>
                  <input
                    type="text"
                    value={newAgent.agent_name}
                    onChange={(e) => setNewAgent({ ...newAgent, agent_name: e.target.value })}
                    placeholder="e.g., Sam - AI Receptionist"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Agent Type</label>
                  <select
                    value={newAgent.agent_type}
                    onChange={(e) => setNewAgent({ ...newAgent, agent_type: e.target.value })}
                  >
                    <option value="receptionist">AI Receptionist</option>
                    <option value="marketing">Marketing Assistant</option>
                    <option value="custom">Custom Agent</option>
                  </select>
                  <span className="form-hint">
                    {newAgent.agent_type === 'receptionist' && 'Pre-configured for handling inbound calls, routing, and lead capture'}
                    {newAgent.agent_type === 'marketing' && 'Pre-configured for outbound campaigns with personalization'}
                    {newAgent.agent_type === 'custom' && 'Start from scratch with custom prompts'}
                  </span>
                </div>

                <div className="form-group">
                  <label>Voice</label>
                  <select
                    value={newAgent.voice_id}
                    onChange={(e) => setNewAgent({ ...newAgent, voice_id: e.target.value })}
                  >
                    <optgroup label="Female Voices">
                      <option value="11labs-Emma">Emma - Professional</option>
                      <option value="11labs-Dorothy">Dorothy - Warm</option>
                      <option value="11labs-Matilda">Matilda - Friendly</option>
                      <option value="11labs-Rachel">Rachel - Clear</option>
                    </optgroup>
                    <optgroup label="Male Voices">
                      <option value="11labs-Adam">Adam - Professional</option>
                      <option value="11labs-Josh">Josh - Casual</option>
                      <option value="11labs-Michael">Michael - Authoritative</option>
                      <option value="11labs-Chris">Chris - Friendly</option>
                    </optgroup>
                    <optgroup label="OpenAI Voices">
                      <option value="openai-Alloy">Alloy - Neutral</option>
                      <option value="openai-Nova">Nova - Energetic</option>
                      <option value="openai-Shimmer">Shimmer - Soft</option>
                    </optgroup>
                  </select>
                </div>

                <div className="form-group">
                  <label>Company Name</label>
                  <input
                    type="text"
                    value={newAgent.company_name}
                    onChange={(e) => setNewAgent({ ...newAgent, company_name: e.target.value })}
                    placeholder="Your Company Name"
                  />
                </div>

                <div className="form-group">
                  <label>Business Hours</label>
                  <input
                    type="text"
                    value={newAgent.business_hours}
                    onChange={(e) => setNewAgent({ ...newAgent, business_hours: e.target.value })}
                    placeholder="Monday-Friday, 9 AM - 6 PM"
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={loading || !newAgent.agent_name}>
                  {loading ? 'Creating...' : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Talk to Agent Modal */}
      <TalkToAgent
        agent={talkingToAgent}
        isOpen={!!talkingToAgent}
        onClose={() => setTalkingToAgent(null)}
      />

      <style>{`
        .agent-studio {
          padding: 24px;
          max-width: 1200px;
          margin: 0 auto;
        }

        .message {
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 16px;
          font-size: 14px;
        }

        .message.error {
          background: #fef2f2;
          color: #dc2626;
          border: 1px solid #fecaca;
        }

        .message.success {
          background: #f0fdf4;
          color: #16a34a;
          border: 1px solid #bbf7d0;
        }

        .agent-studio-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }

        .header-left h1 {
          margin: 0 0 4px 0;
          font-size: 24px;
          color: #1e293b;
        }

        .header-left p {
          margin: 0;
          color: #64748b;
          font-size: 14px;
        }

        .header-right {
          display: flex;
          gap: 12px;
          align-items: center;
        }

        .connection-status {
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 500;
        }

        .connection-status.connected {
          background: #dcfce7;
          color: #16a34a;
        }

        .connection-status.disconnected {
          background: #f1f5f9;
          color: #64748b;
        }

        .btn-primary {
          background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
          color: white;
          border: none;
          padding: 10px 20px;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
        }

        .btn-primary:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }

        .btn-primary:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-secondary {
          background: #f1f5f9;
          color: #475569;
          border: 1px solid #e2e8f0;
          padding: 10px 20px;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
        }

        .stats-bar {
          display: flex;
          gap: 24px;
          padding: 16px 24px;
          background: white;
          border-radius: 12px;
          border: 1px solid #e2e8f0;
          margin-bottom: 24px;
        }

        .stat-item {
          display: flex;
          flex-direction: column;
        }

        .stat-value {
          font-size: 24px;
          font-weight: 600;
          color: #1e293b;
        }

        .stat-label {
          font-size: 13px;
          color: #64748b;
        }

        .connect-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 24px;
          background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
          border-radius: 12px;
          margin-bottom: 24px;
          border: 1px solid #bae6fd;
        }

        .banner-content h3 {
          margin: 0 0 4px 0;
          color: #0369a1;
        }

        .banner-content p {
          margin: 0;
          color: #0c4a6e;
        }

        .agents-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 20px;
        }

        .agent-card {
          position: relative;
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 20px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .agent-card:hover:not(.demo) {
          border-color: #3b82f6;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .agent-card.selected {
          border-color: #3b82f6;
          background: #f0f7ff;
        }

        .agent-card.demo {
          opacity: 0.7;
          cursor: default;
        }

        .agent-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 12px;
        }

        .agent-info {
          display: flex;
          gap: 12px;
          align-items: flex-start;
        }

        .agent-type-icon {
          font-size: 24px;
        }

        .agent-info h3 {
          margin: 0 0 4px 0;
          font-size: 16px;
          color: #1e293b;
        }

        .status-badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 11px;
          font-weight: 500;
        }

        .status-badge.active {
          background: #dcfce7;
          color: #16a34a;
        }

        .status-badge.inactive {
          background: #f1f5f9;
          color: #64748b;
        }

        .agent-actions {
          display: flex;
          gap: 8px;
        }

        .btn-talk {
          background: linear-gradient(135deg, #22c55e, #16a34a);
          color: white;
          border: none;
          padding: 6px 12px;
          border-radius: 6px;
          font-size: 13px;
          cursor: pointer;
        }

        .btn-icon {
          background: none;
          border: none;
          cursor: pointer;
          padding: 4px;
          border-radius: 4px;
        }

        .btn-icon.danger:hover {
          background: #fef2f2;
        }

        .agent-description {
          color: #64748b;
          font-size: 14px;
          margin-bottom: 16px;
        }

        .agent-details {
          display: flex;
          gap: 24px;
        }

        .detail {
          display: flex;
          flex-direction: column;
        }

        .detail-label {
          font-size: 12px;
          color: #94a3b8;
        }

        .detail-value {
          font-size: 14px;
          color: #1e293b;
          font-weight: 500;
        }

        .demo-overlay {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          padding: 12px;
          background: linear-gradient(transparent, rgba(241, 245, 249, 0.95));
          text-align: center;
          border-radius: 0 0 12px 12px;
        }

        .demo-overlay span {
          font-size: 13px;
          color: #64748b;
        }

        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .modal {
          background: white;
          border-radius: 16px;
          width: 100%;
          max-width: 500px;
          max-height: 90vh;
          overflow: hidden;
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px;
          border-bottom: 1px solid #e2e8f0;
        }

        .modal-header h2 {
          margin: 0;
          font-size: 18px;
        }

        .modal-header button {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
          color: #64748b;
        }

        .modal-content {
          padding: 20px;
          overflow-y: auto;
        }

        .modal-footer {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
          padding: 16px 20px;
          border-top: 1px solid #e2e8f0;
        }

        .form-group {
          margin-bottom: 20px;
        }

        .form-group label {
          display: block;
          margin-bottom: 6px;
          font-size: 14px;
          font-weight: 500;
          color: #374151;
        }

        .form-group input,
        .form-group select {
          width: 100%;
          padding: 10px 14px;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          font-size: 14px;
        }

        .form-group input:focus,
        .form-group select:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .form-hint {
          display: block;
          margin-top: 6px;
          font-size: 12px;
          color: #64748b;
        }
      `}</style>
    </div>
  );
};

export default AgentStudio;
