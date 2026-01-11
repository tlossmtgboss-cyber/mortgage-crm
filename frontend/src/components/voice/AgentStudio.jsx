// Voice OS Agent Studio - Main agent management dashboard
import React, { useState, useEffect, useCallback } from 'react';



const AgentStudio = ({ onAgentSelect, onEditAgent }) => {
  console.log('[AgentStudio] Component mounting...');
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  console.log('[AgentStudio] State initialized, loading:', loading);

  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/agents`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch agents: ${response.status}`);
      }

      const data = await response.json();
      setAgents(data.agents || data || []);
    } catch (err) {
      setError(err?.message || 'Failed to load agents');
      // Set default agents for demo
      setAgents([
        {
          id: 'default-sam',
          name: 'Sam - AI Receptionist',
          description: 'Friendly and professional AI receptionist for inbound calls',
          status: 'active',
          voice_id: 'alloy',
          voice_stability: 0.5,
          voice_similarity: 0.75,
          voice_style: 0.5,
          system_prompt: 'You are Sam, a friendly AI receptionist...',
          temperature: 0.7,
          max_tokens: 150,
          interrupt_enabled: true,
          filler_words_enabled: true,
          backchanneling_enabled: true,
          emotion_detection_enabled: true,
          tools_allowed: ['get_contact_by_phone', 'create_lead', 'schedule_appointment'],
          total_calls: 156,
          successful_calls: 142,
          avg_duration_seconds: 185,
          avg_satisfaction: 4.5,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        {
          id: 'default-aria',
          name: 'Aria - LO Assistant',
          description: 'AI assistant for loan officers to manage pipeline',
          status: 'active',
          voice_id: 'nova',
          voice_stability: 0.5,
          voice_similarity: 0.75,
          voice_style: 0.5,
          system_prompt: 'You are Aria, an AI assistant for mortgage loan officers...',
          temperature: 0.7,
          max_tokens: 150,
          interrupt_enabled: true,
          filler_words_enabled: false,
          backchanneling_enabled: true,
          emotion_detection_enabled: true,
          tools_allowed: ['get_loan_status', 'create_task', 'log_call_note'],
          total_calls: 89,
          successful_calls: 82,
          avg_duration_seconds: 120,
          avg_satisfaction: 4.7,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ]);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleAgentClick = (agent) => {
    setSelectedAgent(agent);
    onAgentSelect?.(agent);
  };

  const handleToggleStatus = async (agent) => {
    try {
      const token = localStorage.getItem('token');
      const newStatus = agent.status === 'active' ? 'inactive' : 'active';

      await fetch(`${API_BASE_URL}/api/v1/voice/agents/${agent.id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
      });

      setAgents(agents.map(a =>
        a.id === agent.id ? { ...a, status: newStatus } : a
      ));
    } catch (err) {
      console.error('Failed to toggle agent status:', err);
    }
  };

  const calculateSuccessRate = (agent) => {
    if (agent.total_calls === 0) return '0%';
    return `${Math.round((agent.successful_calls / agent.total_calls) * 100)}%`;
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  console.log('[AgentStudio] Rendering, loading:', loading, 'agents:', agents.length, 'error:', error);

  if (loading) {
    console.log('[AgentStudio] Returning loading UI');
    return (
      <div className="agent-studio-loading" style={{ padding: '40px', textAlign: 'center' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 16px', border: '3px solid #f3f4f6', borderTopColor: '#2563eb', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
        <p>Loading agents...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div className="agent-studio">
      <div className="agent-studio-header">
        <div className="header-left">
          <h1>Agent Studio</h1>
          <p>Manage and configure your AI voice agents</p>
        </div>
        <div className="header-right">
          <button
            className="btn-primary"
            onClick={() => setShowCreateModal(true)}
          >
            + Create Agent
          </button>
          <button
            className="btn-secondary"
            onClick={fetchAgents}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={fetchAgents}>Retry</button>
        </div>
      )}

      <div className="agents-grid">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className={`agent-card ${selectedAgent?.id === agent.id ? 'selected' : ''}`}
            onClick={() => handleAgentClick(agent)}
          >
            <div className="agent-card-header">
              <div className="agent-info">
                <h3>{agent.name}</h3>
                <span className={`status-badge ${agent.status}`}>
                  {agent.status}
                </span>
              </div>
              <div className="agent-actions">
                <button
                  className="btn-icon"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleStatus(agent);
                  }}
                  title={agent.status === 'active' ? 'Deactivate' : 'Activate'}
                >
                  {agent.status === 'active' ? '⏸️' : '▶️'}
                </button>
                <button
                  className="btn-icon"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEditAgent?.(agent);
                  }}
                  title="Edit Agent"
                >
                  ✏️
                </button>
              </div>
            </div>

            <p className="agent-description">{agent.description}</p>

            <div className="agent-stats">
              <div className="stat">
                <span className="stat-value">{agent.total_calls}</span>
                <span className="stat-label">Total Calls</span>
              </div>
              <div className="stat">
                <span className="stat-value">{calculateSuccessRate(agent)}</span>
                <span className="stat-label">Success Rate</span>
              </div>
              <div className="stat">
                <span className="stat-value">{formatDuration(agent.avg_duration_seconds)}</span>
                <span className="stat-label">Avg Duration</span>
              </div>
              <div className="stat">
                <span className="stat-value">
                  {agent.avg_satisfaction ? `${agent.avg_satisfaction.toFixed(1)}/5` : 'N/A'}
                </span>
                <span className="stat-label">Satisfaction</span>
              </div>
            </div>

            <div className="agent-features">
              {agent.interrupt_enabled && <span className="feature-tag">Interrupts</span>}
              {agent.emotion_detection_enabled && <span className="feature-tag">Emotion Detection</span>}
              {agent.filler_words_enabled && <span className="feature-tag">Natural Fillers</span>}
              <span className="feature-tag">{agent.tools_allowed.length} Tools</span>
            </div>

            <div className="agent-voice">
              <span className="voice-label">Voice:</span>
              <span className="voice-id">{agent.voice_id}</span>
            </div>
          </div>
        ))}
      </div>

      {selectedAgent && (
        <div className="agent-detail-panel">
          <div className="panel-header">
            <h2>{selectedAgent.name}</h2>
            <button
              className="btn-close"
              onClick={() => setSelectedAgent(null)}
            >
              ×
            </button>
          </div>

          <div className="panel-content">
            <section>
              <h3>System Prompt</h3>
              <pre className="system-prompt">{selectedAgent.system_prompt}</pre>
            </section>

            <section>
              <h3>Voice Settings</h3>
              <div className="settings-grid">
                <div className="setting">
                  <label>Stability</label>
                  <span>{selectedAgent.voice_stability}</span>
                </div>
                <div className="setting">
                  <label>Similarity</label>
                  <span>{selectedAgent.voice_similarity}</span>
                </div>
                <div className="setting">
                  <label>Style</label>
                  <span>{selectedAgent.voice_style}</span>
                </div>
              </div>
            </section>

            <section>
              <h3>LLM Settings</h3>
              <div className="settings-grid">
                <div className="setting">
                  <label>Temperature</label>
                  <span>{selectedAgent.temperature}</span>
                </div>
                <div className="setting">
                  <label>Max Tokens</label>
                  <span>{selectedAgent.max_tokens}</span>
                </div>
              </div>
            </section>

            <section>
              <h3>Enabled Tools ({selectedAgent.tools_allowed.length})</h3>
              <div className="tools-list">
                {selectedAgent.tools_allowed.map((tool) => (
                  <span key={tool} className="tool-tag">{tool}</span>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}

      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Agent</h2>
              <button onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <div className="modal-content">
              <p>Use the Agent Builder to create a new voice agent.</p>
              <button
                className="btn-primary"
                onClick={() => {
                  setShowCreateModal(false);
                  // Navigate to agent builder or open inline
                }}
              >
                Open Agent Builder
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .agent-studio {
          padding: 24px;
          max-width: 1400px;
          margin: 0 auto;
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
        }

        .header-left p {
          margin: 0;
          color: #666;
        }

        .header-right {
          display: flex;
          gap: 12px;
        }

        .btn-primary {
          background: #2563eb;
          color: white;
          border: none;
          padding: 10px 20px;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
        }

        .btn-primary:hover {
          background: #1d4ed8;
        }

        .btn-secondary {
          background: #f3f4f6;
          color: #374151;
          border: 1px solid #d1d5db;
          padding: 10px 20px;
          border-radius: 8px;
          cursor: pointer;
        }

        .error-banner {
          background: #fef2f2;
          border: 1px solid #fee2e2;
          color: #dc2626;
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 24px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .agents-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
          gap: 20px;
        }

        .agent-card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 20px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .agent-card:hover {
          border-color: #2563eb;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .agent-card.selected {
          border-color: #2563eb;
          background: #f0f7ff;
        }

        .agent-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 12px;
        }

        .agent-info h3 {
          margin: 0 0 8px 0;
          font-size: 18px;
        }

        .status-badge {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
        }

        .status-badge.active {
          background: #dcfce7;
          color: #16a34a;
        }

        .status-badge.inactive {
          background: #f3f4f6;
          color: #6b7280;
        }

        .agent-actions {
          display: flex;
          gap: 8px;
        }

        .btn-icon {
          background: none;
          border: none;
          cursor: pointer;
          font-size: 16px;
          padding: 4px;
        }

        .agent-description {
          color: #666;
          font-size: 14px;
          margin-bottom: 16px;
        }

        .agent-stats {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }

        .stat {
          text-align: center;
        }

        .stat-value {
          display: block;
          font-size: 18px;
          font-weight: 600;
          color: #111;
        }

        .stat-label {
          font-size: 12px;
          color: #666;
        }

        .agent-features {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 12px;
        }

        .feature-tag {
          background: #f3f4f6;
          color: #374151;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
        }

        .agent-voice {
          font-size: 13px;
          color: #666;
        }

        .voice-id {
          font-weight: 500;
          color: #111;
        }

        .agent-detail-panel {
          position: fixed;
          right: 0;
          top: 0;
          width: 400px;
          height: 100vh;
          background: white;
          border-left: 1px solid #e5e7eb;
          box-shadow: -4px 0 12px rgba(0, 0, 0, 0.1);
          overflow-y: auto;
          z-index: 100;
        }

        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px;
          border-bottom: 1px solid #e5e7eb;
        }

        .panel-header h2 {
          margin: 0;
          font-size: 18px;
        }

        .btn-close {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
          color: #666;
        }

        .panel-content {
          padding: 20px;
        }

        .panel-content section {
          margin-bottom: 24px;
        }

        .panel-content h3 {
          font-size: 14px;
          color: #666;
          margin: 0 0 12px 0;
          text-transform: uppercase;
        }

        .system-prompt {
          background: #f9fafb;
          padding: 12px;
          border-radius: 8px;
          font-size: 13px;
          white-space: pre-wrap;
          max-height: 200px;
          overflow-y: auto;
        }

        .settings-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 12px;
        }

        .setting {
          text-align: center;
        }

        .setting label {
          display: block;
          font-size: 12px;
          color: #666;
          margin-bottom: 4px;
        }

        .setting span {
          font-weight: 600;
        }

        .tools-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .tool-tag {
          background: #e0e7ff;
          color: #4338ca;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
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
          z-index: 200;
        }

        .modal {
          background: white;
          border-radius: 12px;
          width: 480px;
          max-width: 90%;
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px;
          border-bottom: 1px solid #e5e7eb;
        }

        .modal-header h2 {
          margin: 0;
        }

        .modal-content {
          padding: 20px;
        }

        .agent-studio-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 400px;
        }

        .spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #f3f4f6;
          border-top-color: #2563eb;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default AgentStudio;
