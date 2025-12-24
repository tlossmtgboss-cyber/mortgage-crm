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

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

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
  const { loading, error, execute: fetchProfile } = useAsyncOperation(null, { showErrorToast: false });
  const { loading: saving, execute: saveProfile } = useFormSubmit({ showErrorToast: false, showSuccessToast: false });
  const { loading: changingPassword, execute: changePassword } = useAsyncOperation(null, { showErrorToast: false });
  const { loading: uploadingPhoto, execute: uploadPhoto } = useAsyncOperation(null, { showErrorToast: false });

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
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({
          ...storedUser,
          full_name: profileData.full_name
        }));

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
        const token = localStorage.getItem('token');
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

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Start Time</label>
                  <input
                    type="time"
                    value={profile.work_hours?.start || '09:00'}
                    onChange={(e) => updateWorkHours('start', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>End Time</label>
                  <input
                    type="time"
                    value={profile.work_hours?.end || '17:00'}
                    onChange={(e) => updateWorkHours('end', e.target.value)}
                    className={fieldErrors.work_hours_end ? 'has-error' : ''}
                  />
                  {fieldErrors.work_hours_end && <span className="field-error">{fieldErrors.work_hours_end}</span>}
                </div>
              </div>

              <div className="form-group">
                <label>Working Days</label>
                <div className="days-grid">
                  {DAYS_OF_WEEK.map(day => (
                    <button
                      key={day.id}
                      type="button"
                      className={`day-btn ${(profile.work_hours?.days || []).includes(day.id) ? 'active' : ''}`}
                      onClick={() => toggleWorkDay(day.id)}
                    >
                      {day.label.substring(0, 3)}
                    </button>
                  ))}
                </div>
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
