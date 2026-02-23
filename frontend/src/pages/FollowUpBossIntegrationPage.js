import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import { connectionApi, settingsApi, stageMappingApi, syncApi, leadMappingApi } from '../services/followupbossApi';
import './FollowUpBossIntegrationPage.css';

const CRM_STAGES = [
  { value: 'NEW', label: 'New' },
  { value: 'ATTEMPTED_CONTACT', label: 'Attempted Contact' },
  { value: 'PROSPECT', label: 'Prospect' },
  { value: 'PRE_QUALIFIED', label: 'Pre-Qualified' },
  { value: 'APPLICATION', label: 'Application' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'UNDER_CONTRACT', label: 'Under Contract' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'LONG_TERM_NURTURE', label: 'Long-Term Nurture' },
  { value: 'WITHDRAWN', label: 'Withdrawn' },
  { value: 'DOES_NOT_QUALIFY', label: 'Does Not Qualify' },
  { value: 'CREDIT_REPAIR', label: 'Credit Repair' },
  { value: 'DO_NOT_CALL', label: 'Do Not Call' },
];

function FollowUpBossIntegrationPage() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('overview');
  const [loading, setLoading] = useState(true);

  // Connection state
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [connecting, setConnecting] = useState(false);

  // Settings state
  const [settings, setSettings] = useState({
    sync_enabled: false,
    sync_notes: true,
    sync_stages: true,
    sync_lead_updates: true,
  });

  // Webhook
  const [webhookUrl, setWebhookUrl] = useState('');

  // Stage mapping state
  const [stageMappings, setStageMappings] = useState([]);
  const [editingMappings, setEditingMappings] = useState(false);
  const [editedMappings, setEditedMappings] = useState([]);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncHistory, setSyncHistory] = useState([]);

  // Lead mappings state
  const [leadMappings, setLeadMappings] = useState([]);
  const [leadMappingsTotal, setLeadMappingsTotal] = useState(0);
  const [leadMappingsPage, setLeadMappingsPage] = useState(0);

  // Load data on mount
  useEffect(() => {
    loadConnectionStatus();
  }, []);

  const loadConnectionStatus = async () => {
    setLoading(true);
    try {
      const data = await connectionApi.getStatus();
      setConnectionStatus(data);
      if (data.connected) {
        await Promise.all([
          loadWebhookUrl(),
          loadStageMappings(),
          loadSyncHistory(),
          loadLeadMappings(),
        ]);
        if (data.settings) {
          setSettings(prev => ({ ...prev, ...data.settings }));
        }
      }
    } catch (err) {
      console.error('Failed to load FUB status:', err);
      setConnectionStatus({ connected: false });
    } finally {
      setLoading(false);
    }
  };

  const loadWebhookUrl = async () => {
    try {
      const data = await connectionApi.getWebhookUrl();
      setWebhookUrl(data.webhook_url || '');
    } catch (err) {
      console.error('Failed to load webhook URL:', err);
    }
  };

  const loadStageMappings = async () => {
    try {
      const data = await stageMappingApi.getMappings();
      setStageMappings(data.mappings || []);
    } catch (err) {
      console.error('Failed to load stage mappings:', err);
    }
  };

  const loadSyncHistory = async () => {
    try {
      const data = await syncApi.getHistory(20);
      setSyncHistory(data.events || []);
    } catch (err) {
      console.error('Failed to load sync history:', err);
    }
  };

  const loadLeadMappings = async (offset = 0) => {
    try {
      const data = await leadMappingApi.getMappings(50, offset);
      setLeadMappings(data.mappings || []);
      setLeadMappingsTotal(data.total || 0);
      setLeadMappingsPage(offset);
    } catch (err) {
      console.error('Failed to load lead mappings:', err);
    }
  };

  // Connection actions
  const handleConnect = async () => {
    if (!apiKey.trim()) {
      toast.error('Please enter your Follow Up Boss API key');
      return;
    }
    setConnecting(true);
    try {
      const data = await connectionApi.connect(apiKey.trim());
      toast.success(`Connected as ${data.fub_user_name || 'Unknown User'}`);
      setApiKey('');
      await loadConnectionStatus();
    } catch (err) {
      toast.error(err.message || 'Failed to connect');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Disconnect Follow Up Boss? This will stop all syncing.')) return;
    try {
      await connectionApi.disconnect();
      toast.success('Disconnected from Follow Up Boss');
      setConnectionStatus({ connected: false });
      setStageMappings([]);
      setSyncHistory([]);
      setLeadMappings([]);
    } catch (err) {
      toast.error(err.message || 'Failed to disconnect');
    }
  };

  const handleVerify = async () => {
    try {
      const data = await connectionApi.verify();
      if (data.valid) {
        toast.success('Connection verified successfully');
      } else {
        toast.error('Connection is no longer valid');
      }
    } catch (err) {
      toast.error(err.message || 'Verification failed');
    }
  };

  // Settings actions
  const handleUpdateSettings = async (key, value) => {
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    try {
      await settingsApi.updateSettings(updated);
      toast.success('Settings updated');
    } catch (err) {
      toast.error(err.message || 'Failed to update settings');
      setSettings(settings); // revert
    }
  };

  // Stage mapping actions
  const handleStartEditMappings = () => {
    setEditedMappings(stageMappings.map(m => ({ ...m })));
    setEditingMappings(true);
  };

  const handleStageChange = (index, crmStage) => {
    const updated = [...editedMappings];
    updated[index] = { ...updated[index], crm_stage: crmStage };
    setEditedMappings(updated);
  };

  const handleSaveMappings = async () => {
    try {
      await stageMappingApi.updateMappings(editedMappings);
      toast.success('Stage mappings saved');
      setStageMappings(editedMappings);
      setEditingMappings(false);
    } catch (err) {
      toast.error(err.message || 'Failed to save mappings');
    }
  };

  const handleRefreshStages = async () => {
    try {
      const data = await stageMappingApi.refreshStages();
      toast.success(`Refreshed ${data.stages_count || 0} stages from Follow Up Boss`);
      await loadStageMappings();
    } catch (err) {
      toast.error(err.message || 'Failed to refresh stages');
    }
  };

  // Sync actions
  const handleTriggerSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const data = await syncApi.triggerSync(100);
      setSyncResult(data);
      toast.success(`Sync complete: ${data.created || 0} created, ${data.updated || 0} updated`);
      await loadSyncHistory();
      await loadLeadMappings();
    } catch (err) {
      toast.error(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  // Lead mapping actions
  const handleDeleteLeadMapping = async (mappingId) => {
    if (!window.confirm('Remove this lead mapping? The lead will not be deleted.')) return;
    try {
      await leadMappingApi.deleteMapping(mappingId);
      toast.success('Lead mapping removed');
      await loadLeadMappings(leadMappingsPage);
    } catch (err) {
      toast.error(err.message || 'Failed to remove mapping');
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  // ===== RENDER HELPERS =====

  const renderSidebar = () => (
    <div className="fub-sidebar">
      <div className="fub-sidebar-header">
        <div className="fub-logo">
          <div className="fub-logo-icon">
            <svg viewBox="0 0 40 40" width="32" height="32">
              <rect width="40" height="40" rx="8" fill="#ff6b35"/>
              <text x="20" y="28" textAnchor="middle" fill="white" fontWeight="bold" fontSize="20">F</text>
            </svg>
          </div>
          <span>Follow Up Boss</span>
        </div>
        <span className={`fub-status ${connectionStatus?.connected ? 'connected' : 'disconnected'}`}>
          {connectionStatus?.connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <nav className="fub-nav">
        {[
          { key: 'overview', icon: '\u{1F4CA}', label: 'Overview' },
          { key: 'connection', icon: '\u{1F517}', label: 'Connection' },
          { key: 'stages', icon: '\u{1F504}', label: 'Stage Mapping', requiresConnection: true },
          { key: 'sync', icon: '\u{26A1}', label: 'Data Sync', requiresConnection: true },
          { key: 'leads', icon: '\u{1F465}', label: 'Synced Leads', requiresConnection: true },
          { key: 'history', icon: '\u{1F4DC}', label: 'History', requiresConnection: true },
        ].map(item => (
          <button
            key={item.key}
            className={`fub-nav-item ${activeSection === item.key ? 'active' : ''}`}
            onClick={() => setActiveSection(item.key)}
            disabled={item.requiresConnection && !connectionStatus?.connected}
          >
            <span className="fub-nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      <div className="fub-sidebar-footer">
        <button className="fub-back-btn" onClick={() => navigate('/settings/integrations')}>
          &larr; Back to Integrations
        </button>
      </div>
    </div>
  );

  const renderOverview = () => (
    <div className="fub-section">
      <h1>Follow Up Boss Integration</h1>
      <p className="fub-description">
        Sync leads bidirectionally between Follow Up Boss and your CRM. Stage changes,
        notes, and new leads flow automatically in both directions.
      </p>

      <div className="fub-stats-grid">
        <div className="fub-stat-card">
          <div className="fub-stat-icon" style={{ background: connectionStatus?.connected ? '#e6f9f0' : '#fef2f2' }}>
            {connectionStatus?.connected ? '\u2705' : '\u274C'}
          </div>
          <div>
            <div className="fub-stat-value">{connectionStatus?.connected ? 'Active' : 'Inactive'}</div>
            <div className="fub-stat-label">Connection Status</div>
          </div>
        </div>
        <div className="fub-stat-card">
          <div className="fub-stat-icon">{'\u{1F465}'}</div>
          <div>
            <div className="fub-stat-value">{leadMappingsTotal}</div>
            <div className="fub-stat-label">Synced Leads</div>
          </div>
        </div>
        <div className="fub-stat-card">
          <div className="fub-stat-icon">{'\u{1F504}'}</div>
          <div>
            <div className="fub-stat-value">{stageMappings.length}</div>
            <div className="fub-stat-label">Stage Mappings</div>
          </div>
        </div>
        <div className="fub-stat-card">
          <div className="fub-stat-icon">{'\u{1F4C5}'}</div>
          <div>
            <div className="fub-stat-value">
              {connectionStatus?.last_sync_at
                ? new Date(connectionStatus.last_sync_at).toLocaleDateString()
                : 'Never'}
            </div>
            <div className="fub-stat-label">Last Sync</div>
          </div>
        </div>
      </div>

      {connectionStatus?.connected && (
        <div className="fub-card">
          <div className="fub-card-header success">
            <span className="fub-card-icon">{'\u2705'}</span>
            Connected to Follow Up Boss
          </div>
          <div className="fub-card-body">
            <div className="fub-info-grid">
              <div className="fub-info-item">
                <span className="fub-info-label">Account</span>
                <span className="fub-info-value">{connectionStatus.fub_user_name || 'Unknown'}</span>
              </div>
              <div className="fub-info-item">
                <span className="fub-info-label">Email</span>
                <span className="fub-info-value">{connectionStatus.fub_user_email || 'N/A'}</span>
              </div>
              <div className="fub-info-item">
                <span className="fub-info-label">Sync Direction</span>
                <span className="fub-info-value">Bidirectional</span>
              </div>
              <div className="fub-info-item">
                <span className="fub-info-label">Auto Sync</span>
                <span className="fub-info-value">{settings.sync_enabled ? 'Enabled' : 'Disabled'}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {!connectionStatus?.connected && (
        <div className="fub-cta-card">
          <h3>Connect Follow Up Boss</h3>
          <p>Enter your API key to start syncing leads between Follow Up Boss and your CRM.</p>
          <button className="fub-btn fub-btn-lg" style={{ background: 'white', color: '#ff6b35' }}
            onClick={() => setActiveSection('connection')}>
            Get Started
          </button>
        </div>
      )}
    </div>
  );

  const renderConnection = () => (
    <div className="fub-section">
      <h1>Connection</h1>
      <p className="fub-description">Manage your Follow Up Boss API connection and sync settings.</p>

      {!connectionStatus?.connected ? (
        <div className="fub-card">
          <div className="fub-card-header">
            <span className="fub-card-icon">{'\u{1F511}'}</span>
            Connect with API Key
          </div>
          <div className="fub-card-body">
            <p style={{ color: '#64748b', marginBottom: '16px' }}>
              Find your API key in Follow Up Boss under <strong>Admin &gt; API</strong>.
              The key starts with <code>fka_</code>.
            </p>
            <div className="fub-input-group">
              <label className="fub-label">API Key</label>
              <input
                type="password"
                className="fub-input"
                placeholder="fka_XXXX..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
              />
            </div>
            <button
              className="fub-btn fub-btn-primary"
              onClick={handleConnect}
              disabled={connecting || !apiKey.trim()}
              style={{ marginTop: '16px' }}
            >
              {connecting ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Connection Info */}
          <div className="fub-card">
            <div className="fub-card-header success">
              <span className="fub-card-icon">{'\u2705'}</span>
              Connected as {connectionStatus.fub_user_name}
            </div>
            <div className="fub-card-body">
              <div className="fub-info-grid">
                <div className="fub-info-item">
                  <span className="fub-info-label">User</span>
                  <span className="fub-info-value">{connectionStatus.fub_user_name}</span>
                </div>
                <div className="fub-info-item">
                  <span className="fub-info-label">Email</span>
                  <span className="fub-info-value">{connectionStatus.fub_user_email || 'N/A'}</span>
                </div>
                <div className="fub-info-item">
                  <span className="fub-info-label">FUB User ID</span>
                  <span className="fub-info-value">{connectionStatus.fub_user_id || 'N/A'}</span>
                </div>
                <div className="fub-info-item">
                  <span className="fub-info-label">Connected Since</span>
                  <span className="fub-info-value">
                    {connectionStatus.connected_at
                      ? new Date(connectionStatus.connected_at).toLocaleDateString()
                      : 'N/A'}
                  </span>
                </div>
              </div>
              <div style={{ marginTop: '16px' }}>
                <button className="fub-btn fub-btn-outline" onClick={handleVerify}>
                  Verify Connection
                </button>
              </div>
            </div>
          </div>

          {/* Webhook Setup */}
          <div className="fub-card">
            <div className="fub-card-header">
              <span className="fub-card-icon">{'\u{1F514}'}</span>
              Webhook Configuration
            </div>
            <div className="fub-card-body">
              <p style={{ color: '#64748b', marginBottom: '16px' }}>
                Configure this webhook URL in Follow Up Boss to receive real-time updates when leads are created, updated, or change stages.
              </p>
              {webhookUrl && (
                <div className="fub-webhook-url-box">
                  <code className="fub-webhook-url">{webhookUrl}</code>
                  <button className="fub-btn fub-btn-sm fub-btn-outline" onClick={() => copyToClipboard(webhookUrl)}>
                    Copy
                  </button>
                </div>
              )}
              <div className="fub-help-steps">
                <h4>Setup Steps:</h4>
                <ol>
                  <li>Go to Follow Up Boss &rarr; Admin &rarr; API</li>
                  <li>Under Webhooks, click "Add Webhook"</li>
                  <li>Paste the URL above</li>
                  <li>Select events: People Created, People Updated, People Stage Updated</li>
                  <li>Save the webhook</li>
                </ol>
              </div>
            </div>
          </div>

          {/* Sync Settings */}
          <div className="fub-card">
            <div className="fub-card-header">
              <span className="fub-card-icon">{'\u2699\uFE0F'}</span>
              Sync Settings
            </div>
            <div className="fub-card-body">
              <div className="fub-settings-list">
                {[
                  { key: 'sync_enabled', label: 'Enable Auto Sync', desc: 'Automatically sync changes between FUB and CRM' },
                  { key: 'sync_notes', label: 'Sync Notes', desc: 'Sync notes and activities between platforms' },
                  { key: 'sync_stages', label: 'Sync Stage Changes', desc: 'Keep lead stages in sync using your stage mappings' },
                  { key: 'sync_lead_updates', label: 'Sync Lead Updates', desc: 'Sync contact info changes (name, email, phone)' },
                ].map(({ key, label, desc }) => (
                  <div key={key} className="fub-setting-row">
                    <div className="fub-setting-info">
                      <div className="fub-setting-label">{label}</div>
                      <div className="fub-setting-desc">{desc}</div>
                    </div>
                    <label className="fub-toggle">
                      <input
                        type="checkbox"
                        checked={settings[key]}
                        onChange={(e) => handleUpdateSettings(key, e.target.checked)}
                      />
                      <span className="fub-toggle-slider" />
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Danger Zone */}
          <div className="fub-card fub-danger-zone">
            <div className="fub-card-header" style={{ background: '#fef2f2', color: '#dc2626' }}>
              <span className="fub-card-icon">{'\u26A0\uFE0F'}</span>
              Danger Zone
            </div>
            <div className="fub-card-body">
              <p style={{ color: '#64748b', marginBottom: '16px' }}>
                Disconnecting will stop all syncing. Existing lead data in your CRM will not be deleted.
              </p>
              <button className="fub-btn fub-btn-danger" onClick={handleDisconnect}>
                Disconnect Follow Up Boss
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  const renderStageMappings = () => {
    const mappingsToShow = editingMappings ? editedMappings : stageMappings;

    return (
      <div className="fub-section">
        <div className="fub-section-header">
          <div>
            <h1>Stage Mapping</h1>
            <p className="fub-description">Map Follow Up Boss stages to your CRM lead stages.</p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="fub-btn fub-btn-outline" onClick={handleRefreshStages}>
              Refresh from FUB
            </button>
            {!editingMappings ? (
              <button className="fub-btn fub-btn-primary" onClick={handleStartEditMappings}>
                Edit Mappings
              </button>
            ) : (
              <>
                <button className="fub-btn fub-btn-outline" onClick={() => setEditingMappings(false)}>
                  Cancel
                </button>
                <button className="fub-btn fub-btn-success" onClick={handleSaveMappings}>
                  Save Mappings
                </button>
              </>
            )}
          </div>
        </div>

        {mappingsToShow.length === 0 ? (
          <div className="fub-empty-state">
            <div className="fub-empty-icon">{'\u{1F504}'}</div>
            <h3>No Stage Mappings</h3>
            <p>Click "Refresh from FUB" to pull your Follow Up Boss stages and auto-map them to CRM stages.</p>
            <button className="fub-btn fub-btn-primary" onClick={handleRefreshStages}>
              Refresh Stages
            </button>
          </div>
        ) : (
          <div className="fub-card">
            <table className="fub-table">
              <thead>
                <tr>
                  <th>Follow Up Boss Stage</th>
                  <th>CRM Stage</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {mappingsToShow.map((mapping, index) => (
                  <tr key={mapping.fub_stage_name || index}>
                    <td>
                      <div className="fub-stage-name">{mapping.fub_stage_name}</div>
                      {mapping.fub_stage_id && (
                        <div className="fub-stage-id">ID: {mapping.fub_stage_id}</div>
                      )}
                    </td>
                    <td>
                      {editingMappings ? (
                        <select
                          className="fub-select"
                          value={mapping.crm_stage || ''}
                          onChange={(e) => handleStageChange(index, e.target.value)}
                        >
                          <option value="">-- Not Mapped --</option>
                          {CRM_STAGES.map(s => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={mapping.crm_stage ? 'fub-mapped' : 'fub-unmapped'}>
                          {mapping.crm_stage
                            ? CRM_STAGES.find(s => s.value === mapping.crm_stage)?.label || mapping.crm_stage
                            : 'Not Mapped'}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`fub-badge ${mapping.is_auto_mapped ? 'auto' : 'manual'}`}>
                        {mapping.is_auto_mapped ? 'Auto' : 'Manual'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  const renderSync = () => (
    <div className="fub-section">
      <h1>Data Sync</h1>
      <p className="fub-description">Manually sync leads from Follow Up Boss to your CRM.</p>

      <div className="fub-sync-grid">
        <div className="fub-sync-card highlight">
          <h4>Pull Leads from FUB</h4>
          <p>Import all contacts from Follow Up Boss into your CRM as leads.</p>
          <button
            className="fub-btn fub-btn-primary"
            onClick={handleTriggerSync}
            disabled={syncing}
          >
            {syncing ? 'Syncing...' : 'Sync Now'}
          </button>
          {syncResult && (
            <div className="fub-sync-results">
              <div className="fub-sync-result-item success">
                <strong>{syncResult.created || 0}</strong> leads created
              </div>
              <div className="fub-sync-result-item info">
                <strong>{syncResult.updated || 0}</strong> leads updated
              </div>
              {syncResult.errors > 0 && (
                <div className="fub-sync-result-item error">
                  <strong>{syncResult.errors}</strong> errors
                </div>
              )}
            </div>
          )}
        </div>

        <div className="fub-sync-card">
          <h4>Real-Time Webhooks</h4>
          <p>When configured, FUB sends real-time updates for new leads, stage changes, and updates.</p>
          <div style={{ fontSize: '13px', color: '#64748b' }}>
            Status: {webhookUrl ? (
              <span style={{ color: '#0d9f6e', fontWeight: 500 }}>Webhook URL configured</span>
            ) : (
              <span style={{ color: '#dc2626' }}>Not configured</span>
            )}
          </div>
        </div>

        <div className="fub-sync-card">
          <h4>Bidirectional Sync</h4>
          <p>Changes made in your CRM can sync back to Follow Up Boss automatically.</p>
          <div style={{ fontSize: '13px', color: '#64748b' }}>
            Status: {settings.sync_enabled ? (
              <span style={{ color: '#0d9f6e', fontWeight: 500 }}>Enabled</span>
            ) : (
              <span style={{ color: '#f59e0b' }}>Disabled</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const renderLeadMappings = () => (
    <div className="fub-section">
      <div className="fub-section-header">
        <div>
          <h1>Synced Leads</h1>
          <p className="fub-description">
            {leadMappingsTotal} leads synced between Follow Up Boss and your CRM.
          </p>
        </div>
      </div>

      {leadMappings.length === 0 ? (
        <div className="fub-empty-state">
          <div className="fub-empty-icon">{'\u{1F465}'}</div>
          <h3>No Synced Leads Yet</h3>
          <p>Run a sync to import leads from Follow Up Boss.</p>
          <button className="fub-btn fub-btn-primary" onClick={() => setActiveSection('sync')}>
            Go to Data Sync
          </button>
        </div>
      ) : (
        <>
          <div className="fub-card">
            <table className="fub-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>FUB Stage</th>
                  <th>CRM Stage</th>
                  <th>Last Synced</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {leadMappings.map(mapping => (
                  <tr key={mapping.id}>
                    <td style={{ fontWeight: 500 }}>
                      {mapping.fub_person_name || `FUB #${mapping.fub_person_id}`}
                    </td>
                    <td style={{ color: '#64748b' }}>{mapping.fub_person_email || 'N/A'}</td>
                    <td>
                      <span className="fub-badge auto">{mapping.fub_stage || 'N/A'}</span>
                    </td>
                    <td>
                      <span className="fub-badge manual">{mapping.crm_stage || 'N/A'}</span>
                    </td>
                    <td style={{ color: '#64748b', fontSize: '13px' }}>
                      {mapping.last_synced_at
                        ? new Date(mapping.last_synced_at).toLocaleString()
                        : 'Never'}
                    </td>
                    <td>
                      <button
                        className="fub-btn fub-btn-sm fub-btn-outline"
                        onClick={() => handleDeleteLeadMapping(mapping.id)}
                        title="Remove mapping"
                      >
                        &times;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {leadMappingsTotal > 50 && (
            <div className="fub-pagination">
              <button
                className="fub-btn fub-btn-sm fub-btn-outline"
                disabled={leadMappingsPage === 0}
                onClick={() => loadLeadMappings(leadMappingsPage - 50)}
              >
                Previous
              </button>
              <span className="fub-pagination-info">
                Showing {leadMappingsPage + 1}-{Math.min(leadMappingsPage + 50, leadMappingsTotal)} of {leadMappingsTotal}
              </span>
              <button
                className="fub-btn fub-btn-sm fub-btn-outline"
                disabled={leadMappingsPage + 50 >= leadMappingsTotal}
                onClick={() => loadLeadMappings(leadMappingsPage + 50)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );

  const renderHistory = () => (
    <div className="fub-section">
      <div className="fub-section-header">
        <div>
          <h1>Sync History</h1>
          <p className="fub-description">Recent sync events and their status.</p>
        </div>
        <button className="fub-btn fub-btn-outline" onClick={loadSyncHistory}>
          Refresh
        </button>
      </div>

      {syncHistory.length === 0 ? (
        <div className="fub-empty-state">
          <div className="fub-empty-icon">{'\u{1F4DC}'}</div>
          <h3>No Sync History</h3>
          <p>Sync events will appear here after your first sync.</p>
        </div>
      ) : (
        <div className="fub-card">
          <table className="fub-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Direction</th>
                <th>Status</th>
                <th>Details</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {syncHistory.map(event => (
                <tr key={event.id}>
                  <td>
                    <span className="fub-event-type">{event.event_type?.replace(/_/g, ' ')}</span>
                  </td>
                  <td>
                    <span className={`fub-badge ${event.direction === 'inbound' ? 'auto' : 'manual'}`}>
                      {event.direction === 'inbound' ? 'FUB \u2192 CRM' : 'CRM \u2192 FUB'}
                    </span>
                  </td>
                  <td>
                    <span className={`fub-status-badge ${event.status}`}>
                      {event.status}
                    </span>
                  </td>
                  <td style={{ color: '#64748b', fontSize: '13px', maxWidth: '300px' }}>
                    {event.error_message || (event.fub_person_name ? `Lead: ${event.fub_person_name}` : '-')}
                  </td>
                  <td style={{ color: '#64748b', fontSize: '13px', whiteSpace: 'nowrap' }}>
                    {event.created_at ? new Date(event.created_at).toLocaleString() : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const renderContent = () => {
    switch (activeSection) {
      case 'overview': return renderOverview();
      case 'connection': return renderConnection();
      case 'stages': return renderStageMappings();
      case 'sync': return renderSync();
      case 'leads': return renderLeadMappings();
      case 'history': return renderHistory();
      default: return renderOverview();
    }
  };

  if (loading) {
    return (
      <div className="fub-page">
        <div className="fub-loading">
          <div className="fub-spinner" />
          <p>Loading Follow Up Boss integration...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fub-page">
      {renderSidebar()}
      <div className="fub-main">
        {renderContent()}
      </div>
    </div>
  );
}

export default FollowUpBossIntegrationPage;
