import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../../utils/toast';
import './SalesforceSetupWizard.css';
import { getToken } from '../../utils/tokenStore';

// Always use api.perenniaai.com for production API calls
const API_URL = window.location.hostname.includes('perenniaai.com')
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Target entities in CRM
const TARGET_ENTITIES = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'loan', label: 'Loan' },
  { value: 'application', label: 'Application' },
  { value: 'property', label: 'Property' },
];

// Transform types
const TRANSFORM_TYPES = [
  { value: 'direct', label: 'Direct Copy' },
  { value: 'picklist_map', label: 'Picklist Mapping' },
  { value: 'stage_map', label: 'Stage Mapping' },
  { value: 'date_format', label: 'Date Format' },
  { value: 'currency_convert', label: 'Currency' },
  { value: 'phone_format', label: 'Phone Format' },
];

function SalesforceSetupWizard({ onComplete }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [schemas, setSchemas] = useState([]);
  const [selectedObject, setSelectedObject] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [mappingStats, setMappingStats] = useState(null);
  const [syncHistory, setSyncHistory] = useState([]);
  const [emailSyncStatus, setEmailSyncStatus] = useState(null);
  const [calendarSyncStatus, setCalendarSyncStatus] = useState(null);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [importingClosedLoans, setImportingClosedLoans] = useState(false);
  const [importResults, setImportResults] = useState(null);
  const [connectionError, setConnectionError] = useState(false); // Track if Salesforce connection is broken
  const [includeAllFields, setIncludeAllFields] = useState(true); // Include all fields by default

  const token = getToken();

  // Check connection status on mount
  useEffect(() => {
    checkConnectionStatus();
  }, []);

  const checkConnectionStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConnectionStatus(data);

        // Determine initial step based on status
        if (!data.connected) {
          setStep(1);
        } else if (data.status === 'connected' || data.status === 'mapping_required') {
          loadSchemas();
          setStep(2);
        } else if (data.status === 'active') {
          loadMappings();
          loadMappingStats();
          loadSyncHistory();
          loadEmailSyncStatus();
          loadCalendarSyncStatus();
          setStep(4);
        }
      }
    } catch (err) {
      console.error('Failed to check connection status:', err);
    }
    setLoading(false);
  };

  const handleConnect = () => {
    // Redirect to OAuth - include token for authentication during redirect
    const connectUrl = new URL(`${API_URL}/api/integrations/salesforce/connect`);
    connectUrl.searchParams.set('return_url', window.location.href);
    if (token) {
      connectUrl.searchParams.set('token', token);
    }
    window.location.href = connectUrl.toString();
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Salesforce?')) return;

    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/disconnect`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Salesforce disconnected');
        setConnectionStatus({ connected: false });
        setStep(1);
      }
    } catch (err) {
      toast.error('Failed to disconnect');
    }
  };

  const loadSchemas = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSchemas(data.objects || []);
        setConnectionError(false);
        // If no schemas and needs discovery, user should click "Discover Schema"
        if (data.needs_discovery) {
          console.log('No schemas found - user should discover schema');
        }
      } else if (res.status === 400) {
        // Not connected - show connect button
        console.log('Salesforce not connected');
        setConnectionError(false);
        setStep(1);
      } else if (res.status === 500 || res.status === 401) {
        // Connection is broken - tokens may be expired
        console.error('Salesforce connection error:', res.status);
        const errorData = await res.json().catch(() => ({}));
        console.error('Error details:', errorData);
        setConnectionError(true);
      }
    } catch (err) {
      console.error('Failed to load schemas:', err);
      setConnectionError(true);
    }
  };

  const discoverSchema = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/discover`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Schema discovered successfully');
        setConnectionError(false);
        await loadSchemas();
        setStep(2);
      } else if (res.status === 500 || res.status === 401) {
        // Connection is broken - tokens may be expired
        setConnectionError(true);
        toast.error('Salesforce connection error. Please reconnect your account.');
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Failed to discover schema');
      }
    } catch (err) {
      toast.error('Failed to discover schema');
      setConnectionError(true);
    }
    setLoading(false);
  };

  const loadSuggestions = async (objectName, includeAll = includeAllFields) => {
    setSelectedObject(objectName);
    try {
      const url = new URL(`${API_URL}/api/integrations/salesforce/schema/objects/${objectName}/suggestions`);
      url.searchParams.set('include_all', includeAll.toString());

      const res = await fetch(url.toString(), {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSuggestions(data.suggestions || []);
        console.log(`Loaded ${data.total_fields || 0} field suggestions (include_all=${includeAll})`);
      }
    } catch (err) {
      console.error('Failed to load suggestions:', err);
    }
  };

  const acceptSuggestions = async (accepted) => {
    if (accepted.length === 0) {
      toast.warning('Please select at least one mapping');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings/bulk`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source_object: selectedObject,
          suggestions: accepted
        })
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(`Created ${data.mappings_created} mappings`);
        await loadMappings();
        await loadMappingStats();
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Failed to create mappings');
      }
    } catch (err) {
      toast.error('Failed to create mappings');
    }
    setLoading(false);
  };

  const loadMappings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMappings(data.mappings || []);
      }
    } catch (err) {
      console.error('Failed to load mappings:', err);
    }
  };

  const loadMappingStats = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings/stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMappingStats(data);
      }
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const loadSyncHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/sync/history?limit=10`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSyncHistory(data.history || []);
      }
    } catch (err) {
      console.error('Failed to load sync history:', err);
    }
  };

  const loadEmailSyncStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/email-sync-status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setEmailSyncStatus(data);
      }
    } catch (err) {
      console.error('Failed to load email sync status:', err);
    }
  };

  const loadCalendarSyncStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/calendar-sync-status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCalendarSyncStatus(data);
      }
    } catch (err) {
      console.error('Failed to load calendar sync status:', err);
    }
  };

  const syncEmails = async () => {
    setSyncingEmails(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/sync-emails`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || `Synced ${data.emails_synced} emails`);
        await loadEmailSyncStatus();
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Email sync failed');
      }
    } catch (err) {
      toast.error('Email sync failed');
    }
    setSyncingEmails(false);
  };

  const syncCalendar = async () => {
    setSyncingCalendar(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/sync-calendar`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || `Synced ${data.events_synced} events`);
        await loadCalendarSyncStatus();
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Calendar sync failed');
      }
    } catch (err) {
      toast.error('Calendar sync failed');
    }
    setSyncingCalendar(false);
  };

  const importClosedLoans = async () => {
    setImportingClosedLoans(true);
    setImportResults(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/salesforce/import-closed-loans`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setImportResults(data);
        toast.success(data.message || `Imported ${data.imported} closed loans`);
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Import failed');
      }
    } catch (err) {
      toast.error('Import closed loans failed');
    }
    setImportingClosedLoans(false);
  };

  const activateIntegration = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/activate`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success('Integration activated!');
        await checkConnectionStatus();
        setStep(4);
        if (onComplete) onComplete();
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Failed to activate');
      }
    } catch (err) {
      toast.error('Failed to activate integration');
    }
    setLoading(false);
  };

  const triggerSync = async (fullSync = false) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/sync`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ full_sync: fullSync })
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(`Sync completed: ${data.records_succeeded} records`);
        await loadSyncHistory();
      } else {
        const error = await res.json();
        toast.error(error.detail || 'Sync failed');
      }
    } catch (err) {
      toast.error('Sync failed');
    }
    setLoading(false);
  };

  const deleteMapping = async (mappingId) => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings/${mappingId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success('Mapping deleted');
        await loadMappings();
        await loadMappingStats();
      }
    } catch (err) {
      toast.error('Failed to delete mapping');
    }
  };

  // Render step 1: Connect to Salesforce
  const renderConnectStep = () => (
    <div className="setup-step">
      <div className="step-header">
        <h2>Connect Your Salesforce Account</h2>
        <p>Link your Salesforce organization to enable data synchronization</p>
      </div>

      <div className="connect-card">
        <div className="salesforce-logo">
          <svg viewBox="0 0 50 50" fill="currentColor">
            <path d="M20.9,8c2.2-2.3,5.2-3.7,8.6-3.7c4.2,0,7.9,2.2,10.1,5.6c1.8-0.8,3.8-1.2,5.9-1.2c8,0,14.5,6.5,14.5,14.5
              c0,8-6.5,14.5-14.5,14.5c-1.1,0-2.2-0.1-3.2-0.4c-1.8,3.1-5.1,5.2-9,5.2c-1.9,0-3.6-0.5-5.1-1.4c-1.8,2.9-5.1,4.9-8.8,4.9
              c-4.5,0-8.3-2.8-9.7-6.8c-0.8,0.2-1.6,0.3-2.4,0.3c-5.6,0-10.2-4.6-10.2-10.2c0-4.3,2.6-7.9,6.3-9.5c-0.2-1-0.3-2-0.3-3.1
              c0-7.2,5.8-13,13-13C17.6,3.7,19.5,5.4,20.9,8z"/>
          </svg>
        </div>

        {!connectionStatus?.connected ? (
          <>
            <h3>Not Connected</h3>
            <p>Click below to authorize Perennia to access your Salesforce data</p>
            <button className="btn btn-primary btn-lg" onClick={handleConnect}>
              Connect Salesforce
            </button>
          </>
        ) : (
          <>
            <h3>Connected</h3>
            <div className="connection-details">
              <p><strong>Organization:</strong> {connectionStatus.sf_org_id}</p>
              <p><strong>User:</strong> {connectionStatus.sf_username}</p>
              <p><strong>Instance:</strong> {connectionStatus.instance_url}</p>
            </div>
            <div className="button-group">
              <button className="btn btn-primary" onClick={() => setStep(2)}>
                Continue Setup
              </button>
              <button className="btn btn-outline-danger" onClick={handleDisconnect}>
                Disconnect
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );

  // Render step 2: Schema Discovery
  const renderSchemaStep = () => (
    <div className="setup-step">
      <div className="step-header">
        <h2>Discover Your Salesforce Schema</h2>
        <p>We'll scan your Salesforce org to find available objects and fields</p>
      </div>

      {/* If not connected or connection error, show connect button */}
      {!connectionStatus?.connected || connectionError ? (
        <div className="discovery-card">
          <h3>{connectionError ? 'Connection Error' : 'Connection Required'}</h3>
          <p>{connectionError
            ? 'Your Salesforce connection has expired or is invalid. Please reconnect your account.'
            : 'Please connect your Salesforce account first before discovering schema'
          }</p>
          <button
            className="btn btn-primary btn-lg"
            onClick={handleConnect}
          >
            {connectionError ? 'Reconnect Salesforce' : 'Connect Salesforce'}
          </button>
        </div>
      ) : schemas.length === 0 ? (
        <div className="discovery-card">
          <h3>Ready to Discover</h3>
          <p>Click below to scan your Salesforce organization</p>
          <button
            className="btn btn-primary btn-lg"
            onClick={discoverSchema}
            disabled={loading}
          >
            {loading ? 'Discovering...' : 'Discover Schema'}
          </button>
        </div>
      ) : (
        <>
          <div className="schema-list">
            <h3>Discovered Objects ({schemas.length})</h3>
            <div className="object-grid">
              {schemas.map(obj => (
                <div
                  key={obj.name}
                  className={`object-card ${selectedObject === obj.name ? 'selected' : ''}`}
                  onClick={() => loadSuggestions(obj.name)}
                >
                  <div className="object-name">{obj.label}</div>
                  <div className="object-meta">
                    {obj.field_count} fields
                    {obj.custom && <span className="badge">Custom</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="step-actions">
            <button className="btn btn-secondary" onClick={() => setStep(1)}>
              Back
            </button>
            <button className="btn btn-primary" onClick={() => setStep(3)}>
              Continue to Field Mapping
            </button>
          </div>
        </>
      )}
    </div>
  );

  // Render step 3: Field Mapping
  const renderMappingStep = () => (
    <div className="setup-step">
      <div className="step-header">
        <h2>Configure Field Mappings</h2>
        <p>Map your Salesforce fields to Perennia CRM fields</p>
      </div>

      <div className="mapping-layout">
        {/* Object selector sidebar */}
        <div className="object-sidebar">
          <h4>Salesforce Objects</h4>
          <label className="include-all-toggle" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', marginBottom: '12px', fontSize: '13px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={includeAllFields}
              onChange={(e) => {
                setIncludeAllFields(e.target.checked);
                if (selectedObject) {
                  loadSuggestions(selectedObject, e.target.checked);
                }
              }}
            />
            <span>Include all fields</span>
          </label>
          {schemas.map(obj => (
            <button
              key={obj.name}
              className={`object-btn ${selectedObject === obj.name ? 'active' : ''}`}
              onClick={() => loadSuggestions(obj.name)}
            >
              {obj.label} ({obj.field_count || '?'} fields)
            </button>
          ))}
        </div>

        {/* Mapping content */}
        <div className="mapping-content">
          {selectedObject && suggestions.length > 0 && (
            <SuggestionsList
              suggestions={suggestions}
              onAccept={acceptSuggestions}
            />
          )}

          {mappings.length > 0 && (
            <div className="existing-mappings">
              <h4>Current Mappings ({mappings.length})</h4>
              <table className="mappings-table">
                <thead>
                  <tr>
                    <th>Source Field</th>
                    <th>Target</th>
                    <th>Transform</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mappings.map(m => (
                    <tr key={m.id}>
                      <td>
                        <span className="source-object">{m.source_object}</span>
                        <span className="source-field">{m.source_field}</span>
                      </td>
                      <td>
                        <span className="target-entity">{m.target_entity}</span>
                        <span className="target-field">{m.target_field}</span>
                      </td>
                      <td>{m.transform_type}</td>
                      <td>
                        <span className={`status-badge ${m.validation_status}`}>
                          {m.validation_status}
                        </span>
                      </td>
                      <td>
                        <button
                          className="btn btn-sm btn-outline-danger"
                          onClick={() => deleteMapping(m.id)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="step-actions">
        <button className="btn btn-secondary" onClick={() => setStep(2)}>
          Back
        </button>
        {mappingStats?.ready_to_activate ? (
          <button className="btn btn-success" onClick={activateIntegration}>
            Activate Integration
          </button>
        ) : (
          <p className="activation-hint">
            Map required fields to activate integration
          </p>
        )}
      </div>
    </div>
  );

  // Render step 4: Active & Sync
  const renderActiveStep = () => (
    <div className="setup-step">
      <div className="step-header success">
        <h2>Integration Active</h2>
        <p>Your Salesforce integration is running</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{mappingStats?.total || 0}</div>
          <div className="stat-label">Field Mappings</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{Object.keys(mappingStats?.by_object || {}).length}</div>
          <div className="stat-label">Objects Mapped</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {connectionStatus?.last_sync_at
              ? new Date(connectionStatus.last_sync_at).toLocaleString()
              : 'Never'}
          </div>
          <div className="stat-label">Last Sync</div>
        </div>
      </div>

      <div className="sync-controls">
        <h3>Data Sync</h3>
        <div className="sync-section">
          <div className="sync-type">
            <h4>Leads & Opportunities</h4>
            <p className="sync-description">Sync contacts, leads, and opportunities from Salesforce</p>
            <div className="button-group">
              <button
                className="btn btn-primary"
                onClick={() => triggerSync(false)}
                disabled={loading}
              >
                {loading ? 'Syncing...' : 'Incremental Sync'}
              </button>
              <button
                className="btn btn-outline-primary"
                onClick={() => triggerSync(true)}
                disabled={loading}
              >
                Full Sync
              </button>
            </div>
          </div>

          <div className="sync-type">
            <h4>Emails</h4>
            <p className="sync-description">
              Sync email history from Salesforce to client profiles
              {emailSyncStatus?.total_synced_emails > 0 && (
                <span className="sync-stat"> ({emailSyncStatus.total_synced_emails} synced)</span>
              )}
            </p>
            <div className="button-group">
              <button
                className="btn btn-primary"
                onClick={syncEmails}
                disabled={syncingEmails}
              >
                {syncingEmails ? 'Syncing Emails...' : 'Sync Emails'}
              </button>
            </div>
            {emailSyncStatus?.last_sync && (
              <p className="last-sync-info">
                Last sync: {new Date(emailSyncStatus.last_sync.timestamp).toLocaleString()}
              </p>
            )}
          </div>

          <div className="sync-type">
            <h4>Calendar</h4>
            <p className="sync-description">
              Sync calendar events and tasks from Salesforce
              {calendarSyncStatus?.total_synced_events > 0 && (
                <span className="sync-stat"> ({calendarSyncStatus.total_synced_events} events, {calendarSyncStatus.total_synced_tasks} tasks synced)</span>
              )}
            </p>
            <div className="button-group">
              <button
                className="btn btn-primary"
                onClick={syncCalendar}
                disabled={syncingCalendar}
              >
                {syncingCalendar ? 'Syncing Calendar...' : 'Sync Calendar'}
              </button>
            </div>
            {calendarSyncStatus?.last_sync && (
              <p className="last-sync-info">
                Last sync: {new Date(calendarSyncStatus.last_sync.timestamp).toLocaleString()}
              </p>
            )}
          </div>

          <div className="sync-type import-closed-loans">
            <h4>Import Closed Loans</h4>
            <p className="sync-description">
              Import all closed/funded loans from Salesforce Opportunities into the CRM with all available fields.
              This is a one-time bulk import.
            </p>
            <div className="button-group">
              <button
                className="btn btn-success btn-lg"
                onClick={importClosedLoans}
                disabled={importingClosedLoans}
              >
                {importingClosedLoans ? 'Importing...' : 'Import All Closed Loans'}
              </button>
            </div>
            {importResults && (
              <div className="import-results">
                <p className="import-summary">
                  <strong>Import Complete:</strong> Found {importResults.total_found} loans in Salesforce
                </p>
                <div className="import-stats">
                  <span className="stat imported">New: {importResults.imported}</span>
                  <span className="stat updated">Updated: {importResults.updated}</span>
                  {importResults.failed > 0 && (
                    <span className="stat failed">Failed: {importResults.failed}</span>
                  )}
                </div>
                {importResults.errors?.length > 0 && (
                  <details className="import-errors">
                    <summary>View Errors ({importResults.errors.length})</summary>
                    <ul>
                      {importResults.errors.slice(0, 10).map((err, i) => (
                        <li key={i}>{err.salesforce_id}: {err.error}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {syncHistory.length > 0 && (
        <div className="sync-history">
          <h3>Recent Sync History</h3>
          <table className="history-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Status</th>
                <th>Records</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {syncHistory.map(h => (
                <tr key={h.id}>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`status-badge ${h.status}`}>{h.status}</span>
                  </td>
                  <td>
                    {h.records_succeeded}/{h.records_processed}
                    {h.records_failed > 0 && (
                      <span className="failed"> ({h.records_failed} failed)</span>
                    )}
                  </td>
                  <td>{h.duration_ms ? `${h.duration_ms}ms` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="step-actions">
        <button className="btn btn-secondary" onClick={() => setStep(3)}>
          Edit Mappings
        </button>
        <button className="btn btn-outline-danger" onClick={handleDisconnect}>
          Disconnect
        </button>
      </div>
    </div>
  );

  // Progress indicator
  const renderProgress = () => (
    <div className="setup-progress">
      <div className={`progress-step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}>
        <div className="step-number">1</div>
        <div className="step-label">Connect</div>
      </div>
      <div className="progress-line" />
      <div className={`progress-step ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}>
        <div className="step-number">2</div>
        <div className="step-label">Discover</div>
      </div>
      <div className="progress-line" />
      <div className={`progress-step ${step >= 3 ? 'active' : ''} ${step > 3 ? 'completed' : ''}`}>
        <div className="step-number">3</div>
        <div className="step-label">Map Fields</div>
      </div>
      <div className="progress-line" />
      <div className={`progress-step ${step >= 4 ? 'active' : ''}`}>
        <div className="step-number">4</div>
        <div className="step-label">Active</div>
      </div>
    </div>
  );

  if (loading && step === 1) {
    return (
      <div className="salesforce-setup-wizard">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="salesforce-setup-wizard">
      {renderProgress()}

      {step === 1 && renderConnectStep()}
      {step === 2 && renderSchemaStep()}
      {step === 3 && renderMappingStep()}
      {step === 4 && renderActiveStep()}
    </div>
  );
}

// Suggestions list component
function SuggestionsList({ suggestions, onAccept }) {
  const [selected, setSelected] = useState(
    suggestions.reduce((acc, s) => ({ ...acc, [s.sourceField]: s.confidence >= 0.9 }), {})
  );

  const toggleSelection = (sourceField) => {
    setSelected(prev => ({ ...prev, [sourceField]: !prev[sourceField] }));
  };

  const selectAll = () => {
    setSelected(suggestions.reduce((acc, s) => ({ ...acc, [s.sourceField]: true }), {}));
  };

  const selectNone = () => {
    setSelected(suggestions.reduce((acc, s) => ({ ...acc, [s.sourceField]: false }), {}));
  };

  const handleAccept = () => {
    const accepted = suggestions
      .filter(s => selected[s.sourceField])
      .map(s => ({
        sourceField: s.sourceField,
        targetEntity: s.targetEntity,
        targetField: s.targetField
      }));
    onAccept(accepted);
  };

  if (suggestions.length === 0) {
    return null;
  }

  const selectedCount = Object.values(selected).filter(Boolean).length;

  return (
    <div className="suggestions-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h4 style={{ margin: 0 }}>Suggested Mappings ({suggestions.length} fields)</h4>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={selectAll}
            style={{
              padding: '6px 12px',
              backgroundColor: '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500'
            }}
          >
            ✓ Select All
          </button>
          <button
            onClick={selectNone}
            style={{
              padding: '6px 12px',
              backgroundColor: '#f5f5f5',
              color: '#333',
              border: '1px solid #ddd',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            Clear All
          </button>
        </div>
      </div>
      <p style={{ margin: '0 0 12px 0', color: '#666' }}>
        {selectedCount} of {suggestions.length} fields selected for import
      </p>

      <div className="suggestions-list">
        {suggestions.map(s => (
          <div
            key={s.sourceField}
            className={`suggestion-item ${selected[s.sourceField] ? 'selected' : ''}`}
            onClick={() => toggleSelection(s.sourceField)}
          >
            <input
              type="checkbox"
              checked={selected[s.sourceField] || false}
              onChange={() => {}}
            />
            <div className="suggestion-fields">
              <span className="sf-field">{s.sourceField}</span>
              <span className="arrow">→</span>
              <span className="crm-field">{s.targetEntity}.{s.targetField}</span>
            </div>
            <div className="confidence">
              <span className={`confidence-badge ${s.confidence >= 0.9 ? 'high' : s.confidence >= 0.7 ? 'medium' : 'low'}`}>
                {Math.round(s.confidence * 100)}%
              </span>
              <span className="reason">{s.reason}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}>
        <button
          onClick={handleAccept}
          disabled={selectedCount === 0}
          style={{
            padding: '10px 24px',
            backgroundColor: selectedCount > 0 ? '#2196F3' : '#ccc',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: selectedCount > 0 ? 'pointer' : 'not-allowed',
            fontSize: '14px',
            fontWeight: '600'
          }}
        >
          Import {selectedCount} Field Mappings
        </button>
        {selectedCount === 0 && (
          <span style={{ color: '#999', fontSize: '13px' }}>Select at least one field to import</span>
        )}
      </div>
    </div>
  );
}

export default SalesforceSetupWizard;
