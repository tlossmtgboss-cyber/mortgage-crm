import React, { useState, useEffect, useCallback } from 'react';
import './AIEmailSetup.css';
import api from '../services/api';

const AIEmailSetup = () => {
  const [settings, setSettings] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [message, setMessage] = useState(null);
  const [showDnsInstructions, setShowDnsInstructions] = useState(false);
  const [dnsInstructions, setDnsInstructions] = useState(null);

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/ai-email-settings');
      setSettings(data);
    } catch (err) {
      console.error('Error fetching settings:', err);
      setMessage({ type: 'error', text: 'Failed to load settings' });
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/ai-email-settings/status');
      setStatus(data);
    } catch (err) {
      console.error('Error fetching status:', err);
    }
  }, []);

  const fetchDnsInstructions = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/ai-email-settings/dns-instructions');
      setDnsInstructions(data);
    } catch (err) {
      console.error('Error fetching DNS instructions:', err);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSettings(), fetchStatus()]);
      setLoading(false);
    };
    loadData();
  }, [fetchSettings, fetchStatus]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const { data } = await api.put('/api/v1/ai-email-settings', settings);
      setSettings(data);
      setMessage({ type: 'success', text: 'Settings saved successfully!' });
      fetchStatus();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setMessage({ type: 'error', text: detail || 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  const handleTestEmail = async () => {
    if (!testEmail) {
      setMessage({ type: 'error', text: 'Please enter an email address to send the test to' });
      return;
    }

    setTestingEmail(true);
    setMessage(null);
    try {
      await api.post(`/api/v1/ai-email-settings/test-email?to_email=${encodeURIComponent(testEmail)}`);
      setMessage({ type: 'success', text: `Test email sent to ${testEmail}! Check your inbox.` });
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setMessage({ type: 'error', text: detail || 'Failed to send test email' });
    } finally {
      setTestingEmail(false);
    }
  };

  const handleShowDns = async () => {
    if (!dnsInstructions) {
      await fetchDnsInstructions();
    }
    setShowDnsInstructions(true);
  };

  const updateField = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return <div className="ai-email-setup loading">Loading...</div>;
  }

  return (
    <div className="ai-email-setup">
      <div className="setup-header">
        <h2>AI Email Setup</h2>
        <p>Configure your AI assistant's email identity and behavior</p>
      </div>

      {message && (
        <div className={`message-alert ${message.type}`}>
          {message.text}
        </div>
      )}

      {/* Status Overview */}
      {status && (
        <div className="status-overview">
          <h3>Email Setup Status</h3>
          <div className="status-grid">
            <div className={`status-item ${status.mx_configured ? 'success' : 'error'}`}>
              <span className="status-icon">{status.mx_configured ? '✓' : '✗'}</span>
              <span className="status-label">MX Records</span>
            </div>
            <div className={`status-item ${status.spf_configured ? 'success' : 'warning'}`}>
              <span className="status-icon">{status.spf_configured ? '✓' : '!'}</span>
              <span className="status-label">SPF Record</span>
            </div>
            <div className={`status-item ${status.mailbox_exists ? 'success' : 'error'}`}>
              <span className="status-icon">{status.mailbox_exists ? '✓' : '✗'}</span>
              <span className="status-label">Mailbox</span>
            </div>
            <div className={`status-item ${status.ready_to_receive ? 'success' : 'warning'}`}>
              <span className="status-icon">{status.ready_to_receive ? '✓' : '!'}</span>
              <span className="status-label">Ready to Receive</span>
            </div>
          </div>

          {status.issues && status.issues.length > 0 && (
            <div className="issues-list">
              <h4>Issues to Address:</h4>
              <ul>
                {status.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
              <button className="dns-help-btn" onClick={handleShowDns}>
                View DNS Setup Instructions
              </button>
            </div>
          )}
        </div>
      )}

      {/* DNS Instructions Modal */}
      {showDnsInstructions && dnsInstructions && (
        <div className="modal-overlay" onClick={() => setShowDnsInstructions(false)}>
          <div className="dns-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>DNS Setup Instructions for {dnsInstructions.domain}</h3>
              <button className="close-btn" onClick={() => setShowDnsInstructions(false)}>×</button>
            </div>
            <div className="modal-content">
              <div className="dns-records">
                <h4>Required DNS Records:</h4>
                <table>
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Host</th>
                      <th>Value</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>MX</td>
                      <td>{dnsInstructions.instructions.mx_record.host}</td>
                      <td className="value-cell">{dnsInstructions.instructions.mx_record.value}</td>
                      <td>{dnsInstructions.instructions.mx_record.priority}</td>
                    </tr>
                    <tr>
                      <td>TXT</td>
                      <td>{dnsInstructions.instructions.spf_record.host}</td>
                      <td className="value-cell">{dnsInstructions.instructions.spf_record.value}</td>
                      <td>-</td>
                    </tr>
                    <tr>
                      <td>CNAME</td>
                      <td>{dnsInstructions.instructions.autodiscover.host}</td>
                      <td className="value-cell">{dnsInstructions.instructions.autodiscover.value}</td>
                      <td>-</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="setup-steps">
                <h4>Setup Steps:</h4>
                <ol>
                  {dnsInstructions.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>
            </div>
          </div>
        </div>
      )}

      {settings && (
        <div className="settings-sections">
          {/* AI Assistant Identity */}
          <div className="settings-section">
            <h3>AI Assistant Identity</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Assistant Name</label>
                <input
                  type="text"
                  value={settings.assistant_name || ''}
                  onChange={(e) => updateField('assistant_name', e.target.value)}
                  placeholder="Sarah"
                />
                <span className="help-text">The name your AI assistant will use</span>
              </div>
              <div className="form-group">
                <label>Assistant Email</label>
                <input
                  type="email"
                  value={settings.assistant_email || ''}
                  onChange={(e) => updateField('assistant_email', e.target.value)}
                  placeholder="sarah@perenniaai.com"
                />
                <span className="help-text">Email address for sending and receiving</span>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Assistant Title</label>
                <input
                  type="text"
                  value={settings.assistant_title || ''}
                  onChange={(e) => updateField('assistant_title', e.target.value)}
                  placeholder="AI Assistant"
                />
              </div>
              <div className="form-group">
                <label>Company Name</label>
                <input
                  type="text"
                  value={settings.company_name || ''}
                  onChange={(e) => updateField('company_name', e.target.value)}
                  placeholder="Perennia AI"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Display Name (From Name)</label>
              <input
                type="text"
                value={settings.from_name || ''}
                onChange={(e) => updateField('from_name', e.target.value)}
                placeholder="Sarah from Perennia AI"
              />
              <span className="help-text">How the sender name appears in emails</span>
            </div>
          </div>

          {/* Email Behavior */}
          <div className="settings-section">
            <h3>Email Behavior</h3>
            <div className="form-row">
              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.auto_respond || false}
                    onChange={(e) => updateField('auto_respond', e.target.checked)}
                  />
                  Auto-respond to incoming emails
                </label>
              </div>
              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.include_calendar_links || false}
                    onChange={(e) => updateField('include_calendar_links', e.target.checked)}
                  />
                  Include calendar scheduling links
                </label>
              </div>
            </div>
            <div className="form-group">
              <label>Reply-To Email (optional)</label>
              <input
                type="email"
                value={settings.reply_to_email || ''}
                onChange={(e) => updateField('reply_to_email', e.target.value)}
                placeholder="Leave blank to use assistant email"
              />
              <span className="help-text">Override where replies are sent</span>
            </div>
          </div>

          {/* Branding */}
          <div className="settings-section">
            <h3>Branding</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Brand Color</label>
                <div className="color-input-wrapper">
                  <input
                    type="color"
                    value={settings.brand_color || '#2563eb'}
                    onChange={(e) => updateField('brand_color', e.target.value)}
                  />
                  <input
                    type="text"
                    value={settings.brand_color || '#2563eb'}
                    onChange={(e) => updateField('brand_color', e.target.value)}
                    placeholder="#2563eb"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Logo URL (optional)</label>
                <input
                  type="url"
                  value={settings.logo_url || ''}
                  onChange={(e) => updateField('logo_url', e.target.value)}
                  placeholder="https://..."
                />
              </div>
            </div>
            <div className="form-group">
              <label>Email Signature (optional)</label>
              <textarea
                value={settings.email_signature || ''}
                onChange={(e) => updateField('email_signature', e.target.value)}
                placeholder="Custom signature to append to emails..."
                rows={4}
              />
            </div>
          </div>

          {/* Microsoft 365 Integration */}
          <div className="settings-section">
            <h3>Microsoft 365 Integration</h3>
            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={settings.microsoft_mailbox_configured || false}
                  onChange={(e) => updateField('microsoft_mailbox_configured', e.target.checked)}
                />
                I have created the mailbox in Microsoft 365
              </label>
              <span className="help-text">
                Check this after creating {settings.assistant_email} in Microsoft 365 Admin Center
              </span>
            </div>
          </div>

          {/* Save Button */}
          <div className="actions-bar">
            <button
              className="save-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
            <button
              className="refresh-btn"
              onClick={() => { fetchSettings(); fetchStatus(); }}
            >
              Refresh Status
            </button>
          </div>

          {/* Test Email */}
          <div className="settings-section test-section">
            <h3>Send Test Email</h3>
            <p>Send a test email to verify your configuration is working.</p>
            <div className="test-email-form">
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="Enter email address to send test to"
              />
              <button
                onClick={handleTestEmail}
                disabled={testingEmail || !testEmail}
              >
                {testingEmail ? 'Sending...' : 'Send Test Email'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIEmailSetup;
