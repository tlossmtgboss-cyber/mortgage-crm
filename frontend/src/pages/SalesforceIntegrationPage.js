import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import { API_BASE_URL } from '../services/api';
import SalesforceFieldMapper from '../components/integrations/SalesforceFieldMapper';
import './SalesforceIntegrationPage.css';

const API_URL = API_BASE_URL;

// Target entities in CRM
const TARGET_ENTITIES = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'loan', label: 'Loan' },
  { value: 'application', label: 'Application' },
  { value: 'property', label: 'Property' },
];

function SalesforceIntegrationPage() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('overview');
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
  const [syncingToMum, setSyncingToMum] = useState(false);
  const [mumSyncResults, setMumSyncResults] = useState(null);
  const [includeAllFields, setIncludeAllFields] = useState(true);
  const [expandedObject, setExpandedObject] = useState(null);
  const [expandedFields, setExpandedFields] = useState([]);
  const [loadingFields, setLoadingFields] = useState(false);

  const token = localStorage.getItem('token');

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

        if (data.connected) {
          loadSchemas();
          loadMappings();
          loadMappingStats();
          loadSyncHistory();
          loadEmailSyncStatus();
          loadCalendarSyncStatus();
        }
      }
    } catch (err) {
      console.error('Failed to check connection status:', err);
    }
    setLoading(false);
  };

  const handleConnect = () => {
    const connectUrl = new URL(`${API_URL}/api/integrations/salesforce/connect`);
    connectUrl.searchParams.set('return_url', window.location.href);
    if (token) {
      connectUrl.searchParams.set('token', token);
    }
    window.location.href = connectUrl.toString();
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Salesforce? This will remove all field mappings.')) return;

    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/disconnect`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Salesforce disconnected');
        setConnectionStatus({ connected: false });
        setSchemas([]);
        setMappings([]);
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
      }
    } catch (err) {
      console.error('Failed to load schemas:', err);
    }
  };

  const discoverSchema = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/discover`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json().catch(() => null);
      if (res.ok && data?.status !== 'error') {
        toast.success('Schema discovery complete!');
        await loadSchemas();
      } else {
        const errMsg = data?.detail || 'Schema discovery failed';
        toast.error(errMsg);
      }
    } catch (err) {
      toast.error('Schema discovery failed: ' + (err.message || 'Network error'));
    }
    setLoading(false);
  };

  const toggleObjectExpand = async (objectName) => {
    if (expandedObject === objectName) {
      setExpandedObject(null);
      setExpandedFields([]);
      return;
    }
    setExpandedObject(objectName);
    setLoadingFields(true);
    try {
      const res = await fetch(
        `${API_URL}/api/integrations/salesforce/schema/objects/${objectName}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setExpandedFields(data.fields || []);
      }
    } catch (err) {
      console.error('Failed to load object fields:', err);
    }
    setLoadingFields(false);
  };

  const toggleObjectEnabled = async (objectName, enabled) => {
    try {
      const res = await fetch(
        `${API_URL}/api/integrations/salesforce/schema/objects/${objectName}/toggle`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ enabled })
        }
      );
      if (res.ok) {
        setSchemas(prev => prev.map(s =>
          s.name === objectName ? { ...s, enabled } : s
        ));
        toast.success(`${objectName} ${enabled ? 'enabled' : 'disabled'}`);
      } else {
        toast.error('Failed to update object');
      }
    } catch (err) {
      toast.error('Failed to update object');
    }
  };

  const loadSuggestions = async (objectName) => {
    setSelectedObject(objectName);
    try {
      const res = await fetch(
        `${API_URL}/api/integrations/salesforce/schema/objects/${objectName}/suggestions?include_all=${includeAllFields}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (err) {
      console.error('Failed to load suggestions:', err);
    }
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
      console.error('Failed to load mapping stats:', err);
    }
  };

  const loadSyncHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/sync-status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSyncHistory(data.recent_events || []);
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

  const acceptSuggestions = async (selectedMappings) => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings/batch`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mappings: selectedMappings.map(s => ({
            source_object: selectedObject,
            source_field: s.sourceField,
            target_entity: s.targetEntity,
            target_field: s.targetField,
            transform_type: 'direct'
          }))
        })
      });

      if (res.ok) {
        const result = await res.json();
        toast.success(`Created ${result.created} mappings`);
        await loadMappings();
        await loadMappingStats();
      }
    } catch (err) {
      toast.error('Failed to save mappings');
    }
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

  const activateIntegration = async () => {
    try {
      const res = await fetch(`${API_URL}/api/integrations/salesforce/activate`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Integration activated!');
        await checkConnectionStatus();
      }
    } catch (err) {
      toast.error('Failed to activate integration');
    }
  };

  const triggerSync = async (fullSync = false) => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/integrations/salesforce/sync?full=${fullSync}`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      if (res.ok) {
        const data = await res.json();
        toast.success(`Sync complete: ${data.records_processed} records processed`);
        await loadSyncHistory();
      }
    } catch (err) {
      toast.error('Sync failed');
    }
    setLoading(false);
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
        toast.success(`Synced ${data.emails_synced} emails`);
        await loadEmailSyncStatus();
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
        toast.success(`Synced ${data.events_synced} events and ${data.tasks_synced} tasks`);
        await loadCalendarSyncStatus();
      }
    } catch (err) {
      toast.error('Calendar sync failed');
    }
    setSyncingCalendar(false);
  };

  const importClosedLoans = async () => {
    setImportingClosedLoans(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/salesforce/import-closed-loans`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        if (data.status === 'started') {
          // Background job started - poll for status
          toast.success('Import started! Processing in background...');

          // Poll for completion (check every 5 seconds, up to 3 minutes)
          let attempts = 0;
          const maxAttempts = 36;
          const pollInterval = setInterval(async () => {
            attempts++;
            try {
              const statusRes = await fetch(`${API_URL}${data.check_status_url}`, {
                headers: { 'Authorization': `Bearer ${token}` }
              });
              const statusData = await statusRes.json();

              if (statusData.status === 'completed') {
                clearInterval(pollInterval);
                setImportResults(statusData.results);
                toast.success(statusData.results?.message || 'Import complete!');
                setImportingClosedLoans(false);
              } else if (statusData.status === 'failed') {
                clearInterval(pollInterval);
                toast.error('Import failed: ' + (statusData.error || 'Unknown error'));
                setImportingClosedLoans(false);
              } else if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                toast.info('Import still running. Check MUM Clients page for results.');
                setImportingClosedLoans(false);
              }
            } catch (pollErr) {
              console.error('Poll error:', pollErr);
            }
          }, 5000);
        } else {
          // Immediate result (old behavior)
          setImportResults(data);
          toast.success(data.message || `Imported ${data.imported} loans, updated ${data.updated}`);
          setImportingClosedLoans(false);
        }
      } else {
        console.error('Import closed loans error:', data);
        toast.error(data.detail || data.message || 'Import failed');
        setImportingClosedLoans(false);
      }
    } catch (err) {
      console.error('Import closed loans exception:', err);
      toast.error('Import failed: ' + (err.message || 'Network error'));
      setImportingClosedLoans(false);
    }
  };

  const syncToMum = async () => {
    setSyncingToMum(true);
    setMumSyncResults(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/salesforce/import-to-mum`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setMumSyncResults(data);
        toast.success(data.message || `Synced ${data.imported} loans to MUM Clients`);
      } else {
        console.error('Sync to MUM error:', data);
        toast.error(data.detail || data.message || 'Sync to MUM failed');
      }
    } catch (err) {
      console.error('Sync to MUM exception:', err);
      toast.error('Sync to MUM failed: ' + (err.message || 'Network error'));
    }
    setSyncingToMum(false);
  };

  // Render sidebar navigation
  const renderSidebar = () => (
    <div className="sf-sidebar">
      <div className="sf-sidebar-header">
        <div className="sf-logo">
          <svg viewBox="0 0 50 50" fill="currentColor" width="32" height="32">
            <path d="M20.9,8c2.2-2.3,5.2-3.7,8.6-3.7c4.2,0,7.9,2.2,10.1,5.6c1.8-0.8,3.8-1.2,5.9-1.2c8,0,14.5,6.5,14.5,14.5
              c0,8-6.5,14.5-14.5,14.5c-1.1,0-2.2-0.1-3.2-0.4c-1.8,3.1-5.1,5.2-9,5.2c-1.9,0-3.6-0.5-5.1-1.4c-1.8,2.9-5.1,4.9-8.8,4.9
              c-4.5,0-8.3-2.8-9.7-6.8c-0.8,0.2-1.6,0.3-2.4,0.3c-5.6,0-10.2-4.6-10.2-10.2c0-4.3,2.6-7.9,6.3-9.5c-0.2-1-0.3-2-0.3-3.1
              c0-7.2,5.8-13,13-13C17.6,3.7,19.5,5.4,20.9,8z"/>
          </svg>
          <span>Salesforce</span>
        </div>
        <span className={`sf-status ${connectionStatus?.connected ? 'connected' : 'disconnected'}`}>
          {connectionStatus?.connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <nav className="sf-nav">
        <button
          className={`sf-nav-item ${activeSection === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveSection('overview')}
        >
          <span className="sf-nav-icon">📊</span>
          Overview
        </button>
        <button
          className={`sf-nav-item ${activeSection === 'connection' ? 'active' : ''}`}
          onClick={() => setActiveSection('connection')}
        >
          <span className="sf-nav-icon">🔗</span>
          Connection
        </button>
        <button
          className={`sf-nav-item ${activeSection === 'schema' ? 'active' : ''}`}
          onClick={() => setActiveSection('schema')}
          disabled={!connectionStatus?.connected}
        >
          <span className="sf-nav-icon">📋</span>
          Schema & Objects
        </button>
        <button
          className={`sf-nav-item ${activeSection === 'mappings' ? 'active' : ''}`}
          onClick={() => setActiveSection('mappings')}
          disabled={!connectionStatus?.connected}
        >
          <span className="sf-nav-icon">🔀</span>
          Field Mappings
        </button>
        <button
          className={`sf-nav-item ${activeSection === 'sync' ? 'active' : ''}`}
          onClick={() => setActiveSection('sync')}
          disabled={!connectionStatus?.connected}
        >
          <span className="sf-nav-icon">🔄</span>
          Data Sync
        </button>
        <button
          className={`sf-nav-item ${activeSection === 'history' ? 'active' : ''}`}
          onClick={() => setActiveSection('history')}
          disabled={!connectionStatus?.connected}
        >
          <span className="sf-nav-icon">📜</span>
          History
        </button>
      </nav>

      <div className="sf-sidebar-footer">
        <button className="sf-back-btn" onClick={() => navigate('/settings/integrations')}>
          ← Back to Integrations
        </button>
      </div>
    </div>
  );

  // Render Overview section
  const renderOverview = () => (
    <div className="sf-section">
      <h1>Salesforce Integration</h1>
      <p className="sf-description">
        Connect your Salesforce org to sync leads, contacts, opportunities, and more.
      </p>

      <div className="sf-stats-grid">
        <div className="sf-stat-card">
          <div className="sf-stat-icon">{connectionStatus?.connected ? '✓' : '✗'}</div>
          <div className="sf-stat-info">
            <div className="sf-stat-value">{connectionStatus?.connected ? 'Connected' : 'Not Connected'}</div>
            <div className="sf-stat-label">Status</div>
          </div>
        </div>
        <div className="sf-stat-card">
          <div className="sf-stat-icon">📦</div>
          <div className="sf-stat-info">
            <div className="sf-stat-value">{schemas.length}</div>
            <div className="sf-stat-label">Objects Discovered</div>
          </div>
        </div>
        <div className="sf-stat-card">
          <div className="sf-stat-icon">🔗</div>
          <div className="sf-stat-info">
            <div className="sf-stat-value">{mappings.length}</div>
            <div className="sf-stat-label">Field Mappings</div>
          </div>
        </div>
        <div className="sf-stat-card">
          <div className="sf-stat-icon">⏰</div>
          <div className="sf-stat-info">
            <div className="sf-stat-value">
              {connectionStatus?.last_sync_at
                ? new Date(connectionStatus.last_sync_at).toLocaleDateString()
                : 'Never'}
            </div>
            <div className="sf-stat-label">Last Sync</div>
          </div>
        </div>
      </div>

      {connectionStatus?.connected && (
        <div className="sf-connection-info">
          <h3>Connection Details</h3>
          <div className="sf-info-grid">
            <div className="sf-info-item">
              <span className="sf-info-label">Organization ID:</span>
              <span className="sf-info-value">{connectionStatus.sf_org_id || 'N/A'}</span>
            </div>
            <div className="sf-info-item">
              <span className="sf-info-label">Username:</span>
              <span className="sf-info-value">{connectionStatus.sf_username || 'N/A'}</span>
            </div>
            <div className="sf-info-item">
              <span className="sf-info-label">Instance URL:</span>
              <span className="sf-info-value">{connectionStatus.instance_url || 'N/A'}</span>
            </div>
            <div className="sf-info-item">
              <span className="sf-info-label">Integration Status:</span>
              <span className={`sf-info-value status-${connectionStatus.status}`}>
                {connectionStatus.status}
              </span>
            </div>
          </div>
        </div>
      )}

      {!connectionStatus?.connected && (
        <div className="sf-cta-card">
          <h3>Get Started</h3>
          <p>Connect your Salesforce account to start syncing data with Perennia CRM.</p>
          <button className="sf-btn sf-btn-primary sf-btn-lg" onClick={handleConnect}>
            Connect Salesforce
          </button>
        </div>
      )}
    </div>
  );

  // Render Connection section
  const renderConnection = () => (
    <div className="sf-section">
      <h2>Connection Settings</h2>

      {connectionStatus?.connected ? (
        <div className="sf-card">
          <div className="sf-card-header success">
            <span className="sf-card-icon">✓</span>
            <span>Connected to Salesforce</span>
          </div>
          <div className="sf-card-body">
            <div className="sf-info-grid">
              <div className="sf-info-item">
                <span className="sf-info-label">Organization:</span>
                <span className="sf-info-value">{connectionStatus.sf_org_id}</span>
              </div>
              <div className="sf-info-item">
                <span className="sf-info-label">User:</span>
                <span className="sf-info-value">{connectionStatus.sf_username}</span>
              </div>
              <div className="sf-info-item">
                <span className="sf-info-label">Instance:</span>
                <span className="sf-info-value">{connectionStatus.instance_url}</span>
              </div>
              <div className="sf-info-item">
                <span className="sf-info-label">Connected:</span>
                <span className="sf-info-value">
                  {connectionStatus.connected_at
                    ? new Date(connectionStatus.connected_at).toLocaleString()
                    : 'Unknown'}
                </span>
              </div>
            </div>
          </div>
          <div className="sf-card-footer">
            <button className="sf-btn sf-btn-outline" onClick={handleConnect}>
              Reconnect
            </button>
            <button className="sf-btn sf-btn-danger" onClick={handleDisconnect}>
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        <div className="sf-card">
          <div className="sf-card-header">
            <span className="sf-card-icon">🔗</span>
            <span>Connect Your Salesforce Account</span>
          </div>
          <div className="sf-card-body">
            <p>Click the button below to authorize Perennia to access your Salesforce data.</p>
            <ul className="sf-feature-list">
              <li>Sync leads and contacts</li>
              <li>Import opportunities and deals</li>
              <li>Sync emails and calendar events</li>
              <li>Two-way data synchronization</li>
            </ul>
          </div>
          <div className="sf-card-footer">
            <button className="sf-btn sf-btn-primary sf-btn-lg" onClick={handleConnect}>
              Connect Salesforce
            </button>
          </div>
        </div>
      )}
    </div>
  );

  // Render Schema section
  const renderSchema = () => (
    <div className="sf-section">
      <div className="sf-section-header">
        <h2>Salesforce Objects</h2>
        <button
          className="sf-btn sf-btn-outline"
          onClick={discoverSchema}
          disabled={loading}
        >
          {loading ? 'Discovering...' : 'Refresh Schema'}
        </button>
      </div>

      {schemas.length === 0 ? (
        <div className="sf-empty-state">
          <div className="sf-empty-icon">📋</div>
          <h3>No Objects Discovered</h3>
          <p>Click "Refresh Schema" to scan your Salesforce org for available objects.</p>
          <button
            className="sf-btn sf-btn-primary"
            onClick={discoverSchema}
            disabled={loading}
          >
            Discover Schema
          </button>
        </div>
      ) : (
        <div className="sf-objects-list">
          {schemas.map(obj => (
            <div key={obj.name} className={`sf-object-card-wrapper ${obj.enabled === false ? 'disabled' : ''}`}>
              <div
                className={`sf-object-card ${expandedObject === obj.name ? 'expanded' : ''} ${obj.enabled === false ? 'disabled' : ''}`}
              >
                <div className="sf-object-card-content" onClick={() => toggleObjectExpand(obj.name)}>
                  <div className="sf-object-header">
                    <span className="sf-object-expand-icon">
                      {expandedObject === obj.name ? '\u25BC' : '\u25B6'}
                    </span>
                    <span className="sf-object-name">{obj.label || obj.name}</span>
                    {obj.custom && <span className="sf-badge">Custom</span>}
                  </div>
                  <div className="sf-object-meta">
                    <span>{obj.field_count || '?'} fields</span>
                    {obj.mapped_field_count > 0 && (
                      <span className="sf-mapped-count">
                        {obj.mapped_field_count} of {obj.field_count || '?'} mapped
                      </span>
                    )}
                  </div>
                </div>
                <label
                  className="sf-object-toggle"
                  onClick={(e) => e.stopPropagation()}
                  title={obj.enabled === false ? 'Enable this object in Field Mappings' : 'Disable this object from Field Mappings'}
                >
                  <input
                    type="checkbox"
                    checked={obj.enabled !== false}
                    onChange={(e) => toggleObjectEnabled(obj.name, e.target.checked)}
                  />
                  <span className="sf-toggle-label">
                    {obj.enabled === false ? 'Disabled' : 'Enabled'}
                  </span>
                </label>
              </div>
              {expandedObject === obj.name && (
                <div className="sf-object-fields">
                  {loadingFields ? (
                    <div className="sf-fields-loading">Loading fields...</div>
                  ) : expandedFields.length === 0 ? (
                    <div className="sf-fields-empty">No fields found</div>
                  ) : (
                    <table className="sf-fields-table">
                      <thead>
                        <tr>
                          <th>Field Name</th>
                          <th>Label</th>
                          <th>Type</th>
                          <th>Mapped</th>
                        </tr>
                      </thead>
                      <tbody>
                        {expandedFields.map((field, idx) => (
                          <tr key={idx} className="sf-field-row">
                            <td className="sf-field-api-name">{field.name}</td>
                            <td>{field.label || field.name}</td>
                            <td><span className="sf-field-type">{field.type || '—'}</span></td>
                            <td>
                              {field.mapped ? (
                                <span className="sf-field-mapped" title="Has active mapping">Mapped</span>
                              ) : (
                                <span className="sf-field-unmapped" title="No mapping">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render Mappings section
  const renderMappings = () => (
    <div className="sf-section">
      <h2>Field Mappings</h2>

      <div className="sf-mappings-layout">
        <div className="sf-mappings-sidebar">
          <h4>Select Object</h4>
          <label className="sf-checkbox-label">
            <input
              type="checkbox"
              checked={includeAllFields}
              onChange={(e) => {
                setIncludeAllFields(e.target.checked);
                if (selectedObject) {
                  loadSuggestions(selectedObject);
                }
              }}
            />
            Include all fields
          </label>
          <div className="sf-object-list">
            {schemas.filter(obj => obj.enabled !== false).map(obj => (
              <button
                key={obj.name}
                className={`sf-object-btn ${selectedObject === obj.name ? 'active' : ''}`}
                onClick={() => loadSuggestions(obj.name)}
              >
                {obj.label || obj.name}
                <span className="sf-field-count">{obj.field_count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="sf-mappings-content">
          {selectedObject && suggestions.length > 0 && (
            <div className="sf-suggestions">
              <div className="sf-suggestions-header">
                <h4>Suggested Mappings for {selectedObject}</h4>
                <div className="sf-suggestions-actions">
                  <button
                    className="sf-btn sf-btn-sm"
                    onClick={() => {
                      const allSelected = suggestions.map(s => ({
                        sourceField: s.sourceField,
                        targetEntity: s.targetEntity,
                        targetField: s.targetField
                      }));
                      acceptSuggestions(allSelected);
                    }}
                  >
                    Accept All
                  </button>
                </div>
              </div>
              <div className="sf-suggestions-list">
                {suggestions.slice(0, 20).map((s, idx) => (
                  <div key={idx} className="sf-suggestion-item">
                    <div className="sf-suggestion-source">
                      <span className="sf-field-name">{s.sourceField}</span>
                      <span className="sf-field-label">{s.sourceLabel}</span>
                    </div>
                    <div className="sf-suggestion-arrow">→</div>
                    <div className="sf-suggestion-target">
                      <span className="sf-entity">{s.targetEntity}</span>
                      <span className="sf-field">{s.targetField}</span>
                    </div>
                    <div className="sf-suggestion-confidence">
                      {Math.round(s.confidence * 100)}%
                    </div>
                    <button
                      className="sf-btn sf-btn-sm sf-btn-primary"
                      onClick={() => acceptSuggestions([s])}
                    >
                      Add
                    </button>
                  </div>
                ))}
              </div>
              {suggestions.length > 20 && (
                <p className="sf-more-hint">And {suggestions.length - 20} more fields...</p>
              )}
            </div>
          )}

          {mappings.length > 0 && (
            <div className="sf-current-mappings">
              <h4>Current Mappings ({mappings.length})</h4>
              <table className="sf-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Target</th>
                    <th>Transform</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mappings.map(m => (
                    <tr key={m.id}>
                      <td>
                        <div className="sf-mapping-source">
                          <span className="sf-object">{m.source_object}</span>
                          <span className="sf-field">{m.source_field}</span>
                        </div>
                      </td>
                      <td>
                        <div className="sf-mapping-target">
                          <span className="sf-entity">{m.target_entity}</span>
                          <span className="sf-field">{m.target_field}</span>
                        </div>
                      </td>
                      <td>{m.transform_type}</td>
                      <td>
                        <button
                          className="sf-btn sf-btn-sm sf-btn-danger"
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

          {mappings.length === 0 && !selectedObject && (
            <div className="sf-empty-state">
              <p>Select an object from the sidebar to configure field mappings.</p>
            </div>
          )}
        </div>
      </div>

      {mappingStats?.ready_to_activate && connectionStatus?.status !== 'active' && (
        <div className="sf-activate-bar">
          <span>Your integration is ready to be activated!</span>
          <button className="sf-btn sf-btn-success" onClick={activateIntegration}>
            Activate Integration
          </button>
        </div>
      )}
    </div>
  );

  // Render Sync section
  const renderSync = () => (
    <div className="sf-section">
      <h2>Data Synchronization</h2>

      <div className="sf-sync-grid">
        <div className="sf-sync-card">
          <h4>Leads & Opportunities</h4>
          <p>Sync contacts, leads, and opportunities from Salesforce</p>
          <div className="sf-sync-actions">
            <button
              className="sf-btn sf-btn-primary"
              onClick={() => triggerSync(false)}
              disabled={loading}
            >
              Incremental Sync
            </button>
            <button
              className="sf-btn sf-btn-outline"
              onClick={() => triggerSync(true)}
              disabled={loading}
            >
              Full Sync
            </button>
          </div>
        </div>

        <div className="sf-sync-card">
          <h4>Email History</h4>
          <p>Sync email conversations to client profiles</p>
          {emailSyncStatus?.total_synced_emails > 0 && (
            <p className="sf-sync-stat">{emailSyncStatus.total_synced_emails} emails synced</p>
          )}
          <div className="sf-sync-actions">
            <button
              className="sf-btn sf-btn-primary"
              onClick={syncEmails}
              disabled={syncingEmails}
            >
              {syncingEmails ? 'Syncing...' : 'Sync Emails'}
            </button>
          </div>
        </div>

        <div className="sf-sync-card">
          <h4>Calendar Events</h4>
          <p>Sync calendar events and tasks</p>
          {calendarSyncStatus?.total_synced_events > 0 && (
            <p className="sf-sync-stat">
              {calendarSyncStatus.total_synced_events} events, {calendarSyncStatus.total_synced_tasks} tasks synced
            </p>
          )}
          <div className="sf-sync-actions">
            <button
              className="sf-btn sf-btn-primary"
              onClick={syncCalendar}
              disabled={syncingCalendar}
            >
              {syncingCalendar ? 'Syncing...' : 'Sync Calendar'}
            </button>
          </div>
        </div>

        <div className="sf-sync-card highlight">
          <h4>Import Closed Loans</h4>
          <p>Bulk import all closed/funded loans from Salesforce</p>
          <div className="sf-sync-actions">
            <button
              className="sf-btn sf-btn-success sf-btn-lg"
              onClick={importClosedLoans}
              disabled={importingClosedLoans}
            >
              {importingClosedLoans ? 'Importing...' : 'Import All Closed Loans'}
            </button>
            <button
              className="sf-btn sf-btn-primary"
              onClick={syncToMum}
              disabled={syncingToMum}
              style={{ marginLeft: '10px' }}
            >
              {syncingToMum ? 'Syncing...' : 'Sync to MUM Clients'}
            </button>
          </div>
          {importResults && (
            <div className="sf-import-results">
              <p>Found: {importResults.total_found} | Imported: {importResults.imported} | Updated: {importResults.updated}{importResults.failed ? ` | Failed: ${importResults.failed}` : ''}</p>
              {importResults.mum_imported !== undefined && (
                <p>MUM Clients: {importResults.mum_imported} added</p>
              )}
              {importResults.errors && importResults.errors.length > 0 && (
                <details style={{marginTop: '8px', fontSize: '12px', color: '#c0392b'}}>
                  <summary>Errors ({importResults.errors.length})</summary>
                  <ul style={{maxHeight: '200px', overflow: 'auto', padding: '4px 16px'}}>
                    {importResults.errors.map((err, i) => (
                      <li key={i}>{typeof err === 'string' ? err : (err.error || err.name || JSON.stringify(err))}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
          {mumSyncResults && (
            <div className="sf-import-results">
              <p>MUM Sync: {mumSyncResults.imported} loans added to MUM Clients</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  // Render History section
  const renderHistory = () => (
    <div className="sf-section">
      <h2>Sync History</h2>

      {syncHistory.length === 0 ? (
        <div className="sf-empty-state">
          <p>No sync history yet. Run a sync to see results here.</p>
        </div>
      ) : (
        <table className="sf-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Status</th>
              <th>Records</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {syncHistory.map((h, idx) => (
              <tr key={idx}>
                <td>{new Date(h.created_at).toLocaleString()}</td>
                <td>{h.event_type}</td>
                <td>
                  <span className={`sf-status-badge ${h.status}`}>{h.status}</span>
                </td>
                <td>
                  {h.records_succeeded || 0}/{h.records_processed || 0}
                  {h.records_failed > 0 && <span className="sf-failed"> ({h.records_failed} failed)</span>}
                </td>
                <td>{h.duration_ms ? `${h.duration_ms}ms` : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );

  if (loading && !connectionStatus) {
    return (
      <div className="sf-page">
        <div className="sf-loading">
          <div className="sf-spinner"></div>
          <p>Loading Salesforce Integration...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="sf-page">
      {renderSidebar()}
      <div className="sf-main">
        {activeSection === 'overview' && renderOverview()}
        {activeSection === 'connection' && renderConnection()}
        {activeSection === 'schema' && renderSchema()}
        {activeSection === 'mappings' && (
          <SalesforceFieldMapper
            isConnected={connectionStatus?.status === 'connected' || connectionStatus?.status === 'active'}
            onMappingSaved={() => {
              toast.success('Field mapping updated');
              loadMappingStats();
            }}
          />
        )}
        {activeSection === 'sync' && renderSync()}
        {activeSection === 'history' && renderHistory()}
      </div>
    </div>
  );
}

export default SalesforceIntegrationPage;
