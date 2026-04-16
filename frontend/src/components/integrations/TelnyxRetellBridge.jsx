import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../services/api';
import './TelnyxRetellBridge.css';
import { getToken } from '../../utils/tokenStore';

const TelnyxRetellBridge = () => {
  const [status, setStatus] = useState(null);
  const [telnyxNumbers, setTelnyxNumbers] = useState([]);
  const [retellAgents, setRetellAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState({});
  const [showTeXML, setShowTeXML] = useState(null);
  const [texmlCode, setTexmlCode] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const token = getToken();
      const headers = { Authorization: `Bearer ${token}` };

      // Load bridge status
      const statusRes = await fetch(`${API_BASE_URL}/api/v1/telnyx-retell/status`, { headers });
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setStatus(statusData);
      }

      // Load Telnyx numbers
      try {
        const numbersRes = await fetch(`${API_BASE_URL}/api/v1/telnyx-retell/telnyx-numbers`, { headers });
        if (numbersRes.ok) {
          const numbersData = await numbersRes.json();
          setTelnyxNumbers(numbersData.phone_numbers || []);
        }
      } catch (e) {
        console.log('Telnyx numbers not available:', e);
      }

      // Load Retell agents
      try {
        const agentsRes = await fetch(`${API_BASE_URL}/api/v1/retell/agents`, { headers });
        if (agentsRes.ok) {
          const agentsData = await agentsRes.json();
          setRetellAgents(agentsData.agents || []);
        }
      } catch (e) {
        console.log('Retell agents not available:', e);
      }

    } catch (err) {
      setError('Failed to load data. Please check your API keys.');
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (phoneNumber) => {
    const agentId = selectedAgent[phoneNumber];
    if (!agentId) {
      setError('Please select a Retell agent first');
      return;
    }

    setConnecting(phoneNumber);
    setError(null);
    setSuccess(null);

    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/v1/telnyx-retell/connect`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone_number: phoneNumber,
          retell_agent_id: agentId,
        }),
      });

      const data = await res.json();

      if (res.ok && data.success) {
        setSuccess(`Connected ${phoneNumber} to Retell agent!`);
        loadData(); // Refresh
      } else {
        setError(data.error || data.detail || 'Failed to connect');
      }
    } catch (err) {
      setError('Connection failed: ' + err.message);
    } finally {
      setConnecting(null);
    }
  };

  const handleDisconnect = async (phoneNumber) => {
    if (!window.confirm(`Disconnect ${phoneNumber} from Retell?`)) return;

    setConnecting(phoneNumber);
    setError(null);

    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/telnyx-retell/disconnect/${encodeURIComponent(phoneNumber)}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (res.ok) {
        setSuccess(`Disconnected ${phoneNumber}`);
        loadData();
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to disconnect');
      }
    } catch (err) {
      setError('Disconnect failed: ' + err.message);
    } finally {
      setConnecting(null);
    }
  };

  const handleGenerateTeXML = async (agentId) => {
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/v1/telnyx-retell/generate-texml`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ retell_agent_id: agentId }),
      });

      if (res.ok) {
        const data = await res.json();
        setTexmlCode(data.texml);
        setShowTeXML(agentId);
      }
    } catch (err) {
      setError('Failed to generate TeXML');
    }
  };

  if (loading) {
    return (
      <div className="telnyx-retell-bridge">
        <div className="loading">Loading Telnyx-Retell Bridge...</div>
      </div>
    );
  }

  if (!status?.bridge_ready) {
    return (
      <div className="telnyx-retell-bridge">
        <div className="setup-required">
          <h3>Setup Required</h3>
          <p>To connect Telnyx phone numbers with Retell AI, you need to configure both integrations:</p>
          <ul>
            <li>
              <span className={status?.telnyx_configured ? 'check' : 'missing'}>
                {status?.telnyx_configured ? '✓' : '○'}
              </span>
              Telnyx API Key {!status?.telnyx_configured && '- Not configured'}
            </li>
            <li>
              <span className={status?.retell_configured ? 'check' : 'missing'}>
                {status?.retell_configured ? '✓' : '○'}
              </span>
              Retell AI API Key {!status?.retell_configured && '- Not configured'}
            </li>
          </ul>
          <p>Go to Settings &gt; Integrations to add your API keys.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="telnyx-retell-bridge">
      <div className="bridge-header">
        <h3>Telnyx + Retell AI Bridge</h3>
        <p>Connect your Telnyx phone numbers to Retell AI voice agents</p>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      <div className="bridge-stats">
        <div className="stat">
          <span className="stat-value">{telnyxNumbers.length}</span>
          <span className="stat-label">Telnyx Numbers</span>
        </div>
        <div className="stat">
          <span className="stat-value">{retellAgents.length}</span>
          <span className="stat-label">Retell Agents</span>
        </div>
        <div className="stat">
          <span className="stat-value">{status?.connected_numbers || 0}</span>
          <span className="stat-label">Connected</span>
        </div>
      </div>

      <div className="numbers-section">
        <h4>Phone Numbers</h4>
        {telnyxNumbers.length === 0 ? (
          <p className="no-data">No Telnyx phone numbers found. Purchase numbers in your Telnyx dashboard.</p>
        ) : (
          <table className="numbers-table">
            <thead>
              <tr>
                <th>Phone Number</th>
                <th>Status</th>
                <th>Retell Agent</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {telnyxNumbers.map((num) => (
                <tr key={num.phone_number}>
                  <td className="phone-number">{num.phone_number}</td>
                  <td>
                    <span className={`status-badge ${num.is_connected_to_retell ? 'connected' : 'disconnected'}`}>
                      {num.is_connected_to_retell ? 'Connected' : 'Not Connected'}
                    </span>
                  </td>
                  <td>
                    {num.is_connected_to_retell ? (
                      <span className="agent-name">
                        {retellAgents.find(a => a.agent_id === num.retell_agent_id)?.agent_name || num.retell_agent_id}
                      </span>
                    ) : (
                      <select
                        value={selectedAgent[num.phone_number] || ''}
                        onChange={(e) => setSelectedAgent({ ...selectedAgent, [num.phone_number]: e.target.value })}
                        disabled={connecting === num.phone_number}
                      >
                        <option value="">Select Agent...</option>
                        {retellAgents.map((agent) => (
                          <option key={agent.agent_id} value={agent.agent_id}>
                            {agent.agent_name}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td>
                    {num.is_connected_to_retell ? (
                      <button
                        className="btn-disconnect"
                        onClick={() => handleDisconnect(num.phone_number)}
                        disabled={connecting === num.phone_number}
                      >
                        {connecting === num.phone_number ? 'Disconnecting...' : 'Disconnect'}
                      </button>
                    ) : (
                      <button
                        className="btn-connect"
                        onClick={() => handleConnect(num.phone_number)}
                        disabled={connecting === num.phone_number || !selectedAgent[num.phone_number]}
                      >
                        {connecting === num.phone_number ? 'Connecting...' : 'Connect'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="webhook-section">
        <h4>Webhook Configuration</h4>
        <p>Configure your Telnyx TeXML application to use this webhook URL for inbound calls:</p>
        <code className="webhook-url">
          {window.location.origin.replace('3000', '8000')}/api/v1/telnyx-retell/webhook/inbound
        </code>
        <p className="webhook-note">
          This webhook automatically routes inbound calls to the connected Retell agent.
        </p>
      </div>

      {retellAgents.length > 0 && (
        <div className="texml-section">
          <h4>Manual TeXML (Alternative)</h4>
          <p>If you prefer manual configuration, generate TeXML code for any agent:</p>
          <div className="agent-texml-list">
            {retellAgents.map((agent) => (
              <div key={agent.agent_id} className="agent-texml-item">
                <span>{agent.agent_name}</span>
                <button
                  className="btn-texml"
                  onClick={() => handleGenerateTeXML(agent.agent_id)}
                >
                  Generate TeXML
                </button>
              </div>
            ))}
          </div>

          {showTeXML && (
            <div className="texml-modal">
              <div className="texml-modal-content">
                <h5>TeXML for Retell Agent</h5>
                <pre>{texmlCode}</pre>
                <div className="texml-actions">
                  <button onClick={() => navigator.clipboard.writeText(texmlCode)}>
                    Copy to Clipboard
                  </button>
                  <button onClick={() => setShowTeXML(null)}>Close</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TelnyxRetellBridge;
