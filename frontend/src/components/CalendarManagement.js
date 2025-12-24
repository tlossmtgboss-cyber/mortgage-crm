/**
 * Calendar Management Component
 *
 * Allows admins to configure which calendars/users receive
 * appointments for different purposes in the application.
 */

import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './CalendarManagement.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

const CalendarManagement = () => {
  const [assignments, setAssignments] = useState([]);
  const [purposes, setPurposes] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // Load all data in parallel
      const [assignmentsRes, purposesRes, usersRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/calendar-assignments`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/calendar-assignments/purposes`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/users/with-calendars`, { headers: getAuthHeaders() })
      ]);

      if (assignmentsRes.ok) {
        const data = await assignmentsRes.json();
        setAssignments(data);
      }

      if (purposesRes.ok) {
        const data = await purposesRes.json();
        setPurposes(data);
      }

      if (usersRes.ok) {
        const data = await usersRes.json();
        setUsers(data);
      }
    } catch (err) {
      console.error('Error loading calendar data:', err);
      setMessage({ type: 'error', text: 'Failed to load calendar settings' });
    } finally {
      setLoading(false);
    }
  };

  const getAssignmentForPurpose = (purpose) => {
    return assignments.find(a => a.purpose === purpose);
  };

  const handleAssignUser = async (purpose, userId) => {
    setSaving(true);
    setMessage(null);

    const existing = getAssignmentForPurpose(purpose);
    const purposeInfo = purposes.find(p => p.purpose === purpose);

    try {
      if (existing) {
        // Update existing assignment
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments/${existing.id}`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            assigned_user_id: userId || null,
            calendly_url: null // Clear custom URL when assigning user
          })
        });

        if (!response.ok) throw new Error('Failed to update assignment');
      } else {
        // Create new assignment
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            purpose: purpose,
            purpose_label: purposeInfo?.label || purpose,
            assigned_user_id: userId || null,
            is_active: true
          })
        });

        if (!response.ok) throw new Error('Failed to create assignment');
      }

      setMessage({ type: 'success', text: 'Calendar assignment saved!' });
      await loadData(); // Refresh data
    } catch (err) {
      console.error('Error saving assignment:', err);
      setMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleSetCustomUrl = async (purpose, url) => {
    setSaving(true);
    setMessage(null);

    const existing = getAssignmentForPurpose(purpose);
    const purposeInfo = purposes.find(p => p.purpose === purpose);

    try {
      if (existing) {
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments/${existing.id}`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            calendly_url: url,
            assigned_user_id: null // Clear user when setting custom URL
          })
        });

        if (!response.ok) throw new Error('Failed to update assignment');
      } else {
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            purpose: purpose,
            purpose_label: purposeInfo?.label || purpose,
            calendly_url: url,
            is_active: true
          })
        });

        if (!response.ok) throw new Error('Failed to create assignment');
      }

      setMessage({ type: 'success', text: 'Calendar URL saved!' });
      setEditingId(null);
      await loadData();
    } catch (err) {
      console.error('Error saving URL:', err);
      setMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleClearAssignment = async (purpose) => {
    const existing = getAssignmentForPurpose(purpose);
    if (!existing) return;

    setSaving(true);
    try {
      await fetch(`${API_BASE}/api/v1/calendar-assignments/${existing.id}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      setMessage({ type: 'success', text: 'Assignment cleared' });
      await loadData();
    } catch (err) {
      console.error('Error clearing assignment:', err);
      setMessage({ type: 'error', text: 'Failed to clear assignment' });
    } finally {
      setSaving(false);
    }
  };

  const startEditing = (purpose) => {
    const existing = getAssignmentForPurpose(purpose);
    setEditingId(purpose);
    setEditForm({
      calendly_url: existing?.calendly_url || ''
    });
  };

  if (loading) {
    return (
      <div className="calendar-management loading">
        <div className="loading-spinner"></div>
        <p>Loading calendar settings...</p>
      </div>
    );
  }

  return (
    <div className="calendar-management">
      <div className="cm-header">
        <h2>Calendar Management</h2>
        <p>Configure which team member receives calendar appointments for different parts of the application.</p>
      </div>

      {message && (
        <div className={`cm-message ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      <div className="cm-section">
        <h3>Application Scheduling</h3>
        <p className="section-desc">These calendars are shown to borrowers during the loan application process.</p>

        <div className="assignment-grid">
          {purposes.map(purpose => {
            const assignment = getAssignmentForPurpose(purpose.purpose);
            const isEditing = editingId === purpose.purpose;

            return (
              <div key={purpose.purpose} className="assignment-card">
                <div className="card-header">
                  <h4>{purpose.label}</h4>
                  <span className={`status-badge ${assignment ? 'assigned' : 'unassigned'}`}>
                    {assignment ? 'Configured' : 'Not Set'}
                  </span>
                </div>

                <div className="card-body">
                  {/* Current Assignment Display */}
                  {assignment && !isEditing && (
                    <div className="current-assignment">
                      {assignment.assigned_user_name ? (
                        <div className="assigned-user">
                          <span className="user-avatar">
                            {assignment.assigned_user_name.charAt(0).toUpperCase()}
                          </span>
                          <div className="user-info">
                            <span className="user-name">{assignment.assigned_user_name}</span>
                            <span className="assignment-type">Team Member Calendar</span>
                          </div>
                        </div>
                      ) : assignment.calendly_url ? (
                        <div className="custom-url">
                          <span className="url-icon">&#128279;</span>
                          <div className="url-info">
                            <span className="url-label">Custom Calendly URL</span>
                            <a href={assignment.calendly_url} target="_blank" rel="noopener noreferrer" className="url-link">
                              {assignment.calendly_url.length > 40
                                ? assignment.calendly_url.substring(0, 40) + '...'
                                : assignment.calendly_url}
                            </a>
                          </div>
                        </div>
                      ) : (
                        <p className="no-assignment">No calendar assigned</p>
                      )}
                    </div>
                  )}

                  {/* User Selection */}
                  <div className="assignment-form">
                    <label>Assign to Team Member:</label>
                    <select
                      value={assignment?.assigned_user_id || ''}
                      onChange={(e) => handleAssignUser(purpose.purpose, e.target.value ? parseInt(e.target.value) : null)}
                      disabled={saving}
                    >
                      <option value="">-- Select Team Member --</option>
                      {users.map(user => (
                        <option key={user.id} value={user.id}>
                          {user.name} {user.has_calendly ? '(Calendly Connected)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Custom URL Option */}
                  <div className="custom-url-section">
                    <label>Or use a custom Calendly URL:</label>
                    {isEditing ? (
                      <div className="url-edit-form">
                        <input
                          type="url"
                          placeholder="https://calendly.com/your-link"
                          value={editForm.calendly_url}
                          onChange={(e) => setEditForm({ ...editForm, calendly_url: e.target.value })}
                        />
                        <div className="url-edit-actions">
                          <button
                            className="btn-save"
                            onClick={() => handleSetCustomUrl(purpose.purpose, editForm.calendly_url)}
                            disabled={saving}
                          >
                            Save
                          </button>
                          <button
                            className="btn-cancel"
                            onClick={() => setEditingId(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        className="btn-set-url"
                        onClick={() => startEditing(purpose.purpose)}
                      >
                        {assignment?.calendly_url ? 'Edit URL' : 'Set Custom URL'}
                      </button>
                    )}
                  </div>

                  {/* Clear Button */}
                  {assignment && (
                    <button
                      className="btn-clear"
                      onClick={() => handleClearAssignment(purpose.purpose)}
                      disabled={saving}
                    >
                      Clear Assignment
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="cm-section">
        <h3>Team Members with Calendars</h3>
        <p className="section-desc">These team members have connected their Calendly accounts and can receive appointments.</p>

        <div className="users-list">
          {users.filter(u => u.has_calendly).length === 0 ? (
            <div className="no-users">
              <p>No team members have connected their Calendly accounts yet.</p>
              <p className="hint">Team members can connect Calendly from their Profile Settings.</p>
            </div>
          ) : (
            <div className="users-grid">
              {users.filter(u => u.has_calendly).map(user => (
                <div key={user.id} className="user-card">
                  <div className="user-avatar-lg">
                    {user.name?.charAt(0).toUpperCase() || '?'}
                  </div>
                  <div className="user-details">
                    <span className="user-name">{user.name}</span>
                    <span className="user-email">{user.email}</span>
                    <span className="calendly-status connected">
                      <span className="dot"></span> Calendly Connected
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CalendarManagement;
