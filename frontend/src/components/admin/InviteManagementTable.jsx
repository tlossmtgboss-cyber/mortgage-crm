import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import './InviteManagementTable.css';
import { toast } from '../../utils/toast';

const InviteManagementTable = ({ onInviteNew }) => {
  const [invites, setInvites] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [actionLoading, setActionLoading] = useState(null);

  const API_BASE = (process.env.REACT_APP_API_URL || 'https://api.perenniaai.com') + '/api';

  useEffect(() => {
    loadInvites();
  }, [filter]);

  const loadInvites = async () => {
    setIsLoading(true);
    try {
      const url = filter === 'all'
        ? `${API_BASE}/admin/invites`
        : `${API_BASE}/admin/invites?status=${filter}`;

      const response = await fetch(url, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setInvites(data.invites || []);
      }
    } catch (error) {
      console.error('Error loading invites:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevoke = async (inviteId) => {
    setActionLoading(inviteId);
    try {
      const response = await fetch(`${API_BASE}/admin/invites/${inviteId}/revoke`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        loadInvites();
      } else {
        toast.error('Failed to revoke invite');
      }
    } catch (error) {
      console.error('Error revoking invite:', error);
      toast.error('Failed to revoke invite');
    } finally {
      setActionLoading(null);
    }
  };

  const copyInviteLink = (token) => {
    const frontendUrl = window.location.origin;
    const inviteUrl = `${frontendUrl}/accept-invite?token=${token}`;
    navigator.clipboard.writeText(inviteUrl);
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      pending: { label: 'Pending', className: 'status-pending' },
      accepted: { label: 'Accepted', className: 'status-accepted' },
      expired: { label: 'Expired', className: 'status-expired' },
      revoked: { label: 'Revoked', className: 'status-revoked' }
    };
    const config = statusConfig[status] || { label: status, className: '' };
    return <span className={`status-badge ${config.className}`}>{config.label}</span>;
  };

  const getRoleBadge = (role) => {
    const roleConfig = {
      admin: { label: 'Admin', className: 'role-admin' },
      leadership: { label: 'Leadership', className: 'role-leadership' },
      management: { label: 'Management', className: 'role-management' },
      sales: { label: 'Sales', className: 'role-sales' },
      processing: { label: 'Processing', className: 'role-processing' },
      operations: { label: 'Operations', className: 'role-operations' }
    };
    const config = roleConfig[role] || { label: role, className: '' };
    return <span className={`role-badge ${config.className}`}>{config.label}</span>;
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const filteredInvites = invites.filter(invite => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      invite.email?.toLowerCase().includes(search) ||
      invite.first_name?.toLowerCase().includes(search) ||
      invite.last_name?.toLowerCase().includes(search) ||
      invite.job_title?.toLowerCase().includes(search)
    );
  });

  const stats = {
    total: invites.length,
    pending: invites.filter(i => i.status === 'pending').length,
    accepted: invites.filter(i => i.status === 'accepted').length,
    expired: invites.filter(i => i.status === 'expired').length
  };

  return (
    <div className="invite-management">
      {/* Stats Cards */}
      <div className="stats-row">
        <div className="stat-card">
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">Total Invites</span>
        </div>
        <div className="stat-card pending">
          <span className="stat-value">{stats.pending}</span>
          <span className="stat-label">Pending</span>
        </div>
        <div className="stat-card accepted">
          <span className="stat-value">{stats.accepted}</span>
          <span className="stat-label">Accepted</span>
        </div>
        <div className="stat-card expired">
          <span className="stat-value">{stats.expired}</span>
          <span className="stat-label">Expired</span>
        </div>
      </div>

      {/* Controls */}
      <div className="table-controls">
        <div className="search-box">
          <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            placeholder="Search by name, email, or title..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="filter-tabs">
          {['all', 'pending', 'accepted', 'expired', 'revoked'].map(status => (
            <button
              key={status}
              className={`filter-tab ${filter === status ? 'active' : ''}`}
              onClick={() => setFilter(status)}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>

        <button className="btn-invite-new" onClick={onInviteNew}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Invite New
        </button>
      </div>

      {/* Table */}
      <div className="table-container">
        {isLoading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading invites...</p>
          </div>
        ) : filteredInvites.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            <h3>No invites found</h3>
            <p>{searchTerm ? 'Try adjusting your search' : 'Create your first employee invite'}</p>
            {!searchTerm && (
              <button className="btn-primary" onClick={onInviteNew}>
                Invite New Employee
              </button>
            )}
          </div>
        ) : (
          <table className="invites-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th>Expires / Accepted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredInvites.map(invite => (
                <tr key={invite.id}>
                  <td className="employee-cell">
                    <div className="employee-avatar">
                      {invite.first_name?.charAt(0)}{invite.last_name?.charAt(0)}
                    </div>
                    <div className="employee-info">
                      <span className="employee-name">{invite.first_name} {invite.last_name}</span>
                      <span className="employee-email">{invite.email}</span>
                      {invite.job_title && <span className="employee-title">{invite.job_title}</span>}
                    </div>
                  </td>
                  <td>{getRoleBadge(invite.permission_role)}</td>
                  <td>{getStatusBadge(invite.status)}</td>
                  <td className="date-cell">{formatDate(invite.created_at)}</td>
                  <td className="date-cell">
                    {invite.status === 'accepted'
                      ? formatDate(invite.accepted_at)
                      : formatDate(invite.expires_at)
                    }
                  </td>
                  <td className="actions-cell">
                    {invite.status === 'pending' && (
                      <>
                        <button
                          className="action-btn copy"
                          onClick={() => copyInviteLink(invite.invite_token)}
                          title="Copy invite link"
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                          </svg>
                        </button>
                        <button
                          className="action-btn revoke"
                          onClick={() => handleRevoke(invite.id)}
                          disabled={actionLoading === invite.id}
                          title="Revoke invite"
                        >
                          {actionLoading === invite.id ? (
                            <div className="btn-spinner"></div>
                          ) : (
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="10" />
                              <path d="M15 9l-6 6M9 9l6 6" />
                            </svg>
                          )}
                        </button>
                      </>
                    )}
                    {invite.status === 'accepted' && (
                      <span className="accepted-label">Completed</span>
                    )}
                    {(invite.status === 'expired' || invite.status === 'revoked') && (
                      <span className="inactive-label">{invite.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default InviteManagementTable;
