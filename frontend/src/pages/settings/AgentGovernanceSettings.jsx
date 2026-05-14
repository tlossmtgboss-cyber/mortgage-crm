import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentAPI } from '../../services/api';
import { toast } from '../../utils/toast';

const AgentGovernanceSettings = ({ activeSection }) => {
  const navigate = useNavigate();

  const [settings, setSettings] = useState({
    // System Settings
    agentGovernanceEnabled: true,
    autoHealthChecks: true,
    costTrackingEnabled: true,
    // Performance Thresholds
    defaultSuccessRate: 90,
    defaultResponseTime: 15000,
    defaultMaxCost: 0.015,
    // Cost Budgets
    defaultDailyBudget: 50,
    systemMonthlyBudget: 30000,
    costAlertThreshold: 80,
    // Alerts
    alertChannel: 'Slack',
    slackWebhook: '',
    dailyDigest: true,
    digestTime: '8:00 AM',
    // Access Control
    requireApproval: false,
    viewPermissions: ['All Users'],
    modifyPermissions: ['Admins Only'],
    auditLogging: true,
    // Compliance
    enforceEliteForTier3: true,
    fairLendingMonitoring: true,
    auditRetentionDays: 2555,
    // Integrations
    anthropicApiKey: '',
    webhookUrl: '',
    websocketEnabled: true,
    // Gym
    autoDailyTesting: true,
    minPassRate: 95,
    blockOnFailedTests: false
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  const loadSettings = async () => {
    setLoading(true);
    try {
      const response = await agentAPI.getSettings();
      if (response) {
        setSettings(prev => ({ ...prev, ...response }));
      }
    } catch (error) {
      console.error('Failed to load agent governance settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });
    try {
      await agentAPI.updateSettings(settings);
      setMessage({ type: 'success', text: 'Agent governance settings saved successfully!' });
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      console.error('Failed to save agent governance settings:', error);
      setMessage({ type: 'error', text: 'Failed to save settings. Please try again.' });
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = (key) => {
    setSettings(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  useEffect(() => {
    loadSettings();
  }, [activeSection]);

  if (activeSection === 'agent-governance-system') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - System Settings</h2>
            <p className="section-description">Control system-wide agent features and monitoring</p>
          </div>
          <div className="header-actions">
            <button className="btn-secondary" onClick={() => navigate('/agents')}>
              View Agent Dashboard
            </button>
            <button className="btn-primary" onClick={saveSettings} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        {loading ? (
          <div className="loading-state">Loading agent settings...</div>
        ) : (
          <div className="settings-grid">
            <div className="settings-card">
              <h3>Core Features</h3>
              <div className="setting-row">
                <div className="setting-info">
                  <label className="setting-label">Enable Agent Governance System</label>
                  <p className="setting-description">Turn on monitoring, testing, and compliance tracking for all agents</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={settings.agentGovernanceEnabled} onChange={() => handleToggle('agentGovernanceEnabled')} />
                  <span className="toggle-slider"></span>
                </label>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <label className="setting-label">Automatic Health Checks</label>
                  <p className="setting-description">Run health checks every hour and send alerts for issues</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={settings.autoHealthChecks} onChange={() => handleToggle('autoHealthChecks')} />
                  <span className="toggle-slider"></span>
                </label>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <label className="setting-label">Cost Tracking</label>
                  <p className="setting-description">Track and enforce cost budgets for agent operations</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={settings.costTrackingEnabled} onChange={() => handleToggle('costTrackingEnabled')} />
                  <span className="toggle-slider"></span>
                </label>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <label className="setting-label">Enable WebSocket Real-time Updates</label>
                  <p className="setting-description">Push live metrics to connected clients every 5 seconds</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={settings.websocketEnabled} onChange={() => handleToggle('websocketEnabled')} />
                  <span className="toggle-slider"></span>
                </label>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <label className="setting-label">Audit Log All Changes</label>
                  <p className="setting-description">Log all agent configuration changes with user attribution</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={settings.auditLogging} onChange={() => handleToggle('auditLogging')} />
                  <span className="toggle-slider"></span>
                </label>
              </div>
            </div>

            <div className="settings-card">
              <h3>Quick Actions</h3>
              <div className="settings-action-grid">
                <button className="btn-secondary" onClick={() => navigate('/agents')}>
                  View Agent Dashboard
                </button>
                <button className="btn-secondary" onClick={() => navigate('/agent-gym')}>
                  Open Agent Gym
                </button>
                <button className="btn-secondary" onClick={async () => {
                  try {
                    const health = await agentAPI.getSystemHealth();
                    toast.info(JSON.stringify(health, null, 2));
                  } catch (e) {
                    toast.error('Failed to fetch system health: ' + e.message);
                  }
                }}>
                  Run Health Check
                </button>
                <button className="btn-secondary" onClick={() => {
                  const config = JSON.stringify(settings, null, 2);
                  const blob = new Blob([config], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'agent-governance-config.json';
                  a.click();
                }}>
                  Export Configuration
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (activeSection === 'agent-governance-thresholds') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - Performance Thresholds</h2>
            <p className="section-description">Set default performance standards for all agents</p>
          </div>
          <button className="btn-primary" onClick={saveSettings} disabled={saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="settings-card">
          <h3>Default Thresholds</h3>
          <p className="card-description">These defaults apply to all agents unless overridden individually.</p>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Minimum Success Rate</label>
              <p className="setting-description">Agents below this rate will be flagged for review</p>
            </div>
            <div className="setting-input-wrapper">
              <input type="number" className="setting-input" value={settings.defaultSuccessRate} onChange={(e) => handleChange('defaultSuccessRate', Number(e.target.value))} min="80" max="100" />
              <span className="input-suffix">%</span>
            </div>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Maximum Response Time (P95)</label>
              <p className="setting-description">95th percentile response time threshold</p>
            </div>
            <div className="setting-input-wrapper">
              <input type="number" className="setting-input" value={settings.defaultResponseTime} onChange={(e) => handleChange('defaultResponseTime', Number(e.target.value))} min="1000" max="60000" />
              <span className="input-suffix">ms</span>
            </div>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Maximum Cost Per Success</label>
              <p className="setting-description">Cost efficiency threshold per successful execution</p>
            </div>
            <div className="setting-input-wrapper">
              <span className="input-prefix">$</span>
              <input type="number" className="setting-input" value={settings.defaultMaxCost} onChange={(e) => handleChange('defaultMaxCost', Number(e.target.value))} step="0.001" min="0" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (activeSection === 'agent-governance-costs') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - Cost Budgets</h2>
            <p className="section-description">Set cost limits and budgets for agent operations</p>
          </div>
          <button className="btn-primary" onClick={saveSettings} disabled={saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="settings-card">
          <h3>Budget Settings</h3>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Daily Budget (per agent)</label>
              <p className="setting-description">Maximum daily spend per individual agent</p>
            </div>
            <div className="setting-input-wrapper">
              <span className="input-prefix">$</span>
              <input type="number" className="setting-input" value={settings.defaultDailyBudget} onChange={(e) => handleChange('defaultDailyBudget', Number(e.target.value))} min="0" />
            </div>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Monthly Budget (system-wide)</label>
              <p className="setting-description">Total monthly budget across all agents</p>
            </div>
            <div className="setting-input-wrapper">
              <span className="input-prefix">$</span>
              <input type="number" className="setting-input" value={settings.systemMonthlyBudget} onChange={(e) => handleChange('systemMonthlyBudget', Number(e.target.value))} min="0" />
            </div>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Cost Alert Threshold</label>
              <p className="setting-description">Trigger alerts when spending reaches this percentage of budget</p>
            </div>
            <div className="setting-input-wrapper">
              <input type="number" className="setting-input" value={settings.costAlertThreshold} onChange={(e) => handleChange('costAlertThreshold', Number(e.target.value))} min="50" max="100" />
              <span className="input-suffix">%</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (activeSection === 'agent-governance-alerts') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - Alerts & Notifications</h2>
            <p className="section-description">Configure how you receive agent alerts and notifications</p>
          </div>
          <button className="btn-primary" onClick={saveSettings} disabled={saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="settings-card">
          <h3>Alert Configuration</h3>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Alert Routing</label>
              <p className="setting-description">Where to send agent alerts</p>
            </div>
            <select className="setting-select" value={settings.alertChannel} onChange={(e) => handleChange('alertChannel', e.target.value)}>
              <option value="Email">Email</option>
              <option value="Slack">Slack</option>
              <option value="Discord">Discord</option>
              <option value="SMS">SMS</option>
            </select>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Slack Webhook URL</label>
              <p className="setting-description">Webhook for Slack notifications</p>
            </div>
            <input type="url" className="setting-input wide" value={settings.slackWebhook} onChange={(e) => handleChange('slackWebhook', e.target.value)} placeholder="https://hooks.slack.com/services/..." />
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Daily Digest Notifications</label>
              <p className="setting-description">Receive daily digest of agent performance and issues</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.dailyDigest} onChange={() => handleToggle('dailyDigest')} />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Digest Time</label>
              <p className="setting-description">When to send the daily digest</p>
            </div>
            <select className="setting-select" value={settings.digestTime} onChange={(e) => handleChange('digestTime', e.target.value)}>
              <option value="8:00 AM">8:00 AM</option>
              <option value="12:00 PM">12:00 PM</option>
              <option value="6:00 PM">6:00 PM</option>
            </select>
          </div>
        </div>
      </div>
    );
  }

  if (activeSection === 'agent-governance-compliance') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - Compliance</h2>
            <p className="section-description">Configure compliance and governance rules for agents</p>
          </div>
          <button className="btn-primary" onClick={saveSettings} disabled={saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="settings-card">
          <h3>Compliance Settings</h3>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Enforce Elite Status for Tier 3 Agents</label>
              <p className="setting-description">Tier 3 agents must maintain Elite performance standards</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.enforceEliteForTier3} onChange={() => handleToggle('enforceEliteForTier3')} />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Fair Lending Monitoring</label>
              <p className="setting-description">Track disparate impact across protected classes for compliance agents</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.fairLendingMonitoring} onChange={() => handleToggle('fairLendingMonitoring')} />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Require Approval for Agent Changes</label>
              <p className="setting-description">All agent configuration changes require admin approval</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.requireApproval} onChange={() => handleToggle('requireApproval')} />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Audit Log Retention</label>
              <p className="setting-description">Required: 7 years (2555 days) for Tier 3 agents</p>
            </div>
            <div className="setting-input-wrapper">
              <input type="number" className="setting-input" value={settings.auditRetentionDays} onChange={(e) => handleChange('auditRetentionDays', Number(e.target.value))} min="365" />
              <span className="input-suffix">days</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (activeSection === 'agent-governance-gym') {
    return (
      <div className="agent-governance-section">
        <div className="page-header">
          <div>
            <h2>Agent Governance - Agent Gym Settings</h2>
            <p className="section-description">Configure agent training and testing settings</p>
          </div>
          <div className="header-actions">
            <button className="btn-secondary" onClick={() => navigate('/agent-gym')}>
              Open Agent Gym
            </button>
            <button className="btn-primary" onClick={saveSettings} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        {message.text && (
          <div className={`message-banner ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="settings-card">
          <h3>Training & Testing Configuration</h3>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Automatic Daily Testing</label>
              <p className="setting-description">Run gym scenarios for all agents at 2 AM daily</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.autoDailyTesting} onChange={() => handleToggle('autoDailyTesting')} />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Minimum Pass Rate for Production</label>
              <p className="setting-description">Agents below this pass rate are flagged for review</p>
            </div>
            <div className="setting-input-wrapper">
              <input type="number" className="setting-input" value={settings.minPassRate} onChange={(e) => handleChange('minPassRate', Number(e.target.value))} min="50" max="100" />
              <span className="input-suffix">%</span>
            </div>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label">Block Deployment on Failed Tests</label>
              <p className="setting-description">Prevent agent deployments if gym tests fail</p>
            </div>
            <label className="toggle-switch">
              <input type="checkbox" checked={settings.blockOnFailedTests} onChange={() => handleToggle('blockOnFailedTests')} />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>
    );
  }

  return null;
};

export default AgentGovernanceSettings;
