import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { getAuthHeaders } from '../utils/auth';
import './PURLDashboard.css';
import { toast } from '../utils/toast';

/**
 * PURLDashboard - Overview of all client portals
 * Provides metrics, filtering, and bulk operations
 */
function PURLDashboard() {
  const [workspaces, setWorkspaces] = useState([]);
  const [metrics, setMetrics] = useState({
    total_workspaces: 0,
    applications_submitted: 0,
    active_today: 0,
    completion_rate: 0,
    documents_uploaded: 0,
    pending_review: 0
  });
  const [filter, setFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
  const PURL_DOMAIN = process.env.REACT_APP_PURL_DOMAIN || 'http://localhost:3000';

  useEffect(() => {
    loadData();
  }, [filter]);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [workspacesRes, metricsRes] = await Promise.all([
        axios.get(`${API_URL}/api/v1/purl-admin/workspaces`, {
          params: { status: filter !== 'all' ? filter : undefined },
          headers: getAuthHeaders()
        }),
        axios.get(`${API_URL}/api/v1/purl-admin/metrics`, {
          headers: getAuthHeaders()
        })
      ]);

      setWorkspaces(workspacesRes.data.workspaces || workspacesRes.data || []);
      setMetrics(metricsRes.data || {});
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
      setError('Failed to load dashboard data. Please try again.');

      // Set mock data for development
      if (error.response?.status === 404 || error.code === 'ERR_NETWORK') {
        setWorkspaces([]);
        setMetrics({
          total_workspaces: 6,
          applications_submitted: 2,
          active_today: 3,
          completion_rate: 33,
          documents_uploaded: 12,
          pending_review: 4
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const filteredWorkspaces = workspaces.filter(ws => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      (ws.display_name || '').toLowerCase().includes(search) ||
      (ws.email || '').toLowerCase().includes(search) ||
      (ws.slug || '').toLowerCase().includes(search)
    );
  });

  const handleBulkResend = async () => {
    const selectedIds = filteredWorkspaces
      .filter(ws => ws.status === 'lead' && !ws.last_activity)
      .map(ws => ws.id);

    if (selectedIds.length === 0) {
      toast.info('No inactive leads to send reminders to.');
      return;
    }

    if (!window.confirm(`Send reminder emails to ${selectedIds.length} inactive leads?`)) {
      return;
    }

    try {
      await axios.post(
        `${API_URL}/api/v1/purl-admin/bulk/resend-invites`,
        { workspace_ids: selectedIds },
        { headers: getAuthHeaders() }
      );
      toast.success(`Reminders sent to ${selectedIds.length} leads!`);
    } catch (error) {
      console.error('Bulk resend failed:', error);
      toast.error('Failed to send bulk reminders.');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  if (isLoading) {
    return (
      <div className="purl-dashboard loading-state">
        <div className="loading-spinner"></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="purl-dashboard">
      <div className="dashboard-header">
        <div className="header-left">
          <h1>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            Client Portals
          </h1>
          <p className="header-subtitle">Manage personalized borrower portals</p>
        </div>
        <div className="header-actions">
          <button className="btn-secondary" onClick={handleBulkResend}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            Bulk Resend
          </button>
          <Link to="/leads" className="btn-primary">
            + Create New Portal
          </Link>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Metrics Overview */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon bg-blue">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.total_workspaces || 0}</div>
            <div className="metric-label">Total Portals</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon bg-green">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.applications_submitted || 0}</div>
            <div className="metric-label">Apps Submitted</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon bg-yellow">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.active_today || 0}</div>
            <div className="metric-label">Active Today</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon bg-purple">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="20" x2="12" y2="10" />
              <line x1="18" y1="20" x2="18" y2="4" />
              <line x1="6" y1="20" x2="6" y2="16" />
            </svg>
          </div>
          <div className="metric-content">
            <div className="metric-value">{metrics.completion_rate || 0}%</div>
            <div className="metric-label">Completion Rate</div>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="filter-section">
        <div className="search-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search by name, email, or slug..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="filter-tabs">
          {['all', 'lead', 'application', 'active_loan', 'closing', 'post_close'].map(status => (
            <button
              key={status}
              className={`tab ${filter === status ? 'active' : ''}`}
              onClick={() => setFilter(status)}
            >
              {status === 'all' ? 'All' : status.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Workspaces Table */}
      <div className="workspaces-table-container">
        {filteredWorkspaces.length === 0 ? (
          <div className="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            <h3>No Portals Found</h3>
            <p>
              {searchTerm
                ? 'No portals match your search criteria.'
                : 'Create your first client portal from a lead profile.'}
            </p>
            <Link to="/leads" className="btn-primary">
              View Leads
            </Link>
          </div>
        ) : (
          <table className="workspaces-table">
            <thead>
              <tr>
                <th>Client Name</th>
                <th>Status</th>
                <th>Application</th>
                <th>Documents</th>
                <th>Last Activity</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredWorkspaces.map(workspace => (
                <tr key={workspace.id}>
                  <td>
                    <div className="client-cell">
                      <strong>{workspace.display_name || 'Unknown'}</strong>
                      <span className="client-email">{workspace.email || workspace.slug}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`status-badge badge-${workspace.status}`}>
                      {(workspace.status || 'lead').replace('_', ' ')}
                    </span>
                  </td>
                  <td>
                    <span className={`app-status status-${workspace.application_status || 'not_started'}`}>
                      {workspace.application_status || 'Not Started'}
                    </span>
                  </td>
                  <td>
                    <span className="document-count">
                      {workspace.document_count || 0} files
                    </span>
                  </td>
                  <td className="date-cell">
                    {formatDate(workspace.last_activity)}
                  </td>
                  <td className="date-cell">
                    {formatDate(workspace.created_at)}
                  </td>
                  <td>
                    <div className="action-buttons">
                      {workspace.lead_id && (
                        <Link
                          to={`/leads/${workspace.lead_id}`}
                          className="action-btn"
                          title="View Lead Profile"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                            <circle cx="12" cy="7" r="4" />
                          </svg>
                        </Link>
                      )}
                      <a
                        href={`${PURL_DOMAIN}/portal/${workspace.slug}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="action-btn"
                        title="Open Portal"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                      <button
                        className="action-btn"
                        title="Copy Portal Link"
                        onClick={() => {
                          navigator.clipboard.writeText(`${PURL_DOMAIN}/portal/${workspace.slug}`);
                          toast.success('Portal link copied!');
                        }}
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination would go here */}
      {filteredWorkspaces.length > 0 && (
        <div className="table-footer">
          <span className="showing-text">
            Showing {filteredWorkspaces.length} of {workspaces.length} portals
          </span>
        </div>
      )}
    </div>
  );
}

export default PURLDashboard;
