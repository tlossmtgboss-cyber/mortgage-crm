/**
 * Calendar Management Component
 *
 * Allows admins to configure which calendars/users receive
 * appointments for different purposes in the application.
 * Supports team member assignment, booking links, and custom scheduling URLs.
 */

import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './CalendarManagement.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const CalendarManagement = () => {
  const [assignments, setAssignments] = useState([]);
  const [purposes, setPurposes] = useState([]);
  const [users, setUsers] = useState([]);
  const [bookingLinks, setBookingLinks] = useState([]);
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
      const [assignmentsRes, purposesRes, usersRes, bookingLinksRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/calendar-assignments`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/calendar-assignments/purposes`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/users/with-calendars`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/scheduler/booking-links/all`, { headers: getAuthHeaders() }).catch(() => null)
      ]);

      if (assignmentsRes.ok) setAssignments(await assignmentsRes.json());
      if (purposesRes.ok) setPurposes(await purposesRes.json());
      if (usersRes.ok) setUsers(await usersRes.json());
      if (bookingLinksRes?.ok) {
        const data = await bookingLinksRes.json();
        setBookingLinks(data.booking_links || []);
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

  const saveAssignment = async (purpose, updates) => {
    setSaving(true);
    setMessage(null);

    const existing = getAssignmentForPurpose(purpose);
    const purposeInfo = purposes.find(p => p.purpose === purpose);

    try {
      if (existing) {
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments/${existing.id}`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify(updates)
        });
        if (!response.ok) throw new Error('Failed to update assignment');
      } else {
        const response = await fetch(`${API_BASE}/api/v1/calendar-assignments`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            purpose: purpose,
            purpose_label: purposeInfo?.label || purpose,
            is_active: true,
            ...updates
          })
        });
        if (!response.ok) throw new Error('Failed to create assignment');
      }

      setMessage({ type: 'success', text: 'Calendar assignment saved!' });
      setEditingId(null);
      await loadData();
    } catch (err) {
      console.error('Error saving assignment:', err);
      setMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleAssignUser = async (purpose, userId) => {
    await saveAssignment(purpose, { assigned_user_id: userId || null });
  };

  const handleAssignBookingLink = async (purpose, linkId) => {
    await saveAssignment(purpose, {
      booking_link_id: linkId || null,
      calendly_url: linkId ? null : undefined // clear calendly if setting booking link
    });
  };

  const handleSetCustomUrl = async (purpose, url) => {
    await saveAssignment(purpose, {
      calendly_url: url || null,
      booking_link_id: url ? null : undefined // clear booking link if setting URL
    });
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
        <h2>Calendar Assignments</h2>
        <p>Configure which team member and scheduling method is used for each purpose. Every assignment requires a team member.</p>
      </div>

      {message && (
        <div className={`cm-message ${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>
          {message.text}
          <button onClick={() => setMessage(null)} aria-label="Dismiss message">&times;</button>
        </div>
      )}

      <div className="cm-section">
        <h3>Application Scheduling</h3>
        <p className="section-desc">These calendars are shown to borrowers during the loan application process.</p>

        <div className="assignment-grid">
          {purposes.map(purpose => {
            const assignment = getAssignmentForPurpose(purpose.purpose);
            const isEditing = editingId === purpose.purpose;
            const assignedLink = assignment?.booking_link_id
              ? bookingLinks.find(l => l.id === assignment.booking_link_id)
              : null;

            return (
              <div key={purpose.purpose} className="assignment-card">
                <div className="card-header">
                  <h4>{purpose.label}</h4>
                  <span className={`status-badge ${assignment?.assigned_user_id ? 'assigned' : 'unassigned'}`}>
                    {assignment?.assigned_user_id ? 'Configured' : 'Not Set'}
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
                            <span className="assignment-type">
                              {assignment.booking_link_slug
                                ? `Booking Link: /book/${assignment.booking_link_slug}`
                                : assignment.calendly_url
                                  ? 'Custom Scheduling URL'
                                  : 'Team Member Calendar'}
                            </span>
                          </div>
                        </div>
                      ) : assignment.calendly_url ? (
                        <div className="custom-url">
                          <span className="url-icon">&#128279;</span>
                          <div className="url-info">
                            <span className="url-label">Custom Scheduling URL (no team member assigned)</span>
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

                  {/* User Selection (Required) */}
                  <div className="assignment-form">
                    <label htmlFor={`calendar-assign-user-${purpose.purpose}`}>Assign to Team Member: <span className="required-star">*</span></label>
                    <select
                      id={`calendar-assign-user-${purpose.purpose}`}
                      value={assignment?.assigned_user_id || ''}
                      onChange={(e) => handleAssignUser(purpose.purpose, e.target.value ? parseInt(e.target.value) : null)}
                      disabled={saving}
                    >
                      <option value="">-- Select Team Member (Required) --</option>
                      {users.map(user => (
                        <option key={user.id} value={user.id}>
                          {user.name} {user.has_calendly ? '(Calendar Active)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Booking Link Selection */}
                  {bookingLinks.length > 0 && (
                    <div className="assignment-form">
                      <label htmlFor={`calendar-assign-booking-${purpose.purpose}`}>Scheduling Method - Booking Link:</label>
                      <select
                        id={`calendar-assign-booking-${purpose.purpose}`}
                        value={assignment?.booking_link_id || ''}
                        onChange={(e) => handleAssignBookingLink(purpose.purpose, e.target.value ? parseInt(e.target.value) : null)}
                        disabled={saving}
                      >
                        <option value="">-- No Booking Link --</option>
                        {bookingLinks.map(link => (
                          <option key={link.id} value={link.id}>
                            {link.link_name} (/book/{link.slug}){link.owner_name ? ` - ${link.owner_name}` : ''}
                          </option>
                        ))}
                      </select>
                      {assignment?.booking_link_slug && (
                        <div className="booking-link-preview">
                          Preview: <a href={`/book/${assignment.booking_link_slug}`} target="_blank" rel="noopener noreferrer">/book/{assignment.booking_link_slug}</a>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Custom URL Option (alternative to booking link) */}
                  {!assignment?.booking_link_id && (
                    <div className="custom-url-section">
                      <label htmlFor={`calendar-custom-url-${purpose.purpose}`}>Or use a custom scheduling URL:</label>
                      {isEditing ? (
                        <div className="url-edit-form">
                          <input
                            id={`calendar-custom-url-${purpose.purpose}`}
                            type="url"
                            placeholder="https://your-scheduling-link.com"
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
                  )}

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
        <p className="section-desc">These team members have active calendars and can receive appointments.</p>

        <div className="users-list">
          {users.filter(u => u.has_calendly).length === 0 ? (
            <div className="no-users">
              <p>No team members have active calendars yet.</p>
              <p className="hint">Team members can set up their calendar from their Profile Settings.</p>
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
                      <span className="dot"></span> Calendar Active
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {bookingLinks.length > 0 && (
        <div className="cm-section">
          <h3>Available Booking Links</h3>
          <p className="section-desc">Native booking links created in Video Meetings &gt; Booking Links. These can be assigned to purposes above.</p>

          <div className="users-list">
            <div className="users-grid">
              {bookingLinks.map(link => (
                <div key={link.id} className="user-card">
                  <div className="user-avatar-lg" style={{ background: 'linear-gradient(135deg, #6366f1, #4f46e5)' }}>
                    B
                  </div>
                  <div className="user-details">
                    <span className="user-name">{link.link_name}</span>
                    <span className="user-email">/book/{link.slug}</span>
                    {link.owner_name && (
                      <span className="calendly-status connected">
                        <span className="dot"></span> Owner: {link.owner_name}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CalendarManagement;
