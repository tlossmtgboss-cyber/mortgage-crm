/**
 * Perennia AI - Smart Scheduler Settings
 *
 * Comprehensive error handling implementation following the Agent Governance pattern:
 * - Field-level validation with inline errors
 * - Loading states for all operations
 * - Toast notifications for success/error feedback
 * - Timezone picker with search
 * - Working hours validation
 * - Capacity estimation
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAsyncOperation, useFormSubmit } from '../hooks/useAsyncOperation';
import { APIError } from '../utils/api/errors';
import { toast } from '../utils/toast';
import { API_BASE_URL } from '../services/api';
import CalendarManagement from '../components/CalendarManagement';
import AppointmentTypesManager from '../components/AppointmentTypesManager';
import BookingLinksManager from '../components/BookingLinksManager';
import BlockedTimeManager from '../components/BlockedTimeManager';
import SchedulerAnalytics from '../components/SchedulerAnalytics';
import './SmartSchedulerSettings.css';

// Day order for display
const DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = {
  monday: 'Monday',
  tuesday: 'Tuesday',
  wednesday: 'Wednesday',
  thursday: 'Thursday',
  friday: 'Friday',
  saturday: 'Saturday',
  sunday: 'Sunday',
};

// Scheduling methods
const SCHEDULING_METHODS = [
  { value: 'direct', label: 'Direct', description: 'Book directly with you — no routing' },
  { value: 'round_robin', label: 'Round Robin', description: 'Distribute appointments evenly' },
  { value: 'priority', label: 'Priority', description: 'Assign to highest priority LO' },
  { value: 'availability', label: 'First Available', description: 'Fastest booking' },
  { value: 'load_balanced', label: 'Load Balanced', description: 'Prevent burnout' },
];

// Validation functions
const validateSettings = (settings) => {
  const errors = {};

  // Validate business hours
  const businessHours = settings.business_hours || {};
  let hasEnabledDay = false;

  DAYS_OF_WEEK.forEach(day => {
    const dayHours = businessHours[day];
    if (dayHours?.enabled) {
      hasEnabledDay = true;

      // Validate time format
      const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
      if (!timeRegex.test(dayHours.start)) {
        errors[`${day}_start`] = 'Invalid time format';
      }
      if (!timeRegex.test(dayHours.end)) {
        errors[`${day}_end`] = 'Invalid time format';
      }

      // Validate end > start
      if (dayHours.start && dayHours.end) {
        const [startH, startM] = dayHours.start.split(':').map(Number);
        const [endH, endM] = dayHours.end.split(':').map(Number);
        const startMinutes = startH * 60 + startM;
        const endMinutes = endH * 60 + endM;

        if (endMinutes <= startMinutes) {
          errors[`${day}_end`] = 'End time must be after start time';
        }
      }
    }
  });

  if (!hasEnabledDay) {
    errors.business_hours = 'At least one day must have working hours enabled';
  }

  // Validate booking settings
  if (settings.booking_settings) {
    if (settings.booking_settings.min_notice_hours < 0) {
      errors.min_notice_hours = 'Cannot be negative';
    }
    if (settings.booking_settings.max_advance_days < 1) {
      errors.max_advance_days = 'Must be at least 1 day';
    }
    if (settings.booking_settings.default_duration_minutes < 15) {
      errors.default_duration_minutes = 'Must be at least 15 minutes';
    }
    if (settings.booking_settings.max_meetings_per_day < 1) {
      errors.max_meetings_per_day = 'Must be at least 1';
    }
  }

  return errors;
};

function SmartSchedulerSettings() {
  const navigate = useNavigate();

  // State
  const [settings, setSettings] = useState({
    timezone: 'America/Chicago',
    scheduling_method: 'direct',
    business_hours: {
      monday: { start: '09:00', end: '17:00', enabled: true },
      tuesday: { start: '09:00', end: '17:00', enabled: true },
      wednesday: { start: '09:00', end: '17:00', enabled: true },
      thursday: { start: '09:00', end: '17:00', enabled: true },
      friday: { start: '09:00', end: '17:00', enabled: true },
      saturday: { start: '10:00', end: '14:00', enabled: false },
      sunday: { start: '10:00', end: '14:00', enabled: false },
    },
    booking_settings: {
      min_notice_hours: 2,
      max_advance_days: 60,
      default_duration_minutes: 30,
      buffer_between_appointments: 5,
      max_meetings_per_day: 8,
    },
    ai_settings: {
      ai_scheduling_enabled: true,
      ai_can_reschedule: true,
      ai_can_cancel: false,
      smart_reminders_enabled: true,
      auto_reschedule_enabled: true,
    },
    default_meeting_mode: 'video',
    zoom_enabled: true,
    google_meet_enabled: true,
    auto_create_meeting_link: true,
  });

  const [timezones, setTimezones] = useState([]);
  const [timezoneSearch, setTimezoneSearch] = useState('');
  const [warnings, setWarnings] = useState([]);
  const [capacity, setCapacity] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [activeTab, setActiveTab] = useState('working-hours');

  // API helper
  const apiRequest = async (url, options = {}) => {
    const token = localStorage.getItem('token');
    const response = await fetch(`${API_BASE_URL}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers,
      },
    });

    const data = await response.json();

    if (!response.ok) {
      if (data.error) {
        const error = new APIError(
          data.error.message || 'Request failed',
          data.error.code || 'UNKNOWN_ERROR',
          {
            details: data.error.details,
            statusCode: response.status,
          }
        );
        if (data.error.field_errors) {
          error.fieldErrors = data.error.field_errors;
        }
        throw error;
      }
      throw new APIError(data.detail || 'Request failed', 'SERVER_ERROR', { statusCode: response.status });
    }

    return data;
  };

  // Fetch settings
  const { execute: fetchSettings, isLoading: isLoadingSettings } = useAsyncOperation(
    async () => {
      const data = await apiRequest('/api/v1/smart-scheduler-settings');
      return data.data;
    },
    {
      showErrorToast: true,
      errorMessage: 'Failed to load scheduler settings',
    }
  );

  // Fetch timezones
  const { execute: fetchTimezones } = useAsyncOperation(
    async (search = '') => {
      const url = search
        ? `/api/v1/smart-scheduler-settings/timezones?search=${encodeURIComponent(search)}`
        : '/api/v1/smart-scheduler-settings/timezones';
      const data = await apiRequest(url);
      return data.data.timezones;
    },
    { showErrorToast: false }
  );

  // Save settings
  const {
    submit: saveSettings,
    isSubmitting,
    fieldErrors,
    clearFieldError
  } = useFormSubmit({
    onSubmit: async (data) => {
      const response = await apiRequest('/api/v1/smart-scheduler-settings', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
      return response;
    },
    validate: validateSettings,
    showSuccessToast: true,
    successMessage: 'Scheduler settings saved successfully',
    onSuccess: (response) => {
      setHasChanges(false);
      if (response.data?.warnings) {
        setWarnings(response.data.warnings);
      }
      if (response.data?.capacity) {
        setCapacity(response.data.capacity);
      }
    },
  });

  // Test configuration
  const { execute: testConfig, isLoading: isTesting } = useAsyncOperation(
    async () => {
      const response = await apiRequest('/api/v1/smart-scheduler-settings/test', {
        method: 'POST',
        body: JSON.stringify({ test_duration: settings.booking_settings.default_duration_minutes }),
      });
      return response.data;
    },
    {
      showSuccessToast: false,
      showErrorToast: true,
      errorMessage: 'Configuration test failed',
      onSuccess: (result) => {
        setTestResult(result);
        if (result.success) {
          toast.success('Configuration test passed!');
        } else {
          toast.warning('Configuration test found issues');
        }
      },
    }
  );

  // Load data on mount
  useEffect(() => {
    loadSettings();
    loadTimezones();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await fetchSettings();
      if (data) {
        setSettings({
          timezone: data.timezone || 'America/Chicago',
          scheduling_method: data.scheduling_method || 'round_robin',
          business_hours: data.business_hours || settings.business_hours,
          booking_settings: data.booking_settings || settings.booking_settings,
          ai_settings: data.ai_settings || settings.ai_settings,
          default_meeting_mode: data.default_meeting_mode || 'video',
          zoom_enabled: data.zoom_enabled ?? true,
          google_meet_enabled: data.google_meet_enabled ?? true,
          auto_create_meeting_link: data.auto_create_meeting_link ?? true,
        });
      }
    } catch (error) {
      // Error already handled by hook
    }
  };

  const loadTimezones = async (search = '') => {
    try {
      const data = await fetchTimezones(search);
      if (data) {
        setTimezones(data);
      }
    } catch (error) {
      // Silently fail, use defaults
      setTimezones([
        { value: 'America/New_York', label: 'Eastern Time (ET)' },
        { value: 'America/Chicago', label: 'Central Time (CT)' },
        { value: 'America/Denver', label: 'Mountain Time (MT)' },
        { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
      ]);
    }
  };

  // Update settings helper
  const updateSetting = useCallback((path, value) => {
    setSettings(prev => {
      const newSettings = { ...prev };
      const keys = path.split('.');
      let current = newSettings;

      for (let i = 0; i < keys.length - 1; i++) {
        current[keys[i]] = { ...current[keys[i]] };
        current = current[keys[i]];
      }
      current[keys[keys.length - 1]] = value;

      return newSettings;
    });
    setHasChanges(true);

    // Clear field error
    const errorKey = path.replace(/\./g, '_');
    if (fieldErrors[errorKey]) {
      clearFieldError(errorKey);
    }
  }, [fieldErrors, clearFieldError]);

  // Update business hours for a day
  const updateBusinessHours = useCallback((day, field, value) => {
    setSettings(prev => ({
      ...prev,
      business_hours: {
        ...prev.business_hours,
        [day]: {
          ...prev.business_hours[day],
          [field]: value,
        },
      },
    }));
    setHasChanges(true);

    // Clear field error
    const errorKey = `${day}_${field}`;
    if (fieldErrors[errorKey]) {
      clearFieldError(errorKey);
    }
  }, [fieldErrors, clearFieldError]);

  // Handle save
  const handleSave = async (e) => {
    e.preventDefault();
    try {
      await saveSettings(settings);
    } catch (error) {
      // Error handled by hook
    }
  };

  // Handle test
  const handleTest = async () => {
    setTestResult(null);
    try {
      await testConfig();
    } catch (error) {
      // Error handled by hook
    }
  };

  // Handle timezone search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (timezoneSearch) {
        loadTimezones(timezoneSearch);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [timezoneSearch]);

  // Loading state
  if (isLoadingSettings) {
    return (
      <div className="scheduler-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading scheduler settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="scheduler-settings-page">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button onClick={() => navigate(-1)} className="back-btn">
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Smart Scheduler Settings</h1>
            <p className="subtitle">Configure your scheduling preferences</p>
          </div>
        </div>
        <div className="header-actions">
          <button
            onClick={handleTest}
            disabled={isTesting || isSubmitting}
            className="btn-secondary"
          >
            {isTesting ? (
              <><i className="fas fa-spinner fa-spin"></i> Testing...</>
            ) : (
              <><i className="fas fa-vial"></i> Test Configuration</>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={isSubmitting || !hasChanges}
            className="btn-primary"
          >
            {isSubmitting ? (
              <><i className="fas fa-spinner fa-spin"></i> Saving...</>
            ) : (
              <><i className="fas fa-save"></i> Save Changes</>
            )}
          </button>
        </div>
      </div>

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div className="warnings-banner">
          <i className="fas fa-exclamation-triangle"></i>
          <div>
            <strong>Configuration Warnings</strong>
            <ul>
              {warnings.map((warning, idx) => (
                <li key={idx}>{warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Test Result */}
      {testResult && (
        <div className={`test-result ${testResult.success ? 'success' : 'warning'}`}>
          <div className="test-header">
            <i className={`fas ${testResult.success ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
            <strong>{testResult.success ? 'Test Passed' : 'Issues Found'}</strong>
          </div>
          <p>Loan officers available: {testResult.loan_officers_available}</p>
          {testResult.issues?.length > 0 && (
            <ul>
              {testResult.issues.map((issue, idx) => (
                <li key={idx}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Capacity Card */}
      {capacity && (
        <div className="capacity-card">
          <div className="capacity-header">
            <i className="fas fa-calendar-check"></i>
            <strong>Weekly Capacity</strong>
          </div>
          <div className="capacity-stats">
            <div className="stat">
              <span className="stat-value">{capacity.total_working_hours}h</span>
              <span className="stat-label">Working Hours</span>
            </div>
            <div className="stat">
              <span className="stat-value">{capacity.working_days}</span>
              <span className="stat-label">Working Days</span>
            </div>
            <div className="stat">
              <span className="stat-value">{capacity.max_meetings_per_week}</span>
              <span className="stat-label">Max Meetings/Week</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="settings-tabs">
        <button
          className={`tab-btn ${activeTab === 'working-hours' ? 'active' : ''}`}
          onClick={() => setActiveTab('working-hours')}
        >
          <i className="fas fa-clock"></i> Working Hours
        </button>
        <button
          className={`tab-btn ${activeTab === 'booking' ? 'active' : ''}`}
          onClick={() => setActiveTab('booking')}
        >
          <i className="fas fa-calendar-alt"></i> Booking
        </button>
        <button
          className={`tab-btn ${activeTab === 'appointment-types' ? 'active' : ''}`}
          onClick={() => setActiveTab('appointment-types')}
        >
          <i className="fas fa-list-alt"></i> Appointment Types
        </button>
        <button
          className={`tab-btn ${activeTab === 'booking-links' ? 'active' : ''}`}
          onClick={() => setActiveTab('booking-links')}
        >
          <i className="fas fa-link"></i> Booking Links
        </button>
        <button
          className={`tab-btn ${activeTab === 'blocked-time' ? 'active' : ''}`}
          onClick={() => setActiveTab('blocked-time')}
        >
          <i className="fas fa-ban"></i> Blocked Time
        </button>
        <button
          className={`tab-btn ${activeTab === 'ai' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          <i className="fas fa-robot"></i> AI Settings
        </button>
        <button
          className={`tab-btn ${activeTab === 'video' ? 'active' : ''}`}
          onClick={() => setActiveTab('video')}
        >
          <i className="fas fa-video"></i> Video
        </button>
        <button
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          <i className="fas fa-chart-bar"></i> Analytics
        </button>
        <button
          className={`tab-btn ${activeTab === 'calendar-assignments' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar-assignments')}
        >
          <i className="fas fa-calendar-check"></i> Calendar Assignments
        </button>
      </div>

      <form onSubmit={handleSave}>
        {/* Working Hours Tab */}
        {activeTab === 'working-hours' && (
          <section className="settings-section">
            <h2>Working Hours</h2>

            {/* Timezone */}
            <div className="form-row">
              <label>Timezone</label>
              <select
                value={settings.timezone}
                onChange={(e) => updateSetting('timezone', e.target.value)}
              >
                {timezones.map(tz => (
                  <option key={tz.value} value={tz.value}>
                    {tz.label} {tz.offset ? `(${tz.offset})` : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* General error for business hours */}
            {fieldErrors.business_hours && (
              <div className="section-error">{fieldErrors.business_hours}</div>
            )}

            {/* Days */}
            <div className="business-hours-grid">
              {DAYS_OF_WEEK.map(day => {
                const dayHours = settings.business_hours[day] || { start: '09:00', end: '17:00', enabled: false };
                const hasStartError = fieldErrors[`${day}_start`];
                const hasEndError = fieldErrors[`${day}_end`];

                return (
                  <div key={day} className={`day-row ${dayHours.enabled ? 'enabled' : 'disabled'}`}>
                    <label className="day-toggle">
                      <input
                        type="checkbox"
                        checked={dayHours.enabled}
                        onChange={(e) => updateBusinessHours(day, 'enabled', e.target.checked)}
                      />
                      <span className="day-name">{DAY_LABELS[day]}</span>
                    </label>

                    {dayHours.enabled && (
                      <div className="time-inputs">
                        <div className="time-input-group">
                          <input
                            type="time"
                            value={dayHours.start}
                            onChange={(e) => updateBusinessHours(day, 'start', e.target.value)}
                            className={hasStartError ? 'has-error' : ''}
                          />
                          {hasStartError && <span className="field-error">{hasStartError}</span>}
                        </div>
                        <span className="time-separator">to</span>
                        <div className="time-input-group">
                          <input
                            type="time"
                            value={dayHours.end}
                            onChange={(e) => updateBusinessHours(day, 'end', e.target.value)}
                            className={hasEndError ? 'has-error' : ''}
                          />
                          {hasEndError && <span className="field-error">{hasEndError}</span>}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Booking Tab */}
        {activeTab === 'booking' && (
          <section className="settings-section">
            <h2>Booking Settings</h2>

            {/* Scheduling Method */}
            <div className="form-row">
              <label>Scheduling Method</label>
              <div className="method-options">
                {SCHEDULING_METHODS.map(method => (
                  <label key={method.value} className={`method-option ${settings.scheduling_method === method.value ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="scheduling_method"
                      value={method.value}
                      checked={settings.scheduling_method === method.value}
                      onChange={(e) => updateSetting('scheduling_method', e.target.value)}
                    />
                    <div className="method-content">
                      <strong>{method.label}</strong>
                      <span>{method.description}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Min Notice */}
            <div className="form-row">
              <label htmlFor="min_notice">Minimum Notice (hours)</label>
              <input
                id="min_notice"
                type="number"
                min="0"
                max="168"
                value={settings.booking_settings.min_notice_hours}
                onChange={(e) => updateSetting('booking_settings.min_notice_hours', parseInt(e.target.value) || 0)}
                className={fieldErrors.min_notice_hours ? 'has-error' : ''}
              />
              {fieldErrors.min_notice_hours && (
                <span className="field-error">{fieldErrors.min_notice_hours}</span>
              )}
              <span className="field-hint">How far in advance bookings must be made</span>
            </div>

            {/* Max Advance */}
            <div className="form-row">
              <label htmlFor="max_advance">Maximum Advance Booking (days)</label>
              <input
                id="max_advance"
                type="number"
                min="1"
                max="365"
                value={settings.booking_settings.max_advance_days}
                onChange={(e) => updateSetting('booking_settings.max_advance_days', parseInt(e.target.value) || 1)}
                className={fieldErrors.max_advance_days ? 'has-error' : ''}
              />
              {fieldErrors.max_advance_days && (
                <span className="field-error">{fieldErrors.max_advance_days}</span>
              )}
              <span className="field-hint">How far in the future clients can book</span>
            </div>

            {/* Default Duration */}
            <div className="form-row">
              <label htmlFor="default_duration">Default Meeting Duration (minutes)</label>
              <select
                id="default_duration"
                value={settings.booking_settings.default_duration_minutes}
                onChange={(e) => updateSetting('booking_settings.default_duration_minutes', parseInt(e.target.value))}
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>60 minutes</option>
                <option value={90}>90 minutes</option>
              </select>
            </div>

            {/* Buffer */}
            <div className="form-row">
              <label htmlFor="buffer">Buffer Between Meetings (minutes)</label>
              <input
                id="buffer"
                type="number"
                min="0"
                max="60"
                value={settings.booking_settings.buffer_between_appointments}
                onChange={(e) => updateSetting('booking_settings.buffer_between_appointments', parseInt(e.target.value) || 0)}
              />
              <span className="field-hint">Break time between consecutive meetings</span>
            </div>

            {/* Max Per Day */}
            <div className="form-row">
              <label htmlFor="max_per_day">Maximum Meetings Per Day</label>
              <input
                id="max_per_day"
                type="number"
                min="1"
                max="24"
                value={settings.booking_settings.max_meetings_per_day}
                onChange={(e) => updateSetting('booking_settings.max_meetings_per_day', parseInt(e.target.value) || 1)}
                className={fieldErrors.max_meetings_per_day ? 'has-error' : ''}
              />
              {fieldErrors.max_meetings_per_day && (
                <span className="field-error">{fieldErrors.max_meetings_per_day}</span>
              )}
            </div>
          </section>
        )}

        {/* AI Tab */}
        {activeTab === 'ai' && (
          <section className="settings-section">
            <h2>AI Scheduling</h2>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.ai_settings.ai_scheduling_enabled}
                  onChange={(e) => updateSetting('ai_settings.ai_scheduling_enabled', e.target.checked)}
                />
                Enable AI Scheduling
                <span className="checkbox-hint">Let AI assist with booking and optimization</span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.ai_settings.ai_can_reschedule}
                  onChange={(e) => updateSetting('ai_settings.ai_can_reschedule', e.target.checked)}
                />
                AI Can Reschedule
                <span className="checkbox-hint">Allow AI to suggest reschedules when conflicts arise</span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label className="warning-checkbox">
                <input
                  type="checkbox"
                  checked={settings.ai_settings.ai_can_cancel}
                  onChange={(e) => updateSetting('ai_settings.ai_can_cancel', e.target.checked)}
                />
                AI Can Cancel Appointments
                <span className="checkbox-hint warning">
                  <i className="fas fa-exclamation-triangle"></i>
                  Allows AI to cancel appointments automatically
                </span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.ai_settings.smart_reminders_enabled}
                  onChange={(e) => updateSetting('ai_settings.smart_reminders_enabled', e.target.checked)}
                />
                Smart Reminders
                <span className="checkbox-hint">AI-optimized reminder timing based on behavior</span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.ai_settings.auto_reschedule_enabled}
                  onChange={(e) => updateSetting('ai_settings.auto_reschedule_enabled', e.target.checked)}
                />
                Auto-Reschedule
                <span className="checkbox-hint">Automatically offer alternative times when requested slot unavailable</span>
              </label>
            </div>
          </section>
        )}

        {/* Video Tab */}
        {activeTab === 'video' && (
          <section className="settings-section">
            <h2>Video Conferencing</h2>

            <div className="form-row">
              <label>Default Meeting Mode</label>
              <div className="toggle-group">
                <button
                  type="button"
                  className={`toggle-btn ${settings.default_meeting_mode === 'video' ? 'active' : ''}`}
                  onClick={() => updateSetting('default_meeting_mode', 'video')}
                >
                  <i className="fas fa-video"></i> Video
                </button>
                <button
                  type="button"
                  className={`toggle-btn ${settings.default_meeting_mode === 'phone' ? 'active' : ''}`}
                  onClick={() => updateSetting('default_meeting_mode', 'phone')}
                >
                  <i className="fas fa-phone"></i> Phone
                </button>
                <button
                  type="button"
                  className={`toggle-btn ${settings.default_meeting_mode === 'in_person' ? 'active' : ''}`}
                  onClick={() => updateSetting('default_meeting_mode', 'in_person')}
                >
                  <i className="fas fa-building"></i> In Person
                </button>
              </div>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.zoom_enabled}
                  onChange={(e) => updateSetting('zoom_enabled', e.target.checked)}
                />
                <i className="fab fa-zoom integration-icon"></i>
                Enable Zoom
                <span className="checkbox-hint">Create Zoom meeting links automatically</span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.google_meet_enabled}
                  onChange={(e) => updateSetting('google_meet_enabled', e.target.checked)}
                />
                <i className="fab fa-google integration-icon"></i>
                Enable Google Meet
                <span className="checkbox-hint">Create Google Meet links automatically</span>
              </label>
            </div>

            <div className="form-row checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={settings.auto_create_meeting_link}
                  onChange={(e) => updateSetting('auto_create_meeting_link', e.target.checked)}
                />
                Auto-Create Meeting Links
                <span className="checkbox-hint">Automatically generate video links when booking</span>
              </label>
            </div>

            {!settings.zoom_enabled && !settings.google_meet_enabled && (
              <div className="inline-warning">
                <i className="fas fa-exclamation-triangle"></i>
                No video conferencing integrations enabled. Video meetings won't have auto-generated links.
              </div>
            )}
          </section>
        )}

        {/* Sticky Save Bar */}
        {hasChanges && (
          <div className="sticky-save-bar">
            <div className="save-bar-content">
              <span>You have unsaved changes</span>
              <div className="save-bar-actions">
                <button
                  type="button"
                  onClick={loadSettings}
                  className="btn-secondary"
                  disabled={isSubmitting}
                >
                  Discard
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        )}
      </form>

      {/* Standalone tabs (outside form - each has own state & API calls) */}
      {activeTab === 'appointment-types' && <AppointmentTypesManager />}
      {activeTab === 'booking-links' && <BookingLinksManager />}
      {activeTab === 'blocked-time' && <BlockedTimeManager />}
      {activeTab === 'analytics' && <SchedulerAnalytics />}
      {activeTab === 'calendar-assignments' && <CalendarManagement />}
    </div>
  );
}

export default SmartSchedulerSettings;
