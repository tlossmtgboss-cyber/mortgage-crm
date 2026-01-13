/**
 * Follow Up Boss Integration Settings Component
 *
 * Allows users to:
 * - Connect/disconnect their FUB account with API key
 * - View connection status
 * - Manage stage mappings
 * - Trigger manual sync
 * - View sync history
 */

import React, { useState, useEffect, useCallback } from 'react';
import followupbossApi from '../../services/followupbossApi';
import './FollowUpBossSettings.css';

// CRM Stage options for mapping
const CRM_STAGES = [
  { value: 'NEW', label: 'New' },
  { value: 'ATTEMPTED_CONTACT', label: 'Attempted Contact' },
  { value: 'PROSPECT', label: 'Prospect' },
  { value: 'PRE_QUALIFIED', label: 'Pre-Qualified' },
  { value: 'APPLICATION', label: 'Application' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'UNDER_CONTRACT', label: 'Under Contract' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'LONG_TERM_NURTURE', label: 'Long Term Nurture' },
  { value: 'WITHDRAWN', label: 'Withdrawn' },
  { value: 'DOES_NOT_QUALIFY', label: 'Does Not Qualify' },
];

const FollowUpBossSettings = () => {
  // Connection state
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [connecting, setConnecting] = useState(false);

  // Settings state
  const [settings, setSettings] = useState({
    sync_enabled: true,
    sync_notes: true,
    sync_stages: true,
    sync_lead_updates: true,
  });

  // Stage mappings state
  const [stageMappings, setStageMappings] = useState([]);
  const [editingMappings, setEditingMappings] = useState(false);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncHistory, setSyncHistory] = useState([]);

  // Lead mappings state
  const [leadMappings, setLeadMappings] = useState([]);
  const [leadMappingsTotal, setLeadMappingsTotal] = useState(0);

  // UI state
  const [activeTab, setActiveTab] = useState('connection');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load connection status on mount
  useEffect(() => {
    loadConnectionStatus();
  }, []);

  const loadConnectionStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await followupbossApi.connection.getStatus();
      setConnectionStatus(status);

      if (status.connected) {
        setSettings({
          sync_enabled: status.sync_enabled,
          sync_notes: true,
          sync_stages: true,
          sync_lead_updates: true,
        });
        // Load additional data
        loadStageMappings();
        loadSyncHistory();
      }
    } catch (err) {
      console.error('Failed to load FUB status:', err);
      setConnectionStatus({ connected: false });
    } finally {
      setLoading(false);
    }
  };

  const loadStageMappings = async () => {
    try {
      const result = await followupbossApi.stageMapping.getMappings();
      setStageMappings(result.mappings || []);
    } catch (err) {
      console.error('Failed to load stage mappings:', err);
    }
  };

  const loadSyncHistory = async () => {
    try {
      const result = await followupbossApi.sync.getHistory(20);
      setSyncHistory(result.events || []);
    } catch (err) {
      console.error('Failed to load sync history:', err);
    }
  };

  const loadLeadMappings = async () => {
    try {
      const result = await followupbossApi.leadMapping.getMappings(50);
      setLeadMappings(result.mappings || []);
      setLeadMappingsTotal(result.total || 0);
    } catch (err) {
      console.error('Failed to load lead mappings:', err);
    }
  };

  const handleConnect = async () => {
    if (!apiKey.trim()) {
      setError('Please enter your Follow Up Boss API key');
      return;
    }

    setConnecting(true);
    setError(null);

    try {
      const result = await followupbossApi.connection.connect(apiKey.trim());
      setConnectionStatus({
        connected: true,
        fub_user_email: result.fub_user_email,
        fub_user_name: result.fub_user_name,
        webhook_url: result.webhook_url,
        sync_enabled: true,
      });
      setApiKey('');
      loadStageMappings();
    } catch (err) {
      setError(err.message || 'Failed to connect Follow Up Boss account');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Follow Up Boss? This will stop syncing data.')) {
      return;
    }

    try {
      await followupbossApi.connection.disconnect();
      setConnectionStatus({ connected: false });
      setStageMappings([]);
      setSyncHistory([]);
      setLeadMappings([]);
    } catch (err) {
      setError(err.message || 'Failed to disconnect');
    }
  };

  const handleUpdateSettings = async () => {
    try {
      await followupbossApi.settings.updateSettings(settings);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to update settings');
    }
  };

  const handleSaveMappings = async () => {
    try {
      await followupbossApi.stageMapping.updateMappings(stageMappings);
      setEditingMappings(false);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to save stage mappings');
    }
  };

  const handleRefreshStages = async () => {
    try {
      const result = await followupbossApi.stageMapping.refreshStages();
      if (result.new_stages_added > 0) {
        loadStageMappings();
      }
    } catch (err) {
      setError(err.message || 'Failed to refresh stages');
    }
  };

  const handleTriggerSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    setError(null);

    try {
      const result = await followupbossApi.sync.triggerSync(100);
      setSyncResult(result);
      loadSyncHistory();
    } catch (err) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const handleStageChange = (index, newCrmStage) => {
    const updated = [...stageMappings];
    updated[index] = {
      ...updated[index],
      crm_stage: newCrmStage,
      is_auto_mapped: false,
    };
    setStageMappings(updated);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    // Could add toast notification here
  };

  if (loading) {
    return (
      <div className="fub-settings">
        <div className="fub-loading">Loading Follow Up Boss settings...</div>
      </div>
    );
  }

  return (
    <div className="fub-settings">
      <div className="fub-header">
        <div className="fub-logo">
          <img
            src="https://www.google.com/s2/favicons?domain=followupboss.com&sz=64"
            alt="Follow Up Boss"
          />
        </div>
        <div className="fub-header-content">
          <h2>Follow Up Boss Integration</h2>
          <p>Sync leads bidirectionally between Follow Up Boss and your CRM</p>
        </div>
        {connectionStatus?.connected && (
          <div className="fub-connection-badge connected">
            Connected as {connectionStatus.fub_user_name || connectionStatus.fub_user_email}
          </div>
        )}
      </div>

      {error && (
        <div className="fub-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {!connectionStatus?.connected ? (
        /* Not Connected - Show connect form */
        <div className="fub-connect-section">
          <div className="fub-connect-card">
            <h3>Connect Your Follow Up Boss Account</h3>
            <p>
              Enter your Follow Up Boss API key to enable bidirectional sync.
              You can find your API key in FUB under Admin {'>'} API.
            </p>

            <div className="fub-form-group">
              <label htmlFor="fub-api-key">API Key</label>
              <input
                id="fub-api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your FUB API key"
                disabled={connecting}
              />
            </div>

            <button
              className="fub-btn fub-btn-primary"
              onClick={handleConnect}
              disabled={connecting || !apiKey.trim()}
            >
              {connecting ? 'Connecting...' : 'Connect Follow Up Boss'}
            </button>

            <div className="fub-help-text">
              <a
                href="https://help.followupboss.com/en/articles/2714440-how-to-find-your-api-key"
                target="_blank"
                rel="noopener noreferrer"
              >
                How to find your API key
              </a>
            </div>
          </div>
        </div>
      ) : (
        /* Connected - Show tabs */
        <>
          <div className="fub-tabs">
            <button
              className={`fub-tab ${activeTab === 'connection' ? 'active' : ''}`}
              onClick={() => setActiveTab('connection')}
            >
              Connection
            </button>
            <button
              className={`fub-tab ${activeTab === 'stages' ? 'active' : ''}`}
              onClick={() => setActiveTab('stages')}
            >
              Stage Mapping
            </button>
            <button
              className={`fub-tab ${activeTab === 'sync' ? 'active' : ''}`}
              onClick={() => setActiveTab('sync')}
            >
              Sync
            </button>
            <button
              className={`fub-tab ${activeTab === 'leads' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('leads');
                loadLeadMappings();
              }}
            >
              Synced Leads
            </button>
          </div>

          <div className="fub-tab-content">
            {/* Connection Tab */}
            {activeTab === 'connection' && (
              <div className="fub-connection-tab">
                <div className="fub-status-card">
                  <h3>Connection Status</h3>
                  <div className="fub-status-row">
                    <span className="fub-status-label">Status</span>
                    <span className="fub-status-value connected">Connected</span>
                  </div>
                  <div className="fub-status-row">
                    <span className="fub-status-label">Account</span>
                    <span className="fub-status-value">
                      {connectionStatus.fub_user_name || connectionStatus.fub_user_email}
                    </span>
                  </div>
                  {connectionStatus.last_sync_at && (
                    <div className="fub-status-row">
                      <span className="fub-status-label">Last Sync</span>
                      <span className="fub-status-value">
                        {new Date(connectionStatus.last_sync_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                  <div className="fub-status-row">
                    <span className="fub-status-label">Synced Leads</span>
                    <span className="fub-status-value">
                      {connectionStatus.total_synced_leads || 0}
                    </span>
                  </div>
                </div>

                <div className="fub-webhook-card">
                  <h3>Webhook Configuration</h3>
                  <p>Configure this webhook URL in Follow Up Boss to receive real-time updates:</p>
                  <div className="fub-webhook-url">
                    <code>{connectionStatus.webhook_url}</code>
                    <button
                      className="fub-btn fub-btn-sm"
                      onClick={() => copyToClipboard(connectionStatus.webhook_url)}
                    >
                      Copy
                    </button>
                  </div>
                  <div className="fub-webhook-instructions">
                    <h4>Setup Instructions:</h4>
                    <ol>
                      <li>Go to Follow Up Boss Admin Settings</li>
                      <li>Navigate to Integrations {'>'} Webhooks</li>
                      <li>Click "Add Webhook"</li>
                      <li>Paste the webhook URL above</li>
                      <li>Select events: people.created, people.updated, people.stage_changed, notes.created</li>
                      <li>Save the webhook</li>
                    </ol>
                  </div>
                </div>

                <div className="fub-settings-card">
                  <h3>Sync Settings</h3>
                  <div className="fub-toggle-group">
                    <label className="fub-toggle">
                      <input
                        type="checkbox"
                        checked={settings.sync_enabled}
                        onChange={(e) => setSettings({ ...settings, sync_enabled: e.target.checked })}
                      />
                      <span>Sync Enabled</span>
                    </label>
                    <label className="fub-toggle">
                      <input
                        type="checkbox"
                        checked={settings.sync_notes}
                        onChange={(e) => setSettings({ ...settings, sync_notes: e.target.checked })}
                      />
                      <span>Sync Notes</span>
                    </label>
                    <label className="fub-toggle">
                      <input
                        type="checkbox"
                        checked={settings.sync_stages}
                        onChange={(e) => setSettings({ ...settings, sync_stages: e.target.checked })}
                      />
                      <span>Sync Stage Changes</span>
                    </label>
                    <label className="fub-toggle">
                      <input
                        type="checkbox"
                        checked={settings.sync_lead_updates}
                        onChange={(e) => setSettings({ ...settings, sync_lead_updates: e.target.checked })}
                      />
                      <span>Sync Lead Updates</span>
                    </label>
                  </div>
                  <button className="fub-btn fub-btn-secondary" onClick={handleUpdateSettings}>
                    Save Settings
                  </button>
                </div>

                <div className="fub-danger-zone">
                  <h3>Danger Zone</h3>
                  <p>Disconnecting will stop all syncing between Follow Up Boss and your CRM.</p>
                  <button className="fub-btn fub-btn-danger" onClick={handleDisconnect}>
                    Disconnect Follow Up Boss
                  </button>
                </div>
              </div>
            )}

            {/* Stage Mapping Tab */}
            {activeTab === 'stages' && (
              <div className="fub-stages-tab">
                <div className="fub-stages-header">
                  <h3>Stage Mapping</h3>
                  <p>Map Follow Up Boss stages to your CRM stages</p>
                  <div className="fub-stages-actions">
                    <button className="fub-btn fub-btn-secondary" onClick={handleRefreshStages}>
                      Refresh from FUB
                    </button>
                    {editingMappings ? (
                      <>
                        <button className="fub-btn fub-btn-secondary" onClick={() => {
                          setEditingMappings(false);
                          loadStageMappings();
                        }}>
                          Cancel
                        </button>
                        <button className="fub-btn fub-btn-primary" onClick={handleSaveMappings}>
                          Save Mappings
                        </button>
                      </>
                    ) : (
                      <button className="fub-btn fub-btn-primary" onClick={() => setEditingMappings(true)}>
                        Edit Mappings
                      </button>
                    )}
                  </div>
                </div>

                <div className="fub-stages-table">
                  <div className="fub-stages-header-row">
                    <div className="fub-stages-col">FUB Stage</div>
                    <div className="fub-stages-col">CRM Stage</div>
                    <div className="fub-stages-col">Auto-Mapped</div>
                  </div>
                  {stageMappings.length === 0 ? (
                    <div className="fub-stages-empty">
                      No stage mappings found. Click "Refresh from FUB" to load stages.
                    </div>
                  ) : (
                    stageMappings.map((mapping, index) => (
                      <div key={index} className="fub-stages-row">
                        <div className="fub-stages-col">{mapping.fub_stage_name}</div>
                        <div className="fub-stages-col">
                          {editingMappings ? (
                            <select
                              value={mapping.crm_stage}
                              onChange={(e) => handleStageChange(index, e.target.value)}
                            >
                              {CRM_STAGES.map(stage => (
                                <option key={stage.value} value={stage.value}>
                                  {stage.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            CRM_STAGES.find(s => s.value === mapping.crm_stage)?.label || mapping.crm_stage
                          )}
                        </div>
                        <div className="fub-stages-col">
                          {mapping.is_auto_mapped ? (
                            <span className="fub-auto-badge">Auto</span>
                          ) : (
                            <span className="fub-manual-badge">Manual</span>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Sync Tab */}
            {activeTab === 'sync' && (
              <div className="fub-sync-tab">
                <div className="fub-sync-action">
                  <h3>Manual Sync</h3>
                  <p>Pull all leads assigned to you from Follow Up Boss</p>
                  <button
                    className="fub-btn fub-btn-primary"
                    onClick={handleTriggerSync}
                    disabled={syncing}
                  >
                    {syncing ? 'Syncing...' : 'Sync Now'}
                  </button>

                  {syncResult && (
                    <div className="fub-sync-result">
                      <span className="fub-sync-result-item success">
                        {syncResult.leads_created} created
                      </span>
                      <span className="fub-sync-result-item info">
                        {syncResult.leads_updated} updated
                      </span>
                      {syncResult.errors > 0 && (
                        <span className="fub-sync-result-item error">
                          {syncResult.errors} errors
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="fub-sync-history">
                  <h3>Sync History</h3>
                  {syncHistory.length === 0 ? (
                    <div className="fub-sync-empty">No sync events yet</div>
                  ) : (
                    <div className="fub-sync-list">
                      {syncHistory.map(event => (
                        <div key={event.id} className={`fub-sync-item ${event.status}`}>
                          <div className="fub-sync-item-main">
                            <span className="fub-sync-type">{event.event_type}</span>
                            <span className={`fub-sync-status ${event.status}`}>
                              {event.status}
                            </span>
                          </div>
                          <div className="fub-sync-item-details">
                            <span className="fub-sync-direction">{event.direction}</span>
                            <span className="fub-sync-time">
                              {new Date(event.created_at).toLocaleString()}
                            </span>
                          </div>
                          {event.error_message && (
                            <div className="fub-sync-error">{event.error_message}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Synced Leads Tab */}
            {activeTab === 'leads' && (
              <div className="fub-leads-tab">
                <div className="fub-leads-header">
                  <h3>Synced Leads ({leadMappingsTotal})</h3>
                  <p>Leads linked between Follow Up Boss and your CRM</p>
                </div>

                {leadMappings.length === 0 ? (
                  <div className="fub-leads-empty">
                    No leads synced yet. Trigger a sync to import leads from Follow Up Boss.
                  </div>
                ) : (
                  <div className="fub-leads-table">
                    <div className="fub-leads-header-row">
                      <div className="fub-leads-col">Lead Name</div>
                      <div className="fub-leads-col">Email</div>
                      <div className="fub-leads-col">FUB Stage</div>
                      <div className="fub-leads-col">CRM Stage</div>
                      <div className="fub-leads-col">Last Synced</div>
                    </div>
                    {leadMappings.map(mapping => (
                      <div key={mapping.id} className="fub-leads-row">
                        <div className="fub-leads-col">{mapping.lead_name}</div>
                        <div className="fub-leads-col">{mapping.lead_email}</div>
                        <div className="fub-leads-col">{mapping.fub_stage || '-'}</div>
                        <div className="fub-leads-col">{mapping.crm_stage || '-'}</div>
                        <div className="fub-leads-col">
                          {mapping.last_synced_at
                            ? new Date(mapping.last_synced_at).toLocaleDateString()
                            : '-'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default FollowUpBossSettings;
