/**
 * PURL Manager - Admin Panel Component
 * Perennia AI - Mortgage CRM
 *
 * Manages PURL workspaces, tokens, and access for loan officers
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import './PURLManager.css';
import { toast } from '../../utils/toast';

// =============================================================================
// API CLIENT
// =============================================================================

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const purlAdminApi = {
  baseUrl: `${API_BASE}/api/v1/purl-admin`,

  async searchContacts(query) {
    const response = await fetch(`${this.baseUrl}/contacts/search?q=${encodeURIComponent(query)}&limit=10`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to search contacts');
    return response.json();
  },

  async createWorkspace(data) {
    const response = await fetch(`${this.baseUrl}/workspaces`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to create workspace' }));
      throw new Error(error.detail || 'Failed to create workspace');
    }
    return response.json();
  },

  async getWorkspaces(params = {}) {
    const query = new URLSearchParams(params).toString();
    const response = await fetch(`${this.baseUrl}/workspaces?${query}`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch workspaces');
    return response.json();
  },

  async getWorkspace(id) {
    const response = await fetch(`${this.baseUrl}/workspaces/${id}`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch workspace');
    return response.json();
  },

  async createToken(workspaceId, data) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/tokens`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to create token');
    return response.json();
  },

  async getTokens(workspaceId) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/tokens`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch tokens');
    return response.json();
  },

  async revokeToken(tokenId, reason) {
    const response = await fetch(`${this.baseUrl}/tokens/${tokenId}/revoke`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ reason }),
    });
    if (!response.ok) throw new Error('Failed to revoke token');
    return response.json();
  },

  async getWorkspaceActivity(workspaceId, limit = 50) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/activity?limit=${limit}`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch activity');
    return response.json();
  },

  async getPurlUrl(workspaceId) {
    const response = await fetch(`${this.baseUrl}/workspaces/${workspaceId}/purl-url`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to get PURL URL');
    return response.json();
  },

  async getMetrics() {
    const response = await fetch(`${this.baseUrl}/metrics`, {
      headers: getAuthHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch metrics');
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
      toast.error('Failed to create workspace: ' + err.message);
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

      {/* Workspace List */}
      <div className="workspace-list">
        {filteredWorkspaces.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">&#128194;</div>
            <h3>No workspaces found</h3>
            <p>Create a workspace to get started with PURL portals</p>
          </div>
        ) : (
          <>
            {/* Table Header */}
            <div className="workspace-list-header">
              <span className="col-name">Client Name</span>
              <span className="col-slug">Slug</span>
              <span className="col-status">Status</span>
              <span className="col-created">Created</span>
              <span className="col-actions">Actions</span>
            </div>
            {/* Table Rows */}
            {filteredWorkspaces.map(workspace => (
              <WorkspaceListItem
                key={workspace.id}
                workspace={workspace}
                onClick={() => setSelectedWorkspace(workspace)}
              />
            ))}
          </>
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
// WORKSPACE LIST ITEM
// =============================================================================

function WorkspaceListItem({ workspace, onClick }) {
  const statusColors = {
    lead: 'status-gray',
    application: 'status-blue',
    active_loan: 'status-green',
    closing: 'status-purple',
    post_close: 'status-emerald',
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return '-';
    }
  };

  return (
    <div className="workspace-list-item" onClick={onClick}>
      <span className="col-name">
        <strong>{workspace.borrower_name || workspace.display_name || 'Unnamed Client'}</strong>
      </span>
      <span className="col-slug">
        <code>{workspace.slug}</code>
      </span>
      <span className="col-status">
        <span className={`status-badge ${statusColors[workspace.status] || 'status-gray'}`}>
          {(workspace.status || 'lead').replace(/_/g, ' ')}
        </span>
      </span>
      <span className="col-created">
        {formatDate(workspace.created_at)}
      </span>
      <span className="col-actions">
        <button className="btn-view" onClick={(e) => { e.stopPropagation(); onClick(); }}>
          View Details
        </button>
      </span>
    </div>
  );
}

// =============================================================================
// CREATE WORKSPACE MODAL
// =============================================================================

function CreateWorkspaceModal({ onClose, onCreate }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedContact, setSelectedContact] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [isNewContact, setIsNewContact] = useState(false);
  const [formData, setFormData] = useState({
    borrower_name: '',
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    loan_id: '',
    custom_slug: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const searchTimeoutRef = React.useRef(null);

  // Debounced search
  const handleSearchChange = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    setError('');

    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (query.length < 2) {
      setSearchResults([]);
      setShowDropdown(false);
      return;
    }

    // Debounce search
    searchTimeoutRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const results = await purlAdminApi.searchContacts(query);
        setSearchResults(results.contacts || []);
        setShowDropdown(true);
      } catch (err) {
        console.error('Search failed:', err);
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);
  };

  const handleSelectContact = (contact) => {
    if (contact.has_workspace) {
      setError(`This borrower already has a client portal (${contact.existing_workspace?.workspace_slug})`);
      return;
    }
    setSelectedContact(contact);
    setSearchQuery(contact.name);
    setShowDropdown(false);
    setIsNewContact(false);
  };

  const handleCreateNew = () => {
    setIsNewContact(true);
    setSelectedContact(null);
    setShowDropdown(false);
    setFormData({
      ...formData,
      borrower_name: searchQuery,
      first_name: searchQuery.split(' ')[0] || '',
      last_name: searchQuery.split(' ').slice(1).join(' ') || '',
    });
  };

  const handleClearSelection = () => {
    setSelectedContact(null);
    setSearchQuery('');
    setIsNewContact(false);
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    try {
      let payload = {
        custom_slug: formData.custom_slug || undefined,
        loan_id: formData.loan_id ? parseInt(formData.loan_id) : undefined,
      };

      if (selectedContact) {
        payload.lead_id = selectedContact.id;
      } else if (isNewContact) {
        payload.borrower_name = formData.borrower_name || searchQuery;
        payload.first_name = formData.first_name;
        payload.last_name = formData.last_name;
        payload.email = formData.email;
        payload.phone = formData.phone;
      } else {
        setError('Please select a borrower or create a new one');
        setSubmitting(false);
        return;
      }

      await onCreate(payload);
    } catch (err) {
      setError(err.message || 'Failed to create workspace');
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
          {error && (
            <div className="form-error" style={{
              background: '#fee2e2',
              border: '1px solid #ef4444',
              color: '#dc2626',
              padding: '0.75rem',
              borderRadius: '0.375rem',
              marginBottom: '1rem',
              fontSize: '0.875rem'
            }}>
              {error}
            </div>
          )}

          <div className="form-group">
            <label>Borrower Name *</label>
            {selectedContact ? (
              <div className="selected-contact" style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem',
                background: '#f0fdf4',
                border: '1px solid #22c55e',
                borderRadius: '0.375rem'
              }}>
                <div>
                  <strong>{selectedContact.name}</strong>
                  {selectedContact.email && <span style={{ color: '#6b7280', marginLeft: '0.5rem' }}>{selectedContact.email}</span>}
                  <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                    Stage: {selectedContact.stage || 'N/A'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleClearSelection}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '1.25rem',
                    color: '#6b7280'
                  }}
                >
                  &times;
                </button>
              </div>
            ) : isNewContact ? (
              <div style={{ background: '#fefce8', border: '1px solid #eab308', borderRadius: '0.375rem', padding: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: '500' }}>Creating new borrower</span>
                  <button
                    type="button"
                    onClick={handleClearSelection}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.25rem' }}
                  >
                    &times;
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <input
                    type="text"
                    value={formData.first_name}
                    onChange={e => setFormData({...formData, first_name: e.target.value})}
                    placeholder="First name"
                    style={{ padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '0.25rem' }}
                  />
                  <input
                    type="text"
                    value={formData.last_name}
                    onChange={e => setFormData({...formData, last_name: e.target.value})}
                    placeholder="Last name"
                    style={{ padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '0.25rem' }}
                  />
                </div>
                <input
                  type="email"
                  value={formData.email}
                  onChange={e => setFormData({...formData, email: e.target.value})}
                  placeholder="Email (optional)"
                  style={{ marginTop: '0.5rem', width: '100%', padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '0.25rem', boxSizing: 'border-box' }}
                />
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={e => setFormData({...formData, phone: e.target.value})}
                  placeholder="Phone (optional)"
                  style={{ marginTop: '0.5rem', width: '100%', padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '0.25rem', boxSizing: 'border-box' }}
                />
              </div>
            ) : (
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={handleSearchChange}
                  onFocus={() => searchQuery.length >= 2 && setShowDropdown(true)}
                  placeholder="Type borrower name to search..."
                  autoComplete="off"
                />
                {isSearching && (
                  <span style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }}>
                    Searching...
                  </span>
                )}
                {showDropdown && (
                  <div className="search-dropdown" style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    background: 'white',
                    border: '1px solid #d1d5db',
                    borderRadius: '0.375rem',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                    maxHeight: '240px',
                    overflowY: 'auto',
                    zIndex: 10
                  }}>
                    {searchResults.length === 0 ? (
                      <div style={{ padding: '0.75rem', color: '#6b7280', textAlign: 'center' }}>
                        No matches found
                      </div>
                    ) : (
                      searchResults.map(contact => (
                        <div
                          key={contact.id}
                          onClick={() => handleSelectContact(contact)}
                          style={{
                            padding: '0.75rem',
                            cursor: contact.has_workspace ? 'not-allowed' : 'pointer',
                            borderBottom: '1px solid #f3f4f6',
                            background: contact.has_workspace ? '#f9fafb' : 'white',
                            opacity: contact.has_workspace ? 0.7 : 1,
                          }}
                          onMouseEnter={e => !contact.has_workspace && (e.target.style.background = '#f3f4f6')}
                          onMouseLeave={e => !contact.has_workspace && (e.target.style.background = 'white')}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <strong>{contact.name}</strong>
                              {contact.email && <span style={{ color: '#6b7280', marginLeft: '0.5rem', fontSize: '0.875rem' }}>{contact.email}</span>}
                            </div>
                            {contact.has_workspace && (
                              <span style={{
                                fontSize: '0.75rem',
                                background: '#fef3c7',
                                color: '#92400e',
                                padding: '0.125rem 0.5rem',
                                borderRadius: '9999px'
                              }}>
                                Has Portal
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                            {contact.phone && <span>{contact.phone}</span>}
                            {contact.stage && <span style={{ marginLeft: '0.5rem' }}>• {contact.stage}</span>}
                          </div>
                        </div>
                      ))
                    )}
                    <div
                      onClick={handleCreateNew}
                      style={{
                        padding: '0.75rem',
                        cursor: 'pointer',
                        background: '#eff6ff',
                        color: '#2563eb',
                        fontWeight: '500',
                        borderTop: '1px solid #d1d5db'
                      }}
                      onMouseEnter={e => e.target.style.background = '#dbeafe'}
                      onMouseLeave={e => e.target.style.background = '#eff6ff'}
                    >
                      + Create new borrower "{searchQuery}"
                    </div>
                  </div>
                )}
              </div>
            )}
            <small>Search for an existing borrower or create a new one</small>
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
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || (!selectedContact && !isNewContact)}
            >
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
      setActivity(activityData.events || activityData.activities || []);
      setPurlUrl(urlData.portal_url || urlData.url || '');
    } catch (err) {
      console.error('Failed to load workspace details:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(purlUrl);
    toast.success('PURL copied to clipboard!');
  };

  const handleViewPortal = () => {
    if (purlUrl) {
      window.open(purlUrl, '_blank');
    } else {
      toast.info('No portal URL available. Click "Generate Portal Link" to create one.');
    }
  };

  const handleGeneratePortalLink = async () => {
    try {
      const result = await purlAdminApi.createToken(workspace.id, {
        token_type: 'full_access',
        expires_in_days: 365,
      });

      // The API returns portal_url with the token
      if (result.portal_url) {
        setPurlUrl(result.portal_url);
        // Copy to clipboard
        navigator.clipboard.writeText(result.portal_url);
        // Ask if they want to open it
        if (window.confirm('Portal link generated and copied to clipboard!\n\nClick OK to open the portal in a new tab.')) {
          window.open(result.portal_url, '_blank');
        }
      }
      loadDetails();
    } catch (err) {
      toast.error('Failed to generate portal link: ' + err.message);
    }
  };

  const handleCreateToken = async () => {
    try {
      const result = await purlAdminApi.createToken(workspace.id, {
        token_type: 'full_access',
        expires_in_days: 365,
      });

      if (result.portal_url) {
        setPurlUrl(result.portal_url);
        navigator.clipboard.writeText(result.portal_url);
        toast.success('Token created! Portal URL copied to clipboard.');
      }
      loadDetails();
    } catch (err) {
      toast.error('Failed to create token: ' + err.message);
    }
  };

  const handleRevokeToken = async (tokenId) => {
    if (!window.confirm('Are you sure you want to revoke this token?')) return;
    try {
      await purlAdminApi.revokeToken(tokenId, 'Revoked by admin');
      loadDetails();
    } catch (err) {
      toast.error('Failed to revoke token: ' + err.message);
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
          <label>Portal Access Link:</label>
          {purlUrl ? (
            <div className="url-display">
              <input type="text" value={purlUrl} readOnly />
              <button onClick={handleCopyUrl}>Copy</button>
              <button
                onClick={handleViewPortal}
                className="btn-view-portal"
                style={{
                  background: '#2563eb',
                  color: 'white',
                  border: 'none',
                  padding: '0.5rem 1rem',
                  borderRadius: '0.375rem',
                  cursor: 'pointer',
                  marginLeft: '0.5rem',
                  fontWeight: '500'
                }}
              >
                Open Portal
              </button>
            </div>
          ) : (
            <div className="url-display" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
              <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>
                Generate a new portal link to share with your client. The link includes authentication and expires in 1 year.
              </p>
              <button
                onClick={handleGeneratePortalLink}
                style={{
                  background: '#059669',
                  color: 'white',
                  border: 'none',
                  padding: '0.625rem 1.25rem',
                  borderRadius: '0.375rem',
                  cursor: 'pointer',
                  fontWeight: '500',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>🔗</span> Generate Portal Link
              </button>
            </div>
          )}
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
