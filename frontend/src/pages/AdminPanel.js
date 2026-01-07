import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { RoleDashboardSwitcher } from '../components/dashboards/RoleDashboards';
import './AdminPanel.css';

/**
 * AdminPanel - Administrative Dashboard
 *
 * Features:
 * - User management
 * - LO/Realtor management
 * - System stats overview
 * - Microsite management
 * - Configuration settings
 */

const AdminPanel = () => {
  const navigate = useNavigate();
  const { userRole, hasPermission, hasAnyPermission } = usePermissions();

  // Permission check - require admin access
  const canAccessAdmin = hasAnyPermission(['admin.view', 'admin.manage', 'system.admin']) || userRole === 'admin' || userRole === 'management';

  // State
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loanOfficers, setLoanOfficers] = useState([]);
  const [realtors, setRealtors] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [aiMetrics, setAiMetrics] = useState(null);
  const [aiMetricsDays, setAiMetricsDays] = useState(7);
  const [aiMetricsLoading, setAiMetricsLoading] = useState(false);
  const [aiMetricsLastUpdate, setAiMetricsLastUpdate] = useState(null);

  // Security monitoring state
  const [securityData, setSecurityData] = useState(null);
  const [securityLoading, setSecurityLoading] = useState(false);

  // Account Management state
  const [accountKpis, setAccountKpis] = useState(null);
  const [accountKpisLoading, setAccountKpisLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountFilter, setAccountFilter] = useState('active');

  // Mission Control state
  const [missionControlData, setMissionControlData] = useState(null);
  const [missionControlLoading, setMissionControlLoading] = useState(false);
  const [missionControlRefreshing, setMissionControlRefreshing] = useState(false);

  // Role switcher state
  const [selectedDashboardView, setSelectedDashboardView] = useState('admin');

  // Handle role view change
  const handleViewChange = (roleId) => {
    setSelectedDashboardView(roleId);
    // Navigate to dashboard if selecting a non-admin role to see that role's view
    if (roleId !== 'admin' && roleId !== 'site_admin') {
      navigate('/dashboard');
    }
  };

  // Modal state
  const [showUserModal, setShowUserModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userForm, setUserForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    role: 'user',
    company: '',
    nmls_id: '',
    slug: '',
    bio: '',
    is_active: true
  });
  const [saving, setSaving] = useState(false);

  // Load dashboard data
  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);

      const [statsRes, usersRes] = await Promise.allSettled([
        api.get('/api/v1/admin/stats'),
        api.get('/api/v1/admin/users'),
      ]);

      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data);
      } else {
        setStats({
          total_users: 0,
          total_los: 0,
          total_realtors: 0,
          total_leads: 0,
          total_loans: 0,
          mtd_volume: 0
        });
      }

      if (usersRes.status === 'fulfilled') {
        const allUsers = usersRes.value.data.users || usersRes.value.data || [];
        setUsers(allUsers);
        setLoanOfficers(allUsers.filter(u => u.role === 'loan_officer'));
        setRealtors(allUsers.filter(u => u.role === 'realtor'));
      }

    } catch (err) {
      console.error('Admin dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // Load AI Metrics
  const loadAiMetrics = useCallback(async () => {
    try {
      setAiMetricsLoading(true);
      const response = await api.get(`/api/v1/ai-metrics/dashboard?days=${aiMetricsDays}`);
      setAiMetrics(response.data);
      setAiMetricsLastUpdate(new Date());
    } catch (err) {
      console.error('Error loading AI metrics:', err);
      setAiMetrics(null);
    } finally {
      setAiMetricsLoading(false);
    }
  }, [aiMetricsDays]);

  // Load AI metrics when tab is active or days change, with auto-refresh
  useEffect(() => {
    if (activeTab === 'ai_metrics') {
      loadAiMetrics();

      // Auto-refresh every 30 seconds for real-time data
      const interval = setInterval(() => {
        loadAiMetrics();
      }, 30000);

      return () => clearInterval(interval);
    }
  }, [activeTab, aiMetricsDays, loadAiMetrics]);

  // Load Security Data
  const loadSecurityData = useCallback(async () => {
    try {
      setSecurityLoading(true);
      const response = await api.get('/api/v1/admin/security/dashboard');
      setSecurityData(response.data);
    } catch (err) {
      console.error('Error loading security data:', err);
      setSecurityData(null);
    } finally {
      setSecurityLoading(false);
    }
  }, []);

  // Load security data when tab is active (overview or security)
  useEffect(() => {
    if (activeTab === 'security' || activeTab === 'overview') {
      loadSecurityData();
    }
  }, [activeTab, loadSecurityData]);

  // Load Mission Control data
  const loadMissionControl = useCallback(async () => {
    try {
      setMissionControlLoading(true);
      const response = await api.get('/api/v1/mission-control/integrations');
      setMissionControlData(response.data);
    } catch (err) {
      console.error('Error loading Mission Control:', err);
      setMissionControlData(null);
    } finally {
      setMissionControlLoading(false);
    }
  }, []);

  // Refresh Mission Control (trigger health checks)
  const refreshMissionControl = useCallback(async () => {
    try {
      setMissionControlRefreshing(true);
      const response = await api.post('/api/v1/mission-control/refresh');
      // After refresh, reload the data
      if (response.data?.status === 'success') {
        await loadMissionControl();
      }
    } catch (err) {
      console.error('Error refreshing Mission Control:', err);
      alert('Failed to refresh system health checks');
    } finally {
      setMissionControlRefreshing(false);
    }
  }, [loadMissionControl]);

  // Load Mission Control when settings tab is active
  useEffect(() => {
    if (activeTab === 'settings') {
      loadMissionControl();
    }
  }, [activeTab, loadMissionControl]);

  // Load Account Management KPIs
  const loadAccountKpis = useCallback(async () => {
    try {
      setAccountKpisLoading(true);
      const response = await api.get('/api/v1/admin/account-management/kpis');
      setAccountKpis(response.data?.data || response.data);
    } catch (err) {
      console.error('Error loading account KPIs:', err);
      setAccountKpis(null);
    } finally {
      setAccountKpisLoading(false);
    }
  }, []);

  // Load Accounts List
  const loadAccounts = useCallback(async (status = 'active') => {
    try {
      setAccountsLoading(true);
      const response = await api.get(`/api/v1/admin/account-management/accounts?status=${status}`);
      setAccounts(response.data?.data?.accounts || response.data?.accounts || []);
    } catch (err) {
      console.error('Error loading accounts:', err);
      setAccounts([]);
    } finally {
      setAccountsLoading(false);
    }
  }, []);

  // Load account data on mount and when filter changes
  useEffect(() => {
    loadAccountKpis();
  }, [loadAccountKpis]);

  useEffect(() => {
    loadAccounts(accountFilter);
  }, [accountFilter, loadAccounts]);

  // Unblock IP
  const handleUnblockIP = async (ip) => {
    try {
      await api.post(`/api/v1/admin/security/unblock-ip/${ip}`);
      loadSecurityData();
    } catch (err) {
      console.error('Error unblocking IP:', err);
      alert('Failed to unblock IP');
    }
  };

  // Filter users
  const filteredUsers = users.filter(user => {
    const matchesRole = roleFilter === 'all' || user.role === roleFilter;
    const matchesSearch = searchTerm === '' ||
      `${user.first_name} ${user.last_name}`.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (user.email && user.email.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchesRole && matchesSearch;
  });

  // Handle user form input
  const handleUserInput = (e) => {
    const { name, value, type, checked } = e.target;
    setUserForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  // Open edit modal
  const openEditModal = (user) => {
    setSelectedUser(user);
    setUserForm({
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      email: user.email || '',
      phone: user.phone || '',
      role: user.role || 'user',
      company: user.company || '',
      nmls_id: user.nmls_id || '',
      slug: user.slug || '',
      bio: user.bio || '',
      is_active: user.is_active !== false
    });
    setShowUserModal(true);
  };

  // Open new user modal
  const openNewUserModal = () => {
    setSelectedUser(null);
    setUserForm({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      role: 'user',
      company: '',
      nmls_id: '',
      slug: '',
      bio: '',
      is_active: true
    });
    setShowUserModal(true);
  };

  // Save user
  const saveUser = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      if (selectedUser) {
        await api.put(`/api/v1/admin/users/${selectedUser.id}`, userForm);
        setShowUserModal(false);
      } else {
        const response = await api.post('/api/v1/admin/users', userForm);
        setShowUserModal(false);
        // Show temp password if one was generated
        if (response.data?.temp_password) {
          alert(`User created successfully!\n\nTemporary Password: ${response.data.temp_password}\n\nPlease share this password with the user securely. They will need to change it on first login.`);
        }
      }
      loadDashboard();
    } catch (err) {
      console.error('Save user error:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to save user. Please try again.';
      alert(errorMsg);
    } finally {
      setSaving(false);
    }
  };

  // Toggle user active status
  const toggleUserStatus = async (user) => {
    try {
      await api.put(`/api/v1/admin/users/${user.id}`, {
        is_active: !user.is_active
      });
      loadDashboard();
    } catch (err) {
      console.error('Toggle status error:', err);
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount || 0);
  };

  // Get role badge class
  const getRoleClass = (role) => {
    const roleMap = {
      'admin': 'admin',
      'loan_officer': 'lo',
      'realtor': 'realtor',
      'processor': 'processor',
      'user': 'user'
    };
    return roleMap[role] || 'user';
  };

  // Generate microsite URL
  const getMicrositeUrl = (user) => {
    if (user.role !== 'loan_officer') return null;
    const slug = user.slug || user.id;
    return `${window.location.origin}/lo/${slug}`;
  };

  // Access denied if user doesn't have admin permissions
  if (!canAccessAdmin) {
    return (
      <div className="admin-panel">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access the Admin Panel.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="admin-panel-loading">
        <div className="loading-spinner"></div>
        <p>Loading admin panel...</p>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      {/* Header */}
      <header className="admin-header">
        <div className="header-left">
          <h1>Admin Panel</h1>
          <p>Manage users, loan officers, and system settings</p>
        </div>
        <div className="header-right">
          <RoleDashboardSwitcher
            currentView={selectedDashboardView}
            onViewChange={handleViewChange}
            isAdmin={true}
          />
          <button className="btn-primary" onClick={openNewUserModal}>
            + Add User
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="admin-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          All Users
        </button>
        <button
          className={`tab ${activeTab === 'loan_officers' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan_officers')}
        >
          Loan Officers
        </button>
        <button
          className={`tab ${activeTab === 'realtors' ? 'active' : ''}`}
          onClick={() => setActiveTab('realtors')}
        >
          Partners
        </button>
        <button
          className={`tab ${activeTab === 'ai_metrics' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai_metrics')}
        >
          AI Metrics
        </button>
        <button
          className={`tab ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
        >
          Security
        </button>
        <button
          className={`tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </nav>

      <main className="admin-content">
        {activeTab === 'overview' && (
          <>
            {/* Security Summary */}
            <section className="security-summary-section">
              <div className="section-header">
                <h2>Security Overview</h2>
                <button onClick={() => setActiveTab('security')} className="btn-secondary btn-sm">
                  View Full Security Dashboard →
                </button>
              </div>

              {securityLoading && !securityData ? (
                <div className="loading-placeholder">Loading security data...</div>
              ) : securityData ? (
                <>
                  {/* Security Alerts */}
                  {((securityData.ip_blocking?.blocked_count || 0) > 0 ||
                    (securityData.failed_logins?.recent_failed_attempts || 0) >= 5) && (
                    <div className="security-alerts">
                      {(securityData.ip_blocking?.blocked_count || 0) > 0 && (
                        <div className="security-alert warning">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                          </svg>
                          <span><strong>{securityData.ip_blocking.blocked_count} IP(s) blocked</strong> for security violations</span>
                        </div>
                      )}
                      {(securityData.failed_logins?.recent_failed_attempts || 0) >= 5 && (
                        <div className="security-alert danger">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                          </svg>
                          <span><strong>{securityData.failed_logins.recent_failed_attempts} failed login attempts</strong> detected recently</span>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="security-metrics-grid">
                    <div
                      className={`security-metric-card clickable ${securityData.status === 'active' ? 'status-good' : 'status-warning'}`}
                      onClick={() => setActiveTab('security')}
                      title="View System Status Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{securityData.status === 'active' ? 'SECURE' : 'CHECK'}</span>
                        <span className="metric-label-sm">System Status</span>
                      </div>
                    </div>

                    <div
                      className={`security-metric-card clickable ${(securityData.ip_blocking?.blocked_count || 0) > 0 ? 'status-warning' : 'status-good'}`}
                      onClick={() => setActiveTab('security')}
                      title="View Blocked IPs Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/>
                          <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{securityData.ip_blocking?.blocked_count || 0}</span>
                        <span className="metric-label-sm">Blocked IPs</span>
                      </div>
                    </div>

                    <div
                      className={`security-metric-card clickable ${(securityData.failed_logins?.recent_failed_attempts || 0) >= 5 ? 'status-danger' : (securityData.failed_logins?.recent_failed_attempts || 0) > 0 ? 'status-warning' : 'status-good'}`}
                      onClick={() => setActiveTab('security')}
                      title="View Failed Logins Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{securityData.failed_logins?.recent_failed_attempts || 0}</span>
                        <span className="metric-label-sm">Failed Logins</span>
                      </div>
                    </div>

                    <div
                      className="security-metric-card clickable status-info"
                      onClick={() => setActiveTab('security')}
                      title="View Rate Limits Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{securityData.rate_limiting?.active_keys || 0}</span>
                        <span className="metric-label-sm">Rate Limits Active</span>
                      </div>
                    </div>

                    <div
                      className="security-metric-card clickable status-info"
                      onClick={() => setActiveTab('security')}
                      title="View Requests Tracking Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                          <polyline points="14 2 14 8 20 8"/>
                          <line x1="16" y1="13" x2="8" y2="13"/>
                          <line x1="16" y1="17" x2="8" y2="17"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{securityData.rate_limiting?.total_requests_tracked || 0}</span>
                        <span className="metric-label-sm">Requests Tracked</span>
                      </div>
                    </div>

                    <div
                      className="security-metric-card clickable status-good"
                      onClick={() => setActiveTab('security')}
                      title="View Middleware Status Details"
                    >
                      <div className="metric-icon-sm">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                          <polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                      </div>
                      <div className="metric-info">
                        <span className="metric-value-sm">{Object.values(securityData.middleware_status || {}).filter(Boolean).length}</span>
                        <span className="metric-label-sm">Middleware Active</span>
                      </div>
                    </div>
                  </div>

                  {/* Recent Blocked IPs */}
                  {securityData.ip_blocking?.blocked_ips?.length > 0 && (
                    <div className="security-blocked-preview">
                      <h4>Recently Blocked IPs</h4>
                      <div className="blocked-ips-compact">
                        {securityData.ip_blocking.blocked_ips.slice(0, 3).map((ip, idx) => (
                          <span key={idx} className="blocked-ip-tag">
                            {ip}
                            <button onClick={() => handleUnblockIP(ip)} className="unblock-btn" title="Unblock">×</button>
                          </span>
                        ))}
                        {securityData.ip_blocking.blocked_ips.length > 3 && (
                          <span className="more-ips">+{securityData.ip_blocking.blocked_ips.length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Top Failed Login Attempts */}
                  {securityData.failed_logins?.top_offenders?.length > 0 && (
                    <div className="security-offenders-preview">
                      <h4>Top Failed Login Attempts</h4>
                      <div className="offenders-compact">
                        {securityData.failed_logins.top_offenders.slice(0, 3).map((item, idx) => (
                          <div key={idx} className="offender-item">
                            <span className="offender-ip">{item.ip}</span>
                            <span className={`offender-attempts ${item.attempts >= 5 ? 'danger' : 'warning'}`}>
                              {item.attempts} attempts
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="security-unavailable">
                  <p>Security monitoring data unavailable</p>
                  <button onClick={loadSecurityData} className="btn-secondary btn-sm">Retry</button>
                </div>
              )}
            </section>

            {/* Account Management */}
            <section className="account-management-section">
              <div className="section-header">
                <h2>Account Management</h2>
                <button onClick={() => navigate('/settings/account-management?action=invite')} className="btn-primary btn-sm">
                  + Invite Subscriber
                </button>
              </div>
              <p className="section-subtitle">Manage all business accounts, users, subscriptions, and costs.</p>

              {accountKpisLoading ? (
                <div className="loading-placeholder">Loading account data...</div>
              ) : (
                <>
                  <div className="account-metrics-grid">
                    <div className="account-metric-card">
                      <span className="metric-label">ACTIVE ACCOUNTS</span>
                      <span className="metric-value">{accountKpis?.totalActiveAccounts || 0}</span>
                      <span className="metric-sublabel">{accountKpis?.totalSuspendedAccounts || 0} suspended</span>
                    </div>

                    <div className="account-metric-card highlight-green">
                      <span className="metric-label">TOTAL MRR</span>
                      <span className="metric-value">${(accountKpis?.totalMRR || 0).toLocaleString()}</span>
                      <span className="metric-sublabel">${(accountKpis?.totalARR || 0).toLocaleString()} ARR</span>
                      {accountKpis?.mrrGrowth > 0 && (
                        <span className="metric-growth positive">↑ {accountKpis.mrrGrowth}% vs last month</span>
                      )}
                    </div>

                    <div className="account-metric-card highlight-blue">
                      <span className="metric-label">SEAT UTILIZATION</span>
                      <span className="metric-value">
                        {accountKpis?.totalSeatsPurchased > 0
                          ? ((accountKpis.totalSeatsUsed / accountKpis.totalSeatsPurchased) * 100).toFixed(1)
                          : 0}%
                      </span>
                      <span className="metric-sublabel">
                        {accountKpis?.totalSeatsUsed || 0} / {accountKpis?.totalSeatsPurchased || 0}
                      </span>
                    </div>

                    <div className="account-metric-card">
                      <span className="metric-label">AVG COST/USER</span>
                      <span className="metric-value">${accountKpis?.avgCostPerUser || 0}</span>
                      <span className="metric-sublabel">per month</span>
                    </div>

                    <div className="account-metric-card highlight-yellow">
                      <span className="metric-label">AVG MARGIN</span>
                      <span className="metric-value">{accountKpis?.avgMarginPercent || 0}%</span>
                      <span className="metric-sublabel">gross margin</span>
                    </div>

                    <div className="account-metric-card highlight-red">
                      <span className="metric-label">AT RISK</span>
                      <span className="metric-value">{accountKpis?.accountsAtRisk || 0}</span>
                      <span className="metric-sublabel">{accountKpis?.accountsNoActivity30d || 0} inactive</span>
                    </div>
                  </div>

                  <div className="account-stats-row">
                    <span className="churn-stat">Churn Rate: <strong>{accountKpis?.churnRate || 0}%</strong></span>
                    <span className="canceled-stat">Canceled: <strong>{accountKpis?.totalCanceledAccounts || 0}</strong></span>
                  </div>

                  {/* Subscriptions Tabs */}
                  <div className="subscriptions-tabs">
                    <button
                      className={`sub-tab ${accountFilter === 'active' ? 'active' : ''}`}
                      onClick={() => setAccountFilter('active')}
                    >
                      Active Subscriptions <span className="badge">{accountKpis?.totalActiveAccounts || 0}</span>
                    </button>
                    <button
                      className={`sub-tab ${accountFilter === 'suspended' ? 'active' : ''}`}
                      onClick={() => setAccountFilter('suspended')}
                    >
                      Suspended Subscriptions <span className="badge">{accountKpis?.totalSuspendedAccounts || 0}</span>
                    </button>
                    <button
                      className={`sub-tab ${accountFilter === 'canceled' ? 'active' : ''}`}
                      onClick={() => setAccountFilter('canceled')}
                    >
                      Canceled Subscriptions <span className="badge">{accountKpis?.totalCanceledAccounts || 0}</span>
                    </button>
                  </div>

                  {/* Accounts List */}
                  {accountsLoading ? (
                    <div className="loading-placeholder">Loading accounts...</div>
                  ) : accounts.length > 0 ? (
                    <div className="accounts-table-container">
                      <table className="accounts-table">
                        <thead>
                          <tr>
                            <th>Account</th>
                            <th>Plan</th>
                            <th>Seats</th>
                            <th>MRR</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {accounts.slice(0, 5).map(account => (
                            <tr key={account.id} onClick={() => navigate(`/settings/account-management?account=${account.id}`)}>
                              <td>
                                <div className="account-name">{account.company_name || account.name}</div>
                                <div className="account-domain">{account.domain}</div>
                              </td>
                              <td><span className="plan-badge">{account.plan || 'Professional'}</span></td>
                              <td>{account.seats_used || 0} / {account.seats_purchased || 0}</td>
                              <td>${(account.mrr || 0).toLocaleString()}</td>
                              <td><span className={`status-badge ${account.status}`}>{account.status}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {accounts.length > 5 && (
                        <button className="btn-link view-all" onClick={() => navigate('/settings/account-management')}>
                          View all {accounts.length} accounts →
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="empty-state">No {accountFilter} accounts found</div>
                  )}
                </>
              )}
            </section>

          </>
        )}

        {activeTab === 'users' && (
          <section className="users-section">
            <div className="section-header">
              <h2>All Users</h2>
              <div className="section-actions">
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Search users..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                </div>
                <select
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                >
                  <option value="all">All Roles</option>
                  <option value="admin">Admin</option>
                  <option value="loan_officer">Loan Officer</option>
                  <option value="realtor">Realtor</option>
                  <option value="processor">Processor</option>
                  <option value="user">User</option>
                </select>
                <button className="btn-primary" onClick={openNewUserModal}>
                  + Add User
                </button>
              </div>
            </div>

            <table className="users-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map(user => (
                  <tr key={user.id}>
                    <td>
                      <div className="user-cell">
                        <div className="user-avatar-small">
                          {(user.first_name || user.email || 'U').charAt(0).toUpperCase()}
                        </div>
                        <span>{user.first_name} {user.last_name}</span>
                      </div>
                    </td>
                    <td>{user.email}</td>
                    <td>
                      <span className={`role-badge ${getRoleClass(user.role)}`}>
                        {user.role?.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <div className="action-buttons">
                        <button
                          className="btn-edit"
                          onClick={() => openEditModal(user)}
                        >
                          Edit
                        </button>
                        <button
                          className="btn-toggle"
                          onClick={() => toggleUserStatus(user)}
                        >
                          {user.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {activeTab === 'loan_officers' && (
          <section className="lo-section">
            <div className="section-header">
              <h2>Loan Officers</h2>
              <button
                className="btn-primary"
                onClick={() => {
                  setUserForm(prev => ({ ...prev, role: 'loan_officer' }));
                  openNewUserModal();
                }}
              >
                + Add LO
              </button>
            </div>

            <div className="lo-grid">
              {loanOfficers.map(lo => (
                <div key={lo.id} className="lo-card">
                  <div className="lo-avatar">
                    {lo.avatar_url ? (
                      <img src={lo.avatar_url} alt={lo.first_name} />
                    ) : (
                      <span>{(lo.first_name || 'L').charAt(0).toUpperCase()}</span>
                    )}
                  </div>
                  <div className="lo-info">
                    <h3>{lo.first_name} {lo.last_name}</h3>
                    <p className="lo-company">{lo.company || 'Mortgage Lending'}</p>
                    {lo.nmls_id && <p className="lo-nmls">NMLS# {lo.nmls_id}</p>}
                    <p className="lo-email">{lo.email}</p>
                  </div>
                  <div className="lo-microsite">
                    <label>Microsite URL:</label>
                    <div className="url-box">
                      <input
                        type="text"
                        value={getMicrositeUrl(lo) || ''}
                        readOnly
                      />
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(getMicrositeUrl(lo));
                          alert('URL copied!');
                        }}
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                  <div className="lo-actions">
                    <button className="btn-edit" onClick={() => openEditModal(lo)}>
                      Edit Profile
                    </button>
                    <a
                      href={getMicrositeUrl(lo)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-view"
                    >
                      View Microsite
                    </a>
                  </div>
                </div>
              ))}

              {loanOfficers.length === 0 && (
                <div className="empty-state">
                  <p>No loan officers yet</p>
                  <button
                    className="btn-primary"
                    onClick={() => {
                      setUserForm(prev => ({ ...prev, role: 'loan_officer' }));
                      openNewUserModal();
                    }}
                  >
                    Add First LO
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === 'realtors' && (
          <section className="realtors-section">
            <div className="section-header">
              <h2>Partners</h2>
              <button
                className="btn-primary"
                onClick={() => {
                  setUserForm(prev => ({ ...prev, role: 'realtor' }));
                  openNewUserModal();
                }}
              >
                + Add Partner
              </button>
            </div>

            <table className="users-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Company</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {realtors.map(realtor => (
                  <tr key={realtor.id}>
                    <td>
                      <div className="user-cell">
                        <div className="user-avatar-small">
                          {(realtor.first_name || 'R').charAt(0).toUpperCase()}
                        </div>
                        <span>{realtor.first_name} {realtor.last_name}</span>
                      </div>
                    </td>
                    <td>{realtor.email}</td>
                    <td>{realtor.company || '-'}</td>
                    <td>
                      <span className={`status-badge ${realtor.is_active ? 'active' : 'inactive'}`}>
                        {realtor.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <div className="action-buttons">
                        <button className="btn-edit" onClick={() => openEditModal(realtor)}>
                          Edit
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {realtors.length === 0 && (
              <div className="empty-state">
                <p>No partners yet</p>
                <button
                  className="btn-primary"
                  onClick={() => {
                    setUserForm(prev => ({ ...prev, role: 'realtor' }));
                    openNewUserModal();
                  }}
                >
                  Add First Partner
                </button>
              </div>
            )}
          </section>
        )}

        {activeTab === 'ai_metrics' && (
          <section className="ai-metrics-section">
            <div className="section-header">
              <div className="header-title-group">
                <h2>AI Agent Metrics</h2>
                {aiMetricsLastUpdate && (
                  <span className="last-update-text">
                    Last updated: {aiMetricsLastUpdate.toLocaleTimeString()}
                    {aiMetricsLoading && <span className="refresh-indicator"> • Refreshing...</span>}
                  </span>
                )}
              </div>
              <div className="section-actions">
                <span className="auto-refresh-badge">Auto-refresh: 30s</span>
                <select
                  value={aiMetricsDays}
                  onChange={(e) => setAiMetricsDays(parseInt(e.target.value))}
                  className="days-select"
                >
                  <option value="7">Last 7 days</option>
                  <option value="14">Last 14 days</option>
                  <option value="30">Last 30 days</option>
                  <option value="90">Last 90 days</option>
                </select>
                <button
                  className={`btn-secondary ${aiMetricsLoading ? 'loading' : ''}`}
                  onClick={loadAiMetrics}
                  disabled={aiMetricsLoading}
                >
                  {aiMetricsLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
            </div>

            {aiMetrics ? (
              <>
                {/* Hallucination Metrics */}
                <div className="metrics-section">
                  <h3>Hallucination Tracking</h3>
                  <div className="metrics-grid">
                    <div className="metric-card faithfulness">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                          <polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.hallucination_metrics?.avg_faithfulness_score || 1) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Faithfulness Score</span>
                        <span className="metric-sublabel">Claims verified by source data</span>
                      </div>
                    </div>

                    <div className="metric-card hallucination">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/>
                          <line x1="12" y1="8" x2="12" y2="12"/>
                          <line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.hallucination_metrics?.avg_hallucination_rate || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Hallucination Rate</span>
                        <span className="metric-sublabel">Claims contradicting source</span>
                      </div>
                    </div>

                    <div className="metric-card responses">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.hallucination_metrics?.total_responses_analyzed || 0}
                        </span>
                        <span className="metric-label">Responses Analyzed</span>
                        <span className="metric-sublabel">
                          {aiMetrics.hallucination_metrics?.clean_responses || 0} clean,{' '}
                          {aiMetrics.hallucination_metrics?.responses_with_hallucinations || 0} with issues
                        </span>
                      </div>
                    </div>

                    <div className="metric-card claims">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                          <polyline points="14 2 14 8 20 8"/>
                          <line x1="16" y1="13" x2="8" y2="13"/>
                          <line x1="16" y1="17" x2="8" y2="17"/>
                          <polyline points="10 9 9 9 8 9"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.hallucination_metrics?.total_claims_extracted || 0}
                        </span>
                        <span className="metric-label">Claims Extracted</span>
                        <span className="metric-sublabel">
                          {aiMetrics.hallucination_metrics?.verified_claims_count || 0} verified,{' '}
                          {aiMetrics.hallucination_metrics?.contradicted_claims_count || 0} contradicted
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Hallucination by Type */}
                  {Object.keys(aiMetrics.hallucination_metrics?.hallucination_by_type || {}).length > 0 && (
                    <div className="breakdown-card">
                      <h4>Hallucination Rate by Claim Type</h4>
                      <div className="breakdown-bars">
                        {Object.entries(aiMetrics.hallucination_metrics.hallucination_by_type).map(([type, rate]) => (
                          <div key={type} className="breakdown-row">
                            <span className="breakdown-label">{type}</span>
                            <div className="breakdown-bar-container">
                              <div
                                className="breakdown-bar"
                                style={{
                                  width: `${Math.min(rate * 100, 100)}%`,
                                  backgroundColor: rate > 0.1 ? '#ef4444' : rate > 0.05 ? '#f59e0b' : '#22c55e'
                                }}
                              />
                            </div>
                            <span className="breakdown-value">{(rate * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Agent Performance */}
                <div className="metrics-section">
                  <h3>Agent Performance</h3>
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {(aiMetrics.agent_performance?.avg_response_time_ms / 1000).toFixed(2)}s
                        </span>
                        <span className="metric-label">Avg Response Time</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.agent_performance?.tool_success_rate || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Tool Success Rate</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.agent_performance?.satisfaction_rate || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">User Satisfaction</span>
                        <span className="metric-sublabel">
                          {aiMetrics.agent_performance?.thumbs_up_count || 0} 👍 / {aiMetrics.agent_performance?.thumbs_down_count || 0} 👎
                        </span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.agent_performance?.error_rate || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Error Rate</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Business Metrics */}
                <div className="metrics-section">
                  <h3>Business Metrics</h3>
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.business_metrics?.total_queries || 0}
                        </span>
                        <span className="metric-label">Total Queries</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.business_metrics?.unique_users || 0}
                        </span>
                        <span className="metric-label">Unique Users</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {(aiMetrics.business_metrics?.queries_per_user || 0).toFixed(1)}
                        </span>
                        <span className="metric-label">Queries per User</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.business_metrics?.actions_executed || 0}
                        </span>
                        <span className="metric-label">Actions Executed</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* AI Quality */}
                <div className="metrics-section">
                  <h3>AI Quality</h3>
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.ai_quality?.intent_accuracy || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Intent Accuracy</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.ai_quality?.tool_selection_accuracy || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Tool Selection Accuracy</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {((aiMetrics.ai_quality?.followup_click_rate || 0) * 100).toFixed(1)}%
                        </span>
                        <span className="metric-label">Follow-up Click Rate</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-content">
                        <span className="metric-value">
                          {aiMetrics.ai_quality?.user_corrections_count || 0}
                        </span>
                        <span className="metric-label">User Corrections</span>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="loading-metrics">
                <div className="loading-spinner"></div>
                <p>Loading AI metrics...</p>
              </div>
            )}
          </section>
        )}

        {activeTab === 'security' && (
          <section className="security-section">
            <div className="section-header">
              <h2>Security Monitoring</h2>
              <div className="section-actions">
                <button className="btn-secondary" onClick={loadSecurityData} disabled={securityLoading}>
                  {securityLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
            </div>

            {securityLoading && !securityData ? (
              <div className="loading-metrics">
                <div className="loading-spinner"></div>
                <p>Loading security data...</p>
              </div>
            ) : securityData ? (
              <>
                {/* Security Status Overview */}
                <div className="metrics-section">
                  <h3>System Security Status</h3>
                  <div className="metrics-grid">
                    <div className={`metric-card ${securityData.status === 'active' ? 'success' : 'warning'}`}>
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value" style={{color: '#22c55e'}}>ACTIVE</span>
                        <span className="metric-label">Security Status</span>
                        <span className="metric-sublabel">{securityData.environment} environment</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/>
                          <line x1="12" y1="8" x2="12" y2="12"/>
                          <line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">{securityData.ip_blocking?.blocked_count || 0}</span>
                        <span className="metric-label">Blocked IPs</span>
                        <span className="metric-sublabel">Auto-blocked for violations</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                          <polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">{securityData.rate_limiting?.active_keys || 0}</span>
                        <span className="metric-label">Active Rate Limits</span>
                        <span className="metric-sublabel">{securityData.rate_limiting?.total_requests_tracked || 0} requests tracked</span>
                      </div>
                    </div>

                    <div className="metric-card">
                      <div className="metric-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                      </div>
                      <div className="metric-content">
                        <span className="metric-value">{securityData.failed_logins?.recent_failed_attempts || 0}</span>
                        <span className="metric-label">Failed Login Attempts</span>
                        <span className="metric-sublabel">{securityData.failed_logins?.unique_ips || 0} unique IPs</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Middleware Status */}
                <div className="metrics-section">
                  <h3>Security Middleware Status</h3>
                  <div className="middleware-grid">
                    {Object.entries(securityData.middleware_status || {}).map(([name, active]) => (
                      <div key={name} className={`middleware-item ${active ? 'active' : 'inactive'}`}>
                        <span className={`status-dot ${active ? 'green' : 'red'}`}></span>
                        <span className="middleware-name">{name.replace(/_/g, ' ')}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Blocked IPs */}
                {securityData.ip_blocking?.blocked_ips?.length > 0 && (
                  <div className="metrics-section">
                    <h3>Blocked IP Addresses</h3>
                    <div className="blocked-ips-list">
                      {securityData.ip_blocking.blocked_ips.map((ip, index) => (
                        <div key={index} className="blocked-ip-item">
                          <span className="ip-address">{ip}</span>
                          <button
                            className="btn-small btn-danger"
                            onClick={() => handleUnblockIP(ip)}
                          >
                            Unblock
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Top Rate Limit Offenders */}
                {securityData.rate_limiting?.top_requesters?.length > 0 && (
                  <div className="metrics-section">
                    <h3>Top API Requesters</h3>
                    <table className="security-table">
                      <thead>
                        <tr>
                          <th>Identifier</th>
                          <th>Requests</th>
                        </tr>
                      </thead>
                      <tbody>
                        {securityData.rate_limiting.top_requesters.slice(0, 10).map((item, index) => (
                          <tr key={index}>
                            <td>{item.key}</td>
                            <td>{item.requests}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Failed Login Offenders */}
                {securityData.failed_logins?.top_offenders?.length > 0 && (
                  <div className="metrics-section">
                    <h3>Failed Login Attempts by IP</h3>
                    <table className="security-table">
                      <thead>
                        <tr>
                          <th>IP Address</th>
                          <th>Attempts</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {securityData.failed_logins.top_offenders.map((item, index) => (
                          <tr key={index}>
                            <td>{item.ip}</td>
                            <td>{item.attempts}</td>
                            <td>
                              <span className={`status-badge ${item.attempts >= 5 ? 'blocked' : 'warning'}`}>
                                {item.attempts >= 5 ? 'Blocked' : 'Warning'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Security Configuration */}
                <div className="metrics-section">
                  <h3>Security Configuration</h3>
                  <div className="config-grid">
                    <div className="config-item">
                      <span className="config-label">Environment</span>
                      <span className="config-value">{securityData.configuration?.environment || 'N/A'}</span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">Whitelisted IPs Configured</span>
                      <span className={`config-value ${securityData.configuration?.whitelisted_ips_configured ? 'success' : 'warning'}`}>
                        {securityData.configuration?.whitelisted_ips_configured ? 'Yes' : 'No'}
                      </span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">Test API Key</span>
                      <span className={`config-value ${securityData.configuration?.test_api_key_configured ? 'warning' : 'success'}`}>
                        {securityData.configuration?.test_api_key_configured ? 'Configured' : 'Not Set'}
                      </span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">Max Request Size</span>
                      <span className="config-value">{securityData.configuration?.max_request_size_mb || 10} MB</span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">Failed Login Threshold</span>
                      <span className="config-value">{securityData.configuration?.failed_login_threshold || 5} attempts</span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">Lockout Window</span>
                      <span className="config-value">{securityData.configuration?.failed_login_window_minutes || 15} minutes</span>
                    </div>
                  </div>
                </div>

                {/* Rate Limit Tiers */}
                <div className="metrics-section">
                  <h3>Rate Limit Tiers</h3>
                  <table className="security-table">
                    <thead>
                      <tr>
                        <th>Tier</th>
                        <th>Requests/Minute</th>
                        <th>Requests/Hour</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td><span className="tier-badge admin">Admin</span></td>
                        <td>500</td>
                        <td>20,000</td>
                      </tr>
                      <tr>
                        <td><span className="tier-badge power">Power User</span></td>
                        <td>300</td>
                        <td>15,000</td>
                      </tr>
                      <tr>
                        <td><span className="tier-badge standard">Standard</span></td>
                        <td>120</td>
                        <td>5,000</td>
                      </tr>
                      <tr>
                        <td><span className="tier-badge anonymous">Anonymous</span></td>
                        <td>60</td>
                        <td>1,000</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>Unable to load security data. Please try again.</p>
                <button className="btn-primary" onClick={loadSecurityData}>
                  Retry
                </button>
              </div>
            )}
          </section>
        )}

        {activeTab === 'settings' && (
          <section className="settings-section">
            <div className="section-header">
              <h2>System Settings</h2>
            </div>

            {/* Mission Control - System Health */}
            <div className="mission-control-section">
              <div className="section-header" style={{marginBottom: '16px'}}>
                <h3>Mission Control - System Health</h3>
                <button
                  className={`btn-secondary ${missionControlRefreshing ? 'loading' : ''}`}
                  onClick={refreshMissionControl}
                  disabled={missionControlRefreshing || missionControlLoading}
                >
                  {missionControlRefreshing ? 'Running Health Checks...' : 'Run Health Check'}
                </button>
              </div>

              {missionControlLoading && !missionControlData ? (
                <div className="loading-placeholder">Loading system health data...</div>
              ) : missionControlData?.integrations ? (
                <div className="integration-health-grid">
                  {missionControlData.integrations.map((integration) => (
                    <div
                      key={integration.name}
                      className={`integration-health-card ${
                        integration.status === 'healthy' ? 'status-healthy' :
                        integration.status === 'degraded' ? 'status-degraded' :
                        integration.status === 'unhealthy' ? 'status-unhealthy' :
                        'status-unknown'
                      }`}
                    >
                      <div className="integration-header">
                        <span className={`status-indicator ${integration.status}`}></span>
                        <span className="integration-name">
                          {integration.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </span>
                      </div>
                      <div className="integration-details">
                        <div className="integration-status">
                          <span className={`status-badge ${integration.status}`}>
                            {integration.status?.toUpperCase() || 'UNKNOWN'}
                          </span>
                        </div>
                        {integration.latency_ms !== null && integration.latency_ms !== undefined && (
                          <div className="integration-latency">
                            <span className="latency-label">Latency:</span>
                            <span className={`latency-value ${
                              integration.latency_ms < 200 ? 'fast' :
                              integration.latency_ms < 500 ? 'normal' :
                              'slow'
                            }`}>
                              {integration.latency_ms}ms
                            </span>
                          </div>
                        )}
                        {integration.error && (
                          <div className="integration-error">
                            <span className="error-label">Error:</span>
                            <span className="error-message">{integration.error}</span>
                          </div>
                        )}
                        {integration.last_check && (
                          <div className="integration-last-check">
                            <span className="last-check-label">Last check:</span>
                            <span className="last-check-value">
                              {new Date(integration.last_check).toLocaleTimeString()}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <p>Unable to load system health data</p>
                  <button className="btn-primary" onClick={loadMissionControl}>
                    Retry
                  </button>
                </div>
              )}

              {missionControlData?.last_refresh && (
                <div className="mission-control-footer">
                  <span className="last-refresh">
                    Last full refresh: {new Date(missionControlData.last_refresh).toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            <div className="settings-grid">
              <div className="settings-card">
                <h3>Company Information</h3>
                <div className="form-group">
                  <label>Company Name</label>
                  <input type="text" placeholder="Your Company Name" />
                </div>
                <div className="form-group">
                  <label>Company NMLS</label>
                  <input type="text" placeholder="Company NMLS #" />
                </div>
                <button className="btn-primary">Save</button>
              </div>

              <div className="settings-card">
                <h3>Email Settings</h3>
                <div className="form-group">
                  <label>From Email</label>
                  <input type="email" placeholder="noreply@company.com" />
                </div>
                <div className="form-group">
                  <label>Reply-To Email</label>
                  <input type="email" placeholder="support@company.com" />
                </div>
                <button className="btn-primary">Save</button>
              </div>

              <div className="settings-card">
                <h3>Integrations</h3>
                <div className="integration-item">
                  <span>Twilio (SMS/Video)</span>
                  <span className="status active">Connected</span>
                </div>
                <div className="integration-item">
                  <span>SendGrid (Email)</span>
                  <span className="status active">Connected</span>
                </div>
                <div className="integration-item">
                  <span>Stripe (Payments)</span>
                  <span className="status inactive">Not Connected</span>
                </div>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* User Modal */}
      {showUserModal && (
        <div className="modal-overlay" onClick={() => setShowUserModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{selectedUser ? 'Edit User' : 'Add New User'}</h2>
              <button className="modal-close" onClick={() => setShowUserModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={saveUser}>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="first_name">First Name *</label>
                  <input
                    type="text"
                    id="first_name"
                    name="first_name"
                    value={userForm.first_name}
                    onChange={handleUserInput}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="last_name">Last Name *</label>
                  <input
                    type="text"
                    id="last_name"
                    name="last_name"
                    value={userForm.last_name}
                    onChange={handleUserInput}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="email">Email *</label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={userForm.email}
                    onChange={handleUserInput}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="phone">Phone</label>
                  <input
                    type="tel"
                    id="phone"
                    name="phone"
                    value={userForm.phone}
                    onChange={handleUserInput}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="role">Role *</label>
                  <select
                    id="role"
                    name="role"
                    value={userForm.role}
                    onChange={handleUserInput}
                    required
                  >
                    <option value="user">User</option>
                    <option value="loan_officer">Loan Officer</option>
                    <option value="realtor">Realtor</option>
                    <option value="processor">Processor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="company">Company</label>
                  <input
                    type="text"
                    id="company"
                    name="company"
                    value={userForm.company}
                    onChange={handleUserInput}
                  />
                </div>
              </div>

              {userForm.role === 'loan_officer' && (
                <>
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="nmls_id">NMLS ID</label>
                      <input
                        type="text"
                        id="nmls_id"
                        name="nmls_id"
                        value={userForm.nmls_id}
                        onChange={handleUserInput}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="slug">Microsite Slug</label>
                      <input
                        type="text"
                        id="slug"
                        name="slug"
                        value={userForm.slug}
                        onChange={handleUserInput}
                        placeholder="e.g., john-smith"
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label htmlFor="bio">Bio</label>
                    <textarea
                      id="bio"
                      name="bio"
                      value={userForm.bio}
                      onChange={handleUserInput}
                      placeholder="Brief bio for microsite..."
                      rows="3"
                    />
                  </div>
                </>
              )}

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    name="is_active"
                    checked={userForm.is_active}
                    onChange={handleUserInput}
                  />
                  Active User
                </label>
              </div>

              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowUserModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Save User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
