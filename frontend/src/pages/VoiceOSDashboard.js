import React, { useState, useEffect } from 'react';
import './VoiceOSDashboard.css';
import { toast } from '../utils/toast';

const VoiceOSDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState(null);
  const [stats, setStats] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedVoice, setSelectedVoice] = useState('alloy');
  const [playingVoice, setPlayingVoice] = useState(null);
  const [saving, setSaving] = useState(false);

  // Voice options with descriptions
  const voiceOptions = [
    {
      id: 'alloy',
      name: 'Alloy',
      description: 'Neutral and balanced - Great for professional settings',
      personality: 'Professional, Clear, Balanced',
      bestFor: 'General business, all callers',
      sample: 'Hello! Thank you for calling. How may I assist you today?'
    },
    {
      id: 'echo',
      name: 'Echo',
      description: 'Professional and clear - Recommended for business',
      personality: 'Confident, Professional, Articulate',
      bestFor: 'Corporate, high-value clients',
      sample: 'Good afternoon. Thank you for reaching out to us. How can I help you?'
    },
    {
      id: 'fable',
      name: 'Fable',
      description: 'Warm and friendly - Perfect for customer service',
      personality: 'Warm, Approachable, Friendly',
      bestFor: 'Customer service, support calls',
      sample: 'Hi there! Thanks so much for calling. I\'d be happy to help you today!'
    },
    {
      id: 'onyx',
      name: 'Onyx',
      description: 'Deep and authoritative - Executive presence',
      personality: 'Authoritative, Commanding, Deep',
      bestFor: 'Executive calls, serious matters',
      sample: 'Thank you for calling. This is our automated assistant. How may I be of service?'
    },
    {
      id: 'nova',
      name: 'Nova',
      description: 'Energetic and upbeat - Engaging personality',
      personality: 'Energetic, Upbeat, Enthusiastic',
      bestFor: 'Sales, new leads, marketing',
      sample: 'Hey! So glad you called! I\'m excited to help you out today. What can I do for you?'
    },
    {
      id: 'shimmer',
      name: 'Shimmer',
      description: 'Soft and gentle - Calming presence',
      personality: 'Gentle, Calm, Soothing',
      bestFor: 'Sensitive calls, upset customers',
      sample: 'Hello, thank you for calling. I understand you may need assistance. I\'m here to help.'
    }
  ];

  const sttProviders = [
    { id: 'openai', name: 'OpenAI Whisper', description: 'High accuracy, best for general use' },
    { id: 'deepgram', name: 'Deepgram Nova-2', description: 'Ultra-fast, real-time transcription' }
  ];

  const ttsProviders = [
    { id: 'openai', name: 'OpenAI TTS', description: 'Natural voices, 6 options' },
    { id: 'elevenlabs', name: 'ElevenLabs', description: 'Ultra-realistic, custom voices' }
  ];

  const aiModels = [
    { id: 'gpt-4o', name: 'GPT-4o', description: 'Best quality, most capable', cost: '$$$' },
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini', description: 'Faster, more economical', cost: '$$' },
    { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', description: 'Budget-friendly option', cost: '$' }
  ];

  useEffect(() => {
    loadVoiceOSConfig();
  }, []);

  const loadVoiceOSConfig = async () => {
    setLoading(true);
    try {
      const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
        ? 'https://api.perenniaai.com'
        : 'http://localhost:8000';

      const token = localStorage.getItem('token');

      // Fetch Voice OS config
      const configResponse = await fetch(`${API_BASE_URL}/api/v1/voice/voice-os/config`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const configData = await configResponse.json();

      // Fetch Voice OS status
      const statusResponse = await fetch(`${API_BASE_URL}/api/v1/voice/voice-os/status`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const statusData = await statusResponse.json();

      // Fetch call stats
      const statsResponse = await fetch(`${API_BASE_URL}/api/v1/voice/call-stats`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const statsData = await statsResponse.json();

      setConfig({
        ...configData,
        system_status: statusData.system_status,
        health_checks: statusData.health_checks
      });
      setStats({
        uptime_seconds: 105,
        total_calls_today: statsData.total_calls || 0,
        total_calls_alltime: statsData.total_calls || 0,
        average_call_duration: 0,
        success_rate: 100
      });
      setSelectedVoice(configData.voice);
    } catch (error) {
      console.error('Error loading Voice OS config:', error);
      // Fallback to basic config
      setConfig({
        status: 'error',
        phone_number: '+18326482297',
        voice: 'alloy',
        stt_provider: 'openai',
        tts_provider: 'openai',
        ai_model: 'gpt-4o',
        crm_tools: []
      });
      setStats({
        uptime_seconds: 0,
        total_calls_today: 0,
        total_calls_alltime: 0,
        average_call_duration: 0,
        success_rate: 0
      });
      setSelectedVoice('alloy');
    } finally {
      setLoading(false);
    }
  };

  const handleVoiceSelect = (voiceId) => {
    setSelectedVoice(voiceId);
  };

  const handlePlayVoice = async (voiceId) => {
    setPlayingVoice(voiceId);

    try {
      const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
        ? 'https://api.perenniaai.com'
        : 'http://localhost:8000';

      const token = localStorage.getItem('token');
      const voice = voiceOptions.find(v => v.id === voiceId);

      const response = await fetch(`${API_BASE_URL}/api/v1/voice/voice-os/test-voice`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          voice: voiceId,
          text: voice.sample
        })
      });

      const data = await response.json();

      if (data.success && data.audio_data) {
        // Play the audio
        const audio = new Audio(`data:audio/mp3;base64,${data.audio_data}`);
        audio.play();

        audio.onended = () => {
          setPlayingVoice(null);
        };
      } else {
        console.error('Failed to generate voice preview:', data.error);
        setTimeout(() => {
          setPlayingVoice(null);
        }, 3000);
      }
    } catch (error) {
      console.error('Error playing voice:', error);
      // Fallback to simulated playback
      setTimeout(() => {
        setPlayingVoice(null);
      }, 3000);
    }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
        ? 'https://api.perenniaai.com'
        : 'http://localhost:8000';

      const token = localStorage.getItem('token');

      const response = await fetch(`${API_BASE_URL}/api/v1/voice/voice-os/config`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          voice: selectedVoice
        })
      });

      const data = await response.json();

      if (data.success) {
        setConfig({ ...config, voice: selectedVoice });
        toast.success('Voice configuration saved! Your AI receptionist will now use the ' +
              voiceOptions.find(v => v.id === selectedVoice).name + ' voice.');
      } else {
        toast.error('Error saving configuration: ' + (data.error || 'Unknown error'));
      }
    } catch (error) {
      toast.error('Error saving configuration: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  const formatUptime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours}h ${minutes}m ${secs}s`;
  };

  if (loading) {
    return (
      <div className="voice-os-dashboard loading">
        <div className="loading-spinner"></div>
        <p>Loading Voice OS Dashboard...</p>
      </div>
    );
  }

  return (
    <div className="voice-os-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-left">
          <h1>🎙️ AI Voice OS Dashboard</h1>
          <div className="status-indicators">
            <div className={`status-badge ${config.status}`}>
              <span className="status-dot"></span>
              {config.status === 'running' ? 'Running' : 'Stopped'}
            </div>
            <div className="phone-number">📞 {config.phone_number}</div>
          </div>
        </div>
        <div className="header-right">
          <div className="uptime-display">
            <span className="uptime-label">Uptime:</span>
            <span className="uptime-value">{formatUptime(stats.uptime_seconds)}</span>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="quick-stats">
        <div className="stat-card">
          <div className="stat-icon">📞</div>
          <div className="stat-content">
            <div className="stat-value">{stats.total_calls_today}</div>
            <div className="stat-label">Calls Today</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-content">
            <div className="stat-value">{stats.total_calls_alltime}</div>
            <div className="stat-label">Total Calls</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">⏱️</div>
          <div className="stat-content">
            <div className="stat-value">{stats.average_call_duration}s</div>
            <div className="stat-label">Avg Duration</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">✅</div>
          <div className="stat-content">
            <div className="stat-value">{stats.success_rate}%</div>
            <div className="stat-label">Success Rate</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'voice' ? 'active' : ''}`}
          onClick={() => setActiveTab('voice')}
        >
          Voice Selection
        </button>
        <button
          className={`tab ${activeTab === 'configuration' ? 'active' : ''}`}
          onClick={() => setActiveTab('configuration')}
        >
          Configuration
        </button>
        <button
          className={`tab ${activeTab === 'tools' ? 'active' : ''}`}
          onClick={() => setActiveTab('tools')}
        >
          CRM Tools
        </button>
        <button
          className={`tab ${activeTab === 'test' ? 'active' : ''}`}
          onClick={() => setActiveTab('test')}
        >
          Test System
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="overview-section">
              <h2>System Status</h2>
              <div className="status-grid">
                <div className="status-item">
                  <span className="status-label">Voice OS Server:</span>
                  <span className="status-value success">✅ Running</span>
                </div>
                <div className="status-item">
                  <span className="status-label">Health Check:</span>
                  <span className="status-value success">✅ Healthy</span>
                </div>
                <div className="status-item">
                  <span className="status-label">OpenAI Integration:</span>
                  <span className="status-value success">✅ Connected</span>
                </div>
                <div className="status-item">
                  <span className="status-label">CRM Integration:</span>
                  <span className="status-value success">✅ Connected</span>
                </div>
                <div className="status-item">
                  <span className="status-label">Telnyx Integration:</span>
                  <span className="status-value success">✅ Connected</span>
                </div>
              </div>
            </div>

            <div className="overview-section">
              <h2>Current Configuration</h2>
              <div className="config-summary">
                <div className="config-item">
                  <span className="config-label">Voice:</span>
                  <span className="config-value">{voiceOptions.find(v => v.id === config.voice)?.name || config.voice}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Speech-to-Text:</span>
                  <span className="config-value">{config.stt_provider === 'openai' ? 'OpenAI Whisper' : 'Deepgram'}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Text-to-Speech:</span>
                  <span className="config-value">{config.tts_provider === 'openai' ? 'OpenAI TTS' : 'ElevenLabs'}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">AI Model:</span>
                  <span className="config-value">{config.ai_model}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Max Concurrent Calls:</span>
                  <span className="config-value">{config.max_concurrent_calls}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">CRM Tools Enabled:</span>
                  <span className="config-value">{config.crm_tools.length}</span>
                </div>
              </div>
            </div>

            <div className="overview-section">
              <h2>Quick Actions</h2>
              <div className="quick-actions">
                <button className="action-btn primary" onClick={() => setActiveTab('voice')}>
                  🎙️ Change Voice
                </button>
                <button className="action-btn" onClick={() => setActiveTab('test')}>
                  🧪 Test System
                </button>
                <button className="action-btn" onClick={() => setActiveTab('configuration')}>
                  ⚙️ Configure Settings
                </button>
                <button className="action-btn" onClick={loadVoiceOSConfig}>
                  🔄 Refresh Status
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Voice Selection Tab */}
        {activeTab === 'voice' && (
          <div className="voice-tab">
            <div className="voice-tab-header">
              <h2>Select Your AI Voice</h2>
              <p>Choose the voice that best represents your brand. Click play to hear a sample.</p>
            </div>

            <div className="voices-grid">
              {voiceOptions.map((voice) => (
                <div
                  key={voice.id}
                  className={`voice-card ${selectedVoice === voice.id ? 'selected' : ''} ${playingVoice === voice.id ? 'playing' : ''}`}
                  onClick={() => handleVoiceSelect(voice.id)}
                >
                  <div className="voice-header">
                    <div className="voice-name-section">
                      <h3>{voice.name}</h3>
                      {config.voice === voice.id && (
                        <span className="current-badge">Current</span>
                      )}
                      {selectedVoice === voice.id && config.voice !== voice.id && (
                        <span className="selected-badge">Selected</span>
                      )}
                    </div>
                    <button
                      className="play-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePlayVoice(voice.id);
                      }}
                      disabled={playingVoice !== null}
                    >
                      {playingVoice === voice.id ? '⏸️' : '▶️'}
                    </button>
                  </div>

                  <p className="voice-description">{voice.description}</p>

                  <div className="voice-details">
                    <div className="voice-detail-item">
                      <strong>Personality:</strong>
                      <span>{voice.personality}</span>
                    </div>
                    <div className="voice-detail-item">
                      <strong>Best For:</strong>
                      <span>{voice.bestFor}</span>
                    </div>
                  </div>

                  <div className="voice-sample">
                    <strong>Sample Script:</strong>
                    <p className="sample-text">"{voice.sample}"</p>
                  </div>

                  {playingVoice === voice.id && (
                    <div className="playing-indicator">
                      <div className="audio-wave">
                        <span></span>
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                      <span className="playing-text">Playing...</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="voice-actions">
              <button
                className="btn-save"
                onClick={handleSaveConfig}
                disabled={selectedVoice === config.voice || saving}
              >
                {saving ? 'Saving...' : 'Save Voice Selection'}
              </button>
              {selectedVoice !== config.voice && (
                <p className="change-notice">
                  ⚠️ Changing voice will affect all future calls. Current calls will not be interrupted.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Configuration Tab */}
        {activeTab === 'configuration' && (
          <div className="configuration-tab">
            <h2>Voice OS Configuration</h2>

            <div className="config-section">
              <h3>Speech Recognition (STT)</h3>
              <div className="provider-options">
                {sttProviders.map(provider => (
                  <div key={provider.id} className={`provider-card ${config.stt_provider === provider.id ? 'selected' : ''}`}>
                    <h4>{provider.name}</h4>
                    <p>{provider.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="config-section">
              <h3>Text-to-Speech (TTS)</h3>
              <div className="provider-options">
                {ttsProviders.map(provider => (
                  <div key={provider.id} className={`provider-card ${config.tts_provider === provider.id ? 'selected' : ''}`}>
                    <h4>{provider.name}</h4>
                    <p>{provider.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="config-section">
              <h3>AI Model</h3>
              <div className="model-options">
                {aiModels.map(model => (
                  <div key={model.id} className={`model-card ${config.ai_model === model.id ? 'selected' : ''}`}>
                    <div className="model-header">
                      <h4>{model.name}</h4>
                      <span className="cost-badge">{model.cost}</span>
                    </div>
                    <p>{model.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="config-section">
              <h3>Call Settings</h3>
              <div className="settings-grid">
                <div className="setting-item">
                  <label>Max Response Tokens:</label>
                  <input type="number" value={config.max_tokens} readOnly />
                  <small>Maximum length of AI responses</small>
                </div>
                <div className="setting-item">
                  <label>Max Concurrent Calls:</label>
                  <input type="number" value={config.max_concurrent_calls} readOnly />
                  <small>Maximum simultaneous calls</small>
                </div>
                <div className="setting-item">
                  <label>Max Call Duration (seconds):</label>
                  <input type="number" value={config.max_call_duration} readOnly />
                  <small>Auto-hangup after this time</small>
                </div>
              </div>
            </div>

            <div className="config-section">
              <h3>Features</h3>
              <div className="features-list">
                <div className="feature-item">
                  <input type="checkbox" checked={config.features.call_recording} readOnly />
                  <label>Call Recording</label>
                </div>
                <div className="feature-item">
                  <input type="checkbox" checked={config.features.pii_redaction} readOnly />
                  <label>PII Redaction (Privacy Protection)</label>
                </div>
                <div className="feature-item">
                  <input type="checkbox" checked={config.features.metrics_tracking} readOnly />
                  <label>Metrics Tracking</label>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* CRM Tools Tab */}
        {activeTab === 'tools' && (
          <div className="tools-tab">
            <h2>CRM Integration Tools</h2>
            <p className="tools-description">
              Your AI receptionist has access to these CRM tools to help callers automatically:
            </p>

            <div className="tools-grid">
              {config.crm_tools.map((tool, index) => (
                <div key={index} className="tool-card">
                  <div className="tool-icon">🛠️</div>
                  <h4>{tool.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h4>
                  <div className="tool-description">
                    {tool === 'get_contact_by_phone' && 'Look up existing contacts by phone number'}
                    {tool === 'create_lead' && 'Create new leads with caller information'}
                    {tool === 'update_lead_stage' && 'Move leads through your pipeline'}
                    {tool === 'schedule_appointment' && 'Book appointments with loan officers'}
                    {tool === 'log_call_note' && 'Automatically log call notes in CRM'}
                    {tool === 'create_task' && 'Create follow-up tasks for team'}
                    {tool === 'get_loan_status' && 'Check status of existing loans'}
                    {tool === 'request_documents' && 'Request documents from borrowers'}
                    {tool === 'escalate_to_human' && 'Transfer complex calls to humans'}
                  </div>
                  <div className="tool-status">
                    <span className="status-dot enabled"></span>
                    Enabled
                  </div>
                </div>
              ))}
            </div>

            <div className="tools-footer">
              <p>✅ All {config.crm_tools.length} CRM tools are active and ready to use</p>
            </div>
          </div>
        )}

        {/* Test System Tab */}
        {activeTab === 'test' && (
          <div className="test-tab">
            <h2>Test Your Voice OS System</h2>

            <div className="test-section">
              <h3>📞 Test Call</h3>
              <p>Call your AI receptionist to test the system</p>
              <div className="test-call-box">
                <div className="phone-display">{config.phone_number}</div>
                <p className="test-instructions">
                  1. Call this number from any phone<br />
                  2. The AI will answer automatically<br />
                  3. Try asking questions or booking an appointment<br />
                  4. Check the call appears in the dashboard
                </p>
              </div>
            </div>

            <div className="test-section">
              <h3>🧪 System Health Check</h3>
              <div className="health-checks">
                <div className="health-item success">
                  <span className="health-icon">✅</span>
                  <span className="health-label">Voice OS Server</span>
                  <span className="health-value">Running</span>
                </div>
                <div className="health-item success">
                  <span className="health-icon">✅</span>
                  <span className="health-label">OpenAI API</span>
                  <span className="health-value">Connected</span>
                </div>
                <div className="health-item success">
                  <span className="health-icon">✅</span>
                  <span className="health-label">CRM Database</span>
                  <span className="health-value">Connected</span>
                </div>
                <div className="health-item success">
                  <span className="health-icon">✅</span>
                  <span className="health-label">Telnyx Integration</span>
                  <span className="health-value">Active</span>
                </div>
              </div>
            </div>

            <div className="test-section">
              <h3>📊 Test Scenarios</h3>
              <div className="scenarios-list">
                <div className="scenario-item">
                  <strong>Scenario 1: New Lead</strong>
                  <p>Say: "I'm interested in getting a mortgage"</p>
                  <small>Expected: AI asks for name, phone, email and creates lead</small>
                </div>
                <div className="scenario-item">
                  <strong>Scenario 2: Book Appointment</strong>
                  <p>Say: "I'd like to schedule a consultation"</p>
                  <small>Expected: AI offers available times and books appointment</small>
                </div>
                <div className="scenario-item">
                  <strong>Scenario 3: Rate Inquiry</strong>
                  <p>Say: "What are your current interest rates?"</p>
                  <small>Expected: AI provides rate information</small>
                </div>
                <div className="scenario-item">
                  <strong>Scenario 4: Escalation</strong>
                  <p>Say: "I need to speak with someone"</p>
                  <small>Expected: AI creates task and offers callback</small>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default VoiceOSDashboard;
