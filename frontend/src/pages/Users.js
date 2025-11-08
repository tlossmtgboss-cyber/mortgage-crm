import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Users.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingUser, setEditingUser] = useState(null);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE_URL}/api/v1/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      setUsers(response.data);
      setError(null);
    } catch (err) {
      console.error('Failed to load users:', err);
      setError('Failed to load users. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      await axios.patch(
        `${API_BASE_URL}/api/v1/admin/users/${userId}`,
        { is_active: !currentStatus },
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      alert('Failed to update user status');
    }
  };

  const handleToggleVerified = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      await axios.patch(
        `${API_BASE_URL}/api/v1/admin/users/${userId}`,
        { email_verified: !currentStatus },
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      alert('Failed to update user verification');
    }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      const token = localStorage.getItem('token');
      await axios.patch(
        `${API_BASE_URL}/api/v1/admin/users/${userId}`,
        { role: newRole },
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      await loadUsers();
      setEditingUser(null);
    } catch (err) {
      console.error('Failed to update role:', err);
      alert('Failed to update user role');
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      await axios.delete(
        `${API_BASE_URL}/api/v1/admin/users/${userId}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      await loadUsers();
    } catch (err) {
      console.error('Failed to delete user:', err);
      alert(err.response?.data?.detail || 'Failed to delete user');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  if (loading) {
    return <div className="users-page"><div className="loading">Loading users...</div></div>;
  }

  return (
    <div className="users-page">
      <div className="page-header">
        <div>
          <h1>User Management</h1>
          <p>Manage all registered users and their permissions</p>
        </div>
        <div className="header-stats">
          <div className="stat-box">
            <div className="stat-value">{users.length}</div>
            <div className="stat-label">Total Users</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{users.filter(u => u.is_active).length}</div>
            <div className="stat-label">Active</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{users.filter(u => u.email_verified).length}</div>
            <div className="stat-label">Verified</div>
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="users-table-container">
        <table className="users-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Verified</th>
              <th>Onboarded</th>
              <th>Registered</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className={!user.is_active ? 'inactive-user' : ''}>
                <td>
                  <div className="user-info">
                    <div className="user-avatar">{user.full_name?.charAt(0) || user.email.charAt(0)}</div>
                    <div>
                      <div className="user-name">{user.full_name || 'Unnamed User'}</div>
                      <div className="user-id">ID: {user.id}</div>
                    </div>
                  </div>
                </td>
                <td>{user.email}</td>
                <td>
                  {editingUser === user.id ? (
                    <select
                      value={user.role}
                      onChange={(e) => handleUpdateRole(user.id, e.target.value)}
                      onBlur={() => setEditingUser(null)}
                      autoFocus
                      className="role-select"
                    >
                      <option value="loan_officer">Loan Officer</option>
                      <option value="admin">Admin</option>
                      <option value="processor">Processor</option>
                      <option value="underwriter">Underwriter</option>
                      <option value="manager">Manager</option>
                    </select>
                  ) : (
                    <span
                      className="role-badge"
                      onClick={() => setEditingUser(user.id)}
                      title="Click to edit"
                    >
                      {user.role || 'loan_officer'}
                    </span>
                  )}
                </td>
                <td>
                  <button
                    className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}
                    onClick={() => handleToggleActive(user.id, user.is_active)}
                  >
                    {user.is_active ? 'Active' : 'Inactive'}
                  </button>
                </td>
                <td>
                  <button
                    className={`verify-badge ${user.email_verified ? 'verified' : 'unverified'}`}
                    onClick={() => handleToggleVerified(user.id, user.email_verified)}
                  >
                    {user.email_verified ? '✓ Verified' : '✗ Not Verified'}
                  </button>
                </td>
                <td>
                  <span className={`onboarding-badge ${user.onboarding_completed ? 'completed' : 'pending'}`}>
                    {user.onboarding_completed ? 'Completed' : 'Pending'}
                  </span>
                </td>
                <td className="date-cell">{formatDate(user.created_at)}</td>
                <td>
                  <button
                    className="btn-delete"
                    onClick={() => handleDeleteUser(user.id)}
                    title="Delete user"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {users.length === 0 && (
          <div className="empty-state">
            <p>No users found</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Users;
