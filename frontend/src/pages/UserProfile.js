import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './UserProfile.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function UserProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [formData, setFormData] = useState({});

  useEffect(() => {
    loadUserProfile();
  }, [id]);

  const loadUserProfile = async () => {
    try {
      setLoading(true);
      setError(null);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error('Failed to load user profile');
      }

      const data = await response.json();
      setUser(data);
      setFormData({
        full_name: data.full_name || '',
        email: data.email || '',
        role: data.role || 'loan_officer',
        is_active: data.is_active || false,
        email_verified: data.email_verified || false
      });
    } catch (err) {
      console.error('Failed to load user:', err);
      setError('Failed to load user profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        throw new Error('Failed to update user');
      }

      alert('User updated successfully');
      setEditMode(false);
      await loadUserProfile();
    } catch (err) {
      console.error('Failed to update user:', err);
      alert('Failed to update user. Please try again.');
    }
  };

  const handleDelete = async () => {
    const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

    if (currentUser.id === parseInt(id)) {
      alert('You cannot delete your own account.');
      return;
    }

    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete user');
      }

      alert('User deleted successfully');
      navigate('/settings');
    } catch (err) {
      console.error('Failed to delete user:', err);
      alert(err.message || 'Failed to delete user');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  if (loading) {
    return (
      <div className="user-profile-page">
        <div className="loading">Loading user profile...</div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="user-profile-page">
        <div className="error-message">{error || 'User not found'}</div>
        <button className="btn-back" onClick={() => navigate('/settings')}>
          ← Back to Settings
        </button>
      </div>
    );
  }

  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isCurrentUser = user.id === currentUser.id;

  return (
    <div className="user-profile-page">
      <div className="profile-header">
        <button className="btn-back" onClick={() => navigate('/settings')}>
          ← Back to User Management
        </button>
        <h1>User Profile</h1>
      </div>

      <div className="profile-content">
        <div className="profile-card">
          <div className="profile-avatar-section">
            <div className="profile-avatar-large">
              {user.full_name?.charAt(0) || user.email.charAt(0)}
            </div>
            <div className="profile-name-section">
              <h2>{user.full_name || 'Unnamed User'}</h2>
              {isCurrentUser && <span className="current-user-badge">You</span>}
              <p className="profile-email">{user.email}</p>
            </div>
          </div>

          {!editMode ? (
            <div className="profile-details">
              <div className="detail-row">
                <label>User ID:</label>
                <span>{user.id}</span>
              </div>
              <div className="detail-row">
                <label>Role:</label>
                <span className="role-badge">{user.role || 'loan_officer'}</span>
              </div>
              <div className="detail-row">
                <label>Status:</label>
                <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="detail-row">
                <label>Email Verified:</label>
                <span className={`verify-badge ${user.email_verified ? 'verified' : 'unverified'}`}>
                  {user.email_verified ? '✓ Verified' : '✗ Not Verified'}
                </span>
              </div>
              <div className="detail-row">
                <label>Onboarding:</label>
                <span className={`onboarding-badge ${user.onboarding_completed ? 'completed' : 'pending'}`}>
                  {user.onboarding_completed ? 'Completed' : 'Pending'}
                </span>
              </div>
              <div className="detail-row">
                <label>Created:</label>
                <span>{formatDate(user.created_at)}</span>
              </div>
              {user.updated_at && (
                <div className="detail-row">
                  <label>Last Updated:</label>
                  <span>{formatDate(user.updated_at)}</span>
                </div>
              )}

              <div className="profile-actions">
                <button className="btn-edit" onClick={() => setEditMode(true)}>
                  Edit Profile
                </button>
                {!isCurrentUser && (
                  <button className="btn-delete" onClick={handleDelete}>
                    Delete User
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="profile-edit-form">
              <div className="form-group">
                <label>Full Name:</label>
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Email:</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Role:</label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="form-select"
                >
                  <option value="loan_officer">Loan Officer</option>
                  <option value="admin">Admin</option>
                  <option value="processor">Processor</option>
                  <option value="underwriter">Underwriter</option>
                  <option value="manager">Manager</option>
                </select>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                  <span>Active</span>
                </label>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.email_verified}
                    onChange={(e) => setFormData({ ...formData, email_verified: e.target.checked })}
                  />
                  <span>Email Verified</span>
                </label>
              </div>

              <div className="profile-actions">
                <button className="btn-save" onClick={handleUpdate}>
                  Save Changes
                </button>
                <button className="btn-cancel" onClick={() => setEditMode(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default UserProfile;
