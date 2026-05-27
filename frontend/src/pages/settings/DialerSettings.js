import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import { API_BASE } from './shared/constants';

const DialerSettings = () => {
  const [settings, setSettings] = useState({
    cell_phone: '',
    business_caller_id: '',
    dialer_enabled: false,
    max_calls_per_day: 100,
    auto_advance: true,
    pause_between_calls: 3
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifiedCallerIds, setVerifiedCallerIds] = useState([]);
  const [verifyPhone, setVerifyPhone] = useState('');
  const [verifyName, setVerifyName] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchSettings();
    fetchVerifiedCallerIds();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (err) {
      console.error('Error fetching dialer settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchVerifiedCallerIds = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verified-caller-ids`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setVerifiedCallerIds(data.caller_ids || []);
      }
    } catch (err) {
      console.error('Error fetching verified caller IDs:', err);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(settings)
      });
      if (response.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
      } else {
        const err = await response.json();
        setMessage({ type: 'error', text: err.detail || 'Failed to save settings' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error saving settings: ' + err.message });
    } finally {
      setSaving(false);
    }
  };

  const startVerification = async () => {
    if (!verifyPhone || !verifyName) {
      setMessage({ type: 'error', text: 'Please enter phone number and name' });
      return;
    }

    setVerifying(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verify-caller-id`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone_number: verifyPhone,
          friendly_name: verifyName
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        setMessage({ type: 'error', text: `Server error (${response.status}): ${errorText}` });
        return;
      }

      const data = await response.json();
      if (data.success) {
        setMessage({
          type: 'success',
          text: `Caller ID "${verifyName}" (${data.phone_number}) registered and verified!`
        });
        setVerifyPhone('');
        setVerifyName('');
        await fetchVerifiedCallerIds();
        await fetchSettings();
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to register caller ID' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error registering caller ID: ' + err.message });
    } finally {
      setVerifying(false);
    }
  };

  const checkVerification = async () => {
    if (!verifyPhone) {
      setMessage({ type: 'error', text: 'Please enter a phone number to check' });
      return;
    }

    setVerifying(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/check-verification/${encodeURIComponent(verifyPhone)}`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await response.json();
      if (data.verified) {
        setMessage({ type: 'success', text: data.message });
        setVerifyPhone('');
        await fetchVerifiedCallerIds();
      } else {
        setMessage({ type: 'warning', text: data.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error checking verification: ' + err.message });
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return <div className="loading-state">Loading dialer settings...</div>;
  }

  return (
    <div className="dialer-settings-section">
      <h2>Power Dialer Settings</h2>
      <p className="section-description">
        Configure your click-to-dial and power dialer settings for outbound calls
      </p>

      {message && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage(null)}>x</button>
        </div>
      )}

      <div className="settings-card">
        <h3>Phone Numbers</h3>

        <div className="form-group">
          <label>Your Cell Phone</label>
          <input
            type="tel"
            value={settings.cell_phone || ''}
            onChange={(e) => setSettings({ ...settings, cell_phone: formatPhoneNumber(e.target.value) })}
            placeholder="+1 (555) 123-4567"
          />
          <small>Your personal phone number for receiving calls</small>
        </div>

        <div className="form-group">
          <label>Business Caller ID</label>
          <select
            value={settings.business_caller_id || ''}
            onChange={(e) => setSettings({ ...settings, business_caller_id: e.target.value })}
          >
            <option value="">Select a verified caller ID...</option>
            {verifiedCallerIds.map((cid) => (
              <option key={cid.sid} value={cid.phone_number}>
                {cid.friendly_name} ({cid.phone_number})
              </option>
            ))}
          </select>
          <small>The phone number shown to contacts when you call them</small>
        </div>

        <div className="verify-caller-id">
          <h4>Add New Caller ID</h4>
          <p>Add a business phone number to use as your outbound caller ID</p>
          <div className="verify-form">
            <input
              type="tel"
              value={verifyPhone}
              onChange={(e) => setVerifyPhone(formatPhoneNumber(e.target.value))}
              placeholder="+1 (555) 123-4567"
            />
            <input
              type="text"
              value={verifyName}
              onChange={(e) => setVerifyName(e.target.value)}
              placeholder="Display Name (e.g., Tim Loss)"
            />
            <div className="verify-buttons">
              <button
                onClick={startVerification}
                disabled={verifying || !verifyPhone || !verifyName}
                className="btn-primary"
              >
                {verifying ? 'Registering...' : 'Register Caller ID'}
              </button>
            </div>
          </div>
          <small>
            <strong>Step 1:</strong> Enter your business phone number and display name.<br />
            <strong>Step 2:</strong> Click "Register Caller ID" to add it as your outbound number.
          </small>
        </div>
      </div>

      <div className="settings-card">
        <h3>Dialer Preferences</h3>

        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={settings.dialer_enabled}
              onChange={(e) => setSettings({ ...settings, dialer_enabled: e.target.checked })}
            />
            Enable Power Dialer
          </label>
          <small>Allow batch calling through the power dialer interface</small>
        </div>

        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={settings.auto_advance}
              onChange={(e) => setSettings({ ...settings, auto_advance: e.target.checked })}
            />
            Auto-Advance to Next Call
          </label>
          <small>Automatically dial the next contact after setting disposition</small>
        </div>

        <div className="form-group">
          <label>Max Calls Per Day</label>
          <input
            type="number"
            min="1"
            max="500"
            value={settings.max_calls_per_day || 100}
            onChange={(e) => setSettings({ ...settings, max_calls_per_day: parseInt(e.target.value) || 100 })}
          />
          <small>Daily call limit to prevent burnout and maintain quality</small>
        </div>

        <div className="form-group">
          <label>Pause Between Calls (seconds)</label>
          <input
            type="number"
            min="0"
            max="30"
            value={settings.pause_between_calls || 3}
            onChange={(e) => setSettings({ ...settings, pause_between_calls: parseInt(e.target.value) || 3 })}
          />
          <small>Time to wait before auto-dialing the next contact</small>
        </div>
      </div>

      <div className="settings-actions">
        <button
          onClick={saveSettings}
          disabled={saving}
          className="btn-primary btn-large"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

export default DialerSettings;
