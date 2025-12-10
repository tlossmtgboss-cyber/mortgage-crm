import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
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

  // State
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loanOfficers, setLoanOfficers] = useState([]);
  const [realtors, setRealtors] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');

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
      } else {
        await api.post('/api/v1/admin/users', userForm);
      }
      setShowUserModal(false);
      loadDashboard();
    } catch (err) {
      console.error('Save user error:', err);
      alert('Failed to save user. Please try again.');
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
          Realtors
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
            {/* Stats Grid */}
            <section className="stats-section">
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-icon users">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_users || 0}</span>
                    <span className="stat-label">Total Users</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon los">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_los || loanOfficers.length}</span>
                    <span className="stat-label">Loan Officers</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon realtors">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                      <polyline points="9 22 9 12 15 12 15 22"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_realtors || realtors.length}</span>
                    <span className="stat-label">Realtors</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon leads">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_leads || 0}</span>
                    <span className="stat-label">Total Leads</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon loans">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                      <line x1="8" y1="21" x2="16" y2="21"/>
                      <line x1="12" y1="17" x2="12" y2="21"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_loans || 0}</span>
                    <span className="stat-label">Total Loans</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon volume">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{formatCurrency(stats?.mtd_volume)}</span>
                    <span className="stat-label">MTD Volume</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Quick Actions */}
            <section className="quick-actions-section">
              <h2>Quick Actions</h2>
              <div className="quick-actions-grid">
                <button onClick={openNewUserModal}>
                  <span className="action-icon">+</span>
                  <span>Add New User</span>
                </button>
                <button onClick={() => setActiveTab('loan_officers')}>
                  <span className="action-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                  </span>
                  <span>Manage LOs</span>
                </button>
                <button onClick={() => navigate('/leads')}>
                  <span className="action-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                    </svg>
                  </span>
                  <span>View Leads</span>
                </button>
                <button onClick={() => navigate('/reports')}>
                  <span className="action-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="20" x2="18" y2="10"/>
                      <line x1="12" y1="20" x2="12" y2="4"/>
                      <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                  </span>
                  <span>View Reports</span>
                </button>
              </div>
            </section>

            {/* Recent Users */}
            <section className="recent-section">
              <div className="section-header">
                <h2>Recent Users</h2>
                <button onClick={() => setActiveTab('users')} className="btn-link">
                  View All
                </button>
              </div>
              <div className="users-list">
                {users.slice(0, 5).map(user => (
                  <div key={user.id} className="user-card" onClick={() => openEditModal(user)}>
                    <div className="user-avatar">
                      {user.avatar_url ? (
                        <img src={user.avatar_url} alt={user.first_name} />
                      ) : (
                        <span>{(user.first_name || user.email || 'U').charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="user-info">
                      <span className="user-name">
                        {user.first_name} {user.last_name}
                      </span>
                      <span className="user-email">{user.email}</span>
                    </div>
                    <span className={`role-badge ${getRoleClass(user.role)}`}>
                      {user.role?.replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
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
              <h2>Realtor Partners</h2>
              <button
                className="btn-primary"
                onClick={() => {
                  setUserForm(prev => ({ ...prev, role: 'realtor' }));
                  openNewUserModal();
                }}
              >
                + Add Realtor
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
                <p>No realtors yet</p>
                <button
                  className="btn-primary"
                  onClick={() => {
                    setUserForm(prev => ({ ...prev, role: 'realtor' }));
                    openNewUserModal();
                  }}
                >
                  Add First Realtor
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
