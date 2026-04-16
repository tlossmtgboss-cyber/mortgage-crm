import { useState, useEffect, useCallback } from 'react';
import './CallRoutingConfig.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

function CallRoutingConfig() {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [testPhone, setTestPhone] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [configuring, setConfiguring] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [error, setError] = useState(null);

  const getAuthHeaders = () => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [configRes, statusRes, logsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/call-routing/config`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/call-routing/status`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/call-routing/logs?limit=20`, { headers: getAuthHeaders() })
      ]);

      if (configRes.ok) {
        const configData = await configRes.json();
        setConfig(configData);
      }

      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setStatus(statusData);
      }

      if (logsRes.ok) {
        const logsData = await logsRes.json();
        setLogs(logsData.logs || []);
      }

    } catch (err) {
      console.error('Error fetching data:', err);
      setError('Failed to load call routing configuration');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleTestLookup = async () => {
    if (!testPhone.trim()) return;

    try {
      const res = await fetch(
        `${API_BASE}/api/v1/call-routing/test-lookup?phone=${encodeURIComponent(testPhone)}`,
        { headers: getAuthHeaders() }
      );

      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      }
    } catch (err) {
      console.error('Test lookup error:', err);
      setTestResult({ error: 'Failed to test lookup' });
    }
  };

  const handleConfigurePhone = async () => {
    setConfiguring(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/call-routing/configure-phone`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await res.json();
      if (data.success) {
        toast.success('Phone number configured for intelligent routing!');
        fetchData();
      } else {
        toast.error(`Configuration failed: ${data.error}`);
      }
    } catch (err) {
      console.error('Configure error:', err);
      toast.error('Failed to configure phone number');
    } finally {
      setConfiguring(false);
    }
  };

  const handleRunMigration = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/call-routing/migrate`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await res.json();
      if (data.success) {
        toast.success('Migration completed successfully!');
      } else {
        toast.error(`Migration failed: ${data.error}`);
      }
    } catch (err) {
      console.error('Migration error:', err);
      toast.error('Failed to run migration');
    }
  };

  const getCallerTypeIcon = (type) => {
    switch (type) {
      case 'lead': return '🎯';
      case 'active_loan': return '📋';
      case 'mum': return '🏆';
      case 'unknown': return '❓';
      default: return '📞';
    }
  };

  const getCallerTypeColor = (type) => {
    switch (type) {
      case 'lead': return '#3b82f6';
      case 'active_loan': return '#10b981';
      case 'mum': return '#8b5cf6';
      case 'unknown': return '#6b7280';
      default: return '#6b7280';
    }
  };

  if (loading) {
    return (
      <div className="call-routing-config">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading Call Routing Configuration...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="call-routing-config">
        <div className="error-container">
          <p>{error}</p>
          <button onClick={fetchData}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="call-routing-config">
      <div className="config-header">
        <div className="header-content">
          <h1>Call Routing Configuration</h1>
          <p className="subtitle">Intelligent call routing based on CRM stages</p>
        </div>
        <div className="header-actions">
          <button onClick={fetchData} className="refresh-btn">
            Refresh
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="status-cards">
        <div className="status-card">
          <div className="status-icon">
            {status?.status === 'active' ? '✅' : '❌'}
          </div>
          <div className="status-content">
            <div className="status-label">System Status</div>
            <div className="status-value">{status?.status || 'Unknown'}</div>
          </div>
        </div>

        <div className="status-card">
          <div className="status-icon">📞</div>
          <div className="status-content">
            <div className="status-label">Calls Today</div>
            <div className="status-value">{status?.today_stats?.total || 0}</div>
          </div>
        </div>

        <div className="status-card">
          <div className="status-icon">🤖</div>
          <div className="status-content">
            <div className="status-label">Assistants</div>
            <div className="status-value">{status?.assistants_configured || 0}</div>
          </div>
        </div>

        <div className="status-card">
          <div className="status-icon">🔗</div>
          <div className="status-content">
            <div className="status-label">Webhook Active</div>
            <div className="status-value">
              {status?.phone_config?.has_server_url ? 'Yes' : 'No'}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="config-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'assistants' ? 'active' : ''}`}
          onClick={() => setActiveTab('assistants')}
        >
          Assistants
        </button>
        <button
          className={`tab ${activeTab === 'test' ? 'active' : ''}`}
          onClick={() => setActiveTab('test')}
        >
          Test Routing
        </button>
        <button
          className={`tab ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => setActiveTab('logs')}
        >
          Routing Logs
        </button>
        <button
          className={`tab ${activeTab === 'setup' ? 'active' : ''}`}
          onClick={() => setActiveTab('setup')}
        >
          Setup
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="routing-flow">
              <h3>How Call Routing Works</h3>
              <div className="flow-diagram">
                <div className="flow-step">
                  <div className="step-icon">📞</div>
                  <div className="step-content">
                    <h4>Incoming Call</h4>
                    <p>Call received on (832) 648-2297</p>
                  </div>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-step">
                  <div className="step-icon">🔍</div>
                  <div className="step-content">
                    <h4>CRM Lookup</h4>
                    <p>Search leads, loans, MUM clients</p>
                  </div>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-step">
                  <div className="step-icon">🤖</div>
                  <div className="step-content">
                    <h4>Route to Assistant</h4>
                    <p>Based on caller's stage</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="routing-rules">
              <h3>Routing Rules</h3>
              <div className="rules-grid">
                <div className="rule-card">
                  <div className="rule-icon" style={{ backgroundColor: '#3b82f6' }}>🎯</div>
                  <h4>Leads</h4>
                  <p>New inquiries, prospects, pre-approval stage</p>
                  <div className="rule-assistant">→ Lead Assistant</div>
                </div>
                <div className="rule-card">
                  <div className="rule-icon" style={{ backgroundColor: '#10b981' }}>📋</div>
                  <h4>Active Loans</h4>
                  <p>Processing, underwriting, closing</p>
                  <div className="rule-assistant">→ Active Loan Assistant</div>
                </div>
                <div className="rule-card">
                  <div className="rule-icon" style={{ backgroundColor: '#8b5cf6' }}>🏆</div>
                  <h4>MUM Clients</h4>
                  <p>Past clients in post-closing program</p>
                  <div className="rule-assistant">→ MUM Concierge</div>
                </div>
                <div className="rule-card">
                  <div className="rule-icon" style={{ backgroundColor: '#6b7280' }}>❓</div>
                  <h4>Unknown Callers</h4>
                  <p>Not found in CRM database</p>
                  <div className="rule-assistant">→ Sam (Receptionist)</div>
                </div>
              </div>
            </div>

            {status?.today_stats && (
              <div className="today-stats">
                <h3>Today's Call Distribution</h3>
                <div className="stats-bars">
                  <div className="stat-bar">
                    <span className="stat-label">Leads</span>
                    <div className="bar-container">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${(status.today_stats.leads / Math.max(status.today_stats.total, 1)) * 100}%`,
                          backgroundColor: '#3b82f6'
                        }}
                      ></div>
                    </div>
                    <span className="stat-count">{status.today_stats.leads}</span>
                  </div>
                  <div className="stat-bar">
                    <span className="stat-label">Active Loans</span>
                    <div className="bar-container">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${(status.today_stats.active_loans / Math.max(status.today_stats.total, 1)) * 100}%`,
                          backgroundColor: '#10b981'
                        }}
                      ></div>
                    </div>
                    <span className="stat-count">{status.today_stats.active_loans}</span>
                  </div>
                  <div className="stat-bar">
                    <span className="stat-label">MUM Clients</span>
                    <div className="bar-container">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${(status.today_stats.mum_clients / Math.max(status.today_stats.total, 1)) * 100}%`,
                          backgroundColor: '#8b5cf6'
                        }}
                      ></div>
                    </div>
                    <span className="stat-count">{status.today_stats.mum_clients}</span>
                  </div>
                  <div className="stat-bar">
                    <span className="stat-label">Unknown</span>
                    <div className="bar-container">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${(status.today_stats.unknown / Math.max(status.today_stats.total, 1)) * 100}%`,
                          backgroundColor: '#6b7280'
                        }}
                      ></div>
                    </div>
                    <span className="stat-count">{status.today_stats.unknown}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'assistants' && config?.assistants && (
          <div className="assistants-tab">
            <h3>Configured Assistants</h3>
            <div className="assistants-grid">
              {Object.entries(config.assistants).map(([key, assistant]) => (
                <div key={key} className="assistant-card">
                  <div className="assistant-header">
                    <h4>{assistant.name}</h4>
                    <span className="assistant-type">{key}</span>
                  </div>
                  <p className="assistant-description">{assistant.description}</p>
                  <div className="assistant-id">
                    <span className="label">Vapi ID:</span>
                    <code>{assistant.id}</code>
                  </div>
                  {assistant.stages && assistant.stages.length > 0 && (
                    <div className="assistant-stages">
                      <span className="label">Handles stages:</span>
                      <div className="stages-list">
                        {assistant.stages.map(stage => (
                          <span key={stage} className="stage-badge">{stage}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'test' && (
          <div className="test-tab">
            <h3>Test Phone Lookup</h3>
            <p>Enter a phone number to test which assistant would handle the call.</p>

            <div className="test-form">
              <input
                type="tel"
                value={testPhone}
                onChange={(e) => setTestPhone(e.target.value)}
                placeholder="Enter phone number (e.g., 555-123-4567)"
              />
              <button onClick={handleTestLookup}>Test Lookup</button>
            </div>

            {testResult && (
              <div className="test-result">
                <h4>Lookup Result</h4>
                <div className="result-details">
                  <div className="result-row">
                    <span className="label">Phone Searched:</span>
                    <span>{testResult.phone_searched}</span>
                  </div>
                  <div className="result-row">
                    <span className="label">Normalized:</span>
                    <span>{testResult.phone_normalized}</span>
                  </div>
                  <div className="result-row">
                    <span className="label">Found in CRM:</span>
                    <span>{testResult.result?.found ? 'Yes' : 'No'}</span>
                  </div>
                  <div className="result-row">
                    <span className="label">Caller Type:</span>
                    <span style={{ color: getCallerTypeColor(testResult.result?.caller_type) }}>
                      {getCallerTypeIcon(testResult.result?.caller_type)} {testResult.result?.caller_type}
                    </span>
                  </div>
                  {testResult.result?.caller_name && (
                    <div className="result-row">
                      <span className="label">Caller Name:</span>
                      <span>{testResult.result.caller_name}</span>
                    </div>
                  )}
                  {testResult.result?.stage && (
                    <div className="result-row">
                      <span className="label">Stage:</span>
                      <span>{testResult.result.stage}</span>
                    </div>
                  )}
                  <div className="result-row highlight">
                    <span className="label">Routes To:</span>
                    <span>{testResult.result?.assistant_name}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="logs-tab">
            <h3>Recent Routing Logs</h3>
            {logs.length === 0 ? (
              <div className="empty-state">No routing logs yet. Calls will appear here.</div>
            ) : (
              <div className="logs-table">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Phone</th>
                      <th>Type</th>
                      <th>Caller</th>
                      <th>Stage</th>
                      <th>Routed To</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr key={log.id}>
                        <td>{new Date(log.created_at).toLocaleString()}</td>
                        <td>{log.phone}</td>
                        <td>
                          <span style={{ color: getCallerTypeColor(log.caller_type) }}>
                            {getCallerTypeIcon(log.caller_type)} {log.caller_type}
                          </span>
                        </td>
                        <td>{log.caller_name || '-'}</td>
                        <td>{log.stage || '-'}</td>
                        <td>{log.assistant_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'setup' && (
          <div className="setup-tab">
            <h3>Setup & Configuration</h3>

            <div className="setup-section">
              <h4>Phone Number Configuration</h4>
              <p>Configure your Vapi phone number to use intelligent routing.</p>
              <div className="config-info">
                <div className="info-row">
                  <span className="label">Phone Number:</span>
                  <span>{status?.phone_config?.number || '(832) 648-2297'}</span>
                </div>
                <div className="info-row">
                  <span className="label">Webhook URL:</span>
                  <code>{config?.webhook_url}</code>
                </div>
                <div className="info-row">
                  <span className="label">Current Status:</span>
                  <span>
                    {status?.phone_config?.has_server_url
                      ? '✅ Routing Active'
                      : '❌ Not Configured'}
                  </span>
                </div>
              </div>
              <button
                onClick={handleConfigurePhone}
                disabled={configuring}
                className="configure-btn"
              >
                {configuring ? 'Configuring...' : 'Configure Phone for Routing'}
              </button>
            </div>

            <div className="setup-section">
              <h4>Database Migration</h4>
              <p>Create the call routing logs table (run once).</p>
              <button onClick={handleRunMigration} className="secondary-btn">
                Run Migration
              </button>
            </div>

            <div className="setup-section">
              <h4>Assistant IDs</h4>
              <p>Current Vapi assistant configurations:</p>
              <div className="id-list">
                <div className="id-item">
                  <span>Sam (Receptionist):</span>
                  <code>120e239e-4d19-4e43-ad92-1f8b07d08c8c</code>
                </div>
                <div className="id-item">
                  <span>Lead Assistant:</span>
                  <code>3e5af9cd-2ba7-4f45-bd93-5320179b2fc4</code>
                </div>
                <div className="id-item">
                  <span>Active Loan Assistant:</span>
                  <code>08fa09ed-5bb2-4e3a-8c67-26ffb966bc84</code>
                </div>
                <div className="id-item">
                  <span>MUM Concierge:</span>
                  <code>faf78118-6808-4742-b63e-af8f7affd3cd</code>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default CallRoutingConfig;
