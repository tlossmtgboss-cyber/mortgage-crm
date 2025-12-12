/**
 * PURL Manager - Admin Panel Component
 * Perennia AI - Mortgage CRM
 *
 * Manages PURL workspaces, tokens, and access for loan officers
 */

import React, { useState, useEffect, useCallback } from 'react';
import './PURLManager.css';

// =============================================================================
// API CLIENT
// =============================================================================

const purlAdminApi = {
  baseUrl: '/api/v1/purl-admin',

  async createWorkspace(data) {
    const response = await fetch(`${this.baseUrl}/workspaces`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to create workspace');
    return response.json();
  },

  async getWorkspaces(params = {}) {
    const query = new URLSearchParams(params).toString();
    const response = await fetch(`${this.baseUrl}/workspaces?${query}`);
    if (!response.ok) throw new Error('Failed to fetch workspaces');
    return response.json();
  },

  async getWorkspace(id) {
    const response = await fetch(`${this.baseUrl}/workspaces/${id}`);
    if (!response.ok) throw new Error('Failed to fetch workspace');
    return response.json();
  },

  async createToken(workspaceId, data) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/tokens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to create token');
    return response.json();
  },

  async getTokens(workspaceId) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/tokens`);
    if (!response.ok) throw new Error('Failed to fetch tokens');
    return response.json();
  },

  async revokeToken(tokenId, reason) {
    const response = await fetch(`${this.baseUrl}/tokens/${tokenId}/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    if (!response.ok) throw new Error('Failed to revoke token');
    return response.json();
  },

  async getWorkspaceActivity(workspaceId, limit = 50) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/activity?limit=${limit}`);
    if (!response.ok) throw new Error('Failed to fetch activity');
    return response.json();
  },

  async getPurlUrl(workspaceId) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/purl-url`);
    if (!response.ok) throw new Error('Failed to get PURL URL');
    return response.json();
  },
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function PURLManager() {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedWorkspace, setSelectedWorkspace] = useState(null);
  const [filter, setFilter] = useState('active');
  const [searchTerm, setSearchTerm] = useState('');

  const loadWorkspaces = useCallback(async () => {
    try {
      setLoading(true);
      const data = await purlAdminApi.getWorkspaces({ status: filter });
      setWorkspaces(data.workspaces || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  const filteredWorkspaces = workspaces.filter(w =>
    w.borrower_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    w.slug?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateWorkspace = async (data) => {
    try {
      await purlAdminApi.createWorkspace(data);
      setShowCreateModal(false);
      loadWorkspaces();
    } catch (err) {
      alert('Failed to create workspace: ' + err.message);
    }
  };

  if (loading && workspaces.length === 0) {
    return (
      <div className="purl-manager loading">
        <div className="spinner"></div>
        <p>Loading workspaces...</p>
      </div>
    );
  }

  return (
    <div className="purl-manager">
      {/* Header */}
      <div className="manager-header">
        <div className="header-title">
          <h1>PURL Manager</h1>
          <p>Manage borrower portal workspaces and access tokens</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          + Create Workspace
        </button>
      </div>

      {/* Filters */}
      <div className="manager-filters">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search by name or slug..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="filter-tabs">
          {['active', 'completed', 'all'].map(f => (
            <button
              key={f}
              className={`filter-tab ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Workspace Grid */}
      <div className="workspace-grid">
        {filteredWorkspaces.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">&#128194;</div>
            <h3>No workspaces found</h3>
            <p>Create a workspace to get started with PURL portals</p>
          </div>
        ) : (
          filteredWorkspaces.map(workspace => (
            <WorkspaceCard
              key={workspace.id}
              workspace={workspace}
              onClick={() => setSelectedWorkspace(workspace)}
            />
          ))
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <CreateWorkspaceModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateWorkspace}
        />
      )}

      {/* Details Modal */}
      {selectedWorkspace && (
        <WorkspaceDetailsModal
          workspace={selectedWorkspace}
          onClose={() => setSelectedWorkspace(null)}
          onRefresh={loadWorkspaces}
        />
      )}
    </div>
  );
}

// =============================================================================
// WORKSPACE CARD
// =============================================================================

function WorkspaceCard({ workspace, onClick }) {
  const statusColors = {
    active: 'status-blue',
    application_started: 'status-yellow',
    application_submitted: 'status-green',
    in_processing: 'status-purple',
    completed: 'status-emerald',
  };

  return (
    <div className="workspace-card" onClick={onClick}>
      <div className="card-header">
        <h3>{workspace.borrower_name || 'Unnamed Borrower'}</h3>
        <span className={`status-badge ${statusColors[workspace.status] || 'status-gray'}`}>
          {workspace.status?.replace(/_/g, ' ')}
        </span>
      </div>

      <div className="card-body">
        <div className="card-detail">
          <span className="label">Slug:</span>
          <span className="value">{workspace.slug}</span>
        </div>
        <div className="card-detail">
          <span className="label">Created:</span>
          <span className="value">{new Date(workspace.created_at).toLocaleDateString()}</span>
        </div>
        {workspace.loan_id && (
          <div className="card-detail">
            <span className="label">Loan:</span>
            <span className="value">{workspace.loan_number || workspace.loan_id}</span>
          </div>
        )}
      </div>

      <div className="card-footer">
        <div className="progress-mini">
          <div
            className="progress-fill"
            style={{ width: `${workspace.progress || 0}%` }}
          ></div>
        </div>
        <span className="progress-text">{workspace.progress || 0}% complete</span>
      </div>
    </div>
  );
}

// =============================================================================
// CREATE WORKSPACE MODAL
// =============================================================================

function CreateWorkspaceModal({ onClose, onCreate }) {
  const [formData, setFormData] = useState({
    contact_id: '',
    loan_id: '',
    custom_slug: '',
    settings: {},
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onCreate(formData);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create New Workspace</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Contact ID *</label>
            <input
              type="text"
              value={formData.contact_id}
              onChange={e => setFormData({...formData, contact_id: e.target.value})}
              placeholder="Enter contact ID"
              required
            />
          </div>

          <div className="form-group">
            <label>Loan ID (optional)</label>
            <input
              type="text"
              value={formData.loan_id}
              onChange={e => setFormData({...formData, loan_id: e.target.value})}
              placeholder="Link to existing loan"
            />
          </div>

          <div className="form-group">
            <label>Custom Slug (optional)</label>
            <input
              type="text"
              value={formData.custom_slug}
              onChange={e => setFormData({...formData, custom_slug: e.target.value})}
              placeholder="e.g., john-smith-2024"
            />
            <small>Leave empty to auto-generate from borrower name</small>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Workspace'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// =============================================================================
// WORKSPACE DETAILS MODAL
// =============================================================================

function WorkspaceDetailsModal({ workspace, onClose, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [details, setDetails] = useState(null);
  const [tokens, setTokens] = useState([]);
  const [activity, setActivity] = useState([]);
  const [purlUrl, setPurlUrl] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDetails();
  }, [workspace.id]);

  const loadDetails = async () => {
    try {
      setLoading(true);
      const [detailsData, tokensData, activityData, urlData] = await Promise.all([
        purlAdminApi.getWorkspace(workspace.id),
        purlAdminApi.getTokens(workspace.id),
        purlAdminApi.getWorkspaceActivity(workspace.id),
        purlAdminApi.getPurlUrl(workspace.id),
      ]);
      setDetails(detailsData);
      setTokens(tokensData.tokens || []);
      setActivity(activityData.events || []);
      setPurlUrl(urlData.url || '');
    } catch (err) {
      console.error('Failed to load workspace details:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(purlUrl);
    alert('PURL copied to clipboard!');
  };

  const handleCreateToken = async () => {
    try {
      await purlAdminApi.createToken(workspace.id, {
        token_type: 'full_access',
        expires_in_days: 30,
      });
      loadDetails();
    } catch (err) {
      alert('Failed to create token: ' + err.message);
    }
  };

  const handleRevokeToken = async (tokenId) => {
    if (!window.confirm('Are you sure you want to revoke this token?')) return;
    try {
      await purlAdminApi.revokeToken(tokenId, 'Revoked by admin');
      loadDetails();
    } catch (err) {
      alert('Failed to revoke token: ' + err.message);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{workspace.borrower_name || 'Workspace Details'}</h2>
            <p className="modal-subtitle">{workspace.slug}</p>
          </div>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        {/* PURL URL */}
        <div className="purl-url-section">
          <label>PURL URL:</label>
          <div className="url-display">
            <input type="text" value={purlUrl} readOnly />
            <button onClick={handleCopyUrl}>Copy</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="modal-tabs">
          {['overview', 'tokens', 'activity'].map(tab => (
            <button
              key={tab}
              className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="modal-body">
          {loading ? (
            <div className="loading-state">Loading...</div>
          ) : (
            <>
              {activeTab === 'overview' && <WorkspaceOverview workspace={details} />}
              {activeTab === 'tokens' && (
                <WorkspaceTokens
                  tokens={tokens}
                  onCreate={handleCreateToken}
                  onRevoke={handleRevokeToken}
                />
              )}
              {activeTab === 'activity' && <WorkspaceActivity activity={activity} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// TAB COMPONENTS
// =============================================================================

function WorkspaceOverview({ workspace }) {
  if (!workspace) return null;

  return (
    <div className="overview-content">
      <div className="overview-grid">
        <div className="overview-item">
          <label>Status</label>
          <span className="value">{workspace.status?.replace(/_/g, ' ')}</span>
        </div>
        <div className="overview-item">
          <label>Progress</label>
          <span className="value">{workspace.progress || 0}%</span>
        </div>
        <div className="overview-item">
          <label>Created</label>
          <span className="value">{new Date(workspace.created_at).toLocaleString()}</span>
        </div>
        <div className="overview-item">
          <label>Last Activity</label>
          <span className="value">
            {workspace.last_activity_at
              ? new Date(workspace.last_activity_at).toLocaleString()
              : 'None'}
          </span>
        </div>
      </div>

      {workspace.settings && (
        <div className="settings-section">
          <h4>Settings</h4>
          <pre>{JSON.stringify(workspace.settings, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function WorkspaceTokens({ tokens, onCreate, onRevoke }) {
  return (
    <div className="tokens-content">
      <div className="tokens-header">
        <h4>Access Tokens</h4>
        <button className="btn btn-sm btn-primary" onClick={onCreate}>
          + New Token
        </button>
      </div>

      {tokens.length === 0 ? (
        <p className="empty-message">No tokens created yet</p>
      ) : (
        <div className="tokens-list">
          {tokens.map(token => (
            <div key={token.id} className={`token-item ${token.is_active ? '' : 'inactive'}`}>
              <div className="token-info">
                <code>{token.token?.substring(0, 20)}...</code>
                <span className="token-type">{token.token_type}</span>
                <span className={`token-status ${token.is_active ? 'active' : 'inactive'}`}>
                  {token.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="token-meta">
                <span>Expires: {token.expires_at ? new Date(token.expires_at).toLocaleDateString() : 'Never'}</span>
                <span>Used: {token.access_count || 0} times</span>
              </div>
              {token.is_active && (
                <button
                  className="btn btn-sm btn-danger"
                  onClick={() => onRevoke(token.id)}
                >
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkspaceActivity({ activity }) {
  const getEventIcon = (type) => {
    const icons = {
      workspace_created: '&#128194;',
      token_created: '&#128273;',
      application_started: '&#128221;',
      application_submitted: '&#9989;',
      document_uploaded: '&#128196;',
      task_completed: '&#9745;',
      message_sent: '&#128172;',
    };
    return icons[type] || '&#128900;';
  };

  return (
    <div className="activity-content">
      {activity.length === 0 ? (
        <p className="empty-message">No activity recorded yet</p>
      ) : (
        <div className="activity-timeline">
          {activity.map((event, index) => (
            <div key={index} className="activity-item">
              <span
                className="activity-icon"
                dangerouslySetInnerHTML={{ __html: getEventIcon(event.event_type) }}
              />
              <div className="activity-details">
                <span className="activity-type">{event.event_type?.replace(/_/g, ' ')}</span>
                <span className="activity-time">
                  {new Date(event.created_at).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
