import React, { useState, useEffect } from 'react';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import './IntegrationSettings.css';

const API_URL = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

const IntegrationSettings = () => {
  const [activeTab, setActiveTab] = useState('all');
  const [integrations, setIntegrations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedIntegration, setSelectedIntegration] = useState(null);
  const [configMode, setConfigMode] = useState(false);
  const [credentials, setCredentials] = useState({});
  const [config, setConfig] = useState({});
  const [syncHistory, setSyncHistory] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');

  const { execute: fetchIntegrations, loading, error } = useAsyncOperation({ showErrorToast: false });
  const { execute: saveConfig, loading: saving } = useFormSubmit({ showErrorToast: false, showSuccessToast: false });

  useEffect(() => {
    loadIntegrations();
    loadCategories();
  }, []);

  const loadIntegrations = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchIntegrations(async () => {
        const res = await fetch(`${API_URL}/api/v1/integration-settings`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) {
          const error = await res.json();
          throw new APIError(error.detail?.message || 'Failed to load integrations', res.status);
        }
        return res.json();
      });

      if (response?.data?.integrations) {
        setIntegrations(response.data.integrations);
      }
    } catch (err) {
      toast.error(err.message || 'Failed to load integrations');
    }
  };

  const loadCategories = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/categories`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCategories(data.data || []);
      }
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  };

  const loadIntegrationDetails = async (integrationId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${integrationId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedIntegration(data.data);
        setConfig(data.data.config || {});
        loadSyncHistory(integrationId);
      }
    } catch (err) {
      toast.error('Failed to load integration details');
    }
  };

  const loadSyncHistory = async (integrationId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${integrationId}/sync-history`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSyncHistory(data.data?.history || []);
      }
    } catch (err) {
      console.error('Failed to load sync history:', err);
    }
  };

  const handleConnect = async (integrationId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${integrationId}/connect`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        if (data.data.auth_type === 'oauth2' && data.data.oauth_url) {
          // Redirect to OAuth
          window.open(data.data.oauth_url, '_blank');
          toast.success('OAuth window opened. Complete authorization to connect.');
        } else {
          toast.success('Integration connected successfully');
          loadIntegrations();
        }
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to connect');
      }
    } catch (err) {
      toast.error('Failed to connect integration');
    }
  };

  const handleDisconnect = async (integrationId) => {
    if (!window.confirm('Are you sure you want to disconnect this integration?')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${integrationId}/disconnect`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success('Integration disconnected');
        loadIntegrations();
        setSelectedIntegration(null);
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to disconnect');
      }
    } catch (err) {
      toast.error('Failed to disconnect integration');
    }
  };

  const handleSaveCredentials = async () => {
    if (!selectedIntegration) return;

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${selectedIntegration.id}/credentials`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(credentials)
      });

      if (res.ok) {
        toast.success('Credentials saved securely');
        setCredentials({});
        loadIntegrationDetails(selectedIntegration.id);
      } else {
        const error = await res.json();
        if (error.detail?.errors) {
          const fieldErrors = error.detail.errors.map(e => `${e.field}: ${e.message}`).join('\n');
          toast.error(`Validation errors:\n${fieldErrors}`);
        } else {
          toast.error(error.detail?.message || 'Failed to save credentials');
        }
      }
    } catch (err) {
      toast.error('Failed to save credentials');
    }
  };

  const handleSaveConfig = async () => {
    if (!selectedIntegration) return;

    try {
      const token = localStorage.getItem('token');
      await saveConfig(async () => {
        const res = await fetch(`${API_URL}/api/v1/integration-settings/${selectedIntegration.id}/config`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            integration_id: selectedIntegration.id,
            ...config
          })
        });

        if (!res.ok) {
          const error = await res.json();
          throw new APIError(error.detail?.message || 'Failed to save configuration', res.status);
        }
        return res.json();
      });

      toast.success('Configuration saved');
      setConfigMode(false);
    } catch (err) {
      toast.error(err.message || 'Failed to save configuration');
    }
  };

  const handleTriggerSync = async () => {
    if (!selectedIntegration) return;

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${selectedIntegration.id}/sync?sync_type=incremental`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(`Sync triggered (ID: ${data.data.sync_id})`);
        loadSyncHistory(selectedIntegration.id);
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to trigger sync');
      }
    } catch (err) {
      toast.error('Failed to trigger sync');
    }
  };

  const handleTestConnection = async () => {
    if (!selectedIntegration) return;

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/integration-settings/${selectedIntegration.id}/test`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        if (data.data.test_passed) {
          toast.success(`Connection test passed (${data.data.latency_ms}ms)`);
        } else {
          toast.error('Connection test failed');
        }
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Connection test failed');
      }
    } catch (err) {
      toast.error('Connection test failed');
    }
  };

  const updateConfig = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const filteredIntegrations = integrations.filter(int => {
    const matchesSearch = !searchQuery ||
      int.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      int.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = activeTab === 'all' || int.category === activeTab;
    return matchesSearch && matchesCategory;
  });

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'status-connected';
      case 'error': return 'status-error';
      case 'pending': return 'status-pending';
      default: return 'status-disconnected';
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      crm: '👥',
      communication: '💬',
      calendar: '📅',
      storage: '📁',
      payment: '💳',
      marketing: '📧',
      productivity: '⚡',
      ai: '🤖',
      document: '📄'
    };
    return icons[category] || '🔌';
  };

  if (loading && integrations.length === 0) {
    return (
      <div className="integration-settings">
        <div className="loading-state">Loading integrations...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="integration-settings">
        <div className="error-state">
          <h3>Error Loading Integrations</h3>
          <p>{error.message}</p>
          <button onClick={loadIntegrations} className="btn-retry">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="integration-settings">
      <div className="page-header">
        <div className="header-content">
          <h1>Integration Settings</h1>
          <p>Connect and configure third-party services</p>
        </div>
        <div className="header-stats">
          <div className="stat-item">
            <span className="stat-value">{integrations.filter(i => i.status === 'connected').length}</span>
            <span className="stat-label">Connected</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{integrations.length}</span>
            <span className="stat-label">Available</span>
          </div>
        </div>
      </div>

      <div className="search-bar">
        <input
          type="text"
          placeholder="Search integrations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <div className="tabs-container">
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            All
          </button>
          {categories.map(cat => (
            <button
              key={cat.id}
              className={`tab ${activeTab === cat.id ? 'active' : ''}`}
              onClick={() => setActiveTab(cat.id)}
            >
              {getCategoryIcon(cat.id)} {cat.name}
            </button>
          ))}
        </div>
      </div>

      <div className="content-layout">
        <div className="integrations-grid">
          {filteredIntegrations.map(integration => (
            <div
              key={integration.id}
              className={`integration-card ${selectedIntegration?.id === integration.id ? 'selected' : ''}`}
              onClick={() => loadIntegrationDetails(integration.id)}
            >
              <div className="card-header">
                <div className="integration-icon">
                  {getCategoryIcon(integration.category)}
                </div>
                <div className={`status-badge ${getStatusColor(integration.status)}`}>
                  {integration.status}
                </div>
              </div>
              <div className="card-body">
                <h3>{integration.name}</h3>
                <p>{integration.description}</p>
              </div>
              <div className="card-footer">
                <span className="category-tag">{integration.category}</span>
                <span className="auth-type">{integration.auth_type}</span>
              </div>
            </div>
          ))}
        </div>

        {selectedIntegration && (
          <div className="integration-detail">
            <div className="detail-header">
              <div className="detail-title">
                <span className="detail-icon">{getCategoryIcon(selectedIntegration.category)}</span>
                <h2>{selectedIntegration.name}</h2>
                <span className={`status-badge ${getStatusColor(selectedIntegration.status)}`}>
                  {selectedIntegration.status}
                </span>
              </div>
              <button className="btn-close" onClick={() => setSelectedIntegration(null)}>×</button>
            </div>

            <p className="detail-description">{selectedIntegration.description}</p>

            <div className="detail-actions">
              {selectedIntegration.status === 'connected' ? (
                <>
                  <button className="btn-primary" onClick={handleTriggerSync}>
                    Sync Now
                  </button>
                  <button className="btn-secondary" onClick={handleTestConnection}>
                    Test Connection
                  </button>
                  <button className="btn-danger" onClick={() => handleDisconnect(selectedIntegration.id)}>
                    Disconnect
                  </button>
                </>
              ) : (
                <button className="btn-primary" onClick={() => handleConnect(selectedIntegration.id)}>
                  Connect
                </button>
              )}
            </div>

            {/* Credentials Section */}
            {selectedIntegration.auth_type === 'api_key' && (
              <div className="detail-section">
                <h3>API Credentials</h3>
                <div className="credentials-form">
                  <div className="form-group">
                    <label>API Key</label>
                    <input
                      type="password"
                      value={credentials.api_key || ''}
                      onChange={(e) => setCredentials({ ...credentials, api_key: e.target.value })}
                      placeholder="Enter API key"
                    />
                  </div>
                  {selectedIntegration.id === 'twilio' && (
                    <div className="form-group">
                      <label>API Secret / Auth Token</label>
                      <input
                        type="password"
                        value={credentials.api_secret || ''}
                        onChange={(e) => setCredentials({ ...credentials, api_secret: e.target.value })}
                        placeholder="Enter API secret"
                      />
                    </div>
                  )}
                  <button className="btn-primary" onClick={handleSaveCredentials}>
                    Save Credentials
                  </button>
                </div>
              </div>
            )}

            {/* Configuration Section */}
            <div className="detail-section">
              <div className="section-header">
                <h3>Configuration</h3>
                {!configMode ? (
                  <button className="btn-sm" onClick={() => setConfigMode(true)}>Edit</button>
                ) : (
                  <div className="config-actions">
                    <button className="btn-sm" onClick={() => setConfigMode(false)}>Cancel</button>
                    <button className="btn-sm btn-primary" onClick={handleSaveConfig} disabled={saving}>
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                )}
              </div>

              <div className="config-form">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={config.enabled || false}
                    onChange={(e) => updateConfig('enabled', e.target.checked)}
                    disabled={!configMode}
                  />
                  <span>Enabled</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={config.sync_enabled || false}
                    onChange={(e) => updateConfig('sync_enabled', e.target.checked)}
                    disabled={!configMode}
                  />
                  <span>Auto Sync</span>
                </label>

                <div className="form-group">
                  <label>Sync Interval (minutes)</label>
                  <input
                    type="number"
                    value={config.sync_interval_minutes || 60}
                    onChange={(e) => updateConfig('sync_interval_minutes', parseInt(e.target.value) || 60)}
                    min={5}
                    max={1440}
                    disabled={!configMode}
                  />
                </div>

                <div className="form-group">
                  <label>Sync Direction</label>
                  <select
                    value={config.sync_direction || 'bidirectional'}
                    onChange={(e) => updateConfig('sync_direction', e.target.value)}
                    disabled={!configMode}
                  >
                    <option value="incoming">Incoming Only</option>
                    <option value="outgoing">Outgoing Only</option>
                    <option value="bidirectional">Bidirectional</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Features */}
            {selectedIntegration.features && (
              <div className="detail-section">
                <h3>Features</h3>
                <div className="features-list">
                  {selectedIntegration.features.map(feature => (
                    <span key={feature} className="feature-tag">{feature}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Sync History */}
            {syncHistory.length > 0 && (
              <div className="detail-section">
                <h3>Recent Syncs</h3>
                <div className="sync-history">
                  {syncHistory.map(sync => (
                    <div key={sync.sync_id} className="sync-item">
                      <div className="sync-info">
                        <span className={`sync-status ${sync.status}`}>{sync.status}</span>
                        <span className="sync-type">{sync.sync_type}</span>
                      </div>
                      <div className="sync-stats">
                        <span>{sync.items_synced} items</span>
                        {sync.errors > 0 && <span className="sync-errors">{sync.errors} errors</span>}
                      </div>
                      <div className="sync-time">
                        {new Date(sync.started_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default IntegrationSettings;
