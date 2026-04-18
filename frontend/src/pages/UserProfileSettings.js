/**
 * User Profile Settings Page
 * Comprehensive error handling pattern for user profile management
 */

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAuthHeaders } from '../utils/auth';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import './UserProfileSettings.css';
import { getToken, getUserData, setTokens } from '../utils/tokenStore';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const TABS = [
  { id: 'profile', label: 'Profile', icon: 'fa-user' },
  { id: 'work-hours', label: 'Work Hours', icon: 'fa-clock' },
  { id: 'security', label: 'Security', icon: 'fa-lock' },
  { id: 'notifications', label: 'Notifications', icon: 'fa-bell' },
];

const DAYS_OF_WEEK = [
  { id: 'monday', label: 'Monday' },
  { id: 'tuesday', label: 'Tuesday' },
  { id: 'wednesday', label: 'Wednesday' },
  { id: 'thursday', label: 'Thursday' },
  { id: 'friday', label: 'Friday' },
  { id: 'saturday', label: 'Saturday' },
  { id: 'sunday', label: 'Sunday' },
];

const UserProfileSettings = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  // Tab state
  const [activeTab, setActiveTab] = useState('profile');

  // Profile state
  const [profile, setProfile] = useState(null);
  const [originalProfile, setOriginalProfile] = useState(null);
  const [completeness, setCompleteness] = useState(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Password state
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [passwordRequirements, setPasswordRequirements] = useState(null);

  // Form validation
  const [fieldErrors, setFieldErrors] = useState({});
  const [warnings, setWarnings] = useState([]);

  // Timezones
  const [timezones, setTimezones] = useState([]);

  // Async operations - disable automatic toasts since we handle them manually in catch blocks
  const { loading, error, execute: fetchProfile } = useAsyncOperation({ showErrorToast: false });
  const { loading: saving, execute: saveProfile } = useFormSubmit({ showErrorToast: false, showSuccessToast: false });
  const { loading: changingPassword, execute: changePassword } = useAsyncOperation({ showErrorToast: false });
  const { loading: uploadingPhoto, execute: uploadPhoto } = useAsyncOperation({ showErrorToast: false });

  // Fetch profile on mount
  useEffect(() => {
    loadProfile();
    loadTimezones();
    loadPasswordRequirements();
  }, []);

  // Track unsaved changes
  useEffect(() => {
    if (profile && originalProfile) {
      const changed = JSON.stringify(profile) !== JSON.stringify(originalProfile);
      setHasUnsavedChanges(changed);
    }
  }, [profile, originalProfile]);

  const loadProfile = async () => {
    try {
      const response = await fetchProfile(async () => {
        const res = await fetch(`${API_BASE}/api/v1/user-profile-settings`, {
          headers: getAuthHeaders()
        });
        if (!res.ok) {
          const err = await res.json();
          throw new APIError(err.message || 'Failed to load profile', res.status, err.field_errors);
        }
        return res.json();
      });

      if (response?.success && response.data) {
        const profileData = response.data.profile;
        setProfile(profileData);
        setOriginalProfile(profileData);
        setCompleteness(response.data.completeness);
        setWarnings(response.warnings || []);
      }
    } catch (err) {
      console.error('Error loading profile:', err);
      toast.error('Failed to load profile settings');
    }
  };

  const loadTimezones = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/user-profile-settings/timezones`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setTimezones(data.data.us_timezones || []);
        }
      }
    } catch (err) {
      console.error('Error loading timezones:', err);
    }
  };

  const loadPasswordRequirements = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/user-profile-settings/password-requirements`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setPasswordRequirements(data.data);
        }
      }
    } catch (err) {
      console.error('Error loading password requirements:', err);
    }
  };

  const handleSave = async () => {
    // Client-side validation
    const errors = validateProfile(profile);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      const response = await saveProfile(async () => {
        const res = await fetch(`${API_BASE}/api/v1/user-profile-settings`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            first_name: profile.first_name,
            last_name: profile.last_name,
            phone: profile.phone,
            job_title: profile.job_title,
            nmls_number: profile.nmls_number,
            bio: profile.bio,
            timezone: profile.timezone,
            work_hours_start: profile.work_hours?.start,
            work_hours_end: profile.work_hours?.end,
            work_days: profile.work_hours?.days,
            daily_hours: profile.work_hours?.daily_hours,
            blocked_times: profile.work_hours?.blocked_times,
            email_notifications: profile.notifications?.email,
            sms_notifications: profile.notifications?.sms,
            push_notifications: profile.notifications?.push,
            daily_digest: profile.notifications?.daily_digest,
            task_reminders: profile.notifications?.task_reminders,
            lead_alerts: profile.notifications?.lead_alerts,
          })
        });

        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to save profile', res.status, data.field_errors);
        }
        return data;
      });

      if (response?.success) {
        const profileData = response.data.profile;
        setProfile(profileData);
        setOriginalProfile(profileData);
        setCompleteness(response.data.completeness);
        setHasUnsavedChanges(false);
        setFieldErrors({});
        setWarnings(response.warnings || []);

        // Update localStorage
        const storedUser = getUserData() || {};
        await setTokens({ user_data: {
          ...storedUser,
          full_name: profileData.full_name
        } });

        toast.success('Profile saved successfully');
      }
    } catch (err) {
      if (err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
      }
      toast.error('Failed to save profile');
    }
  };

  const handleReset = () => {
    setProfile({ ...originalProfile });
    setFieldErrors({});
    setHasUnsavedChanges(false);
  };

  const validateProfile = (p) => {
    const errors = {};

    if (!p.first_name?.trim()) {
      errors.first_name = 'First name is required';
    }
    if (!p.last_name?.trim()) {
      errors.last_name = 'Last name is required';
    }
    if (p.phone && !/^\+?[\d\s\-\(\)\.]{7,20}$/.test(p.phone)) {
      errors.phone = 'Invalid phone number format';
    }
    if (p.nmls_number && !/^\d{5,10}$/.test(p.nmls_number.replace(/\D/g, ''))) {
      errors.nmls_number = 'NMLS number should be 5-10 digits';
    }

    // Work hours validation
    if (p.work_hours?.start && p.work_hours?.end) {
      const startParts = p.work_hours.start.split(':').map(Number);
      const endParts = p.work_hours.end.split(':').map(Number);
      const startMinutes = startParts[0] * 60 + startParts[1];
      const endMinutes = endParts[0] * 60 + endParts[1];
      if (endMinutes <= startMinutes) {
        errors.work_hours_end = 'End time must be after start time';
      }
    }

    return errors;
  };

  const updateField = (field, value) => {
    setProfile(prev => ({ ...prev, [field]: value }));
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const updateWorkHours = (field, value) => {
    setProfile(prev => ({
      ...prev,
      work_hours: { ...prev.work_hours, [field]: value }
    }));
  };

  const updateNotifications = (field, value) => {
    setProfile(prev => ({
      ...prev,
      notifications: { ...prev.notifications, [field]: value }
    }));
  };

  const toggleWorkDay = (day) => {
    const currentDays = profile.work_hours?.days || [];
    const newDays = currentDays.includes(day)
      ? currentDays.filter(d => d !== day)
      : [...currentDays, day];
    updateWorkHours('days', newDays);
  };

  const updateDayHours = (day, field, value) => {
    const currentDailyHours = profile.work_hours?.daily_hours || {};
    const currentDay = currentDailyHours[day] || { start: profile.work_hours?.start || '09:00', end: profile.work_hours?.end || '17:00' };
    updateWorkHours('daily_hours', { ...currentDailyHours, [day]: { ...currentDay, [field]: value } });
  };

  const addBlockedTime = () => {
    const current = profile.work_hours?.blocked_times || [];
    const newBlock = {
      id: Math.random().toString(36).substr(2, 8),
      label: '',
      days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
      start: '12:00',
      end: '13:00'
    };
    updateWorkHours('blocked_times', [...current, newBlock]);
  };

  const updateBlockedTime = (idx, field, value) => {
    const updated = [...(profile.work_hours?.blocked_times || [])];
    updated[idx] = { ...updated[idx], [field]: value };
    updateWorkHours('blocked_times', updated);
  };

  const removeBlockedTime = (idx) => {
    const updated = (profile.work_hours?.blocked_times || []).filter((_, i) => i !== idx);
    updateWorkHours('blocked_times', updated);
  };

  const toggleBlockedDay = (idx, day) => {
    const block = (profile.work_hours?.blocked_times || [])[idx];
    const blockDays = block?.days || [];
    const newDays = blockDays.includes(day) ? blockDays.filter(d => d !== day) : [...blockDays, day];
    updateBlockedTime(idx, 'days', newDays);
  };

  const handleChangePassword = async () => {
    // Validate
    const errors = {};
    if (!passwordData.current_password) {
      errors.current_password = 'Current password is required';
    }
    if (!passwordData.new_password) {
      errors.new_password = 'New password is required';
    } else if (passwordData.new_password.length < 8) {
      errors.new_password = 'Password must be at least 8 characters';
    } else if (!/[A-Z]/.test(passwordData.new_password)) {
      errors.new_password = 'Password must contain an uppercase letter';
    } else if (!/[a-z]/.test(passwordData.new_password)) {
      errors.new_password = 'Password must contain a lowercase letter';
    } else if (!/[0-9]/.test(passwordData.new_password)) {
      errors.new_password = 'Password must contain a number';
    }
    if (passwordData.new_password !== passwordData.confirm_password) {
      errors.confirm_password = 'Passwords do not match';
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      const response = await changePassword(async () => {
        const res = await fetch(`${API_BASE}/api/v1/user-profile-settings/password`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify(passwordData)
        });
        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to change password', res.status, data.field_errors);
        }
        return data;
      });

      if (response?.success) {
        setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
        setFieldErrors({});
        toast.success('Password changed successfully!');
      }
    } catch (err) {
      if (err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
      }
      toast.error(err.message || 'Failed to change password');
    }
  };

  const handlePhotoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      setFieldErrors({ photo: 'Invalid file type. Use JPEG, PNG, GIF, or WebP.' });
      return;
    }

    // Validate file size (5MB)
    if (file.size > 5 * 1024 * 1024) {
      setFieldErrors({ photo: 'File too large. Maximum size is 5MB.' });
      return;
    }

    try {
      const formData = new FormData();
      formData.append('photo', file);

      const response = await uploadPhoto(async () => {
        const token = getToken();
        const res = await fetch(`${API_BASE}/api/v1/user-profile-settings/photo`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });
        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to upload photo', res.status, data.field_errors);
        }
        return data;
      });

      if (response?.success) {
        setProfile(prev => ({ ...prev, photo_url: response.data.photo_url }));
        setFieldErrors({});
        toast.success('Photo uploaded successfully');
      }
    } catch (err) {
      if (err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
      }
      toast.error('Failed to upload photo');
    }
  };

  // Loading state
  if (loading && !profile) {
    return (
      <div className="profile-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading profile...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !profile) {
    return (
      <div className="profile-settings-page">
        <div className="error-state">
          <i className="fas fa-exclamation-circle"></i>
          <h2>Failed to Load Profile</h2>
          <p>{error}</p>
          <button className="btn-primary" onClick={loadProfile}>
            <i className="fas fa-redo"></i> Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="profile-settings-page">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/settings')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Profile Settings</h1>
            <p className="subtitle">Manage your personal information and preferences</p>
          </div>
        </div>
        {completeness && (
          <div className="completeness-badge">
            <div className="completeness-ring" style={{ '--percent': completeness.completeness_percent }}>
              <span>{completeness.completeness_percent}%</span>
            </div>
            <span>Complete</span>
          </div>
        )}
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="warnings-banner">
          <i className="fas fa-exclamation-triangle"></i>
          <div>
            <strong>Complete Your Profile</strong>
            <ul>
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="settings-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <i className={`fas ${tab.icon}`}></i>
            {tab.label}
          </button>
        ))}
      </div>

      {profile && (
        <div className="settings-content">
          {/* Profile Tab */}
          {activeTab === 'profile' && (
            <div className="settings-section">
              <h2>Personal Information</h2>
              <p className="section-description">Your basic profile information</p>

              {/* Photo Upload */}
              <div className="photo-upload-section">
                <div className="photo-preview">
                  {profile.photo_url ? (
                    <img src={profile.photo_url} alt="Profile" />
                  ) : (
                    <div className="photo-placeholder">
                      {profile.first_name?.charAt(0) || profile.email?.charAt(0) || '?'}
                    </div>
                  )}
                </div>
                <div className="photo-actions">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/gif,image/webp"
                    onChange={handlePhotoUpload}
                    style={{ display: 'none' }}
                  />
                  <button
                    className="btn-secondary"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingPhoto}
                  >
                    {uploadingPhoto ? 'Uploading...' : 'Upload Photo'}
                  </button>
                  {fieldErrors.photo && <span className="field-error">{fieldErrors.photo}</span>}
                </div>
              </div>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={profile.first_name || ''}
                    onChange={(e) => updateField('first_name', e.target.value)}
                    className={fieldErrors.first_name ? 'has-error' : ''}
                    placeholder="Enter first name"
                  />
                  {fieldErrors.first_name && <span className="field-error">{fieldErrors.first_name}</span>}
                </div>
                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={profile.last_name || ''}
                    onChange={(e) => updateField('last_name', e.target.value)}
                    className={fieldErrors.last_name ? 'has-error' : ''}
                    placeholder="Enter last name"
                  />
                  {fieldErrors.last_name && <span className="field-error">{fieldErrors.last_name}</span>}
                </div>
              </div>

              <div className="form-group">
                <label>Email</label>
                <input
                  type="email"
                  value={profile.email || ''}
                  disabled
                  className="disabled-input"
                />
                <span className="field-hint">Email cannot be changed. Contact administrator.</span>
              </div>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Phone Number</label>
                  <input
                    type="tel"
                    value={profile.phone || ''}
                    onChange={(e) => updateField('phone', e.target.value)}
                    className={fieldErrors.phone ? 'has-error' : ''}
                    placeholder="(555) 123-4567"
                  />
                  {fieldErrors.phone && <span className="field-error">{fieldErrors.phone}</span>}
                </div>
                <div className="form-group">
                  <label>Job Title</label>
                  <input
                    type="text"
                    value={profile.job_title || ''}
                    onChange={(e) => updateField('job_title', e.target.value)}
                    placeholder="Loan Officer"
                  />
                </div>
              </div>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>NMLS Number</label>
                  <input
                    type="text"
                    value={profile.nmls_number || ''}
                    onChange={(e) => updateField('nmls_number', e.target.value)}
                    className={fieldErrors.nmls_number ? 'has-error' : ''}
                    placeholder="12345"
                  />
                  {fieldErrors.nmls_number && <span className="field-error">{fieldErrors.nmls_number}</span>}
                  <span className="field-hint">Your NMLS license number</span>
                </div>
                <div className="form-group">
                  <label>Timezone</label>
                  <select
                    value={profile.timezone || 'America/New_York'}
                    onChange={(e) => updateField('timezone', e.target.value)}
                  >
                    {timezones.map(tz => (
                      <option key={tz.value} value={tz.value}>{tz.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Bio</label>
                <textarea
                  value={profile.bio || ''}
                  onChange={(e) => updateField('bio', e.target.value)}
                  placeholder="A brief description about yourself..."
                  rows={3}
                  maxLength={500}
                />
                <span className="field-hint">{(profile.bio || '').length}/500 characters</span>
              </div>
            </div>
          )}

          {/* Work Hours Tab */}
          {activeTab === 'work-hours' && (
            <div className="settings-section">
              <h2>Work Hours</h2>
              <p className="section-description">Set your availability for scheduling</p>

              {/* Per-Day Schedule */}
              <div className="form-group">
                <label>Daily Schedule</label>
                <p style={{ fontSize: '13px', color: '#666', marginBottom: '12px' }}>Set different hours for each day</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {DAYS_OF_WEEK.map(day => {
                    const isEnabled = (profile.work_hours?.days || []).includes(day.id);
                    const dayHours = (profile.work_hours?.daily_hours || {})[day.id] || {};
                    const dayStart = dayHours.start || profile.work_hours?.start || '09:00';
                    const dayEnd = dayHours.end || profile.work_hours?.end || '17:00';

                    return (
                      <div key={day.id} style={{
                        display: 'grid',
                        gridTemplateColumns: '100px 40px 1fr 1fr',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '8px 12px',
                        background: isEnabled ? '#fff' : '#f9fafb',
                        borderRadius: '8px',
                        border: '1px solid',
                        borderColor: isEnabled ? '#d1d5db' : '#e5e7eb'
                      }}>
                        <span style={{ fontSize: '14px', fontWeight: isEnabled ? '600' : '400', color: isEnabled ? '#1a1a1a' : '#9ca3af' }}>
                          {day.label.substring(0, 3)}
                        </span>
                        <label style={{ position: 'relative', display: 'inline-block', width: '34px', height: '18px', cursor: 'pointer' }}>
                          <input type="checkbox" checked={isEnabled} onChange={() => toggleWorkDay(day.id)} style={{ opacity: 0, width: 0, height: 0 }} />
                          <span style={{
                            position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                            backgroundColor: isEnabled ? '#217F8D' : '#d1d5db', borderRadius: '18px', transition: 'background-color 0.2s'
                          }}>
                            <span style={{
                              position: 'absolute', height: '14px', width: '14px', left: isEnabled ? '18px' : '2px', bottom: '2px',
                              backgroundColor: 'white', borderRadius: '50%', transition: 'left 0.2s'
                            }} />
                          </span>
                        </label>
                        {isEnabled ? (
                          <>
                            <select value={dayStart} onChange={(e) => updateDayHours(day.id, 'start', e.target.value)}
                              style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }}>
                              {Array.from({ length: 48 }, (_, i) => {
                                const h = Math.floor(i / 2); const m = i % 2 === 0 ? '00' : '30';
                                const val = `${h.toString().padStart(2, '0')}:${m}`;
                                const disp = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                return <option key={val} value={val}>{disp}</option>;
                              })}
                            </select>
                            <select value={dayEnd} onChange={(e) => updateDayHours(day.id, 'end', e.target.value)}
                              style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }}>
                              {Array.from({ length: 48 }, (_, i) => {
                                const h = Math.floor(i / 2); const m = i % 2 === 0 ? '00' : '30';
                                const val = `${h.toString().padStart(2, '0')}:${m}`;
                                const disp = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                return <option key={val} value={val}>{disp}</option>;
                              })}
                            </select>
                          </>
                        ) : (
                          <span style={{ gridColumn: 'span 2', fontSize: '13px', color: '#9ca3af', fontStyle: 'italic' }}>Day off</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Blocked Time Slots */}
              <div className="form-group" style={{ marginTop: '24px' }}>
                <label>Blocked Time Slots</label>
                <p style={{ fontSize: '13px', color: '#666', marginBottom: '12px' }}>Protect specific times from being scheduled</p>

                {(profile.work_hours?.blocked_times || []).length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                    {(profile.work_hours?.blocked_times || []).map((block, idx) => (
                      <div key={block.id || idx} style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 110px 110px 32px',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '8px 12px',
                        background: '#fff',
                        borderRadius: '8px',
                        border: '1px solid #d1d5db'
                      }}>
                        <input
                          type="text"
                          value={block.label || ''}
                          placeholder="Label"
                          onChange={(e) => updateBlockedTime(idx, 'label', e.target.value)}
                          style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }}
                        />
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
                          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, di) => {
                            const fullDay = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][di];
                            const sel = (block.days || []).includes(fullDay);
                            return (
                              <button key={d} type="button" onClick={() => toggleBlockedDay(idx, fullDay)}
                                style={{
                                  padding: '1px 5px', fontSize: '10px', borderRadius: '3px', cursor: 'pointer',
                                  border: '1px solid', borderColor: sel ? '#217F8D' : '#d1d5db',
                                  background: sel ? 'rgba(33,127,141,0.1)' : '#fff', color: sel ? '#217F8D' : '#999',
                                  fontWeight: sel ? '600' : '400'
                                }}>
                                {d}
                              </button>
                            );
                          })}
                        </div>
                        <select value={block.start || '12:00'} onChange={(e) => updateBlockedTime(idx, 'start', e.target.value)}
                          style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }}>
                          {Array.from({ length: 48 }, (_, i) => {
                            const h = Math.floor(i / 2); const m = i % 2 === 0 ? '00' : '30';
                            const val = `${h.toString().padStart(2, '0')}:${m}`;
                            const disp = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                            return <option key={val} value={val}>{disp}</option>;
                          })}
                        </select>
                        <select value={block.end || '13:00'} onChange={(e) => updateBlockedTime(idx, 'end', e.target.value)}
                          style={{ padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }}>
                          {Array.from({ length: 48 }, (_, i) => {
                            const h = Math.floor(i / 2); const m = i % 2 === 0 ? '00' : '30';
                            const val = `${h.toString().padStart(2, '0')}:${m}`;
                            const disp = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                            return <option key={val} value={val}>{disp}</option>;
                          })}
                        </select>
                        <button type="button" onClick={() => removeBlockedTime(idx)}
                          style={{ padding: '4px', background: 'none', border: '1px solid #e5e7eb', borderRadius: '4px', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                          title="Remove">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <button type="button" onClick={addBlockedTime}
                  style={{
                    padding: '8px 16px', background: '#fff', border: '2px dashed #d1d5db', borderRadius: '8px',
                    cursor: 'pointer', fontSize: '13px', color: '#217F8D', fontWeight: '500',
                    display: 'flex', alignItems: 'center', gap: '6px'
                  }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
                  Add Time Block
                </button>
              </div>

              <div className="info-card">
                <i className="fas fa-info-circle"></i>
                <div>
                  <strong>Work Hours Usage</strong>
                  <p>Your work hours are used for:</p>
                  <ul>
                    <li>Smart Scheduler availability</li>
                    <li>Task assignment timing</li>
                    <li>Notification quiet hours</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Security Tab */}
          {activeTab === 'security' && (
            <div className="settings-section">
              <h2>Change Password</h2>
              <p className="section-description">Update your account password</p>

              {passwordRequirements && (
                <div className="password-requirements">
                  <strong>Password Requirements:</strong>
                  <ul>
                    {passwordRequirements.requirements.map((req, i) => (
                      <li key={i}>{req}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="form-group">
                <label>Current Password</label>
                <input
                  type="password"
                  value={passwordData.current_password}
                  onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })}
                  className={fieldErrors.current_password ? 'has-error' : ''}
                  placeholder="Enter current password"
                />
                {fieldErrors.current_password && <span className="field-error">{fieldErrors.current_password}</span>}
              </div>

              <div className="form-group">
                <label>New Password</label>
                <input
                  type="password"
                  value={passwordData.new_password}
                  onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                  className={fieldErrors.new_password ? 'has-error' : ''}
                  placeholder="Enter new password"
                />
                {fieldErrors.new_password && <span className="field-error">{fieldErrors.new_password}</span>}
              </div>

              <div className="form-group">
                <label>Confirm New Password</label>
                <input
                  type="password"
                  value={passwordData.confirm_password}
                  onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                  className={fieldErrors.confirm_password ? 'has-error' : ''}
                  placeholder="Confirm new password"
                />
                {fieldErrors.confirm_password && <span className="field-error">{fieldErrors.confirm_password}</span>}
              </div>

              <button
                className="btn-primary"
                onClick={handleChangePassword}
                disabled={changingPassword}
              >
                {changingPassword ? <><i className="fas fa-spinner fa-spin"></i> Changing...</> : 'Change Password'}
              </button>
            </div>
          )}

          {/* Notifications Tab */}
          {activeTab === 'notifications' && (
            <div className="settings-section">
              <h2>Notification Preferences</h2>
              <p className="section-description">Control how you receive notifications</p>

              <div className="notification-group">
                <h3>Channels</h3>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.email ?? true}
                      onChange={(e) => updateNotifications('email', e.target.checked)}
                    />
                    <span>Email Notifications</span>
                  </label>
                  <span className="option-hint">Receive notifications via email</span>
                </div>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.sms ?? false}
                      onChange={(e) => updateNotifications('sms', e.target.checked)}
                    />
                    <span>SMS Notifications</span>
                  </label>
                  <span className="option-hint">Receive text message alerts</span>
                </div>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.push ?? true}
                      onChange={(e) => updateNotifications('push', e.target.checked)}
                    />
                    <span>Push Notifications</span>
                  </label>
                  <span className="option-hint">Browser push notifications</span>
                </div>
              </div>

              <div className="notification-group">
                <h3>Alert Types</h3>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.daily_digest ?? true}
                      onChange={(e) => updateNotifications('daily_digest', e.target.checked)}
                    />
                    <span>Daily Digest</span>
                  </label>
                  <span className="option-hint">Daily summary of activity</span>
                </div>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.task_reminders ?? true}
                      onChange={(e) => updateNotifications('task_reminders', e.target.checked)}
                    />
                    <span>Task Reminders</span>
                  </label>
                  <span className="option-hint">Reminders for upcoming tasks</span>
                </div>
                <div className="notification-option">
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.notifications?.lead_alerts ?? true}
                      onChange={(e) => updateNotifications('lead_alerts', e.target.checked)}
                    />
                    <span>New Lead Alerts</span>
                  </label>
                  <span className="option-hint">Alerts when new leads are assigned</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sticky Save Bar */}
      {hasUnsavedChanges && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button className="btn-secondary" onClick={handleReset} disabled={saving}>
                Discard
              </button>
              <button className="btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserProfileSettings;
