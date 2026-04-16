import React, { useState, useEffect } from 'react';
import { toast } from '../../utils/toast';
import { API_BASE_URL, LEAD_STAGES } from './shared/constants';
import { getToken } from '../../utils/tokenStore';

const IntegrationDetails = ({
  activeSection,
  setActiveSection,
  // Gmail state
  gmailStatus, setGmailStatus,
  loadingGmail, setLoadingGmail,
  connectedIntegrations, setConnectedIntegrations,
  // Microsoft state
  microsoftStatus, setMicrosoftStatus,
  loadingMicrosoft, setLoadingMicrosoft,
  syncingMicrosoft, setSyncingMicrosoft,
  syncingCalendar, setSyncingCalendar,
  // Microsoft OAuth config
  microsoftOAuthConfig, setMicrosoftOAuthConfig,
  showMicrosoftConfig, setShowMicrosoftConfig,
  savingMicrosoftConfig, setSavingMicrosoftConfig,
  microsoftConfigMessage, setMicrosoftConfigMessage,
  // Email processing settings
  emailProcessingSettings, setEmailProcessingSettings,
  savingEmailSettings, setSavingEmailSettings,
  // Calendly state
  calendlyStatus, setCalendlyStatus,
  calendlyEventTypes, setCalendlyEventTypes,
  calendarMappings, setCalendarMappings,
  loadingCalendly, setLoadingCalendly,
  selectedStage, setSelectedStage,
  selectedEventType, setSelectedEventType,
  calendlySettings, setCalendlySettings,
  // Functions
  checkGmailStatus, connectGmail, disconnectGmail,
  checkMicrosoftStatus, connectMicrosoft365, disconnectMicrosoft,
  syncMicrosoftNow, syncMicrosoftCalendar,
  fetchMicrosoftOAuthConfig, saveMicrosoftOAuthConfig,
  fetchEmailProcessingSettings, saveEmailProcessingSettings,
  fetchCalendlyStatus, connectCalendly, disconnectCalendly,
  updateCalendlySettings, fetchCalendlyEventTypes,
  fetchCalendarMappings, createCalendarMapping,
}) => {
  // Simple "coming soon" integrations
  const simpleIntegrations = {
    'teams': { title: 'Microsoft Teams Integration', desc: 'Send messages, make calls, and collaborate with your team' },
    'salesforce': { title: 'Salesforce Integration', desc: 'Sync contacts and deals with your Salesforce CRM' },
    'hubspot': { title: 'HubSpot Integration', desc: 'Marketing automation and lead nurturing' },
    'mailchimp': { title: 'Mailchimp Integration', desc: 'Email marketing campaigns for your clients' },
    'ringcentral': { title: 'RingCentral Integration', desc: 'Click-to-call and SMS via RingCentral phone system' },
    'slack': { title: 'Slack Integration', desc: 'Get notifications and updates in your Slack workspace' },
    'synthflow': { title: 'Synthflow AI Integration', desc: 'AI-powered voice agents for automated client calls and lead qualification' },
    'recallai': { title: 'Recall.ai Integration', desc: 'Record and transcribe meetings from Zoom, Teams, and Google Meet with AI' },
    'stripe': { title: 'Stripe Integration', desc: 'Collect payments and processing fees' },
    'quickbooks': { title: 'QuickBooks Integration', desc: 'Sync financial data and commission tracking' },
    'google-calendar': { title: 'Google Calendar Integration', desc: 'Sync appointments with Google Calendar' },
    'google-drive': { title: 'Google Drive Integration', desc: 'Store and share loan documents in Google Drive' },
    'docusign': { title: 'DocuSign Integration', desc: 'Send and sign loan documents electronically' },
  };

  // For simple placeholder integrations, render a generic card
  if (simpleIntegrations[activeSection]) {
    const info = simpleIntegrations[activeSection];
    return (
      <div className="integration-detail-section">
        <h2>{info.title}</h2>
        <p className="section-description">{info.desc}</p>
        <div className="integration-connect-card">
          <h3>Connect {info.title.replace(' Integration', '')}</h3>
          <p>This integration is available for configuration.</p>
          <div className="connect-form">
            <button className="btn-connect" disabled>Coming Soon</button>
          </div>
        </div>
      </div>
    );
  }

  // Zoom - has a form
  if (activeSection === 'zoom') {
    return (
      <div className="integration-detail-section">
        <h2>Zoom Integration</h2>
        <p className="section-description">Host virtual meetings and consultations with clients</p>
        <div className="integration-connect-card">
          <h3>Connect Zoom</h3>
          <p>Connect your Zoom account to schedule and host virtual meetings with clients</p>
          <div className="connect-form">
            <div className="form-group">
              <label>Zoom API Key</label>
              <input type="text" className="form-input" placeholder="Enter your Zoom API Key" />
            </div>
            <div className="form-group">
              <label>Zoom API Secret</label>
              <input type="password" className="form-input" placeholder="Enter your Zoom API Secret" />
            </div>
            <button className="btn-connect">Connect Zoom</button>
          </div>
        </div>
        <div className="integration-features" style={{marginTop: '24px'}}>
          <h4>Features</h4>
          <ul>
            <li>Schedule Zoom meetings from CRM</li>
            <li>Auto-generate meeting links for appointments</li>
            <li>Send meeting invites to clients</li>
            <li>Track meeting attendance and duration</li>
          </ul>
        </div>
      </div>
    );
  }

  // Zapier
  if (activeSection === 'zapier') {
    return (
      <div className="integration-detail-section">
        <h2>Zapier Integration</h2>
        <p className="section-description">Connect with 5,000+ apps through automated workflows</p>
        <div className="integration-connect-card">
          <h3>Connect Zapier</h3>
          <p>Use your API key to connect this CRM with Zapier</p>
          <div className="info-box">
            <p>Go to <strong>Settings - API Keys</strong> to generate an API key for Zapier integration.</p>
            <button className="btn-secondary" onClick={() => setActiveSection('api-keys')}>Go to API Keys</button>
          </div>
        </div>
        <div className="integration-features" style={{marginTop: '24px'}}>
          <h4>Popular Zaps</h4>
          <ul>
            <li>Create lead from new email</li>
            <li>Add lead to Google Sheets</li>
            <li>Send SMS when lead stage changes</li>
            <li>Create calendar event for appointments</li>
            <li>Notify team on Slack for new leads</li>
          </ul>
        </div>
      </div>
    );
  }

  // Gmail
  if (activeSection === 'gmail') {
    return (
      <div className="integration-detail-section">
        <h2>Gmail Integration</h2>
        <p className="section-description">Sync Gmail emails and automatically extract lead information with AI</p>
        {gmailStatus.connected ? (
          <div className="connection-status-card connected gmail">
            <div className="connection-status-header">
              <div className="connection-status-indicator"></div>
              <div className="connection-status-info">
                <h3>Gmail Connected</h3>
                <p className="connection-email">{gmailStatus.email}</p>
              </div>
              <div className="connection-actions">
                <button className="btn-sync" onClick={async () => {
                  setLoadingGmail(true);
                  try {
                    const response = await fetch(`${API_BASE_URL}/api/v1/gmail/sync?days_back=7&max_results=100`, {
                      method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}` }
                    });
                    const data = await response.json();
                    if (response.ok) { toast.success(`Gmail sync complete! ${data.processed_count} emails processed.`); }
                    else { toast.error(`Sync failed: ${data.detail || 'Unknown error'}`); }
                  } catch (error) { console.error('Gmail sync error:', error); toast.error('Failed to sync Gmail'); }
                  finally { setLoadingGmail(false); }
                }} disabled={loadingGmail}>{loadingGmail ? 'Syncing...' : 'Sync Now'}</button>
                <button className="btn-disconnect" onClick={disconnectGmail} disabled={loadingGmail}>Disconnect</button>
              </div>
            </div>
            {gmailStatus.connected_at && (<div className="connection-meta">Connected: {new Date(gmailStatus.connected_at).toLocaleString()}</div>)}
          </div>
        ) : (
          <div className="connection-prompt-card">
            <h3>Connect Gmail</h3>
            <p>Connect your Gmail account to sync emails and extract lead information automatically</p>
            <button className="btn-connect" onClick={connectGmail} disabled={loadingGmail}>{loadingGmail ? 'Connecting...' : 'Connect Gmail'}</button>
          </div>
        )}
        <div className="integration-features" style={{marginTop: '24px'}}>
          <h4>Features</h4>
          <ul>
            <li>Automatic email sync every 5 minutes</li>
            <li>AI-powered lead extraction</li>
            <li>Mortgage-related email detection</li>
            <li>Auto-link to existing leads and loans</li>
          </ul>
        </div>
      </div>
    );
  }

  // Outlook Email
  if (activeSection === 'outlook-email') {
    return (
      <div className="integration-detail-section">
        <h2>Outlook Email Integration</h2>
        <p className="section-description">Sync your Microsoft 365 / Outlook emails and automatically link them to loan files</p>

        <div className="settings-card" style={{marginBottom: '24px'}}>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
            <h3 style={{margin: 0}}>Microsoft Azure App Configuration</h3>
            <button className="btn-secondary" onClick={() => setShowMicrosoftConfig(!showMicrosoftConfig)}>
              {showMicrosoftConfig ? 'Hide Configuration' : 'Configure Azure App'}
            </button>
          </div>
          {microsoftOAuthConfig.client_id && !showMicrosoftConfig && (
            <div style={{color: '#22c55e', fontSize: '14px'}}>App configured (Client ID: {microsoftOAuthConfig.client_id.substring(0, 8)}...)</div>
          )}
          {showMicrosoftConfig && (
            <div className="oauth-config-form">
              {microsoftConfigMessage.text && (<div className={`message-banner ${microsoftConfigMessage.type}`} style={{marginBottom: '16px'}}>{microsoftConfigMessage.text}</div>)}
              <p style={{fontSize: '14px', color: '#666', marginBottom: '16px'}}>
                Enter your Microsoft Azure App credentials. You can get these from the
                <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" target="_blank" rel="noopener noreferrer" style={{marginLeft: '4px'}}>Azure Portal App Registrations</a>
              </p>
              <div className="form-group">
                <label>Application (Client) ID *</label>
                <input type="text" value={microsoftOAuthConfig.client_id} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_id: e.target.value})} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                <small>Found in Azure Portal &gt; App registrations &gt; Your App &gt; Overview</small>
              </div>
              <div className="form-group">
                <label>Client Secret *</label>
                <input type="password" value={microsoftOAuthConfig.client_secret} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_secret: e.target.value})} placeholder="Enter client secret (or leave blank to keep existing)" />
                <small>Found in Azure Portal &gt; App registrations &gt; Your App &gt; Certificates & secrets</small>
              </div>
              <div className="form-group">
                <label>Tenant ID</label>
                <input type="text" value={microsoftOAuthConfig.tenant_id} onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, tenant_id: e.target.value})} placeholder="common (for multi-tenant apps)" />
                <small>Use "common" for multi-tenant apps, or your specific tenant ID</small>
              </div>
              <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f0f9ff', borderRadius: '8px', border: '1px solid #bae6fd'}}>
                <h4 style={{margin: '0 0 8px 0', fontSize: '14px', color: '#0369a1'}}>Required Redirect URI</h4>
                <p style={{margin: 0, fontSize: '13px', color: '#0c4a6e'}}>Add this redirect URI to your Azure App:</p>
                <code style={{display: 'block', marginTop: '8px', padding: '8px', backgroundColor: '#fff', borderRadius: '4px', fontSize: '12px'}}>{window.location.origin}/oauth/callback</code>
              </div>
              <div style={{marginTop: '16px', display: 'flex', gap: '12px'}}>
                <button className="btn-primary" onClick={saveMicrosoftOAuthConfig} disabled={savingMicrosoftConfig || !microsoftOAuthConfig.client_id}>
                  {savingMicrosoftConfig ? 'Saving...' : 'Save Configuration'}
                </button>
                <button className="btn-secondary" onClick={() => setShowMicrosoftConfig(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>

        {microsoftStatus.connected ? (
          <div className="connection-status-card connected outlook">
            <div className="connection-status-header">
              <div className="connection-status-indicator"></div>
              <div className="connection-status-info"><h3>Outlook Connected</h3><p className="connection-email">{microsoftStatus.email}</p></div>
              <div className="connection-actions">
                <button className="btn-sync" onClick={syncMicrosoftNow} disabled={syncingMicrosoft}>{syncingMicrosoft ? 'Syncing...' : 'Sync Now'}</button>
                <button className="btn-disconnect" onClick={disconnectMicrosoft} disabled={loadingMicrosoft}>Disconnect</button>
              </div>
            </div>
            {microsoftStatus.last_sync_at && (<div className="connection-meta">Last Sync: {new Date(microsoftStatus.last_sync_at).toLocaleString()}</div>)}
            {microsoftStatus.connected_at && (<div className="connection-meta">Connected: {new Date(microsoftStatus.connected_at).toLocaleString()}</div>)}
          </div>
        ) : (
          <div className="connection-prompt-card">
            <h3>Connect Outlook</h3>
            <p>Connect your Microsoft 365 / Outlook account to sync emails with loan files automatically</p>
            {!microsoftOAuthConfig.client_id && (<p style={{color: '#f59e0b', fontSize: '14px', marginBottom: '12px'}}>Please configure your Azure App credentials above before connecting.</p>)}
            <button className="btn-connect" onClick={connectMicrosoft365} disabled={loadingMicrosoft || !microsoftOAuthConfig.client_id}>{loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}</button>
          </div>
        )}

        <div className="email-processing-settings" style={{ marginTop: '24px', padding: '20px', background: '#f9fafb', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
          <h4 style={{margin: '0 0 16px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937'}}>Email Processing Settings</h4>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', cursor: 'pointer', padding: '12px', background: 'white', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
            <input type="checkbox" checked={emailProcessingSettings.delete_from_inbox_after_processing} onChange={(e) => {
              const newSettings = { ...emailProcessingSettings, delete_from_inbox_after_processing: e.target.checked };
              saveEmailProcessingSettings(newSettings);
            }} disabled={savingEmailSettings} style={{ width: '20px', height: '20px', marginTop: '2px', accentColor: '#218D8D' }} />
            <div>
              <span style={{fontWeight: '500', color: '#1f2937', display: 'block'}}>Delete emails from inbox after processing</span>
              <span style={{fontSize: '13px', color: '#6b7280', marginTop: '4px', display: 'block'}}>When you approve or reject emails in the Reconciliation Center, they will also be moved to trash in your inbox. You can override this per-email when processing.</span>
            </div>
          </label>
          {emailProcessingSettings.delete_from_inbox_after_processing && (
            <div style={{ marginTop: '12px', padding: '12px', background: '#fef3c7', borderRadius: '8px', fontSize: '13px', color: '#92400e', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span>Warning:</span>
              <span>Emails will be moved to your Trash folder (not permanently deleted). You can recover them from Trash within 30 days.</span>
            </div>
          )}
        </div>

        <div className="integration-features" style={{marginTop: '24px'}}>
          <h4>Features</h4>
          <ul>
            <li>Automatic email sync with loan files</li>
            <li>AI-powered lead extraction</li>
            <li>Auto-link emails to existing loans</li>
            <li>Two-way email sync</li>
          </ul>
        </div>
      </div>
    );
  }

  // Outlook Calendar
  if (activeSection === 'outlook-calendar') {
    return (
      <div className="integration-detail-section">
        <h2>Outlook Calendar Integration</h2>
        <p className="section-description">Sync your Microsoft 365 / Outlook calendar events</p>
        {microsoftStatus.connected ? (
          <div className="connection-status-card connected outlook">
            <div className="connection-status-header">
              <div className="connection-status-indicator"></div>
              <div className="connection-status-info"><h3>Calendar Connected</h3><p className="connection-email">{microsoftStatus.email}</p></div>
              <div className="connection-actions">
                <button className="btn-sync" onClick={syncMicrosoftCalendar} disabled={syncingCalendar}>{syncingCalendar ? 'Syncing...' : 'Sync Calendar'}</button>
              </div>
            </div>
          </div>
        ) : (
          <div className="connection-prompt-card">
            <h3>Connect Outlook Calendar</h3>
            <p>Connect your Microsoft 365 / Outlook account to sync calendar events</p>
            <button className="btn-connect" onClick={connectMicrosoft365} disabled={loadingMicrosoft}>{loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}</button>
          </div>
        )}
        <div className="integration-features" style={{marginTop: '24px'}}>
          <h4>Features</h4>
          <ul><li>Sync calendar events with CRM</li><li>Schedule appointments with borrowers</li><li>Automatic reminders</li></ul>
        </div>
      </div>
    );
  }

  // Calendly
  if (activeSection === 'calendly') {
    return (
      <div className="calendar-settings-section">
        <h2>Calendly Integration</h2>
        <p className="section-description">Connect Calendly and configure AI scheduling for automatic appointment booking</p>

        <div className="calendly-connection-card">
          <div className="connection-header">
            <div className="connection-icon" style={{background: '#006bff'}}>C</div>
            <div className="connection-info">
              <h3>Calendly Connection</h3>
              {calendlyStatus.isConnected ? (
                <p>Connected as <strong>{calendlyStatus.userName}</strong> ({calendlyStatus.userEmail})</p>
              ) : (
                <p>Connect your Calendly account to sync calendars and manage appointments</p>
              )}
            </div>
            <div className="connection-status">
              {calendlyStatus.isConnected ? (<span className="status-badge connected">Connected</span>) : (<span className="status-badge disconnected">Not Connected</span>)}
            </div>
          </div>
          <div className="connection-actions">
            {calendlyStatus.isConnected ? (
              <>
                <button className="btn-refresh" onClick={fetchCalendlyStatus} disabled={loadingCalendly}>{loadingCalendly ? 'Refreshing...' : 'Refresh'}</button>
                <button className="btn-disconnect" onClick={disconnectCalendly} disabled={loadingCalendly} style={{ marginLeft: '8px', background: '#dc3545', color: '#fff' }}>Disconnect</button>
                <span className="connection-detail" style={{ marginLeft: '12px' }}>{calendlyEventTypes.length} event types available</span>
              </>
            ) : (
              <button className="btn-connect-calendly" onClick={connectCalendly} disabled={loadingCalendly}>{loadingCalendly ? 'Connecting...' : 'Connect with Calendly'}</button>
            )}
          </div>
        </div>

        {calendlyStatus.isConnected && (
          <div className="calendly-settings-card" style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '24px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '16px' }}>Integration Settings</h3>
            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label>Default Event Type for AI Scheduling</label>
              <select value={calendlySettings.selectedEventTypeUri || ''} onChange={(e) => {
                setCalendlySettings(prev => ({ ...prev, selectedEventTypeUri: e.target.value }));
                updateCalendlySettings({ selected_event_type_uri: e.target.value });
              }} className="form-select" disabled={loadingCalendly || calendlyEventTypes.length === 0} style={{ width: '100%', padding: '10px', marginTop: '8px' }}>
                <option value="">Select default event type...</option>
                {calendlyEventTypes.map(eventType => {
                  const uuid = eventType.uri.split('/').pop();
                  return (<option key={uuid} value={eventType.uri}>{eventType.name} ({eventType.duration} min)</option>);
                })}
              </select>
              <p style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>This event type will be used when the AI schedules appointments</p>
            </div>
            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input type="checkbox" checked={calendlyStatus.syncToSmartScheduler} onChange={(e) => updateCalendlySettings({ sync_to_smart_scheduler: e.target.checked })} style={{ marginRight: '8px' }} />
                Sync Calendly bookings to Smart Scheduler
              </label>
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input type="checkbox" checked={calendlyStatus.autoCreateContacts} onChange={(e) => updateCalendlySettings({ auto_create_contacts: e.target.checked })} style={{ marginRight: '8px' }} />
                Auto-create contacts from Calendly bookings
              </label>
            </div>
          </div>
        )}

        <div className="info-card">
          <div className="info-content">
            <h3>How AI Scheduling Works</h3>
            <p>When AI schedules appointments with leads, it automatically selects the right calendar based on the lead's current stage.</p>
            <ul>
              <li><strong>New Lead</strong> - Discovery Call (30 min)</li>
              <li><strong>Qualified</strong> - Consultation (60 min)</li>
              <li><strong>Application Started</strong> - Application Review (45 min)</li>
            </ul>
          </div>
        </div>

        <div className="mapping-form-card">
          <h3>Create Calendar Mapping</h3>
          <div className="mapping-form">
            <div className="form-row">
              <div className="form-group">
                <label>Lead Stage</label>
                <select value={selectedStage} onChange={(e) => setSelectedStage(e.target.value)} className="form-select">
                  <option value="">Select a stage...</option>
                  {LEAD_STAGES.map(stage => (<option key={stage.value} value={stage.value}>{stage.label}</option>))}
                </select>
              </div>
              <div className="form-group">
                <label>Calendly Event Type</label>
                {loadingCalendly ? (<div className="loading-spinner">Loading calendars...</div>) : (
                  <select value={selectedEventType} onChange={(e) => setSelectedEventType(e.target.value)} className="form-select" disabled={calendlyEventTypes.length === 0}>
                    <option value="">Select a calendar...</option>
                    {calendlyEventTypes.map(eventType => {
                      const uuid = eventType.uri.split('/').pop();
                      return (<option key={uuid} value={uuid}>{eventType.name} ({eventType.duration} min)</option>);
                    })}
                  </select>
                )}
              </div>
              <div className="form-actions">
                <button onClick={createCalendarMapping} disabled={!selectedStage || !selectedEventType} className="btn-save-mapping">Save Mapping</button>
              </div>
            </div>
          </div>
        </div>

        <div className="current-mappings-card">
          <h3>Current Mappings</h3>
          {calendarMappings.length === 0 ? (
            <div className="empty-state"><p>No calendar mappings configured yet.</p><p className="empty-hint">Create your first mapping above to get started.</p></div>
          ) : (
            <div className="mappings-table">
              <table>
                <thead><tr><th>Lead Stage</th><th>Calendar Type</th><th>Status</th></tr></thead>
                <tbody>
                  {calendarMappings.map(mapping => {
                    const stageLabel = LEAD_STAGES.find(s => s.value === mapping.stage)?.label || mapping.stage;
                    return (
                      <tr key={mapping.id}>
                        <td><div className="stage-cell"><span className="stage-badge">{stageLabel}</span></div></td>
                        <td><div className="calendar-cell"><strong>{mapping.event_type_name}</strong><br /><span className="calendar-uuid">{mapping.event_type_uuid}</span></div></td>
                        <td><span className="status-badge active">Active</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="help-card">
          <h4>Need Help?</h4>
          <p>To get your Calendly event types:</p>
          <ol>
            <li>Go to <a href="https://calendly.com/event_types/user/me" target="_blank" rel="noopener noreferrer">calendly.com/event_types</a></li>
            <li>Create different event types for each stage</li>
            <li>Come back here and map each stage to the appropriate event type</li>
            <li>The AI will automatically use the right calendar when scheduling!</li>
          </ol>
        </div>
      </div>
    );
  }

  return null;
};

export default IntegrationDetails;
