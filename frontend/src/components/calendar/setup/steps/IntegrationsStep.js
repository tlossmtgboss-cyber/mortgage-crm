/**
 * IntegrationsStep - Step 6 of Smart Calendar guided setup
 *
 * Connect external calendars, video conferencing, CRM sync, and calendar feeds.
 * Four integration groups:
 *   1. Calendar Sync (Google Calendar, Microsoft Outlook)
 *   2. Video Conferencing (Zoom, Google Meet, Manual/Other)
 *   3. CRM Sync (Perennia CRM -- always connected)
 *   4. External Calendar Feeds (iCal export/import)
 *
 * Saves to: PUT /api/v1/scheduler/settings/integrations
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { calendarSettingsAPI, API_BASE_URL } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './IntegrationsStep.css';
import { getToken } from '../../../../utils/tokenStore';

// ============================================================================
// Constants
// ============================================================================

const CALENDAR_SYNC_ITEMS = [
  {
    key: 'google_calendar',
    name: 'Google Calendar',
    description: 'Sync events with your Google Calendar to avoid double-bookings.',
    icon: 'fa-google',
    iconFamily: 'fab',
    recommended: true,
    syncItems: ['Calendar events', 'Availability / free-busy', 'All-day events'],
  },
  {
    key: 'microsoft_outlook',
    name: 'Microsoft Outlook',
    description: 'Sync events with your Outlook calendar for unified scheduling.',
    icon: 'fa-microsoft',
    iconFamily: 'fab',
    recommended: false,
    syncItems: ['Calendar events', 'Availability / free-busy', 'All-day events'],
  },
];

const VIDEO_CONFERENCING_ITEMS = [
  {
    key: 'zoom',
    name: 'Zoom',
    description: 'Auto-generate Zoom meeting links for video appointments.',
    icon: 'fa-video',
    iconFamily: 'fas',
    recommended: true,
  },
  {
    key: 'google_meet',
    name: 'Google Meet',
    description: 'Auto-add Google Meet links to new appointments.',
    icon: 'fa-video',
    iconFamily: 'fas',
    recommended: false,
  },
  {
    key: 'manual_link',
    name: 'Manual / Other',
    description: 'Provide a custom meeting link or use a physical location.',
    icon: 'fa-link',
    iconFamily: 'fas',
    recommended: false,
    isManual: true,
  },
];

const CRM_TOGGLES = [
  { key: 'auto_create_activity', label: 'Auto-create activity on appointment', defaultOn: true },
  { key: 'link_to_leads_loans', label: 'Link appointments to leads / loans', defaultOn: true },
  { key: 'show_client_info', label: 'Show client info on calendar events', defaultOn: true },
  { key: 'sync_outcomes_pipeline', label: 'Sync appointment outcomes to pipeline', defaultOn: false },
];

const STATUS_MAP = {
  connected: { label: 'Connected', className: 'integrations-step__status--connected' },
  disconnected: { label: 'Disconnected', className: 'integrations-step__status--disconnected' },
  syncing: { label: 'Syncing...', className: 'integrations-step__status--syncing' },
};

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Status badge for integration connection state.
 */
const StatusBadge = ({ status }) => {
  const info = STATUS_MAP[status] || STATUS_MAP.disconnected;
  return (
    <span className={`integrations-step__status ${info.className}`}>
      {status === 'syncing' && <i className="fas fa-sync fa-spin" aria-hidden="true" />}
      {info.label}
    </span>
  );
};

/**
 * Toggle switch (reused across sections).
 */
const Toggle = ({ checked, onChange, label }) => (
  <label className="integrations-step__toggle" aria-label={label}>
    <input type="checkbox" checked={checked} onChange={onChange} />
    <span className="integrations-step__toggle-track">
      <span className="integrations-step__toggle-thumb" />
    </span>
  </label>
);

/**
 * "What gets synced" expandable panel.
 */
const SyncDetails = ({ items, expanded, onToggleExpand }) => (
  <div className="integrations-step__sync-details">
    <button
      type="button"
      className="integrations-step__sync-details-trigger"
      onClick={onToggleExpand}
      aria-expanded={expanded}
    >
      <i className={`fas fa-chevron-${expanded ? 'up' : 'down'}`} aria-hidden="true" />
      What gets synced
    </button>
    {expanded && (
      <ul className="integrations-step__sync-list">
        {items.map((item, idx) => (
          <li key={idx}>
            <i className="fas fa-check" aria-hidden="true" />
            {item}
          </li>
        ))}
      </ul>
    )}
  </div>
);

/**
 * Calendar Sync card (Google / Outlook).
 */
const CalendarSyncCard = ({ item, state, onConnect, onDisconnect, onSettingChange }) => {
  const [syncDetailsOpen, setSyncDetailsOpen] = useState(false);
  const isConnected = state.connected;

  return (
    <div className={`integrations-step__card ${isConnected ? 'integrations-step__card--connected' : ''}`}>
      <div className="integrations-step__card-header">
        <div className="integrations-step__card-icon">
          <i className={`${item.iconFamily} ${item.icon}`} aria-hidden="true" />
        </div>
        <div className="integrations-step__card-info">
          <div className="integrations-step__card-title-row">
            <span className="integrations-step__card-name">{item.name}</span>
            {item.recommended && (
              <span className="integrations-step__recommended">Recommended</span>
            )}
          </div>
          <p className="integrations-step__card-desc">{item.description}</p>
        </div>
        <div className="integrations-step__card-actions">
          <StatusBadge status={isConnected ? 'connected' : 'disconnected'} />
          <button
            type="button"
            className={`integrations-step__connect-btn ${isConnected ? 'integrations-step__connect-btn--disconnect' : ''}`}
            onClick={() => isConnected ? onDisconnect(item.key) : onConnect(item.key)}
            aria-label={isConnected ? `Disconnect ${item.name}` : `Connect ${item.name}`}
          >
            {isConnected ? 'Disconnect' : 'Connect'}
          </button>
        </div>
      </div>

      {isConnected && (
        <div className="integrations-step__card-settings">
          <div className="integrations-step__setting-row">
            <span className="integrations-step__setting-label">Sync direction</span>
            <select
              className="integrations-step__select"
              value={state.syncDirection || 'two_way'}
              onChange={(e) => onSettingChange(item.key, 'syncDirection', e.target.value)}
              aria-label="Sync direction"
            >
              <option value="one_way">One-way (read only)</option>
              <option value="two_way">Two-way</option>
            </select>
          </div>
          <div className="integrations-step__setting-row">
            <span className="integrations-step__setting-label">Auto-sync</span>
            <Toggle
              checked={state.autoSync !== false}
              onChange={() => onSettingChange(item.key, 'autoSync', !(state.autoSync !== false))}
              label={`Toggle auto-sync for ${item.name}`}
            />
          </div>
          {state.lastSynced && (
            <div className="integrations-step__last-sync">
              <i className="fas fa-clock" aria-hidden="true" />
              Last synced: {state.lastSynced}
            </div>
          )}
          <SyncDetails
            items={item.syncItems}
            expanded={syncDetailsOpen}
            onToggleExpand={() => setSyncDetailsOpen(prev => !prev)}
          />
        </div>
      )}
    </div>
  );
};

/**
 * Video Conferencing card (Zoom / Google Meet / Manual).
 */
const VideoCard = ({ item, state, onConnect, onDisconnect, onSettingChange }) => {
  const isConnected = state.connected;

  if (item.isManual) {
    return (
      <div className={`integrations-step__card ${state.customLink || state.usePhysicalLocation ? 'integrations-step__card--connected' : ''}`}>
        <div className="integrations-step__card-header">
          <div className="integrations-step__card-icon">
            <i className={`${item.iconFamily} ${item.icon}`} aria-hidden="true" />
          </div>
          <div className="integrations-step__card-info">
            <div className="integrations-step__card-title-row">
              <span className="integrations-step__card-name">{item.name}</span>
            </div>
            <p className="integrations-step__card-desc">{item.description}</p>
          </div>
        </div>
        <div className="integrations-step__card-settings integrations-step__card-settings--always">
          <div className="integrations-step__setting-row">
            <span className="integrations-step__setting-label">Custom meeting link pattern</span>
            <input
              type="text"
              className="integrations-step__input"
              value={state.customLink || ''}
              onChange={(e) => onSettingChange(item.key, 'customLink', e.target.value)}
              placeholder="https://meet.example.com/my-room"
              aria-label="Custom meeting link"
            />
          </div>
          <div className="integrations-step__setting-row">
            <span className="integrations-step__setting-label">Use physical location instead</span>
            <Toggle
              checked={!!state.usePhysicalLocation}
              onChange={() => onSettingChange(item.key, 'usePhysicalLocation', !state.usePhysicalLocation)}
              label="Toggle physical location"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`integrations-step__card ${isConnected ? 'integrations-step__card--connected' : ''}`}>
      <div className="integrations-step__card-header">
        <div className="integrations-step__card-icon">
          <i className={`${item.iconFamily} ${item.icon}`} aria-hidden="true" />
        </div>
        <div className="integrations-step__card-info">
          <div className="integrations-step__card-title-row">
            <span className="integrations-step__card-name">{item.name}</span>
            {item.recommended && (
              <span className="integrations-step__recommended">Recommended</span>
            )}
          </div>
          <p className="integrations-step__card-desc">{item.description}</p>
        </div>
        <div className="integrations-step__card-actions">
          <StatusBadge status={isConnected ? 'connected' : 'disconnected'} />
          <button
            type="button"
            className={`integrations-step__connect-btn ${isConnected ? 'integrations-step__connect-btn--disconnect' : ''}`}
            onClick={() => isConnected ? onDisconnect(item.key) : onConnect(item.key)}
            aria-label={isConnected ? `Disconnect ${item.name}` : `Connect ${item.name}`}
          >
            {isConnected ? 'Disconnect' : 'Connect'}
          </button>
        </div>
      </div>

      {isConnected && (
        <div className="integrations-step__card-settings">
          <div className="integrations-step__setting-row">
            <span className="integrations-step__setting-label">
              {item.key === 'zoom' ? 'Auto-generate meeting link' : 'Auto-add meeting link'}
            </span>
            <Toggle
              checked={state.autoGenerateLink !== false}
              onChange={() => onSettingChange(item.key, 'autoGenerateLink', !(state.autoGenerateLink !== false))}
              label={`Toggle auto-generate link for ${item.name}`}
            />
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * CRM Sync section (always connected).
 */
const CrmSyncCard = ({ toggles, onToggle }) => (
  <div className="integrations-step__card integrations-step__card--connected integrations-step__card--crm">
    <div className="integrations-step__card-header">
      <div className="integrations-step__card-icon integrations-step__card-icon--crm">
        <i className="fas fa-database" aria-hidden="true" />
      </div>
      <div className="integrations-step__card-info">
        <div className="integrations-step__card-title-row">
          <span className="integrations-step__card-name">Perennia CRM</span>
          <span className="integrations-step__always-connected">Always connected</span>
        </div>
        <p className="integrations-step__card-desc">
          Your calendar is part of Perennia CRM. Configure how appointments interact with your pipeline.
        </p>
      </div>
      <div className="integrations-step__card-actions">
        <StatusBadge status="connected" />
      </div>
    </div>

    <div className="integrations-step__card-settings integrations-step__card-settings--always">
      {CRM_TOGGLES.map(toggle => (
        <div key={toggle.key} className="integrations-step__setting-row">
          <span className="integrations-step__setting-label">{toggle.label}</span>
          <Toggle
            checked={!!toggles[toggle.key]}
            onChange={() => onToggle(toggle.key)}
            label={toggle.label}
          />
        </div>
      ))}
    </div>
  </div>
);

/**
 * External Calendar Feeds (iCal export / import).
 */
const CalendarFeedCard = ({ feedUrl, importUrl, onRegenerateUrl, onImportUrlChange, copied, onCopy }) => (
  <div className="integrations-step__card">
    <div className="integrations-step__card-header">
      <div className="integrations-step__card-icon">
        <i className="fas fa-rss" aria-hidden="true" />
      </div>
      <div className="integrations-step__card-info">
        <div className="integrations-step__card-title-row">
          <span className="integrations-step__card-name">Calendar Feeds</span>
        </div>
        <p className="integrations-step__card-desc">
          Share a read-only iCal feed or import an external calendar via URL.
        </p>
      </div>
    </div>

    <div className="integrations-step__card-settings integrations-step__card-settings--always">
      {/* iCal export */}
      <div className="integrations-step__feed-section">
        <span className="integrations-step__feed-label">
          <i className="fas fa-share-alt" aria-hidden="true" /> iCal Feed URL (read-only)
        </span>
        <div className="integrations-step__feed-row">
          <input
            type="text"
            className="integrations-step__input integrations-step__input--feed"
            value={feedUrl}
            readOnly
            aria-label="iCal feed URL"
          />
          <button
            type="button"
            className="integrations-step__copy-btn"
            onClick={onCopy}
            aria-label="Copy iCal URL"
          >
            <i className={`fas ${copied ? 'fa-check' : 'fa-copy'}`} aria-hidden="true" />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <button
          type="button"
          className="integrations-step__regen-btn"
          onClick={onRegenerateUrl}
        >
          <i className="fas fa-redo" aria-hidden="true" /> Regenerate URL
        </button>
      </div>

      {/* iCal import */}
      <div className="integrations-step__feed-section">
        <span className="integrations-step__feed-label">
          <i className="fas fa-download" aria-hidden="true" /> Import external calendar
        </span>
        <input
          type="text"
          className="integrations-step__input"
          value={importUrl}
          onChange={(e) => onImportUrlChange(e.target.value)}
          placeholder="https://calendar.example.com/feed.ics"
          aria-label="External calendar URL to import"
        />
      </div>
    </div>
  </div>
);

// ============================================================================
// Main component
// ============================================================================

const IntegrationsStep = ({ stepData = {}, onChange, allStepData }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Calendar sync state
  const [calendarStates, setCalendarStates] = useState(() => {
    const saved = stepData.calendarSync || {};
    return {
      google_calendar: { connected: false, syncDirection: 'two_way', autoSync: true, lastSynced: null, ...saved.google_calendar },
      microsoft_outlook: { connected: false, syncDirection: 'two_way', autoSync: true, lastSynced: null, ...saved.microsoft_outlook },
    };
  });

  // Video conferencing state
  const [videoStates, setVideoStates] = useState(() => {
    const saved = stepData.videoConferencing || {};
    return {
      zoom: { connected: false, autoGenerateLink: true, ...saved.zoom },
      google_meet: { connected: false, autoGenerateLink: true, ...saved.google_meet },
      manual_link: { customLink: '', usePhysicalLocation: false, ...saved.manual_link },
    };
  });

  // CRM toggles
  const [crmToggles, setCrmToggles] = useState(() => {
    const saved = stepData.crmSync || {};
    const defaults = {};
    CRM_TOGGLES.forEach(t => { defaults[t.key] = t.defaultOn; });
    return { ...defaults, ...saved };
  });

  // Calendar feed state
  const [feedUrl, setFeedUrl] = useState(
    stepData.calendarFeed?.feedUrl || `https://api.perenniaai.com/api/v1/calendar/feed/${generateFeedId()}.ics`
  );
  const [importUrl, setImportUrl] = useState(stepData.calendarFeed?.importUrl || '');
  const [feedCopied, setFeedCopied] = useState(false);

  // --------------------------------------------------------------------------
  // Load saved integration settings
  // --------------------------------------------------------------------------
  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = calendarSettingsAPI.getIntegrations
        ? await calendarSettingsAPI.getIntegrations()
        : null;
      if (res?.data?.integrations) {
        const d = res.data.integrations;
        if (d.calendarSync) setCalendarStates(prev => ({ ...prev, ...d.calendarSync }));
        if (d.videoConferencing) setVideoStates(prev => ({ ...prev, ...d.videoConferencing }));
        if (d.crmSync) setCrmToggles(prev => ({ ...prev, ...d.crmSync }));
        if (d.calendarFeed?.feedUrl) setFeedUrl(d.calendarFeed.feedUrl);
        if (d.calendarFeed?.importUrl) setImportUrl(d.calendarFeed.importUrl);
      }
    } catch (err) {
      // Endpoint may not exist yet; use defaults
      console.error('Failed to load integration settings:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // --------------------------------------------------------------------------
  // Notify parent of data changes
  // --------------------------------------------------------------------------
  const buildPayload = useCallback(() => ({
    calendarSync: calendarStates,
    videoConferencing: videoStates,
    crmSync: crmToggles,
    calendarFeed: { feedUrl, importUrl },
  }), [calendarStates, videoStates, crmToggles, feedUrl, importUrl]);

  useEffect(() => {
    if (onChange) {
      onChange(buildPayload());
    }
  }, [calendarStates, videoStates, crmToggles, feedUrl, importUrl, onChange, buildPayload]);

  // --------------------------------------------------------------------------
  // Calendar sync handlers
  // --------------------------------------------------------------------------
  // Poll localStorage for OAuth result (set by OAuthCallback.js)
  const oauthPollRef = useRef(null);

  const handleCalendarConnect = useCallback(async (key) => {
    const token = getToken();

    // Fetch the OAuth URL via authenticated API call to avoid exposing
    // the JWT in the URL query string.
    const authUrlEndpoints = {
      google_calendar: `${API_BASE_URL}/api/v1/google-calendar/auth-url`,
      microsoft_outlook: `${API_BASE_URL}/api/v1/microsoft/auth-url`,
    };
    const endpoint = authUrlEndpoints[key];
    if (!endpoint) return;

    // Clear any stale OAuth result
    localStorage.removeItem('oauth_result');

    let oauthUrl;
    try {
      const resp = await fetch(endpoint, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to initiate connection');
        return;
      }
      const data = await resp.json();
      oauthUrl = data.auth_url;
    } catch (err) {
      toast.error('Failed to initiate connection');
      return;
    }

    // Open OAuth in a popup window
    const popup = window.open(oauthUrl, 'oauth_popup', 'width=600,height=700,left=200,top=100');

    // Poll for completion (OAuthCallback.js stores result in localStorage)
    if (oauthPollRef.current) clearInterval(oauthPollRef.current);
    oauthPollRef.current = setInterval(() => {
      // Check if popup closed
      if (popup && popup.closed) {
        clearInterval(oauthPollRef.current);
        oauthPollRef.current = null;
      }

      // Check for OAuth result in localStorage
      const result = localStorage.getItem('oauth_result');
      if (result) {
        clearInterval(oauthPollRef.current);
        oauthPollRef.current = null;
        localStorage.removeItem('oauth_result');
        try {
          const parsed = JSON.parse(result);
          if (parsed.type === 'MICROSOFT_OAUTH_SUCCESS' || parsed.type === 'GOOGLE_OAUTH_SUCCESS') {
            setCalendarStates(prev => ({
              ...prev,
              [key]: { ...prev[key], connected: true, lastSynced: new Date().toISOString() },
            }));
            toast.success(`${key === 'google_calendar' ? 'Google Calendar' : 'Microsoft Outlook'} connected!`);
          } else if (parsed.type?.includes('ERROR')) {
            toast.error(parsed.error || 'Connection failed. Please try again.');
          }
        } catch (e) {
          // ignore parse errors
        }
      }
    }, 500);
  }, []);

  const handleCalendarDisconnect = useCallback((key) => {
    setCalendarStates(prev => ({
      ...prev,
      [key]: { ...prev[key], connected: false, lastSynced: null },
    }));
    toast.info(`${key === 'google_calendar' ? 'Google Calendar' : 'Microsoft Outlook'} disconnected`);
  }, []);

  const handleCalendarSettingChange = useCallback((key, setting, value) => {
    setCalendarStates(prev => ({
      ...prev,
      [key]: { ...prev[key], [setting]: value },
    }));
  }, []);

  // --------------------------------------------------------------------------
  // Video conferencing handlers
  // --------------------------------------------------------------------------
  const handleVideoConnect = useCallback((key) => {
    setVideoStates(prev => ({
      ...prev,
      [key]: { ...prev[key], connected: true },
    }));
    toast.success(`${key === 'zoom' ? 'Zoom' : 'Google Meet'} connected`);
  }, []);

  const handleVideoDisconnect = useCallback((key) => {
    setVideoStates(prev => ({
      ...prev,
      [key]: { ...prev[key], connected: false },
    }));
    toast.info(`${key === 'zoom' ? 'Zoom' : 'Google Meet'} disconnected`);
  }, []);

  const handleVideoSettingChange = useCallback((key, setting, value) => {
    setVideoStates(prev => ({
      ...prev,
      [key]: { ...prev[key], [setting]: value },
    }));
  }, []);

  // --------------------------------------------------------------------------
  // CRM toggle handler
  // --------------------------------------------------------------------------
  const handleCrmToggle = useCallback((key) => {
    setCrmToggles(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // --------------------------------------------------------------------------
  // Calendar feed handlers
  // --------------------------------------------------------------------------
  const handleCopyFeedUrl = useCallback(() => {
    navigator.clipboard.writeText(feedUrl).then(() => {
      setFeedCopied(true);
      toast.success('iCal URL copied to clipboard');
      setTimeout(() => setFeedCopied(false), 2000);
    }).catch(() => {
      toast.error('Failed to copy URL');
    });
  }, [feedUrl]);

  const handleRegenerateFeedUrl = useCallback(() => {
    const newUrl = `https://api.perenniaai.com/api/v1/calendar/feed/${generateFeedId()}.ics`;
    setFeedUrl(newUrl);
    toast.info('Feed URL regenerated. Previous URL will stop working.');
  }, []);

  // --------------------------------------------------------------------------
  // Connected counts
  // --------------------------------------------------------------------------
  const connectedCount = useMemo(() => {
    let count = 1; // CRM is always connected
    if (calendarStates.google_calendar.connected) count++;
    if (calendarStates.microsoft_outlook.connected) count++;
    if (videoStates.zoom.connected) count++;
    if (videoStates.google_meet.connected) count++;
    return count;
  }, [calendarStates, videoStates]);

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="integrations-step__loading" role="status" aria-label="Loading integration settings">
        <div className="integrations-step__spinner" aria-hidden="true" />
        <span>Loading integration settings...</span>
      </div>
    );
  }

  return (
    <div className="integrations-step">
      {/* Header */}
      <div className="integrations-step__header">
        <div className="integrations-step__step-badge">Step 6</div>
        <h2 className="integrations-step__title">Integrations</h2>
        <p className="integrations-step__subtitle">
          Connect your calendar, video conferencing, and CRM to create a seamless scheduling experience.
        </p>
      </div>

      {/* Connected summary */}
      <div className="integrations-step__summary-bar" role="status" aria-live="polite">
        <i className="fas fa-plug" aria-hidden="true" />
        <span>
          <strong>{connectedCount}</strong> integration{connectedCount !== 1 ? 's' : ''} active
        </span>
      </div>

      {/* Section 1: Calendar Sync */}
      <section className="integrations-step__section" aria-label="Calendar Sync">
        <h3 className="integrations-step__section-title">
          <i className="fas fa-calendar-alt" aria-hidden="true" />
          Calendar Sync
        </h3>
        <p className="integrations-step__section-desc">
          Sync with your existing calendar to prevent double-bookings.
        </p>
        <div className="integrations-step__cards-grid">
          {CALENDAR_SYNC_ITEMS.map(item => (
            <CalendarSyncCard
              key={item.key}
              item={item}
              state={calendarStates[item.key]}
              onConnect={handleCalendarConnect}
              onDisconnect={handleCalendarDisconnect}
              onSettingChange={handleCalendarSettingChange}
            />
          ))}
        </div>
      </section>

      {/* Section 2: Video Conferencing */}
      <section className="integrations-step__section" aria-label="Video Conferencing">
        <h3 className="integrations-step__section-title">
          <i className="fas fa-video" aria-hidden="true" />
          Video Conferencing
        </h3>
        <p className="integrations-step__section-desc">
          Automatically add meeting links to video appointments.
        </p>
        <div className="integrations-step__cards-grid">
          {VIDEO_CONFERENCING_ITEMS.map(item => (
            <VideoCard
              key={item.key}
              item={item}
              state={videoStates[item.key]}
              onConnect={handleVideoConnect}
              onDisconnect={handleVideoDisconnect}
              onSettingChange={handleVideoSettingChange}
            />
          ))}
        </div>
      </section>

      {/* Section 3: CRM Sync */}
      <section className="integrations-step__section" aria-label="CRM Sync">
        <h3 className="integrations-step__section-title">
          <i className="fas fa-database" aria-hidden="true" />
          CRM Sync
        </h3>
        <p className="integrations-step__section-desc">
          Control how your calendar integrates with the Perennia CRM pipeline.
        </p>
        <CrmSyncCard toggles={crmToggles} onToggle={handleCrmToggle} />
      </section>

      {/* Section 4: External Calendar Feeds */}
      <section className="integrations-step__section" aria-label="External Calendar Feeds">
        <h3 className="integrations-step__section-title">
          <i className="fas fa-rss" aria-hidden="true" />
          External Calendar Feeds
        </h3>
        <p className="integrations-step__section-desc">
          Share your calendar via iCal or import events from another source.
        </p>
        <CalendarFeedCard
          feedUrl={feedUrl}
          importUrl={importUrl}
          onRegenerateUrl={handleRegenerateFeedUrl}
          onImportUrlChange={setImportUrl}
          copied={feedCopied}
          onCopy={handleCopyFeedUrl}
        />
      </section>

      {/* Info note */}
      <div className="integrations-step__info">
        <i className="fas fa-info-circle" aria-hidden="true" />
        <span>
          All integrations can be changed later from Calendar Settings. Connecting external
          services will redirect you to their authorization page.
        </span>
      </div>
    </div>
  );
};

// ============================================================================
// Helpers
// ============================================================================

/**
 * Generate a random feed ID for iCal URL.
 */
function generateFeedId() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let id = '';
  for (let i = 0; i < 16; i++) {
    id += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return id;
}

export default IntegrationsStep;
