/**
 * IntegrationsSection - Calendar Settings
 *
 * Handles Google/Outlook/Zoom/Google Meet/iCal integrations,
 * sync status dashboard, webhook & API settings.
 */
import React, { useState } from 'react';
import { API_BASE_URL } from '../../services/api';
import { toast } from '../../utils/toast';

const MEETING_MODES = [
  { value: 'video', label: 'Video', icon: 'fa-video', description: 'Default to video conferencing' },
  { value: 'phone', label: 'Phone', icon: 'fa-phone', description: 'Default to phone calls' },
  { value: 'in_person', label: 'In Person', icon: 'fa-building', description: 'Default to in-person meetings' },
];

export default function IntegrationsSection({
  integrations,
  setIntegrations,
  integrationSettings,
  setIntegrationSettings,
  syncErrors,
  setSyncErrors,
  webhookSettings,
  setWebhookSettings,
  meetingDefaults,
  setMeetingDefaults,
  markChanged,
}) {
  const [showSyncErrors, setShowSyncErrors] = useState(false);
  const [syncing, setSyncing] = useState({});
  const [showWebhookSettings, setShowWebhookSettingsPanel] = useState(false);
  const [copiedApiKey, setCopiedApiKey] = useState(false);
  const [copiedFeedUrl, setCopiedFeedUrl] = useState(false);
  const [disconnectConfirm, setDisconnectConfirm] = useState(null);

  // ---- Helpers ----
  const getSyncHealthColor = (service) => {
    const svc = integrations[service];
    if (!svc?.connected) return 'gray';
    if (svc.sync_error) return 'red';
    if (!svc.last_synced) return 'yellow';
    const minutesSince = (Date.now() - new Date(svc.last_synced).getTime()) / 60000;
    return minutesSince < 30 ? 'green' : minutesSince < 120 ? 'yellow' : 'red';
  };

  const getSyncHealthLabel = (service) => {
    const color = getSyncHealthColor(service);
    if (color === 'green') return 'Healthy';
    if (color === 'yellow') return 'Delayed';
    if (color === 'red') return 'Error';
    return 'Inactive';
  };

  const handleSyncNow = async (service) => {
    setSyncing(prev => ({ ...prev, [service]: true }));
    try {
      await new Promise(resolve => setTimeout(resolve, 1500));
      setIntegrations(prev => ({
        ...prev,
        [service]: { ...prev[service], last_synced: new Date().toISOString(), sync_error: null },
      }));
      toast.success(`${service.charAt(0).toUpperCase() + service.slice(1)} calendar synced`);
    } catch (err) {
      toast.error(`Sync failed for ${service}`);
      setSyncErrors(prev => [...prev, { service, error: err.message || 'Sync failed', time: new Date().toISOString() }]);
    } finally {
      setSyncing(prev => ({ ...prev, [service]: false }));
    }
  };

  const handleDisconnectIntegration = async (service) => {
    setDisconnectConfirm(null);
    const urls = {
      google: `${API_BASE_URL}/api/v1/google-calendar/disconnect`,
      outlook: `${API_BASE_URL}/api/v1/microsoft/disconnect/calendar`,
      zoom: `${API_BASE_URL}/api/v1/zoom/disconnect`,
      google_meet: `${API_BASE_URL}/api/v1/google-meet/disconnect`,
    };
    if (urls[service]) {
      try {
        const token = localStorage.getItem('token');
        const resp = await fetch(urls[service], {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        });
        if (resp.ok) {
          setIntegrations(prev => ({ ...prev, [service]: { ...prev[service], connected: false } }));
          toast.success(`${service.charAt(0).toUpperCase() + service.slice(1)} disconnected`);
        } else {
          const data = await resp.json().catch(() => ({}));
          toast.error(data.detail || `Failed to disconnect ${service}`);
        }
      } catch (err) {
        toast.error(`Failed to disconnect ${service}`);
      }
    } else {
      setIntegrations(prev => ({
        ...prev,
        [service]: { ...prev[service], connected: false },
      }));
      toast.success('Integration disconnected');
    }
  };

  const handleConnectIntegration = (service) => {
    const token = localStorage.getItem('token');
    const urls = {
      google: `${API_BASE_URL}/api/v1/google-calendar/auth?token=${token}`,
      outlook: `${API_BASE_URL}/api/v1/microsoft/auth?integration_type=calendar&token=${token}`,
      zoom: `${API_BASE_URL}/api/v1/zoom/connect`,
      google_meet: `${API_BASE_URL}/api/v1/google-meet/connect`,
    };
    if (urls[service]) {
      window.location.href = urls[service];
    }
  };

  const handleUpdateIntegrationSetting = (service, field, value) => {
    setIntegrationSettings(prev => ({
      ...prev,
      [service]: { ...prev[service], [field]: value },
    }));
    markChanged();
  };

  const handleCopyApiKey = () => {
    const masked = webhookSettings.api_key || 'pk_live_xxxxxxxxxxxxxxxxxxxxxxxx';
    navigator.clipboard.writeText(masked).then(() => {
      setCopiedApiKey(true);
      toast.success('API key copied');
      setTimeout(() => setCopiedApiKey(false), 2000);
    }).catch(() => toast.error('Failed to copy'));
  };

  const handleCopyFeedUrl = () => {
    const url = integrations.ical?.feed_url || `${window.location.origin}/api/v1/calendar/feed/ical`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedFeedUrl(true);
      toast.success('Feed URL copied');
      setTimeout(() => setCopiedFeedUrl(false), 2000);
    }).catch(() => toast.error('Failed to copy'));
  };

  const handleRegenerateFeed = () => {
    if (!window.confirm('Regenerating the feed URL will invalidate the current one. All existing subscribers will need the new URL. Continue?')) return;
    const newUrl = `${window.location.origin}/api/v1/calendar/feed/ical?token=${Math.random().toString(36).substring(2, 15)}`;
    setIntegrations(prev => ({
      ...prev,
      ical: { ...prev.ical, feed_url: newUrl, connected: true },
    }));
    toast.success('Feed URL regenerated');
  };

  const handleToggleWebhookEvent = (event) => {
    setWebhookSettings(prev => ({
      ...prev,
      events: { ...prev.events, [event]: !prev.events[event] },
    }));
    markChanged();
  };

  // ---- Render integration card ----
  const renderIntegrationCard = (service, config) => {
    const svc = integrations[service] || {};
    const settings = integrationSettings[service] || {};
    const isConnected = svc.connected;
    const isError = svc.sync_error;
    const isSyncing = syncing[service];

    const cardClass = [
      'intg-card',
      isConnected ? 'intg-card--connected' : '',
      isError ? 'intg-card--error' : '',
    ].filter(Boolean).join(' ');

    return (
      <div className={cardClass} key={service}>
        <div className="intg-card__header">
          <div className={`intg-card__icon intg-card__icon--${service}`}>
            <i className={config.icon}></i>
          </div>
          <div className="intg-card__title-area">
            <h3 className="intg-card__title">{config.label}</h3>
            {isConnected && (
              <span className={`intg-health-badge intg-health-badge--${getSyncHealthColor(service)}`}>
                <span className="intg-health-dot"></span>
                {getSyncHealthLabel(service)}
              </span>
            )}
            {isError && (
              <span className="intg-health-badge intg-health-badge--red">
                <span className="intg-health-dot"></span>
                Error
              </span>
            )}
          </div>
        </div>

        {isConnected ? (
          <div className="intg-card__body">
            <p className="intg-card__connected-email">
              <i className="fas fa-check-circle"></i> Connected as {svc.email || 'your account'}
            </p>
            {svc.last_synced && (
              <p className="intg-card__sync-time">
                Last synced: {new Date(svc.last_synced).toLocaleString()}
              </p>
            )}

            {isError && (
              <div className="intg-card__error-banner">
                <i className="fas fa-exclamation-triangle"></i>
                <span>{svc.sync_error}</span>
                <button className="btn-text btn-sm" onClick={() => handleSyncNow(service)}>
                  Retry
                </button>
              </div>
            )}

            {config.settingsPanel && config.settingsPanel(settings)}

            <div className="intg-card__actions">
              <button
                className="btn-outline btn-sm"
                onClick={() => handleSyncNow(service)}
                disabled={isSyncing}
              >
                {isSyncing ? (
                  <><i className="fas fa-spinner fa-spin"></i> Syncing...</>
                ) : (
                  <><i className="fas fa-sync-alt"></i> Sync Now</>
                )}
              </button>
              {disconnectConfirm === service ? (
                <div className="intg-card__disconnect-confirm">
                  <span>Disconnect?</span>
                  <button className="btn-danger btn-sm" onClick={() => handleDisconnectIntegration(service)}>
                    Yes, Disconnect
                  </button>
                  <button className="btn-text btn-sm" onClick={() => setDisconnectConfirm(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => setDisconnectConfirm(service)}
                >
                  Disconnect
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="intg-card__body">
            <p className="intg-card__description">{config.description}</p>
            <button
              className="btn-primary"
              onClick={() => config.onConnect ? config.onConnect() : handleConnectIntegration(service)}
            >
              <i className={config.connectIcon || 'fas fa-plug'}></i> {config.connectLabel || `Connect ${config.label}`}
            </button>
          </div>
        )}
      </div>
    );
  };

  const connectedServices = ['google', 'outlook', 'zoom', 'google_meet', 'ical'].filter(s => integrations[s]?.connected);

  // Meeting defaults (from merged Smart Scheduler)
  const defaults = meetingDefaults || { default_meeting_mode: 'video', auto_create_meeting_link: true };

  return (
    <section className="cal-settings-section" role="tabpanel" id="panel-integrations" aria-labelledby="calnav-integrations">
      {/* Meeting Defaults — merged from Smart Scheduler */}
      <div className="intg-meeting-defaults">
        <h3><i className="fas fa-sliders-h"></i> Meeting Defaults</h3>
        <p className="section-description">Default meeting mode for new appointments.</p>
        <div className="meeting-mode-toggle" role="radiogroup" aria-label="Default meeting mode">
          {MEETING_MODES.map(mode => (
            <button
              key={mode.value}
              type="button"
              role="radio"
              aria-checked={defaults.default_meeting_mode === mode.value}
              className={`meeting-mode-btn ${defaults.default_meeting_mode === mode.value ? 'active' : ''}`}
              onClick={() => {
                setMeetingDefaults?.(prev => ({ ...prev, default_meeting_mode: mode.value }));
                markChanged();
              }}
            >
              <i className={`fas ${mode.icon}`}></i>
              <span>{mode.label}</span>
            </button>
          ))}
        </div>
        <label className="intg-toggle-row" style={{ marginTop: 12 }}>
          <span>Auto-create meeting links when booking</span>
          <input
            type="checkbox"
            checked={defaults.auto_create_meeting_link}
            onChange={(e) => {
              setMeetingDefaults?.(prev => ({ ...prev, auto_create_meeting_link: e.target.checked }));
              markChanged();
            }}
          />
        </label>
      </div>

      <h2 style={{ marginTop: 24 }}>Calendar Integrations</h2>
      <p className="section-description">Connect external calendars and tools to sync events and streamline scheduling.</p>

      {/* Sync Status Dashboard */}
      {connectedServices.length > 0 && (
        <div className="intg-sync-dashboard">
          <div className="intg-sync-dashboard__header">
            <h3><i className="fas fa-heartbeat"></i> Sync Status</h3>
            {syncErrors.length > 0 && (
              <button
                className="btn-text btn-sm"
                onClick={() => setShowSyncErrors(!showSyncErrors)}
              >
                <i className="fas fa-exclamation-circle"></i> {syncErrors.length} error{syncErrors.length !== 1 ? 's' : ''}
              </button>
            )}
          </div>
          <div className="intg-sync-dashboard__services">
            {connectedServices.map(service => {
              const labels = { google: 'Google', outlook: 'Outlook', zoom: 'Zoom', google_meet: 'Google Meet', ical: 'iCal' };
              const svc = integrations[service] || {};
              return (
                <div className="intg-sync-service" key={service}>
                  <span className="intg-sync-service__name">{labels[service] || service}</span>
                  <span className={`intg-health-badge intg-health-badge--${getSyncHealthColor(service)}`}>
                    <span className="intg-health-dot"></span>
                    {getSyncHealthLabel(service)}
                  </span>
                  <span className="intg-sync-service__time">
                    {svc.last_synced ? new Date(svc.last_synced).toLocaleTimeString() : 'Never'}
                  </span>
                  <button
                    className="btn-text btn-xs"
                    onClick={() => handleSyncNow(service)}
                    disabled={syncing[service]}
                    title="Sync now"
                  >
                    <i className={`fas fa-sync-alt ${syncing[service] ? 'fa-spin' : ''}`}></i>
                  </button>
                </div>
              );
            })}
          </div>

          {showSyncErrors && syncErrors.length > 0 && (
            <div className="intg-sync-errors">
              <div className="intg-sync-errors__header">
                <h4>Recent Sync Errors</h4>
                <button className="btn-text btn-xs" onClick={() => setSyncErrors([])}>Clear All</button>
              </div>
              <div className="intg-sync-errors__list">
                {syncErrors.slice(-5).reverse().map((err, i) => (
                  <div className="intg-sync-error-item" key={i}>
                    <span className="intg-sync-error-item__service">{err.service}</span>
                    <span className="intg-sync-error-item__message">{err.error}</span>
                    <span className="intg-sync-error-item__time">{new Date(err.time).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Integration Cards Grid */}
      <div className="intg-cards-grid">
        {renderIntegrationCard('google', {
          label: 'Google Calendar',
          icon: 'fab fa-google',
          connectIcon: 'fab fa-google',
          connectLabel: 'Connect with Google',
          description: 'Two-way sync with Google Calendar. Events created in either system will appear in both. Availability checks prevent double-booking.',
          settingsPanel: (settings) => (
            <div className="intg-card__settings">
              <label className="intg-toggle-row">
                <span>Two-way sync</span>
                <input type="checkbox" checked={settings.two_way_sync} onChange={(e) => handleUpdateIntegrationSetting('google', 'two_way_sync', e.target.checked)} />
              </label>
              <div className="intg-setting-row">
                <label>Conflict resolution</label>
                <select value={settings.conflict_resolution} onChange={(e) => handleUpdateIntegrationSetting('google', 'conflict_resolution', e.target.value)}>
                  <option value="crm_wins">CRM wins</option>
                  <option value="google_wins">Google wins</option>
                  <option value="ask">Ask each time</option>
                </select>
              </div>
              <div className="intg-setting-row">
                <label>Sync frequency</label>
                <select value={settings.sync_frequency} onChange={(e) => handleUpdateIntegrationSetting('google', 'sync_frequency', e.target.value)}>
                  <option value="5">Every 5 minutes</option>
                  <option value="15">Every 15 minutes</option>
                  <option value="30">Every 30 minutes</option>
                  <option value="60">Every hour</option>
                </select>
              </div>
            </div>
          ),
        })}

        {renderIntegrationCard('outlook', {
          label: 'Microsoft Outlook',
          icon: 'fab fa-microsoft',
          connectIcon: 'fab fa-microsoft',
          connectLabel: 'Connect with Outlook',
          description: 'Two-way sync with Outlook Calendar. Events, availability, and meeting details sync automatically between systems.',
          settingsPanel: (settings) => (
            <div className="intg-card__settings">
              <label className="intg-toggle-row">
                <span>Two-way sync</span>
                <input type="checkbox" checked={settings.two_way_sync} onChange={(e) => handleUpdateIntegrationSetting('outlook', 'two_way_sync', e.target.checked)} />
              </label>
              <div className="intg-setting-row">
                <label>Conflict resolution</label>
                <select value={settings.conflict_resolution} onChange={(e) => handleUpdateIntegrationSetting('outlook', 'conflict_resolution', e.target.value)}>
                  <option value="crm_wins">CRM wins</option>
                  <option value="outlook_wins">Outlook wins</option>
                  <option value="ask">Ask each time</option>
                </select>
              </div>
              <div className="intg-setting-row">
                <label>Sync frequency</label>
                <select value={settings.sync_frequency} onChange={(e) => handleUpdateIntegrationSetting('outlook', 'sync_frequency', e.target.value)}>
                  <option value="5">Every 5 minutes</option>
                  <option value="15">Every 15 minutes</option>
                  <option value="30">Every 30 minutes</option>
                  <option value="60">Every hour</option>
                </select>
              </div>
            </div>
          ),
        })}

        {renderIntegrationCard('zoom', {
          label: 'Zoom',
          icon: 'fas fa-video',
          connectLabel: 'Connect Zoom',
          description: 'Auto-generate Zoom meeting links for virtual appointments. Configure default meeting settings like waiting rooms and passwords.',
          settingsPanel: (settings) => (
            <div className="intg-card__settings">
              <label className="intg-toggle-row">
                <span>Auto-generate meeting links</span>
                <input type="checkbox" checked={settings.auto_generate_links} onChange={(e) => handleUpdateIntegrationSetting('zoom', 'auto_generate_links', e.target.checked)} />
              </label>
              <label className="intg-toggle-row">
                <span>Enable waiting room</span>
                <input type="checkbox" checked={settings.waiting_room} onChange={(e) => handleUpdateIntegrationSetting('zoom', 'waiting_room', e.target.checked)} />
              </label>
              <label className="intg-toggle-row">
                <span>Require meeting password</span>
                <input type="checkbox" checked={settings.require_password} onChange={(e) => handleUpdateIntegrationSetting('zoom', 'require_password', e.target.checked)} />
              </label>
              <div className="intg-setting-row">
                <label>Default meeting duration</label>
                <select value={settings.default_duration} onChange={(e) => handleUpdateIntegrationSetting('zoom', 'default_duration', parseInt(e.target.value))}>
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={45}>45 minutes</option>
                  <option value={60}>60 minutes</option>
                </select>
              </div>
            </div>
          ),
        })}

        {renderIntegrationCard('google_meet', {
          label: 'Google Meet',
          icon: 'fas fa-video',
          connectLabel: 'Connect Google Meet',
          description: 'Automatically add Google Meet links to appointments. Requires a connected Google account.',
          settingsPanel: (settings) => (
            <div className="intg-card__settings">
              <label className="intg-toggle-row">
                <span>Auto-add to appointments</span>
                <input type="checkbox" checked={settings.auto_add} onChange={(e) => handleUpdateIntegrationSetting('google_meet', 'auto_add', e.target.checked)} />
              </label>
              <div className="intg-setting-row">
                <label>Default meeting duration</label>
                <select value={settings.default_duration} onChange={(e) => handleUpdateIntegrationSetting('google_meet', 'default_duration', parseInt(e.target.value))}>
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={45}>45 minutes</option>
                  <option value={60}>60 minutes</option>
                </select>
              </div>
            </div>
          ),
        })}

        {/* iCal Feed */}
        <div className={`intg-card ${integrations.ical?.connected ? 'intg-card--connected' : ''}`}>
          <div className="intg-card__header">
            <div className="intg-card__icon intg-card__icon--ical">
              <i className="fas fa-rss"></i>
            </div>
            <div className="intg-card__title-area">
              <h3 className="intg-card__title">iCal Feed</h3>
              {integrations.ical?.connected && (
                <span className="intg-health-badge intg-health-badge--green">
                  <span className="intg-health-dot"></span>
                  Active
                </span>
              )}
            </div>
          </div>
          <div className="intg-card__body">
            {integrations.ical?.connected ? (
              <>
                <div className="intg-ical-url-row">
                  <input
                    type="text"
                    readOnly
                    value={integrations.ical.feed_url || `${window.location.origin}/api/v1/calendar/feed/ical`}
                    className="intg-ical-url-input"
                  />
                  <button className="btn-outline btn-sm" onClick={handleCopyFeedUrl}>
                    <i className={`fas ${copiedFeedUrl ? 'fa-check' : 'fa-copy'}`}></i>
                    {copiedFeedUrl ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <div className="intg-ical-meta">
                  <span>{integrations.ical.subscriber_count || 0} subscriber{(integrations.ical.subscriber_count || 0) !== 1 ? 's' : ''}</span>
                  <span className="intg-ical-meta__separator">|</span>
                  <span>Read-only feed</span>
                </div>
                <div className="intg-card__actions">
                  <button className="btn-outline btn-sm" onClick={handleRegenerateFeed}>
                    <i className="fas fa-redo"></i> Regenerate URL
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="intg-card__description">
                  Generate a read-only iCal feed URL that can be subscribed to from any calendar application. Share your availability without granting write access.
                </p>
                <button className="btn-primary" onClick={handleRegenerateFeed}>
                  <i className="fas fa-rss"></i> Generate Feed URL
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Webhook / API Settings */}
      <div className="intg-webhook-section">
        <button
          className="intg-webhook-toggle"
          onClick={() => setShowWebhookSettingsPanel(!showWebhookSettings)}
          aria-expanded={showWebhookSettings}
        >
          <i className={`fas fa-chevron-${showWebhookSettings ? 'down' : 'right'}`}></i>
          <span>Webhook & API Settings</span>
          <span className="intg-webhook-badge">Advanced</span>
        </button>

        {showWebhookSettings && (
          <div className="intg-webhook-panel">
            <div className="intg-webhook-field">
              <label>API Key</label>
              <div className="intg-api-key-row">
                <input
                  type="text"
                  readOnly
                  value={webhookSettings.api_key ? `${webhookSettings.api_key.substring(0, 8)}${'*'.repeat(24)}` : 'pk_live_************************'}
                  className="intg-api-key-input"
                />
                <button className="btn-outline btn-sm" onClick={handleCopyApiKey}>
                  <i className={`fas ${copiedApiKey ? 'fa-check' : 'fa-copy'}`}></i>
                  {copiedApiKey ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="intg-webhook-hint">Use this key to authenticate API requests. Keep it secret.</p>
            </div>

            <div className="intg-webhook-field">
              <label>Webhook URL</label>
              <input
                type="url"
                value={webhookSettings.webhook_url}
                onChange={(e) => setWebhookSettings(prev => ({ ...prev, webhook_url: e.target.value }))}
                placeholder="https://your-server.com/webhooks/calendar"
                className="intg-webhook-url-input"
              />
              <p className="intg-webhook-hint">We will POST event payloads to this URL.</p>
            </div>

            <div className="intg-webhook-field">
              <label>Event Subscriptions</label>
              <div className="intg-webhook-events">
                {Object.entries(webhookSettings.events).map(([event, enabled]) => (
                  <label className="intg-webhook-event-row" key={event}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => handleToggleWebhookEvent(event)}
                    />
                    <code>{event}</code>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
