import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './APIKeysSettings.css';
import { getToken } from '../utils/tokenStore';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://api.perenniaai.com';

const APIKeysSettings = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access for API key management
  const canAccessAPIKeys = isAdmin || hasAnyPermission(['admin.manage', 'api.manage', 'system.admin']) || userRole === 'admin';

  const [activeTab, setActiveTab] = useState('keys');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data states
  const [apiKeys, setApiKeys] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [rateLimits, setRateLimits] = useState({});
  const [scopes, setScopes] = useState([]);
  const [events, setEvents] = useState([]);

  // Modal states
  const [showCreateKeyModal, setShowCreateKeyModal] = useState(false);
  const [showCreateWebhookModal, setShowCreateWebhookModal] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [selectedWebhook, setSelectedWebhook] = useState(null);
  const [newKeyData, setNewKeyData] = useState(null);

  // Form states
  const [keyForm, setKeyForm] = useState({
    name: '',
    description: '',
    scopes: [],
    rate_limit_per_minute: 60,
    rate_limit_per_day: 10000,
    ip_whitelist: []
  });

  const [webhookForm, setWebhookForm] = useState({
    name: '',
    url: '',
    events: [],
    is_active: true,
    retry_count: 3,
    timeout_seconds: 30
  });

  const [rateLimitForm, setRateLimitForm] = useState({
    default_per_minute: 60,
    default_per_day: 10000,
    burst_limit: 100,
    enable_rate_limiting: true,
    rate_limit_by_ip: true,
    rate_limit_by_key: true
  });

  const getAuthHeaders = useCallback(() => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Load data
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [keysRes, webhooksRes, rateLimitsRes, scopesRes, eventsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/api-keys`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/api-keys/webhooks/endpoints`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/api-keys/rate-limits`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/api-keys/scopes`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/api-keys/webhooks/events`, { headers: getAuthHeaders() })
      ]);

      if (keysRes.ok) {
        const keysData = await keysRes.json();
        setApiKeys(keysData.data || []);
      }

      if (webhooksRes.ok) {
        const webhooksData = await webhooksRes.json();
        setWebhooks(webhooksData.data || []);
      }

      if (rateLimitsRes.ok) {
        const rateLimitsData = await rateLimitsRes.json();
        setRateLimits(rateLimitsData.data || {});
        setRateLimitForm(rateLimitsData.data || rateLimitForm);
      }

      if (scopesRes.ok) {
        const scopesData = await scopesRes.json();
        setScopes(scopesData.data || []);
      }

      if (eventsRes.ok) {
        const eventsData = await eventsRes.json();
        setEvents(eventsData.data || []);
      }

      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    loadData();
  }, [loadData]);


  // Create API Key
  const handleCreateKey = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(keyForm)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new APIError(error.detail?.message || 'Failed to create API key', response.status);
      }

      const result = await response.json();
      setNewKeyData(result.data);
      setShowCreateKeyModal(false);
      loadData();
      toast.success('API key created successfully');
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Delete API Key
  const handleDeleteKey = async (keyId) => {
    if (!window.confirm('Are you sure you want to delete this API key? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new APIError('Failed to delete API key', response.status);
      }

      loadData();
      setSelectedKey(null);
      toast.success('API key deleted successfully');
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Rotate API Key
  const handleRotateKey = async (keyId) => {
    if (!window.confirm('Are you sure you want to rotate this API key? The old key will be invalidated.')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/${keyId}/rotate`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new APIError('Failed to rotate API key', response.status);
      }

      const result = await response.json();
      setNewKeyData(result.data);
      loadData();
      toast.success('API key rotated successfully');
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Toggle key active status
  const handleToggleKeyStatus = async (keyId, currentStatus) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/${keyId}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ is_active: !currentStatus })
      });

      if (!response.ok) {
        throw new APIError('Failed to update API key', response.status);
      }

      loadData();
      toast.success(`API key ${currentStatus ? 'disabled' : 'enabled'} successfully`);
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Create Webhook
  const handleCreateWebhook = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/webhooks/endpoints`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(webhookForm)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new APIError(error.detail?.message || 'Failed to create webhook', response.status);
      }

      const result = await response.json();
      setShowCreateWebhookModal(false);
      loadData();
      toast.success(`Webhook created. Secret: ${result.data.secret}`);
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Delete Webhook
  const handleDeleteWebhook = async (webhookId) => {
    if (!window.confirm('Are you sure you want to delete this webhook?')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/webhooks/endpoints/${webhookId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new APIError('Failed to delete webhook', response.status);
      }

      loadData();
      setSelectedWebhook(null);
      toast.success('Webhook deleted successfully');
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Test Webhook
  const handleTestWebhook = async (webhookId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/webhooks/endpoints/${webhookId}/test`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        throw new APIError('Webhook test failed', response.status);
      }

      const result = await response.json();
      toast.success(`Test successful! Response: ${result.data.response_code} (${result.data.response_time_ms}ms)`);
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Save Rate Limits
  const handleSaveRateLimits = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/rate-limits`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(rateLimitForm)
      });

      if (!response.ok) {
        throw new APIError('Failed to update rate limits', response.status);
      }

      toast.success('Rate limit settings saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Copy to clipboard
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  // Render tabs
  const tabs = [
    { id: 'keys', label: 'API Keys', icon: '🔑' },
    { id: 'webhooks', label: 'Webhooks', icon: '🔗' },
    { id: 'rate-limits', label: 'Rate Limits', icon: '⚡' },
    { id: 'usage', label: 'Usage & Analytics', icon: '📊' }
  ];

  if (loading) {
    return (
      <div className="api-keys-settings">
        <div className="loading-container">Loading API settings...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="api-keys-settings">
        <div className="error-container">
          <p>Error loading settings: {error}</p>
          <button onClick={loadData}>Retry</button>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have admin permissions
  if (!canAccessAPIKeys) {
    return (
      <div className="api-keys-settings">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage API keys.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="api-keys-settings">
      <div className="page-header">
        <div>
          <h1>API Keys & Webhooks</h1>
          <p>Manage API access, webhooks, and rate limiting</p>
        </div>
        <button className="btn-back" onClick={() => navigate('/settings')}>
          ← Back to Settings
        </button>
      </div>

      {/* Tabs */}
      <div className="tabs-container">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* API Keys Tab */}
        {activeTab === 'keys' && (
          <div className="keys-tab">
            <div className="section-header">
              <h2>API Keys</h2>
              <button className="btn-primary" onClick={() => setShowCreateKeyModal(true)}>
                + Create API Key
              </button>
            </div>

            {apiKeys.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🔑</div>
                <h3>No API Keys</h3>
                <p>Create an API key to integrate with external systems</p>
              </div>
            ) : (
              <div className="keys-list">
                {apiKeys.map(key => (
                  <div
                    key={key.id}
                    className={`key-card ${!key.is_active ? 'disabled' : ''} ${selectedKey?.id === key.id ? 'selected' : ''}`}
                    onClick={() => setSelectedKey(key)}
                  >
                    <div className="key-header">
                      <h3>{key.name}</h3>
                      <span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>
                        {key.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="key-value">
                      <code>{key.masked_key}</code>
                      <button className="btn-icon" onClick={(e) => { e.stopPropagation(); copyToClipboard(key.masked_key); }}>
                        📋
                      </button>
                    </div>
                    <div className="key-meta">
                      <span>{key.scopes?.length || 0} scopes</span>
                      <span>•</span>
                      <span>{key.usage_count || 0} requests</span>
                      <span>•</span>
                      <span>Created {new Date(key.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="key-actions">
                      <button
                        className="btn-sm"
                        onClick={(e) => { e.stopPropagation(); handleToggleKeyStatus(key.id, key.is_active); }}
                      >
                        {key.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        className="btn-sm"
                        onClick={(e) => { e.stopPropagation(); handleRotateKey(key.id); }}
                      >
                        Rotate
                      </button>
                      <button
                        className="btn-sm btn-danger"
                        onClick={(e) => { e.stopPropagation(); handleDeleteKey(key.id); }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Webhooks Tab */}
        {activeTab === 'webhooks' && (
          <div className="webhooks-tab">
            <div className="section-header">
              <h2>Webhook Endpoints</h2>
              <button className="btn-primary" onClick={() => setShowCreateWebhookModal(true)}>
                + Create Webhook
              </button>
            </div>

            {webhooks.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🔗</div>
                <h3>No Webhooks</h3>
                <p>Create a webhook to receive real-time event notifications</p>
              </div>
            ) : (
              <div className="webhooks-list">
                {webhooks.map(webhook => (
                  <div
                    key={webhook.id}
                    className={`webhook-card ${!webhook.is_active ? 'disabled' : ''}`}
                  >
                    <div className="webhook-header">
                      <h3>{webhook.name}</h3>
                      <span className={`status-badge ${webhook.is_active ? 'active' : 'inactive'}`}>
                        {webhook.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="webhook-url">
                      <code>{webhook.url}</code>
                    </div>
                    <div className="webhook-events">
                      {webhook.events?.slice(0, 3).map(event => (
                        <span key={event} className="event-badge">{event}</span>
                      ))}
                      {webhook.events?.length > 3 && (
                        <span className="event-badge more">+{webhook.events.length - 3} more</span>
                      )}
                    </div>
                    <div className="webhook-stats">
                      <span className="success">✓ {webhook.success_count || 0}</span>
                      <span className="failure">✗ {webhook.failure_count || 0}</span>
                    </div>
                    <div className="webhook-actions">
                      <button
                        className="btn-sm"
                        onClick={() => handleTestWebhook(webhook.id)}
                      >
                        Test
                      </button>
                      <button
                        className="btn-sm btn-danger"
                        onClick={() => handleDeleteWebhook(webhook.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Rate Limits Tab */}
        {activeTab === 'rate-limits' && (
          <div className="rate-limits-tab">
            <h2>Rate Limiting Configuration</h2>
            <form onSubmit={handleSaveRateLimits} className="rate-limits-form">
              <div className="form-row">
                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={rateLimitForm.enable_rate_limiting}
                      onChange={(e) => setRateLimitForm({ ...rateLimitForm, enable_rate_limiting: e.target.checked })}
                    />
                    Enable Rate Limiting
                  </label>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Default Requests per Minute</label>
                  <input
                    type="number"
                    value={rateLimitForm.default_per_minute}
                    onChange={(e) => setRateLimitForm({ ...rateLimitForm, default_per_minute: parseInt(e.target.value) })}
                    min="1"
                    max="10000"
                  />
                </div>
                <div className="form-group">
                  <label>Default Requests per Day</label>
                  <input
                    type="number"
                    value={rateLimitForm.default_per_day}
                    onChange={(e) => setRateLimitForm({ ...rateLimitForm, default_per_day: parseInt(e.target.value) })}
                    min="1"
                    max="1000000"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Burst Limit</label>
                  <input
                    type="number"
                    value={rateLimitForm.burst_limit}
                    onChange={(e) => setRateLimitForm({ ...rateLimitForm, burst_limit: parseInt(e.target.value) })}
                    min="1"
                    max="1000"
                  />
                  <span className="help-text">Maximum requests allowed in a burst</span>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={rateLimitForm.rate_limit_by_ip}
                      onChange={(e) => setRateLimitForm({ ...rateLimitForm, rate_limit_by_ip: e.target.checked })}
                    />
                    Apply Rate Limits by IP Address
                  </label>
                </div>
                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={rateLimitForm.rate_limit_by_key}
                      onChange={(e) => setRateLimitForm({ ...rateLimitForm, rate_limit_by_key: e.target.checked })}
                    />
                    Apply Rate Limits by API Key
                  </label>
                </div>
              </div>

              <div className="form-actions">
                <button type="submit" className="btn-primary">Save Rate Limit Settings</button>
              </div>
            </form>
          </div>
        )}

        {/* Usage Tab */}
        {activeTab === 'usage' && (
          <div className="usage-tab">
            <h2>API Usage & Analytics</h2>
            <div className="usage-overview">
              <div className="usage-card">
                <div className="usage-value">12,450</div>
                <div className="usage-label">Total Requests (30 days)</div>
              </div>
              <div className="usage-card">
                <div className="usage-value">98.5%</div>
                <div className="usage-label">Success Rate</div>
              </div>
              <div className="usage-card">
                <div className="usage-value">145ms</div>
                <div className="usage-label">Avg Response Time</div>
              </div>
              <div className="usage-card">
                <div className="usage-value">42</div>
                <div className="usage-label">Rate Limited</div>
              </div>
            </div>

            <div className="usage-details">
              <h3>Top Endpoints</h3>
              <div className="endpoint-list">
                {[
                  { endpoint: '/api/v1/leads', requests: 4500, pct: 36 },
                  { endpoint: '/api/v1/loans', requests: 3200, pct: 26 },
                  { endpoint: '/api/v1/contacts', requests: 2100, pct: 17 },
                  { endpoint: '/api/v1/documents', requests: 1800, pct: 14 },
                  { endpoint: '/api/v1/analytics', requests: 850, pct: 7 }
                ].map(item => (
                  <div key={item.endpoint} className="endpoint-row">
                    <code>{item.endpoint}</code>
                    <div className="endpoint-bar">
                      <div className="endpoint-fill" style={{ width: `${item.pct}%` }}></div>
                    </div>
                    <span>{item.requests.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Create Key Modal */}
      {showCreateKeyModal && (
        <div className="modal-overlay" onClick={() => setShowCreateKeyModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create API Key</h2>
              <button className="close-btn" onClick={() => setShowCreateKeyModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateKey}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Name *</label>
                  <input
                    type="text"
                    value={keyForm.name}
                    onChange={(e) => setKeyForm({ ...keyForm, name: e.target.value })}
                    placeholder="e.g., Production Integration"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    value={keyForm.description}
                    onChange={(e) => setKeyForm({ ...keyForm, description: e.target.value })}
                    placeholder="What is this key used for?"
                  />
                </div>
                <div className="form-group">
                  <label>Scopes</label>
                  <div className="scopes-grid">
                    {scopes.map(scope => (
                      <label key={scope.id} className="scope-checkbox">
                        <input
                          type="checkbox"
                          checked={keyForm.scopes.includes(scope.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setKeyForm({ ...keyForm, scopes: [...keyForm.scopes, scope.id] });
                            } else {
                              setKeyForm({ ...keyForm, scopes: keyForm.scopes.filter(s => s !== scope.id) });
                            }
                          }}
                        />
                        <span className="scope-name">{scope.name}</span>
                        <span className="scope-desc">{scope.description}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Rate Limit (per minute)</label>
                    <input
                      type="number"
                      value={keyForm.rate_limit_per_minute}
                      onChange={(e) => setKeyForm({ ...keyForm, rate_limit_per_minute: parseInt(e.target.value) })}
                      min="1"
                      max="10000"
                    />
                  </div>
                  <div className="form-group">
                    <label>Rate Limit (per day)</label>
                    <input
                      type="number"
                      value={keyForm.rate_limit_per_day}
                      onChange={(e) => setKeyForm({ ...keyForm, rate_limit_per_day: parseInt(e.target.value) })}
                      min="1"
                      max="1000000"
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateKeyModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create API Key
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Webhook Modal */}
      {showCreateWebhookModal && (
        <div className="modal-overlay" onClick={() => setShowCreateWebhookModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create Webhook</h2>
              <button className="close-btn" onClick={() => setShowCreateWebhookModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateWebhook}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Name *</label>
                  <input
                    type="text"
                    value={webhookForm.name}
                    onChange={(e) => setWebhookForm({ ...webhookForm, name: e.target.value })}
                    placeholder="e.g., CRM Sync"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Endpoint URL *</label>
                  <input
                    type="url"
                    value={webhookForm.url}
                    onChange={(e) => setWebhookForm({ ...webhookForm, url: e.target.value })}
                    placeholder="https://your-server.com/webhook"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Events</label>
                  <div className="events-grid">
                    {events.map(event => (
                      <label key={event.id} className="event-checkbox">
                        <input
                          type="checkbox"
                          checked={webhookForm.events.includes(event.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setWebhookForm({ ...webhookForm, events: [...webhookForm.events, event.id] });
                            } else {
                              setWebhookForm({ ...webhookForm, events: webhookForm.events.filter(ev => ev !== event.id) });
                            }
                          }}
                        />
                        <span>{event.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Retry Count</label>
                    <input
                      type="number"
                      value={webhookForm.retry_count}
                      onChange={(e) => setWebhookForm({ ...webhookForm, retry_count: parseInt(e.target.value) })}
                      min="0"
                      max="10"
                    />
                  </div>
                  <div className="form-group">
                    <label>Timeout (seconds)</label>
                    <input
                      type="number"
                      value={webhookForm.timeout_seconds}
                      onChange={(e) => setWebhookForm({ ...webhookForm, timeout_seconds: parseInt(e.target.value) })}
                      min="5"
                      max="120"
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateWebhookModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Webhook
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Key Created Modal */}
      {newKeyData && (
        <div className="modal-overlay" onClick={() => setNewKeyData(null)}>
          <div className="modal key-created-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>🔑 API Key Created</h2>
            </div>
            <div className="modal-body">
              <div className="warning-banner">
                <strong>Important:</strong> Copy your API key now. You won't be able to see it again!
              </div>
              <div className="key-display">
                <code>{newKeyData.api_key}</code>
                <button
                  className="btn-copy"
                  onClick={() => copyToClipboard(newKeyData.api_key)}
                >
                  📋 Copy
                </button>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-primary" onClick={() => setNewKeyData(null)}>
                I've Saved My Key
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default APIKeysSettings;
