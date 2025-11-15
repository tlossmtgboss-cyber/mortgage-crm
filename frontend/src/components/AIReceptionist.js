import React, { useState, useEffect } from 'react';
import { voiceAPI, aiAPI } from '../services/api';
import './AIReceptionist.css';

function AIReceptionist() {
  const [config, setConfig] = useState(null);
  const [stats, setStats] = useState(null);
  const [callHistory, setCallHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard'); // dashboard, make-call, history, settings
  const [memoryStats, setMemoryStats] = useState(null);

  // Make Call form
  const [callForm, setCallForm] = useState({
    to_number: '',
    script_type: 'default',
    lead_id: null
  });
  const [makingCall, setMakingCall] = useState(false);
  const [callResult, setCallResult] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [configData, statsData, historyData, memStats] = await Promise.all([
        voiceAPI.getConfig(),
        voiceAPI.getCallStats(),
        voiceAPI.getCallHistory({ limit: 10 }),
        aiAPI.getMemoryStats().catch(() => null)
      ]);

      setConfig(configData);
      setStats(statsData);
      setCallHistory(historyData.calls || []);
      setMemoryStats(memStats);
      setLoading(false);
    } catch (error) {
      console.error('Error loading AI Receptionist data:', error);
      setLoading(false);
    }
  };

  const handleMakeCall = async (e) => {
    e.preventDefault();
    setMakingCall(true);
    setCallResult(null);

    try {
      const result = await voiceAPI.makeCall(callForm);

      if (result.success) {
        setCallResult({ success: true, message: 'Call initiated successfully!' });
        setCallForm({ to_number: '', script_type: 'default', lead_id: null });
        // Refresh call history
        setTimeout(() => loadData(), 2000);
      } else {
        setCallResult({ success: false, message: result.error || 'Failed to make call' });
      }
    } catch (error) {
      setCallResult({ success: false, message: error.message || 'Error making call' });
    } finally {
      setMakingCall(false);
    }
  };

  const formatPhoneNumber = (phone) => {
    if (!phone) return 'Unknown';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 11 && cleaned.startsWith('1')) {
      return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
    }
    return phone;
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  if (loading) {
    return <div className="ai-receptionist-loading">Loading AI Receptionist...</div>;
  }

  if (!config || !config.enabled) {
    return (
      <div className="ai-receptionist-disabled">
        <h2>AI Receptionist Not Configured</h2>
        <p>Please configure Twilio and OpenAI API keys to enable the AI Receptionist.</p>
        <div className="setup-requirements">
          <h3>Requirements:</h3>
          <ul>
            <li>✓ Twilio Account SID</li>
            <li>✓ Twilio Auth Token</li>
            <li>✓ Twilio Phone Number</li>
            <li>✓ OpenAI API Key (for Realtime API)</li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-receptionist-container">
      <div className="ai-receptionist-header">
        <div className="header-title">
          <h2>🤖 AI Receptionist</h2>
          <span className="status-badge enabled">Active</span>
        </div>
        <div className="header-info">
          <span className="phone-number">📞 {formatPhoneNumber(config.phone_number)}</span>
        </div>
      </div>

      <div className="ai-receptionist-tabs">
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={activeTab === 'make-call' ? 'active' : ''}
          onClick={() => setActiveTab('make-call')}
        >
          Make Call
        </button>
        <button
          className={activeTab === 'history' ? 'active' : ''}
          onClick={() => setActiveTab('history')}
        >
          Call History
        </button>
        <button
          className={activeTab === 'settings' ? 'active' : ''}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </div>

      <div className="ai-receptionist-content">
        {activeTab === 'dashboard' && (
          <div className="dashboard-tab">
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-icon">📞</div>
                <div className="stat-content">
                  <div className="stat-label">Total Calls</div>
                  <div className="stat-value">{stats?.total_calls || 0}</div>
                  <div className="stat-subtitle">Last 30 days</div>
                </div>
              </div>

              <div className="stat-card">
                <div className="stat-icon">📥</div>
                <div className="stat-content">
                  <div className="stat-label">Inbound</div>
                  <div className="stat-value">{stats?.inbound_calls || 0}</div>
                  <div className="stat-subtitle">Calls answered by AI</div>
                </div>
              </div>

              <div className="stat-card">
                <div className="stat-icon">📤</div>
                <div className="stat-content">
                  <div className="stat-label">Outbound</div>
                  <div className="stat-value">{stats?.outbound_calls || 0}</div>
                  <div className="stat-subtitle">AI calls made</div>
                </div>
              </div>

              <div className="stat-card">
                <div className="stat-icon">👥</div>
                <div className="stat-content">
                  <div className="stat-label">Leads Generated</div>
                  <div className="stat-value">{stats?.leads_generated || 0}</div>
                  <div className="stat-subtitle">From phone calls</div>
                </div>
              </div>
            </div>

            <div className="features-section">
              <h3>AI Capabilities</h3>
              <div className="features-grid">
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Answer Calls</div>
                  <div className="feature-desc">AI answers all inbound calls automatically</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Lead Qualification</div>
                  <div className="feature-desc">Qualifies leads and extracts key information</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Schedule Appointments</div>
                  <div className="feature-desc">Books appointments with your calendar</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Transfer Calls</div>
                  <div className="feature-desc">Transfers to team members when needed</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Take Messages</div>
                  <div className="feature-desc">Creates tasks from voicemails and messages</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon">✅</div>
                  <div className="feature-name">Make Outbound Calls</div>
                  <div className="feature-desc">AI can call leads for follow-ups</div>
                </div>
              </div>
            </div>

            <div className="recent-calls-section">
              <h3>Recent Calls</h3>
              {callHistory.length === 0 ? (
                <p className="no-calls">No calls yet</p>
              ) : (
                <div className="calls-list">
                  {callHistory.slice(0, 5).map((call, index) => (
                    <div key={index} className="call-item">
                      <div className="call-icon">
                        {call.metadata?.direction === 'inbound' ? '📥' : '📤'}
                      </div>
                      <div className="call-details">
                        <div className="call-description">{call.description}</div>
                        <div className="call-meta">
                          {call.created_at && new Date(call.created_at).toLocaleString()}
                          {call.metadata?.duration && ` • ${formatDuration(call.metadata.duration)}`}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <button
                className="view-all-btn"
                onClick={() => setActiveTab('history')}
              >
                View All Calls
              </button>
            </div>
          </div>
        )}

        {activeTab === 'make-call' && (
          <div className="make-call-tab">
            <h3>Make Outbound AI Call</h3>
            <form onSubmit={handleMakeCall} className="make-call-form">
              <div className="form-group">
                <label>Phone Number *</label>
                <input
                  type="tel"
                  value={callForm.to_number}
                  onChange={(e) => setCallForm({ ...callForm, to_number: e.target.value })}
                  placeholder="+1 (555) 123-4567"
                  required
                />
                <small>Enter phone number in format: +1234567890</small>
              </div>

              <div className="form-group">
                <label>Call Script Type</label>
                <select
                  value={callForm.script_type}
                  onChange={(e) => setCallForm({ ...callForm, script_type: e.target.value })}
                >
                  <option value="default">General Inquiry</option>
                  <option value="follow_up">Follow-up Call</option>
                  <option value="appointment_reminder">Appointment Reminder</option>
                  <option value="rate_update">Rate Update</option>
                </select>
              </div>

              {callResult && (
                <div className={`call-result ${callResult.success ? 'success' : 'error'}`}>
                  {callResult.message}
                </div>
              )}

              <button type="submit" className="make-call-btn" disabled={makingCall}>
                {makingCall ? 'Calling...' : '📞 Make Call'}
              </button>
            </form>

            <div className="call-info">
              <h4>How AI Calls Work</h4>
              <ul>
                <li>AI will call the number and speak naturally using OpenAI Realtime API</li>
                <li>The conversation is recorded and transcribed automatically</li>
                <li>AI will qualify the lead and extract important information</li>
                <li>A task is created automatically with the call summary</li>
                <li>You can listen to the recording from the call history</li>
              </ul>
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="history-tab">
            <div className="history-header">
              <h3>Call History</h3>
              <button onClick={loadData} className="refresh-btn">🔄 Refresh</button>
            </div>

            {callHistory.length === 0 ? (
              <div className="no-history">
                <p>No call history available</p>
              </div>
            ) : (
              <div className="history-table">
                <table>
                  <thead>
                    <tr>
                      <th>Direction</th>
                      <th>Description</th>
                      <th>Date & Time</th>
                      <th>Duration</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {callHistory.map((call, index) => (
                      <tr key={index}>
                        <td>
                          <span className={`direction-badge ${call.metadata?.direction}`}>
                            {call.metadata?.direction === 'inbound' ? '📥 Inbound' : '📤 Outbound'}
                          </span>
                        </td>
                        <td>{call.description}</td>
                        <td>{call.created_at ? new Date(call.created_at).toLocaleString() : 'N/A'}</td>
                        <td>{call.metadata?.duration ? formatDuration(call.metadata.duration) : 'N/A'}</td>
                        <td>
                          <span className="status-badge">
                            {call.metadata?.status || 'completed'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="settings-tab">
            <h3>AI Receptionist Settings</h3>

            <div className="settings-section">
              <h4>Business Information</h4>
              <div className="form-group">
                <label>Business Name</label>
                <input
                  type="text"
                  value={config.business_name}
                  readOnly
                />
                <small>The name AI will use when greeting callers</small>
              </div>

              <div className="form-group">
                <label>Phone Number</label>
                <input
                  type="text"
                  value={formatPhoneNumber(config.phone_number)}
                  readOnly
                />
                <small>Your Twilio phone number for calls</small>
              </div>
            </div>

            <div className="settings-section">
              <h4>Business Hours</h4>
              <div className="business-hours">
                <div className="form-row">
                  <div className="form-group">
                    <label>Start Time</label>
                    <input
                      type="time"
                      value={config.business_hours?.start || '09:00'}
                      readOnly
                    />
                  </div>
                  <div className="form-group">
                    <label>End Time</label>
                    <input
                      type="time"
                      value={config.business_hours?.end || '17:00'}
                      readOnly
                    />
                  </div>
                </div>
                <small>AI will adapt its greeting based on business hours</small>
              </div>
            </div>

            <div className="settings-section">
              <h4>Webhook Configuration</h4>
              <div className="webhook-info">
                <p>Configure these webhooks in your Twilio console:</p>
                <div className="webhook-url">
                  <label>Incoming Call Webhook:</label>
                  <code>https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/incoming</code>
                  <button onClick={() => navigator.clipboard.writeText('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/incoming')}>
                    Copy
                  </button>
                </div>
                <div className="webhook-url">
                  <label>Call Status Callback:</label>
                  <code>https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/call-status</code>
                  <button onClick={() => navigator.clipboard.writeText('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/call-status')}>
                    Copy
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AIReceptionist;
