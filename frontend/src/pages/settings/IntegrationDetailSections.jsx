import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken, getUserData } from '../../utils/tokenStore';
import { toast } from '../../utils/toast';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import { API_BASE_URL, LEAD_STAGES, AVAILABLE_INTEGRATIONS } from './shared/constants';
import {
  TeamsDetail, ZoomDetail, SalesforceDetail, HubSpotDetail, MailchimpDetail,
  RingCentralDetail, SlackDetail, ZapierDetail, SynthflowDetail, RecallAIDetail,
  StripeDetail, QuickBooksDetail, GoogleCalendarDetail, GoogleDriveDetail, DocuSignDetail
} from './IntegrationSimplePages';

const IntegrationDetailSections = ({ activeSection, setActiveSection }) => {
  const navigate = useNavigate();
  const currentUser = getUserData() || {};

  // --- Integration state ---
  const [searchTerm, setSearchTerm] = useState('');
  const [connectedIntegrations, setConnectedIntegrations] = useState(new Set());

  // Gmail
  const [gmailStatus, setGmailStatus] = useState({ connected: false, email: null, connected_at: null });
  const [loadingGmail, setLoadingGmail] = useState(false);

  // Microsoft
  const [microsoftStatus, setMicrosoftStatus] = useState({ connected: false, email: null, connected_at: null, sync_enabled: false, last_sync_at: null });
  const [loadingMicrosoft, setLoadingMicrosoft] = useState(false);
  const [syncingMicrosoft, setSyncingMicrosoft] = useState(false);
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [microsoftOAuthConfig, setMicrosoftOAuthConfig] = useState({ client_id: '', client_secret: '', tenant_id: 'common' });
  const [showMicrosoftConfig, setShowMicrosoftConfig] = useState(false);
  const [savingMicrosoftConfig, setSavingMicrosoftConfig] = useState(false);
  const [microsoftConfigMessage, setMicrosoftConfigMessage] = useState({ type: '', text: '' });
  const [emailProcessingSettings, setEmailProcessingSettings] = useState({ delete_from_inbox_after_processing: false });
  const [savingEmailSettings, setSavingEmailSettings] = useState(false);

  // Calendly
  const [calendlyStatus, setCalendlyStatus] = useState({ isConnected: false, userName: null, userEmail: null, selectedEventTypeName: null, connectedAt: null, syncToSmartScheduler: true, autoCreateContacts: true });
  const [calendlyEventTypes, setCalendlyEventTypes] = useState([]);
  const [calendarMappings, setCalendarMappings] = useState([]);
  const [loadingCalendly, setLoadingCalendly] = useState(false);
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('');
  const [calendlySettings, setCalendlySettings] = useState({ selectedEventTypeUri: '', syncToSmartScheduler: true, autoCreateContacts: true });

  // Phone integration
  const [testPhoneNumber, setTestPhoneNumber] = useState('');
  const [testResults, setTestResults] = useState([]);

  // Sections that are NOT integration detail pages -- return nothing for those
  const integrationSections = new Set([
    'gmail', 'outlook-email', 'outlook-calendar', 'teams', 'calendly', 'zoom',
    'salesforce', 'hubspot', 'mailchimp', 'ringcentral', 'slack', 'zapier',
    'synthflow', 'recallai', 'stripe', 'quickbooks', 'google-calendar',
    'google-drive', 'docusign', 'integration-marketplace', 'phone-integration'
  ]);

  if (!integrationSections.has(activeSection)) return null;

  // --- Data fetchers (defined inline to use state) ---
  const checkGmailStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) { const data = await response.json(); setGmailStatus(data); const n = new Set(connectedIntegrations); if (data.connected) n.add('gmail'); else n.delete('gmail'); setConnectedIntegrations(n); }
    } catch (error) { console.error('Error checking Gmail status:', error); }
  };

  const connectGmail = async () => {
    setLoadingGmail(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/auth-url`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error('Failed to get Gmail auth URL');
      const data = await response.json();
      const w = 600, h = 700, left = (window.screen.width / 2) - (w / 2), top = (window.screen.height / 2) - (h / 2);
      const popup = window.open(data.auth_url, 'Gmail Login', `width=${w},height=${h},top=${top},left=${left}`);
      if (!popup) { toast.error('Popup was blocked! Please allow popups for this site.'); setLoadingGmail(false); return; }
      localStorage.removeItem('oauth_result');
      const handleMessage = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data && (event.data.type === 'gmail_connected' || event.data.type === 'GMAIL_OAUTH_SUCCESS')) {
          clearInterval(checkPopup); window.removeEventListener('message', handleMessage); localStorage.removeItem('oauth_result');
          setGmailStatus({ connected: true, email: event.data.email, connected_at: new Date().toISOString() });
          const n = new Set(connectedIntegrations); n.add('gmail'); setConnectedIntegrations(n); setLoadingGmail(false);
          if (popup && !popup.closed) popup.close(); toast.success('Gmail connected successfully!');
        } else if (event.data && event.data.type === 'GMAIL_OAUTH_ERROR') {
          clearInterval(checkPopup); window.removeEventListener('message', handleMessage); localStorage.removeItem('oauth_result');
          setLoadingGmail(false); if (popup && !popup.closed) popup.close();
          toast.error('Failed to connect Gmail: ' + (event.data.error || 'Unknown error'));
        }
      };
      window.addEventListener('message', handleMessage);
      const checkPopup = setInterval(async () => {
        const storedResult = localStorage.getItem('oauth_result');
        if (storedResult) {
          try { const result = JSON.parse(storedResult);
            if (Date.now() - result.timestamp < 30000) {
              clearInterval(checkPopup); localStorage.removeItem('oauth_result'); window.removeEventListener('message', handleMessage);
              if (popup && !popup.closed) popup.close(); setLoadingGmail(false);
              if (result.type === 'GMAIL_OAUTH_SUCCESS') { await checkGmailStatus(); toast.success('Gmail connected successfully!'); }
              else if (result.type === 'GMAIL_OAUTH_ERROR') { toast.error('Failed to connect Gmail: ' + (result.error || 'Unknown error')); }
              return;
            }
          } catch (e) { console.error('Error parsing OAuth result:', e); }
        }
        if (popup.closed) { clearInterval(checkPopup); window.removeEventListener('message', handleMessage); setLoadingGmail(false); checkGmailStatus(); }
      }, 500);
    } catch (error) { console.error('Error connecting Gmail:', error); toast.error('Failed to connect Gmail: ' + error.message); setLoadingGmail(false); }
  };

  const disconnectGmail = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/disconnect`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) { setGmailStatus({ connected: false, email: null, connected_at: null }); const n = new Set(connectedIntegrations); n.delete('gmail'); setConnectedIntegrations(n); }
      else throw new Error('Failed to disconnect Gmail');
    } catch (error) { console.error('Error disconnecting Gmail:', error); toast.error('Failed to disconnect Gmail'); }
  };

  const checkMicrosoftStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) {
        const data = await response.json();
        setMicrosoftStatus({ connected: data.connected || false, email: data.email_address || data.email || null, sync_enabled: data.sync_enabled || false, last_sync_at: data.last_sync_at || null, connected_at: data.connected_at || null });
        const n = new Set(connectedIntegrations);
        if (data.connected) { n.add('outlook-email'); n.add('outlook-calendar'); } else { n.delete('outlook-email'); n.delete('outlook-calendar'); }
        setConnectedIntegrations(n);
      }
    } catch (error) { console.error('Error checking Microsoft status:', error); }
  };

  const connectMicrosoft365 = async () => {
    setLoadingMicrosoft(true);
    try {
      const currentOrigin = window.location.origin;
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/auth-url?origin=${encodeURIComponent(currentOrigin)}`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error('Failed to get Microsoft auth URL');
      const data = await response.json();
      const w = 600, h = 700, left = window.screenX + (window.outerWidth - w) / 2, top = window.screenY + (window.outerHeight - h) / 2;
      const popup = window.open(data.auth_url, 'Microsoft365OAuth', `width=${w},height=${h},left=${left},top=${top},scrollbars=yes,resizable=yes`);
      if (!popup || popup.closed) { setLoadingMicrosoft(false); toast.error('Popup was blocked! Please allow popups for this site.'); return; }
      localStorage.removeItem('oauth_result');
      const handleMessage = async (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === 'MICROSOFT_OAUTH_SUCCESS') { clearInterval(pollTimer); window.removeEventListener('message', handleMessage); localStorage.removeItem('oauth_result'); if (popup && !popup.closed) popup.close(); setLoadingMicrosoft(false); await checkMicrosoftStatus(); toast.success('Microsoft 365 connected successfully!'); }
        else if (event.data?.type === 'MICROSOFT_OAUTH_ERROR') { clearInterval(pollTimer); window.removeEventListener('message', handleMessage); localStorage.removeItem('oauth_result'); if (popup && !popup.closed) popup.close(); setLoadingMicrosoft(false); toast.error('Failed to connect Microsoft 365: ' + (event.data.error || 'Unknown error')); }
      };
      window.addEventListener('message', handleMessage);
      const pollTimer = setInterval(async () => {
        const storedResult = localStorage.getItem('oauth_result');
        if (storedResult) {
          try { const result = JSON.parse(storedResult);
            if (Date.now() - result.timestamp < 30000) {
              clearInterval(pollTimer); localStorage.removeItem('oauth_result'); window.removeEventListener('message', handleMessage);
              if (popup && !popup.closed) popup.close(); setLoadingMicrosoft(false);
              if (result.type === 'MICROSOFT_OAUTH_SUCCESS') { await checkMicrosoftStatus(); toast.success('Microsoft 365 connected successfully!'); }
              else if (result.type === 'MICROSOFT_OAUTH_ERROR') { toast.error('Failed to connect Microsoft 365: ' + (result.error || 'Unknown error')); }
              return;
            }
          } catch (e) { console.error('Error parsing OAuth result:', e); }
        }
        if (popup.closed) { clearInterval(pollTimer); window.removeEventListener('message', handleMessage); setLoadingMicrosoft(false); await checkMicrosoftStatus(); }
      }, 500);
      setTimeout(() => { clearInterval(pollTimer); window.removeEventListener('message', handleMessage); localStorage.removeItem('oauth_result'); if (popup && !popup.closed) popup.close(); setLoadingMicrosoft(false); }, 300000);
    } catch (error) { console.error('Error connecting Microsoft:', error); toast.error('Failed to connect Microsoft 365: ' + error.message); setLoadingMicrosoft(false); }
  };

  const disconnectMicrosoft = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/disconnect`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) { setMicrosoftStatus({ connected: false, email: null, connected_at: null, sync_enabled: false, last_sync_at: null }); const n = new Set(connectedIntegrations); n.delete('outlook-email'); n.delete('outlook-calendar'); setConnectedIntegrations(n); }
      else throw new Error('Failed to disconnect Microsoft');
    } catch (error) { console.error('Error disconnecting Microsoft:', error); toast.error('Failed to disconnect Microsoft 365'); }
  };

  const syncMicrosoftNow = async () => {
    setSyncingMicrosoft(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-now`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } });
      const data = await response.json();
      if (response.ok) { toast.success(`Sync complete! ${data.processed_count || data.emails_synced || 0} emails processed.`); checkMicrosoftStatus(); }
      else { const errorMsg = data.error || data.detail || 'Sync failed'; toast.error(`Sync failed: ${errorMsg}`); }
    } catch (error) { console.error('Error syncing Microsoft:', error); toast.error('Failed to sync Microsoft emails.'); }
    finally { setSyncingMicrosoft(false); }
  };

  const syncMicrosoftCalendar = async () => {
    setSyncingCalendar(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-calendar`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } });
      const data = await response.json();
      if (response.ok) { toast.success(`Calendar sync complete! ${data.events_synced || 0} events processed.`); }
      else { toast.error(`Calendar sync failed: ${data.error || data.detail || 'Unknown error'}`); }
    } catch (error) { console.error('Error syncing calendar:', error); toast.error('Failed to sync Outlook calendar.'); }
    finally { setSyncingCalendar(false); }
  };

  const fetchMicrosoftOAuthConfig = async () => {
    try { const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth-config`, { headers: { 'Authorization': `Bearer ${getToken()}` } }); if (response.ok) { const data = await response.json(); setMicrosoftOAuthConfig({ client_id: data.client_id || '', client_secret: '', tenant_id: data.tenant_id || 'common' }); } } catch (error) { console.error('Error fetching Microsoft OAuth config:', error); }
  };

  const saveMicrosoftOAuthConfig = async () => {
    setSavingMicrosoftConfig(true); setMicrosoftConfigMessage({ type: '', text: '' });
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth-config`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify(microsoftOAuthConfig) });
      if (response.ok) { setMicrosoftConfigMessage({ type: 'success', text: 'Microsoft OAuth configuration saved!' }); setShowMicrosoftConfig(false); await fetchMicrosoftOAuthConfig(); }
      else { const error = await response.json(); setMicrosoftConfigMessage({ type: 'error', text: error.detail || 'Failed to save configuration' }); }
    } catch (error) { setMicrosoftConfigMessage({ type: 'error', text: 'Error saving configuration: ' + error.message }); }
    finally { setSavingMicrosoftConfig(false); }
  };

  const fetchEmailProcessingSettings = async () => {
    try { const response = await fetch(`${API_BASE_URL}/api/v1/user-settings/email-processing`, { headers: { 'Authorization': `Bearer ${getToken()}` } }); if (response.ok) { const data = await response.json(); setEmailProcessingSettings(data); } } catch (error) { console.error('Error fetching email processing settings:', error); }
  };

  const saveEmailProcessingSettings = async (newSettings) => {
    setSavingEmailSettings(true);
    try { const response = await fetch(`${API_BASE_URL}/api/v1/user-settings/email-processing`, { method: 'PUT', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify(newSettings) }); if (response.ok) setEmailProcessingSettings(newSettings); } catch (error) { console.error('Error saving email processing settings:', error); }
    finally { setSavingEmailSettings(false); }
  };

  // Calendly handlers
  const fetchCalendlyStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/status?user_id=${currentUser?.id}`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
      if (response.ok) { const data = await response.json(); setCalendlyStatus({ isConnected: data.is_connected, userName: data.calendly_user_name, userEmail: data.calendly_user_email, selectedEventTypeName: data.selected_event_type_name, connectedAt: data.connected_at, syncToSmartScheduler: data.sync_to_smart_scheduler, autoCreateContacts: data.auto_create_contacts }); if (data.is_connected) { const n = new Set(connectedIntegrations); n.add('calendly'); setConnectedIntegrations(n); await fetchCalendlyEventTypes(); } }
    } catch (error) { console.error('[Calendly] Error fetching status:', error); }
  };

  const connectCalendly = async () => {
    setLoadingCalendly(true);
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/connect?user_id=${currentUser?.id}`, { headers: { 'Authorization': `Bearer ${getToken()}` } }); if (response.ok) { const data = await response.json(); localStorage.setItem('calendly_oauth_state', data.state); window.location.href = data.authorization_url; } else { toast.error('Failed to initiate Calendly connection.'); } } catch (error) { toast.error('Error connecting to Calendly: ' + error.message); }
    finally { setLoadingCalendly(false); }
  };

  const disconnectCalendly = async () => {
    if (!window.confirm('Are you sure you want to disconnect Calendly?')) return;
    setLoadingCalendly(true);
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/disconnect?user_id=${currentUser?.id}`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } }); if (response.ok) { setCalendlyStatus({ isConnected: false, userName: null, userEmail: null, selectedEventTypeName: null, connectedAt: null, syncToSmartScheduler: true, autoCreateContacts: true }); setCalendlyEventTypes([]); const n = new Set(connectedIntegrations); n.delete('calendly'); setConnectedIntegrations(n); toast.success('Calendly disconnected successfully'); } else { const error = await response.json(); toast.error(`Failed to disconnect: ${error.detail || 'Please try again'}`); } } catch (error) { toast.error('Error disconnecting Calendly: ' + error.message); }
    finally { setLoadingCalendly(false); }
  };

  const updateCalendlySettings = async (updates) => {
    setLoadingCalendly(true);
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/settings?user_id=${currentUser?.id}`, { method: 'PUT', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify(updates) }); if (response.ok) { const data = await response.json(); setCalendlyStatus(prev => ({ ...prev, selectedEventTypeName: data.selected_event_type_name, syncToSmartScheduler: data.sync_to_smart_scheduler, autoCreateContacts: data.auto_create_contacts })); toast.success('Settings updated successfully'); } else { const error = await response.json(); toast.error(`Failed to update settings: ${error.detail || 'Please try again'}`); } } catch (error) { toast.error('Error updating settings: ' + error.message); }
    finally { setLoadingCalendly(false); }
  };

  const fetchCalendlyEventTypes = async () => {
    setLoadingCalendly(true);
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/event-types?user_id=${currentUser?.id}`, { headers: { 'Authorization': `Bearer ${getToken()}` } }); if (response.ok) { const data = await response.json(); setCalendlyEventTypes(data.event_types || []); const n = new Set(connectedIntegrations); if (data.event_types?.length > 0) n.add('calendly'); else n.delete('calendly'); setConnectedIntegrations(n); } else { setCalendlyEventTypes([]); const n = new Set(connectedIntegrations); n.delete('calendly'); setConnectedIntegrations(n); } } catch (error) { console.error('[Calendly] Error:', error); setCalendlyEventTypes([]); }
    finally { setLoadingCalendly(false); }
  };

  const fetchCalendarMappings = async () => {
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, { headers: { 'Authorization': `Bearer ${getToken()}` } }); const data = await response.json(); setCalendarMappings(data.mappings || []); } catch (error) { console.error('Error fetching calendar mappings:', error); }
  };

  const createCalendarMapping = async () => {
    if (!selectedStage || !selectedEventType) { toast.error('Please select both a lead stage and a calendar type'); return; }
    const eventType = calendlyEventTypes.find(et => et.uri.includes(selectedEventType));
    if (!eventType) { toast.error('Event type not found'); return; }
    try { const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ stage: selectedStage, event_type_uuid: selectedEventType, event_type_name: eventType.name, event_type_url: eventType.scheduling_url }) }); if (response.ok) { toast.success('Calendar mapping saved!'); setSelectedStage(''); setSelectedEventType(''); fetchCalendarMappings(); } else { toast.error('Failed to save calendar mapping'); } } catch (error) { toast.error('Error saving calendar mapping'); }
  };

  // Phone test helpers
  const addTestResult = (feature, status, message) => { setTestResults(prev => [{ feature, status, message, timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5)); };
  const testClickToCall = () => { if (!testPhoneNumber) { addTestResult('Click-to-Call', 'error', 'Please enter a phone number'); return; } try { window.open(`tel:${testPhoneNumber.replace(/[^0-9+]/g, '')}`, '_self'); addTestResult('Click-to-Call', 'success', `Dialer opened for ${testPhoneNumber}`); } catch (error) { addTestResult('Click-to-Call', 'error', `Failed: ${error.message}`); } };
  const testSMS = () => { if (!testPhoneNumber) { addTestResult('SMS', 'error', 'Please enter a phone number'); return; } try { window.open(`sms:${testPhoneNumber.replace(/[^0-9+]/g, '')}`, '_blank'); addTestResult('SMS', 'success', `Messaging app opened for ${testPhoneNumber}`); } catch (error) { addTestResult('SMS', 'error', `Failed: ${error.message}`); } };

  const toggleIntegration = (integrationId) => { setActiveSection(integrationId); };
  const filteredIntegrations = AVAILABLE_INTEGRATIONS.filter(i => i.name.toLowerCase().includes(searchTerm.toLowerCase()) || i.description.toLowerCase().includes(searchTerm.toLowerCase()) || i.category.toLowerCase().includes(searchTerm.toLowerCase()));

  // Load data on section change -- use a self-invoking async function
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    if (activeSection === 'integration-marketplace') { checkGmailStatus(); checkMicrosoftStatus(); }
    if (activeSection === 'outlook-email' || activeSection === 'outlook-calendar') { checkMicrosoftStatus(); fetchMicrosoftOAuthConfig(); fetchEmailProcessingSettings(); }
    if (activeSection === 'calendly') { fetchCalendlyStatus(); fetchCalendarMappings(); }
    if (activeSection === 'gmail') { checkGmailStatus(); }
  }, [activeSection]);

  // --- Simple detail pages ---
  if (activeSection === 'teams') return <TeamsDetail />;
  if (activeSection === 'zoom') return <ZoomDetail />;
  if (activeSection === 'salesforce') return <SalesforceDetail />;
  if (activeSection === 'hubspot') return <HubSpotDetail />;
  if (activeSection === 'mailchimp') return <MailchimpDetail />;
  if (activeSection === 'ringcentral') return <RingCentralDetail />;
  if (activeSection === 'slack') return <SlackDetail />;
  if (activeSection === 'zapier') return <ZapierDetail setActiveSection={setActiveSection} />;
  if (activeSection === 'synthflow') return <SynthflowDetail />;
  if (activeSection === 'recallai') return <RecallAIDetail />;
  if (activeSection === 'stripe') return <StripeDetail />;
  if (activeSection === 'quickbooks') return <QuickBooksDetail />;
  if (activeSection === 'google-calendar') return <GoogleCalendarDetail />;
  if (activeSection === 'google-drive') return <GoogleDriveDetail />;
  if (activeSection === 'docusign') return <DocuSignDetail />;

  // --- Gmail ---
  if (activeSection === 'gmail') {
    return (
      <div className="integration-detail-section">
        <h2>Gmail Integration</h2>
        <p className="section-description">Sync Gmail emails and automatically extract lead information with AI</p>
        {gmailStatus.connected ? (
          <div className="connection-status-card connected gmail">
            <div className="connection-status-header">
              <div className="connection-status-indicator"></div>
              <div className="connection-status-info"><h3>Gmail Connected</h3><p className="connection-email">{gmailStatus.email}</p></div>
              <div className="connection-actions">
                <button className="btn-sync" onClick={async () => { setLoadingGmail(true); try { const response = await fetch(`${API_BASE_URL}/api/v1/gmail/sync?days_back=7&max_results=100`, { method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` } }); const data = await response.json(); if (response.ok) toast.success(`Gmail sync complete! ${data.processed_count} emails processed.`); else toast.error(`Sync failed: ${data.detail || 'Unknown error'}`); } catch (error) { toast.error('Failed to sync Gmail'); } finally { setLoadingGmail(false); } }} disabled={loadingGmail}>{loadingGmail ? 'Syncing...' : 'Sync Now'}</button>
                <button className="btn-disconnect" onClick={disconnectGmail} disabled={loadingGmail}>Disconnect</button>
              </div>
            </div>
            {gmailStatus.connected_at && <div className="connection-meta">Connected: {new Date(gmailStatus.connected_at).toLocaleString()}</div>}
          </div>
        ) : (
          <div className="connection-prompt-card"><h3>Connect Gmail</h3><p>Connect your Gmail account to sync emails and extract lead information automatically</p><button className="btn-connect" onClick={connectGmail} disabled={loadingGmail}>{loadingGmail ? 'Connecting...' : 'Connect Gmail'}</button></div>
        )}
        <div className="integration-features" style={{marginTop: '24px'}}><h4>Features</h4><ul><li>Automatic email sync every 5 minutes</li><li>AI-powered lead extraction</li><li>Mortgage-related email detection</li><li>Auto-link to existing leads and loans</li></ul></div>
      </div>
    );
  }

  // --- Outlook Email ---
  if (activeSection === 'outlook-email') {
    return (
      <div className="integration-detail-section">
        <h2>Outlook Email Integration</h2>
        <p className="section-description">Sync your Microsoft 365 / Outlook emails and automatically link them to loan files</p>
        <div className="settings-card" style={{marginBottom: '24px'}}>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}><h3 style={{margin: 0}}>Microsoft Azure App Configuration</h3><button className="btn-secondary" onClick={() => setShowMicrosoftConfig(!showMicrosoftConfig)}>{showMicrosoftConfig ? 'Hide Configuration' : 'Configure Azure App'}</button></div>
          {microsoftOAuthConfig.client_id && !showMicrosoftConfig && <div style={{color: '#22c55e', fontSize: '14px'}}>App configured (Client ID: {microsoftOAuthConfig.client_id.substring(0, 8)}...)</div>}
          {showMicrosoftConfig && (
            <div className="oauth-config-form">
              {microsoftConfigMessage.text && <div className={`message-banner ${microsoftConfigMessage.type}`} style={{marginBottom: '16px'}}>{microsoftConfigMessage.text}</div>}
              <p style={{fontSize: '14px', color: '#666', marginBottom: '16px'}}>Enter your Microsoft Azure App credentials. <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" target="_blank" rel="noopener noreferrer">Azure Portal</a></p>
              <div className="form-group"><label>Application (Client) ID *</label><input type="text" value={microsoftOAuthConfig.client_id} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_id: e.target.value})} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /><small>Found in Azure Portal &gt; App registrations &gt; Overview</small></div>
              <div className="form-group"><label>Client Secret *</label><input type="password" value={microsoftOAuthConfig.client_secret} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_secret: e.target.value})} placeholder="Enter client secret (or leave blank to keep existing)" /><small>Found in Azure Portal &gt; Certificates & secrets</small></div>
              <div className="form-group"><label>Tenant ID</label><input type="text" value={microsoftOAuthConfig.tenant_id} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, tenant_id: e.target.value})} placeholder="common (for multi-tenant apps)" /></div>
              <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f0f9ff', borderRadius: '8px', border: '1px solid #bae6fd'}}><h4 style={{margin: '0 0 8px 0', fontSize: '14px', color: '#0369a1'}}>Required Redirect URI</h4><code style={{display: 'block', marginTop: '8px', padding: '8px', backgroundColor: '#fff', borderRadius: '4px', fontSize: '12px'}}>{window.location.origin}/oauth/callback</code></div>
              <div style={{marginTop: '16px', display: 'flex', gap: '12px'}}><button className="btn-primary" onClick={saveMicrosoftOAuthConfig} disabled={savingMicrosoftConfig || !microsoftOAuthConfig.client_id}>{savingMicrosoftConfig ? 'Saving...' : 'Save Configuration'}</button><button className="btn-secondary" onClick={() => setShowMicrosoftConfig(false)}>Cancel</button></div>
            </div>
          )}
        </div>
        {microsoftStatus.connected ? (
          <div className="connection-status-card connected outlook">
            <div className="connection-status-header"><div className="connection-status-indicator"></div><div className="connection-status-info"><h3>Outlook Connected</h3><p className="connection-email">{microsoftStatus.email}</p></div>
              <div className="connection-actions"><button className="btn-sync" onClick={syncMicrosoftNow} disabled={syncingMicrosoft}>{syncingMicrosoft ? 'Syncing...' : 'Sync Now'}</button><button className="btn-disconnect" onClick={disconnectMicrosoft} disabled={loadingMicrosoft}>Disconnect</button></div>
            </div>
            {microsoftStatus.last_sync_at && <div className="connection-meta">Last Sync: {new Date(microsoftStatus.last_sync_at).toLocaleString()}</div>}
            {microsoftStatus.connected_at && <div className="connection-meta">Connected: {new Date(microsoftStatus.connected_at).toLocaleString()}</div>}
          </div>
        ) : (
          <div className="connection-prompt-card"><h3>Connect Outlook</h3><p>Connect your Microsoft 365 / Outlook account to sync emails with loan files</p>{!microsoftOAuthConfig.client_id && <p style={{color: '#f59e0b', fontSize: '14px', marginBottom: '12px'}}>Please configure your Azure App credentials above before connecting.</p>}<button className="btn-connect" onClick={connectMicrosoft365} disabled={loadingMicrosoft || !microsoftOAuthConfig.client_id}>{loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}</button></div>
        )}
        <div className="email-processing-settings" style={{ marginTop: '24px', padding: '20px', background: '#f9fafb', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
          <h4 style={{margin: '0 0 16px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937'}}>Email Processing Settings</h4>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', cursor: 'pointer', padding: '12px', background: 'white', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
            <input type="checkbox" checked={emailProcessingSettings.delete_from_inbox_after_processing} onChange={(e) => { saveEmailProcessingSettings({ ...emailProcessingSettings, delete_from_inbox_after_processing: e.target.checked }); }} disabled={savingEmailSettings} style={{ width: '20px', height: '20px', marginTop: '2px', accentColor: '#218D8D' }} />
            <div><span style={{fontWeight: '500', color: '#1f2937', display: 'block'}}>Delete emails from inbox after processing</span><span style={{fontSize: '13px', color: '#6b7280', marginTop: '4px', display: 'block'}}>When you approve or reject emails in the Reconciliation Center, they will also be moved to trash in your inbox.</span></div>
          </label>
          {emailProcessingSettings.delete_from_inbox_after_processing && <div style={{ marginTop: '12px', padding: '12px', background: '#fef3c7', borderRadius: '8px', fontSize: '13px', color: '#92400e' }}>Emails will be moved to your Trash folder (not permanently deleted). You can recover them from Trash within 30 days.</div>}
        </div>
        <div className="integration-features" style={{marginTop: '24px'}}><h4>Features</h4><ul><li>Automatic email sync with loan files</li><li>AI-powered lead extraction</li><li>Auto-link emails to existing loans</li><li>Two-way email sync</li></ul></div>
      </div>
    );
  }

  // --- Outlook Calendar ---
  if (activeSection === 'outlook-calendar') {
    return (
      <div className="integration-detail-section">
        <h2>Outlook Calendar Integration</h2>
        <p className="section-description">Sync your Microsoft 365 / Outlook calendar events</p>
        {microsoftStatus.connected ? (
          <div className="connection-status-card connected outlook"><div className="connection-status-header"><div className="connection-status-indicator"></div><div className="connection-status-info"><h3>Calendar Connected</h3><p className="connection-email">{microsoftStatus.email}</p></div><div className="connection-actions"><button className="btn-sync" onClick={syncMicrosoftCalendar} disabled={syncingCalendar}>{syncingCalendar ? 'Syncing...' : 'Sync Calendar'}</button></div></div></div>
        ) : (
          <div className="connection-prompt-card"><h3>Connect Outlook Calendar</h3><p>Connect your Microsoft 365 / Outlook account to sync calendar events</p><button className="btn-connect" onClick={connectMicrosoft365} disabled={loadingMicrosoft}>{loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}</button></div>
        )}
        <div className="integration-features" style={{marginTop: '24px'}}><h4>Features</h4><ul><li>Sync calendar events with CRM</li><li>Schedule appointments with borrowers</li><li>Automatic reminders</li></ul></div>
      </div>
    );
  }

  // --- Calendly (complex -- has settings, event types, mappings) ---
  if (activeSection === 'calendly') {
    return (
      <div className="calendar-settings-section">
        <h2>Calendly Integration</h2>
        <p className="section-description">Connect Calendly and configure AI scheduling for automatic appointment booking</p>
        <div className="calendly-connection-card">
          <div className="connection-header">
            <div className="connection-icon" style={{background: '#006bff'}}>&#128197;</div>
            <div className="connection-info"><h3>Calendly Connection</h3>{calendlyStatus.isConnected ? <p>Connected as <strong>{calendlyStatus.userName}</strong> ({calendlyStatus.userEmail})</p> : <p>Connect your Calendly account to sync calendars and manage appointments</p>}</div>
            <div className="connection-status">{calendlyStatus.isConnected ? <span className="status-badge connected">Connected</span> : <span className="status-badge disconnected">Not Connected</span>}</div>
          </div>
          <div className="connection-actions">
            {calendlyStatus.isConnected ? (<><button className="btn-refresh" onClick={fetchCalendlyStatus} disabled={loadingCalendly}>{loadingCalendly ? 'Refreshing...' : 'Refresh'}</button><button className="btn-disconnect" onClick={disconnectCalendly} disabled={loadingCalendly} style={{ marginLeft: '8px', background: '#dc3545', color: '#fff' }}>Disconnect</button><span className="connection-detail" style={{ marginLeft: '12px' }}>{calendlyEventTypes.length} event types available</span></>) : (<button className="btn-connect-calendly" onClick={connectCalendly} disabled={loadingCalendly}>{loadingCalendly ? 'Connecting...' : 'Connect with Calendly'}</button>)}
          </div>
        </div>
        {calendlyStatus.isConnected && (
          <div className="calendly-settings-card" style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '24px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '16px' }}>Integration Settings</h3>
            <div className="form-group" style={{ marginBottom: '16px' }}><label>Default Event Type for AI Scheduling</label><select value={calendlySettings.selectedEventTypeUri || ''} onChange={(e) => { setCalendlySettings(prev => ({ ...prev, selectedEventTypeUri: e.target.value })); updateCalendlySettings({ selected_event_type_uri: e.target.value }); }} disabled={loadingCalendly || calendlyEventTypes.length === 0} style={{ width: '100%', padding: '10px', marginTop: '8px' }}><option value="">Select default event type...</option>{calendlyEventTypes.map(et => { const uuid = et.uri.split('/').pop(); return <option key={uuid} value={et.uri}>{et.name} ({et.duration} min)</option>; })}</select></div>
            <div className="form-group" style={{ marginBottom: '16px' }}><label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={calendlyStatus.syncToSmartScheduler} onChange={(e) => updateCalendlySettings({ sync_to_smart_scheduler: e.target.checked })} style={{ marginRight: '8px' }} />Sync Calendly bookings to Smart Scheduler</label></div>
            <div className="form-group"><label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={calendlyStatus.autoCreateContacts} onChange={(e) => updateCalendlySettings({ auto_create_contacts: e.target.checked })} style={{ marginRight: '8px' }} />Auto-create contacts from Calendly bookings</label></div>
          </div>
        )}
        <div className="mapping-form-card"><h3>Create Calendar Mapping</h3><div className="mapping-form"><div className="form-row"><div className="form-group"><label>Lead Stage</label><select value={selectedStage} onChange={(e) => setSelectedStage(e.target.value)} className="form-select"><option value="">Select a stage...</option>{LEAD_STAGES.map(stage => <option key={stage.value} value={stage.value}>{stage.label}</option>)}</select></div><div className="form-group"><label>Calendly Event Type</label>{loadingCalendly ? <div className="loading-spinner">Loading calendars...</div> : <select value={selectedEventType} onChange={(e) => setSelectedEventType(e.target.value)} className="form-select" disabled={calendlyEventTypes.length === 0}><option value="">Select a calendar...</option>{calendlyEventTypes.map(et => { const uuid = et.uri.split('/').pop(); return <option key={uuid} value={uuid}>{et.name} ({et.duration} min)</option>; })}</select>}</div><div className="form-actions"><button onClick={createCalendarMapping} disabled={!selectedStage || !selectedEventType} className="btn-save-mapping">Save Mapping</button></div></div></div></div>
        <div className="current-mappings-card"><h3>Current Mappings</h3>{calendarMappings.length === 0 ? <div className="empty-state"><p>No calendar mappings configured yet.</p></div> : <div className="mappings-table"><table><thead><tr><th>Lead Stage</th><th>Calendar Type</th><th>Status</th></tr></thead><tbody>{calendarMappings.map(m => { const stageLabel = LEAD_STAGES.find(s => s.value === m.stage)?.label || m.stage; return <tr key={m.id}><td><span className="stage-badge">{stageLabel}</span></td><td><strong>{m.event_type_name}</strong><br /><span className="calendar-uuid">{m.event_type_uuid}</span></td><td><span className="status-badge active">Active</span></td></tr>; })}</tbody></table></div>}</div>
      </div>
    );
  }

  // --- Integration Marketplace ---
  if (activeSection === 'integration-marketplace') {
    return (
      <div className="integrations-marketplace">
        <div className="marketplace-header"><div className="header-text"><h2>Integrations & Apps</h2><p className="section-description">Discover ({AVAILABLE_INTEGRATIONS.length}) | Manage ({connectedIntegrations.size})</p></div><div className="search-box"><input type="text" placeholder="Find integrations, apps, and more" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} className="integration-search" /></div></div>
        <div className="all-integrations-section"><div className="integrations-grid">{filteredIntegrations.map(integration => (<div key={integration.id} className="integration-grid-card" onClick={() => toggleIntegration(integration.id)}><div className="card-icon" style={{background: integration.color}}>{integration.icon}</div><div className="card-content"><div className="card-header"><h4>{integration.name}</h4>{connectedIntegrations.has(integration.id) && <span className="connected-badge">Connected</span>}</div><p className="card-description">{integration.description}</p></div></div>))}</div>{filteredIntegrations.length === 0 && <div className="no-results"><p>No integrations found matching "{searchTerm}"</p></div>}</div>
      </div>
    );
  }

  // --- Phone Integration ---
  if (activeSection === 'phone-integration') {
    return (
      <div className="phone-integration-section">
        <h2>Phone Integration</h2>
        <p className="section-description">Manage phone, SMS, and calling features</p>
        <div className="phone-status-card"><div className="card-header"><h3>Integration Status</h3></div><div className="status-grid"><div className="status-item"><div className="status-info"><h4>Click-to-Call</h4><p>Native phone integration</p><span className="status-badge connected">Active</span></div></div><div className="status-item"><div className="status-info"><h4>SMS/Text</h4><p>Native messaging integration</p><span className="status-badge connected">Active</span></div></div></div></div>
        <div className="phone-test-card"><h3>Test Phone Features</h3><div className="test-form"><div className="form-group"><label>Test Phone Number</label><input type="tel" className="form-input" placeholder="Enter phone number" value={testPhoneNumber} onChange={(e) => setTestPhoneNumber(formatPhoneNumber(e.target.value))} /></div><div className="test-actions"><button className="btn-test call" onClick={testClickToCall} disabled={!testPhoneNumber}>Test Click-to-Call</button><button className="btn-test sms" onClick={testSMS} disabled={!testPhoneNumber}>Test SMS</button></div></div>
          {testResults.length > 0 && <div className="test-results"><h4>Recent Tests</h4><div className="results-list">{testResults.map((result, index) => <div key={index} className={`result-item ${result.status}`}><span className="result-icon">{result.status === 'success' ? '✓' : '✗'}</span><div className="result-content"><div className="result-feature">{result.feature}</div><div className="result-message">{result.message}</div></div><div className="result-time">{result.timestamp}</div></div>)}</div></div>}
        </div>
        <div className="info-card"><div className="info-content"><h3>How Phone Integration Works</h3><ul><li><strong>Click-to-Call:</strong> Click any phone number to open your dialer</li><li><strong>SMS/Text:</strong> Click to open your messaging app</li><li>Works with any carrier</li><li>No configuration required</li></ul></div></div>
      </div>
    );
  }

  return null;
};

export default IntegrationDetailSections;
