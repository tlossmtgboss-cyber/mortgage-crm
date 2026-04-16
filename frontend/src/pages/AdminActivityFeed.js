/**
 * AdminActivityFeed Page
 *
 * Real-time activity feed showing document uploads, status changes,
 * and borrower portal interactions across all loans.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import './AdminActivityFeed.css';
import { getToken } from '../utils/tokenStore';

const AdminActivityFeed = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access
  const canAccessAdminFeed = isAdmin || hasAnyPermission(['admin.view', 'admin.manage', 'system.admin']) || userRole === 'admin' || userRole === 'management';

  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filters, setFilters] = useState({
    activity_type: '',
    lo_id: '',
    date_range: '7',
  });
  const [loanOfficers, setLoanOfficers] = useState([]);
  const [stats, setStats] = useState({
    total_uploads: 0,
    pending_reviews: 0,
    approvals_today: 0,
    active_borrowers: 0,
  });

  const refreshIntervalRef = useRef(null);

  // Fetch activities
  const fetchActivities = useCallback(async () => {
    try {
      const token = getToken();
      const params = new URLSearchParams({
        limit: 50,
        ...(filters.activity_type && { type: filters.activity_type }),
        ...(filters.lo_id && { lo_id: filters.lo_id }),
        days: filters.date_range,
      });

      const response = await fetch(
        `${API_BASE_URL}/api/v1/perennia-docs/activity-feed?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch activities');
      }

      const data = await response.json();
      setActivities(data.activities || []);
      if (data.stats) {
        setStats(data.stats);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  // Fetch loan officers for filter
  const fetchLoanOfficers = useCallback(async () => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/users?role=loan_officer`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setLoanOfficers(data.users || []);
      }
    } catch (err) {
      console.error('Failed to fetch loan officers:', err);
    }
  }, []);

  useEffect(() => {
    fetchLoanOfficers();
  }, [fetchLoanOfficers]);

  useEffect(() => {
    fetchActivities();
  }, [fetchActivities]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(fetchActivities, 30000);
    } else {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [autoRefresh, fetchActivities]);

  // Handle filter changes
  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setLoading(true);
  };

  // Get activity icon
  const getActivityIcon = (type) => {
    switch (type) {
      case 'document_uploaded':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
          </svg>
        );
      case 'document_approved':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        );
      case 'document_rejected':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        );
      case 'borrower_login':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
            <polyline points="10 17 15 12 10 7" />
            <line x1="15" y1="12" x2="3" y2="12" />
          </svg>
        );
      case 'status_change':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        );
      case 'message_sent':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        );
      case 'reminder_sent':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        );
      default:
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        );
    }
  };

  // Get activity type class
  const getActivityClass = (type) => {
    if (type.includes('upload')) return 'upload';
    if (type.includes('approved')) return 'approved';
    if (type.includes('rejected')) return 'rejected';
    if (type.includes('login')) return 'login';
    if (type.includes('message') || type.includes('reminder')) return 'message';
    if (type.includes('status')) return 'status';
    return '';
  };

  // Format relative time
  const formatRelativeTime = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return date.toLocaleDateString();
  };

  // Format activity description
  const formatActivityDescription = (activity) => {
    const { type, actor_name, borrower_name, document_type, loan_number, details } = activity;

    switch (type) {
      case 'document_uploaded':
        return (
          <>
            <strong>{borrower_name}</strong> uploaded a{' '}
            <span className="highlight">{formatDocType(document_type)}</span> for loan{' '}
            <span className="loan-link">{loan_number}</span>
          </>
        );
      case 'document_approved':
        return (
          <>
            <strong>{actor_name}</strong> approved{' '}
            <span className="highlight">{formatDocType(document_type)}</span> for{' '}
            <strong>{borrower_name}</strong>
          </>
        );
      case 'document_rejected':
        return (
          <>
            <strong>{actor_name}</strong> rejected{' '}
            <span className="highlight">{formatDocType(document_type)}</span> for{' '}
            <strong>{borrower_name}</strong>
            {details?.reason && (
              <span className="rejection-reason">: {details.reason}</span>
            )}
          </>
        );
      case 'borrower_login':
        return (
          <>
            <strong>{borrower_name}</strong> logged into the portal
          </>
        );
      case 'status_change':
        return (
          <>
            Loan <span className="loan-link">{loan_number}</span> moved from{' '}
            <span className="status old">{details?.from_status}</span> to{' '}
            <span className="status new">{details?.to_status}</span>
          </>
        );
      case 'message_sent':
        return (
          <>
            <strong>{actor_name}</strong> sent a message to{' '}
            <strong>{borrower_name}</strong>
          </>
        );
      case 'reminder_sent':
        return (
          <>
            Document reminder sent to <strong>{borrower_name}</strong> for{' '}
            <span className="loan-link">{loan_number}</span>
          </>
        );
      default:
        return activity.description || 'Activity occurred';
    }
  };

  // Format document type
  const formatDocType = (type) => {
    if (!type) return 'document';
    return type
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const activityTypes = [
    { id: '', label: 'All Activities' },
    { id: 'document_uploaded', label: 'Document Uploads' },
    { id: 'document_approved', label: 'Document Approvals' },
    { id: 'document_rejected', label: 'Document Rejections' },
    { id: 'borrower_login', label: 'Portal Logins' },
    { id: 'status_change', label: 'Status Changes' },
    { id: 'message_sent', label: 'Messages Sent' },
    { id: 'reminder_sent', label: 'Reminders Sent' },
  ];

  // Access denied if user doesn't have admin permissions
  if (!canAccessAdminFeed) {
    return (
      <div className="admin-activity-feed-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to view the Activity Feed.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-activity-feed-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Activity Feed</h1>
          <p>Real-time document and portal activity across all loans</p>
        </div>
        <div className="header-controls">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh</span>
          </label>
          <button className="btn-secondary" onClick={fetchActivities} disabled={loading}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon uploads">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          </div>
          <div className="stat-content">
            <span className="stat-value">{stats.total_uploads}</span>
            <span className="stat-label">Total Uploads</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon pending">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div className="stat-content">
            <span className="stat-value">{stats.pending_reviews}</span>
            <span className="stat-label">Pending Review</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon approvals">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="stat-content">
            <span className="stat-value">{stats.approvals_today}</span>
            <span className="stat-label">Approved Today</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon borrowers">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <div className="stat-content">
            <span className="stat-value">{stats.active_borrowers}</span>
            <span className="stat-label">Active Borrowers</span>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Filters */}
      <div className="filters-bar">
        <div className="filter-group">
          <select
            value={filters.activity_type}
            onChange={(e) => handleFilterChange('activity_type', e.target.value)}
          >
            {activityTypes.map((type) => (
              <option key={type.id} value={type.id}>
                {type.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <select
            value={filters.lo_id}
            onChange={(e) => handleFilterChange('lo_id', e.target.value)}
          >
            <option value="">All Loan Officers</option>
            {loanOfficers.map((lo) => (
              <option key={lo.id} value={lo.id}>
                {lo.name}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <select
            value={filters.date_range}
            onChange={(e) => handleFilterChange('date_range', e.target.value)}
          >
            <option value="1">Today</option>
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
            <option value="90">Last 90 Days</option>
          </select>
        </div>
      </div>

      {/* Activity List */}
      <div className="activity-feed-container">
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>Loading activities...</p>
          </div>
        ) : activities.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
            <h3>No Activities</h3>
            <p>No activities match your current filters.</p>
          </div>
        ) : (
          <div className="activity-list">
            {activities.map((activity) => (
              <div
                key={activity.id}
                className={`activity-item ${getActivityClass(activity.type)}`}
              >
                <div className={`activity-icon ${getActivityClass(activity.type)}`}>
                  {getActivityIcon(activity.type)}
                </div>
                <div className="activity-content">
                  <p className="activity-description">
                    {formatActivityDescription(activity)}
                  </p>
                  <div className="activity-meta">
                    <span className="activity-time">
                      {formatRelativeTime(activity.created_at)}
                    </span>
                    {activity.lo_name && (
                      <span className="activity-lo">LO: {activity.lo_name}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminActivityFeed;
