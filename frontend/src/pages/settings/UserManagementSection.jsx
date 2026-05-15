import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../../utils/toast';
import { API_BASE_URL, formatDate } from './shared/constants';
import { getToken, getUserData } from '../../utils/tokenStore';

const UserManagementSection = () => {
  const navigate = useNavigate();

  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [addingUser, setAddingUser] = useState(false);
  const [newUser, setNewUser] = useState({
    email: '', first_name: '', last_name: '', role: 'loan_officer', is_active: true
  });
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [deletingUsers, setDeletingUsers] = useState(false);

  const [expandedCards, setExpandedCards] = useState({
    userManagement: false,
    securityMonitoring: false
  });

  const [securityData] = useState({
    loginHistory: [],
    activeSessions: [],
    failedAttempts: [],
    auditLog: []
  });
  const [loadingSecurityData] = useState(false);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoadingUsers(true);
    setUsersError(null);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`Failed to load users: ${response.status}`);
      const data = await response.json();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load users:', err);
      setUsersError('Failed to load users. Please try again.');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    if (!newUser.email || !newUser.first_name || !newUser.last_name) {
      toast.error('First name, last name, and email are required');
      return;
    }
    const roleMapping = {
      'loan_officer': 'sales', 'admin': 'admin', 'processor': 'processing',
      'underwriter': 'operations', 'manager': 'management', 'application_analyst': 'operations'
    };
    setAddingUser(true);
    try {
      const token = getToken();
      const fullName = `${newUser.first_name} ${newUser.last_name}`.trim();
      const permissionRole = roleMapping[newUser.role] || 'sales';
      const response = await fetch(`${API_BASE_URL}/api/v1/invitations`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: newUser.email, full_name: fullName, role: permissionRole, send_email: true })
      });
      if (!response.ok) {
        const errorText = await response.text();
        let errorDetail = `Failed to invite user (${response.status})`;
        try { const errorData = JSON.parse(errorText); errorDetail = errorData.detail || errorData.error || errorData.message || errorDetail; } catch (e) { errorDetail = errorText || errorDetail; }
        throw new Error(errorDetail);
      }
      setNewUser({ email: '', first_name: '', last_name: '', role: 'loan_officer', is_active: true });
      setShowAddUserModal(false);
      await loadUsers();
      toast.success('Invitation sent! The user will receive an email to set up their account.');
    } catch (err) {
      console.error('Failed to invite user:', err);
      toast.error(err.message || 'Failed to invite user');
    } finally {
      setAddingUser(false);
    }
  };

  const handleSelectUser = (userId) => {
    setSelectedUsers(prev => prev.includes(userId) ? prev.filter(id => id !== userId) : [...prev, userId]);
  };

  const handleSelectAll = () => {
    const currentUserData = getUserData() || {};
    const selectableUsers = users.filter(u => u.id !== currentUserData.id).map(u => u.id);
    setSelectedUsers(prev => prev.length === selectableUsers.length ? [] : selectableUsers);
  };

  const handleBulkDelete = async () => {
    if (selectedUsers.length === 0) { toast.error('No users selected'); return; }
    if (!window.confirm(`Are you sure you want to delete ${selectedUsers.length} user(s)? This action cannot be undone.`)) return;
    setDeletingUsers(true);
    try {
      const token = getToken();
      let successCount = 0, failCount = 0;
      for (const userId of selectedUsers) {
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 60000);
          const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
            method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` }, signal: controller.signal
          });
          clearTimeout(timeoutId);
          if (response.ok) { successCount++; } else { failCount++; }
        } catch (err) { failCount++; }
      }
      setSelectedUsers([]);
      await loadUsers();
      if (failCount === 0) { toast.success(`Successfully deleted ${successCount} user(s)`); }
      else { toast.error(`Deleted ${successCount} user(s). Failed to delete ${failCount} user(s).`); }
    } catch (err) { toast.error('Failed to delete users'); }
    finally { setDeletingUsers(false); }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentStatus })
      });
      if (!response.ok) throw new Error('Failed to update user status');
      await loadUsers();
    } catch (err) { toast.error('Failed to update user status'); }
  };

  const handleToggleVerified = async (userId, currentStatus) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email_verified: !currentStatus })
      });
      if (!response.ok) throw new Error('Failed to update verification');
      await loadUsers();
    } catch (err) { toast.error('Failed to update user verification'); }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole })
      });
      if (!response.ok) throw new Error('Failed to update role');
      await loadUsers();
      setEditingUser(null);
    } catch (err) { toast.error('Failed to update user role'); }
  };

  const handleDeleteUser = async (userId) => {
    const currentUserData = getUserData() || {};
    if (currentUserData.id === userId) { toast.error('You cannot delete your own account.'); return; }
    try {
      const token = getToken();
      if (!token) { toast.error('You are not authenticated. Please log in again.'); return; }
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) { const errorData = await response.json().catch(() => ({})); throw new Error(errorData.detail || 'Failed to delete user'); }
      toast.success('User deleted successfully');
      await loadUsers();
    } catch (err) { toast.error(err.message || 'Failed to delete user'); }
  };

  return (
    <div className="account-mgmt-section">
      <div className="page-header">
        <div>
          <h2>Account Management</h2>
          <p className="section-description">Manage users, permissions, and security monitoring</p>
        </div>
      </div>

      <div className="collapsible-cards-container">
        {/* User Management Card */}
        <div
          className={`collapsible-card ${expandedCards.userManagement ? 'expanded' : ''}`}
          onClick={() => !expandedCards.userManagement && setExpandedCards(prev => ({ ...prev, userManagement: true, securityMonitoring: false }))}
        >
          <div className="collapsible-card-header" onClick={(e) => { e.stopPropagation(); setExpandedCards(prev => ({ ...prev, userManagement: !prev.userManagement })); }}>
            <div className="card-header-content">
              <div className="card-icon">&#128101;</div>
              <div><h3>User Management</h3><p>Manage registered users and permissions</p></div>
            </div>
            <div className="card-header-right">
              <div className="card-stats">
                <span className="stat">{users.length} users</span>
                <span className="stat">{users.filter(u => u.is_active).length} active</span>
              </div>
              <span className="expand-arrow">{expandedCards.userManagement ? '▼' : '▶'}</span>
            </div>
          </div>

          {expandedCards.userManagement && (
            <div className="collapsible-card-content" onClick={(e) => e.stopPropagation()}>
              <div className="card-actions-bar">
                <button className="btn-primary" onClick={() => setShowAddUserModal(true)}>+ Add User</button>
                {selectedUsers.length > 0 && (
                  <button className="btn-danger" onClick={handleBulkDelete} disabled={deletingUsers}>
                    {deletingUsers ? 'Deleting...' : `Delete Selected (${selectedUsers.length})`}
                  </button>
                )}
              </div>

              {usersError && <div className="error-message">{usersError}</div>}

              {loadingUsers ? (
                <div className="loading">Loading users...</div>
              ) : (
                <div className="users-table-container">
                  <table className="users-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>
                          <input type="checkbox" onChange={handleSelectAll}
                            checked={selectedUsers.length > 0 && selectedUsers.length === users.filter(u => u.id !== (getUserData() || {}).id).length}
                            style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                        </th>
                        <th>User</th><th>Role</th><th>Status</th><th>Verified</th><th>Onboarded</th><th>Registered</th><th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => {
                        const currentUserData = getUserData() || {};
                        const isCurrentUser = user.id === currentUserData.id;
                        return (
                          <tr key={user.id}
                            className={`clickable-user-row ${!user.is_active ? 'inactive-user' : ''} ${selectedUsers.includes(user.id) ? 'selected-row' : ''}`}
                            onClick={() => navigate(`/users/${user.id}`)} style={{ cursor: 'pointer' }}>
                            <td onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={selectedUsers.includes(user.id)} onChange={() => handleSelectUser(user.id)}
                                disabled={isCurrentUser} style={{ width: '18px', height: '18px', cursor: isCurrentUser ? 'not-allowed' : 'pointer' }} />
                            </td>
                            <td>
                              <div className="user-info">
                                <div className="user-avatar">{user.full_name?.charAt(0) || user.email.charAt(0)}</div>
                                <div>
                                  <div className="user-name">{user.full_name || 'Unnamed User'}{isCurrentUser && <span className="current-user-badge">You</span>}</div>
                                  <div className="user-email-small">{user.email}</div>
                                  <div className="user-id">ID: {user.id}</div>
                                </div>
                              </div>
                            </td>
                            <td>
                              {editingUser === user.id ? (
                                <select value={user.role} onChange={(e) => handleUpdateRole(user.id, e.target.value)} onBlur={() => setEditingUser(null)} onClick={(e) => e.stopPropagation()} autoFocus className="role-select">
                                  <option value="loan_officer">Loan Officer</option><option value="admin">Admin</option><option value="processor">Processor</option>
                                  <option value="underwriter">Underwriter</option><option value="manager">Manager</option>
                                </select>
                              ) : (
                                <span className="role-badge" onClick={(e) => { e.stopPropagation(); setEditingUser(user.id); }} title="Click to edit">
                                  {user.role || 'loan_officer'}
                                </span>
                              )}
                            </td>
                            <td>
                              <button className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}
                                onClick={(e) => { e.stopPropagation(); handleToggleActive(user.id, user.is_active); }}>
                                {user.is_active ? 'Active' : 'Inactive'}
                              </button>
                            </td>
                            <td>
                              <button className={`verify-badge ${user.email_verified ? 'verified' : 'unverified'}`}
                                onClick={(e) => { e.stopPropagation(); handleToggleVerified(user.id, user.email_verified); }}>
                                {user.email_verified ? 'Verified' : 'Not Verified'}
                              </button>
                            </td>
                            <td>
                              <span className={`onboarding-badge ${user.onboarding_completed ? 'completed' : 'pending'}`}>
                                {user.onboarding_completed ? 'Completed' : 'Pending'}
                              </span>
                            </td>
                            <td className="date-cell">{formatDate(user.created_at)}</td>
                            <td>
                              <button className="btn-delete" onClick={(e) => { e.stopPropagation(); handleDeleteUser(user.id); }}
                                disabled={isCurrentUser} title={isCurrentUser ? "You cannot delete your own account" : "Delete user"}>Delete</button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {users.length === 0 && <div className="empty-state"><p>No users found</p></div>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Security Monitoring Card */}
        <div
          className={`collapsible-card ${expandedCards.securityMonitoring ? 'expanded' : ''}`}
          onClick={() => !expandedCards.securityMonitoring && setExpandedCards(prev => ({ ...prev, securityMonitoring: true, userManagement: false }))}
        >
          <div className="collapsible-card-header" onClick={(e) => { e.stopPropagation(); setExpandedCards(prev => ({ ...prev, securityMonitoring: !prev.securityMonitoring })); }}>
            <div className="card-header-content">
              <div className="card-icon">&#128274;</div>
              <div><h3>Security Monitoring</h3><p>Login history, sessions, and audit logs</p></div>
            </div>
            <div className="card-header-right">
              <div className="card-stats"><span className="stat">{securityData.activeSessions?.length || 0} active sessions</span></div>
              <span className="expand-arrow">{expandedCards.securityMonitoring ? '▼' : '▶'}</span>
            </div>
          </div>

          {expandedCards.securityMonitoring && (
            <div className="collapsible-card-content" onClick={(e) => e.stopPropagation()}>
              {loadingSecurityData ? (
                <div className="loading">Loading security data...</div>
              ) : (
                <div className="security-monitoring-content">
                  <div className="security-section">
                    <h4>Active Sessions</h4>
                    <div className="sessions-list">
                      {securityData.activeSessions?.length > 0 ? (
                        securityData.activeSessions.map((session, i) => (
                          <div key={i} className="session-item">
                            <div className="session-info">
                              <span className="session-device">{session.device || 'Unknown Device'}</span>
                              <span className="session-location">{session.location || 'Unknown'}</span>
                            </div>
                            <span className="session-time">{session.lastActive || 'Now'}</span>
                          </div>
                        ))
                      ) : (<div className="empty-state-small"><p>Current session is active</p></div>)}
                    </div>
                  </div>

                  <div className="security-section">
                    <h4>Recent Login History</h4>
                    <div className="login-history-list">
                      {securityData.loginHistory?.length > 0 ? (
                        securityData.loginHistory.slice(0, 5).map((login, i) => (
                          <div key={i} className={`login-item ${login.success ? 'success' : 'failed'}`}>
                            <div className="login-info">
                              <span className={`login-status ${login.success ? 'success' : 'failed'}`}>{login.success ? '✓' : '✗'}</span>
                              <span className="login-email">{login.email || 'Unknown'}</span>
                            </div>
                            <div className="login-meta">
                              <span className="login-ip">{login.ip || '-'}</span>
                              <span className="login-time">{login.timestamp || '-'}</span>
                            </div>
                          </div>
                        ))
                      ) : (<div className="empty-state-small"><p>No recent login activity</p></div>)}
                    </div>
                  </div>

                  <div className="security-section">
                    <h4>Recent Audit Activity</h4>
                    <div className="audit-log-list">
                      {securityData.auditLog?.length > 0 ? (
                        securityData.auditLog.slice(0, 5).map((log, i) => (
                          <div key={i} className="audit-item">
                            <div className="audit-info">
                              <span className="audit-action">{log.action}</span>
                              <span className="audit-user">{log.user || 'System'}</span>
                            </div>
                            <span className="audit-time">{log.timestamp || '-'}</span>
                          </div>
                        ))
                      ) : (<div className="empty-state-small"><p>No recent audit activity</p></div>)}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Add User Modal */}
      {showAddUserModal && (
        <div className="modal-overlay" style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div className="modal-content" style={{
            background: 'white', borderRadius: '12px', padding: '24px', width: '100%', maxWidth: '500px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>Invite New User</h3>
              <button onClick={() => setShowAddUserModal(false)} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#666' }}>&times;</button>
            </div>

            <div style={{ background: '#eff6ff', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', fontSize: '13px', color: '#1d4ed8' }}>
              <strong>Note:</strong> An invitation email will be sent to the user to create their account and set their password.
            </div>

            <form onSubmit={handleAddUser}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>First Name *</label>
                  <input type="text" value={newUser.first_name} onChange={(e) => setNewUser({ ...newUser, first_name: e.target.value })} placeholder="John" required
                    style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Last Name *</label>
                  <input type="text" value={newUser.last_name} onChange={(e) => setNewUser({ ...newUser, last_name: e.target.value })} placeholder="Doe" required
                    style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }} />
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Email *</label>
                <input type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} placeholder="john@example.com" required
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }} />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Role</label>
                <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }}>
                  <option value="loan_officer">Loan Officer</option><option value="admin">Admin</option><option value="processor">Processor</option>
                  <option value="underwriter">Underwriter</option><option value="manager">Manager</option><option value="application_analyst">Application Analyst</option>
                </select>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input type="checkbox" checked={newUser.is_active} onChange={(e) => setNewUser({ ...newUser, is_active: e.target.checked })} style={{ width: '18px', height: '18px' }} />
                  <span>Set as Active User</span>
                </label>
              </div>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowAddUserModal(false)}
                  style={{ padding: '10px 20px', background: '#f3f4f6', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}>Cancel</button>
                <button type="submit" disabled={addingUser}
                  style={{ padding: '10px 20px', background: '#8A6D30', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '500', opacity: addingUser ? 0.7 : 1 }}>
                  {addingUser ? 'Sending Invite...' : 'Send Invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagementSection;
