import React, { useState, useEffect, useCallback } from 'react';
import './SmartScheduler.css';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const SmartScheduler = ({ onClose, leadId, loanId, contactId, preselectedType }) => {
  const [view, setView] = useState('calendar'); // calendar, types, booking-links, settings, tutorial
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data states
  const [appointments, setAppointments] = useState([]);
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [bookingLinks, setBookingLinks] = useState([]);
  const [config, setConfig] = useState(null);

  // Selection states
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [selectedType, setSelectedType] = useState(preselectedType || null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(new Date());

  // Booking form
  const [bookingForm, setBookingForm] = useState({
    title: '',
    attendee_name: '',
    attendee_email: '',
    attendee_phone: '',
    duration_minutes: 30,
    meeting_mode: 'video',
    notes: ''
  });

  // Modal states
  const [showBookingModal, setShowBookingModal] = useState(false);
  const [showNewTypeModal, setShowNewTypeModal] = useState(false);
  const [showNewLinkModal, setShowNewLinkModal] = useState(false);
  const [editingType, setEditingType] = useState(null);

  // Settings sub-tab state
  const [settingsTab, setSettingsTab] = useState('working-hours'); // working-hours, booking, ai
  const [editableConfig, setEditableConfig] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);

  // New link form state
  const [linkForm, setLinkForm] = useState({
    slug: '',
    link_name: '',
    description: '',
    appointment_type_ids: []
  });

  // Appointment type form state
  const [typeForm, setTypeForm] = useState({
    type_name: '',
    type_key: '',
    description: '',
    default_duration_minutes: 30,
    allowed_durations: [15, 30, 45, 60],
    color: '#10b981',
    icon: 'calendar',
    is_public: true,
    requires_confirmation: false,
    buffer_before_minutes: 5,
    buffer_after_minutes: 5
  });

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Fetch initial data
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [configRes, typesRes, appointmentsRes, linksRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/scheduler/config`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/scheduler/appointment-types`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/scheduler/appointments?limit=100`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/scheduler/booking-links`, { headers: getAuthHeaders() })
      ]);

      if (configRes.ok) {
        const configData = await configRes.json();
        const loadedConfig = configData.config || configData.defaults;
        setConfig(loadedConfig);
        // Initialize editable config with current values
        setEditableConfig(JSON.parse(JSON.stringify(loadedConfig)));
      }

      if (typesRes.ok) {
        const typesData = await typesRes.json();
        setAppointmentTypes(typesData.appointment_types || []);
      }

      if (appointmentsRes.ok) {
        const appointmentsData = await appointmentsRes.json();
        setAppointments(appointmentsData.appointments || []);
      }

      if (linksRes.ok) {
        const linksData = await linksRes.json();
        setBookingLinks(linksData.booking_links || []);
      }
    } catch (err) {
      setError('Failed to load scheduler data');
      console.error('Scheduler fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch available slots for selected date range
  const fetchAvailableSlots = async (startDate, endDate, typeId = null) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/available-slots`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          start_date: startDate.toISOString().split('T')[0],
          end_date: endDate.toISOString().split('T')[0],
          duration_minutes: bookingForm.duration_minutes,
          appointment_type_id: typeId,
          lead_id: leadId,
          loan_id: loanId
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAvailableSlots(data.available_slots || []);
      }
    } catch (err) {
      console.error('Failed to fetch available slots:', err);
    }
  };

  // Book appointment
  const handleBookAppointment = async () => {
    if (!selectedSlot) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/appointments`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          appointment_type_id: selectedType?.id,
          title: bookingForm.title || `${selectedType?.type_name || 'Meeting'} with ${bookingForm.attendee_name}`,
          scheduled_start: selectedSlot.start,
          duration_minutes: bookingForm.duration_minutes,
          meeting_mode: bookingForm.meeting_mode,
          attendee_name: bookingForm.attendee_name,
          attendee_email: bookingForm.attendee_email,
          attendee_phone: bookingForm.attendee_phone,
          attendee_notes: bookingForm.notes,
          lead_id: leadId,
          loan_id: loanId,
          contact_id: contactId
        })
      });

      if (response.ok) {
        const data = await response.json();
        setShowBookingModal(false);
        setSelectedSlot(null);
        resetBookingForm();
        fetchData(); // Refresh appointments
        alert(`Appointment booked successfully!`);
      } else {
        const err = await response.json();
        alert(`Failed to book: ${err.detail}`);
      }
    } catch (err) {
      console.error('Booking error:', err);
      alert('Failed to book appointment');
    }
  };

  // Cancel appointment
  const handleCancelAppointment = async (appointmentId, reason = '') => {
    if (!window.confirm('Are you sure you want to cancel this appointment?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/appointments/${appointmentId}/cancel?reason=${encodeURIComponent(reason)}`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
      } else {
        alert('Failed to cancel appointment');
      }
    } catch (err) {
      console.error('Cancel error:', err);
    }
  };

  // Seed default appointment types
  const handleSeedDefaults = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/seed-defaults`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
        alert('Default appointment types created!');
      }
    } catch (err) {
      console.error('Seed error:', err);
    }
  };

  // Create or update appointment type
  const handleSaveAppointmentType = async () => {
    try {
      const isEditing = editingType !== null;
      const url = isEditing
        ? `${API_BASE}/api/v1/scheduler/appointment-types/${editingType.id}`
        : `${API_BASE}/api/v1/scheduler/appointment-types`;

      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          ...typeForm,
          type_key: typeForm.type_key || typeForm.type_name.toLowerCase().replace(/\s+/g, '_')
        })
      });

      if (response.ok) {
        setShowNewTypeModal(false);
        setEditingType(null);
        resetTypeForm();
        fetchData();
        alert(isEditing ? 'Appointment type updated!' : 'Appointment type created!');
      } else {
        const err = await response.json();
        alert(`Failed to save: ${err.detail}`);
      }
    } catch (err) {
      console.error('Save type error:', err);
      alert('Failed to save appointment type');
    }
  };

  // Delete appointment type
  const handleDeleteAppointmentType = async (typeId) => {
    if (!window.confirm('Are you sure you want to delete this appointment type?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types/${typeId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
        alert('Appointment type deleted!');
      } else {
        const err = await response.json();
        alert(`Failed to delete: ${err.detail}`);
      }
    } catch (err) {
      console.error('Delete type error:', err);
    }
  };

  // Open edit modal for appointment type
  const handleEditType = (type) => {
    setEditingType(type);
    setTypeForm({
      type_name: type.type_name || '',
      type_key: type.type_key || '',
      description: type.description || '',
      default_duration_minutes: type.default_duration_minutes || 30,
      allowed_durations: type.allowed_durations || [15, 30, 45, 60],
      color: type.color || '#10b981',
      icon: type.icon || 'calendar',
      is_public: type.is_public !== false,
      requires_confirmation: type.requires_confirmation || false,
      buffer_before_minutes: type.buffer_before_minutes || 5,
      buffer_after_minutes: type.buffer_after_minutes || 5
    });
    setShowNewTypeModal(true);
  };

  // Reset type form
  const resetTypeForm = () => {
    setTypeForm({
      type_name: '',
      type_key: '',
      description: '',
      default_duration_minutes: 30,
      allowed_durations: [15, 30, 45, 60],
      color: '#10b981',
      icon: 'calendar',
      is_public: true,
      requires_confirmation: false,
      buffer_before_minutes: 5,
      buffer_after_minutes: 5
    });
  };

  // Create booking link
  const handleCreateBookingLink = async (linkData) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/booking-links`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(linkData)
      });

      if (response.ok) {
        setShowNewLinkModal(false);
        fetchData();
      } else {
        const err = await response.json();
        alert(`Failed to create link: ${err.detail}`);
      }
    } catch (err) {
      console.error('Create link error:', err);
    }
  };

  const resetBookingForm = () => {
    setBookingForm({
      title: '',
      attendee_name: '',
      attendee_email: '',
      attendee_phone: '',
      duration_minutes: 30,
      meeting_mode: 'video',
      notes: ''
    });
  };

  // Save settings to backend
  const handleSaveSettings = async () => {
    if (!editableConfig) return;

    setSavingSettings(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/config`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(editableConfig)
      });

      if (response.ok) {
        const data = await response.json();
        setConfig(data.config || editableConfig);
        alert('Settings saved successfully!');
      } else {
        const err = await response.json();
        alert(`Failed to save: ${err.detail}`);
      }
    } catch (err) {
      console.error('Save settings error:', err);
      alert('Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  // Update working hours for a specific day
  const updateWorkingHours = (day, field, value) => {
    setEditableConfig(prev => ({
      ...prev,
      working_hours: {
        ...prev.working_hours,
        [day]: {
          ...prev.working_hours[day],
          [field]: value
        }
      }
    }));
  };

  // Update a general config field
  const updateConfigField = (field, value) => {
    setEditableConfig(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Calendar helpers
  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const days = [];

    // Add empty days for alignment
    for (let i = 0; i < firstDay.getDay(); i++) {
      days.push(null);
    }

    for (let i = 1; i <= lastDay.getDate(); i++) {
      days.push(new Date(year, month, i));
    }

    return days;
  };

  const getAppointmentsForDate = (date) => {
    if (!date) return [];
    const dateStr = date.toISOString().split('T')[0];
    return appointments.filter(a => a.scheduled_start.startsWith(dateStr));
  };

  const formatTime = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  };

  const formatDate = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  };

  // Render calendar view
  const renderCalendarView = () => (
    <div className="scheduler-calendar-view">
      <div className="calendar-header">
        <button
          className="calendar-nav-btn"
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))}
        >
          &lt;
        </button>
        <h3>{currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</h3>
        <button
          className="calendar-nav-btn"
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))}
        >
          &gt;
        </button>
      </div>

      <div className="calendar-weekdays">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
          <div key={day} className="weekday">{day}</div>
        ))}
      </div>

      <div className="calendar-days">
        {getDaysInMonth(currentMonth).map((day, idx) => (
          <div
            key={idx}
            className={`calendar-day ${day ? '' : 'empty'} ${day && day.toDateString() === selectedDate?.toDateString() ? 'selected' : ''} ${day && day.toDateString() === new Date().toDateString() ? 'today' : ''}`}
            onClick={() => day && setSelectedDate(day)}
          >
            {day && (
              <>
                <span className="day-number">{day.getDate()}</span>
                {getAppointmentsForDate(day).length > 0 && (
                  <div className="appointment-dots">
                    {getAppointmentsForDate(day).slice(0, 3).map((_, i) => (
                      <span key={i} className="dot"></span>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {selectedDate && (
        <div className="day-appointments">
          <h4>{selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</h4>

          {getAppointmentsForDate(selectedDate).length === 0 ? (
            <p className="no-appointments">No appointments scheduled</p>
          ) : (
            <div className="appointments-list">
              {getAppointmentsForDate(selectedDate).map(appt => (
                <div key={appt.id} className={`appointment-card status-${appt.status}`}>
                  <div className="appointment-time">{formatTime(appt.scheduled_start)}</div>
                  <div className="appointment-details">
                    <div className="appointment-title">{appt.title}</div>
                    <div className="appointment-meta">
                      <span className="meeting-mode">{appt.meeting_mode}</span>
                      <span className="duration">{appt.duration_minutes}min</span>
                      {appt.attendee_name && <span className="attendee">{appt.attendee_name}</span>}
                    </div>
                  </div>
                  <div className="appointment-actions">
                    {appt.video_link && (
                      <a href={appt.video_link} target="_blank" rel="noopener noreferrer" className="join-btn">Join</a>
                    )}
                    {appt.status === 'booked' && (
                      <button
                        className="cancel-btn"
                        onClick={() => handleCancelAppointment(appt.id)}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            className="new-appointment-btn"
            onClick={() => {
              fetchAvailableSlots(selectedDate, selectedDate);
              setShowBookingModal(true);
            }}
          >
            + New Appointment
          </button>
        </div>
      )}
    </div>
  );

  // Render appointment types view
  const renderTypesView = () => (
    <div className="scheduler-types-view">
      <div className="types-header">
        <h3>Appointment Types</h3>
        <div className="types-actions">
          <button className="seed-btn" onClick={handleSeedDefaults}>
            Seed Defaults
          </button>
          <button className="add-type-btn" onClick={() => {
            setEditingType(null);
            resetTypeForm();
            setShowNewTypeModal(true);
          }}>
            + New Type
          </button>
        </div>
      </div>

      {appointmentTypes.length === 0 ? (
        <div className="empty-state">
          <p>No appointment types configured</p>
          <button onClick={handleSeedDefaults}>Create Default Types</button>
        </div>
      ) : (
        <div className="types-grid">
          {appointmentTypes.map(type => (
            <div
              key={type.id || type.type_key}
              className="type-card clickable"
              style={{ borderLeftColor: type.color }}
              onClick={() => handleEditType(type)}
            >
              <div className="type-header">
                <h4>{type.type_name}</h4>
              </div>
              <p className="type-description">{type.description}</p>
              <div className="type-meta">
                <span>{type.default_duration_minutes} min</span>
                <span className={`public-badge ${type.is_public ? 'public' : 'private'}`}>
                  {type.is_public ? 'Public' : 'Private'}
                </span>
              </div>
              <div className="type-durations">
                {type.allowed_durations?.map(d => (
                  <span key={d} className="duration-chip">{d}m</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render booking links view
  const renderBookingLinksView = () => (
    <div className="scheduler-links-view">
      <div className="links-header">
        <h3>Booking Links</h3>
        <button className="add-link-btn" onClick={() => setShowNewLinkModal(true)}>
          + New Link
        </button>
      </div>

      {bookingLinks.length === 0 ? (
        <div className="empty-state">
          <p>No booking links created</p>
          <p className="hint">Create shareable links for clients to book appointments</p>
        </div>
      ) : (
        <div className="links-list">
          {bookingLinks.map(link => (
            <div key={link.id} className="link-card">
              <div className="link-info">
                <h4>{link.link_name}</h4>
                <p className="link-url">/book/{link.slug}</p>
                {link.description && <p className="link-description">{link.description}</p>}
              </div>
              <div className="link-stats">
                <span className="stat">
                  <span className="stat-value">{link.view_count}</span>
                  <span className="stat-label">Views</span>
                </span>
                <span className="stat">
                  <span className="stat-value">{link.booking_count}</span>
                  <span className="stat-label">Bookings</span>
                </span>
              </div>
              <div className="link-actions">
                <button
                  className="copy-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/book/${link.slug}`);
                    alert('Link copied!');
                  }}
                >
                  Copy Link
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Generate time options for select dropdowns (5:00 AM to 10:00 PM)
  const timeOptions = [];
  for (let h = 5; h <= 22; h++) {
    for (let m = 0; m < 60; m += 30) {
      const hour = h.toString().padStart(2, '0');
      const minute = m.toString().padStart(2, '0');
      const time24 = `${hour}:${minute}`;
      const hour12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const label = `${hour12}:${minute.padStart(2, '0')} ${ampm}`;
      timeOptions.push({ value: time24, label });
    }
  }

  // Render working hours tab content
  const renderWorkingHoursTab = () => {
    const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const dayLabels = {
      sunday: 'Sunday',
      monday: 'Monday',
      tuesday: 'Tuesday',
      wednesday: 'Wednesday',
      thursday: 'Thursday',
      friday: 'Friday',
      saturday: 'Saturday'
    };

    return (
      <div className="settings-tab-content">
        <p className="settings-description">Configure which days and hours you're available for appointments.</p>
        <div className="working-hours-editor">
          {days.map(day => {
            const hours = editableConfig?.working_hours?.[day] || { enabled: false, start: '09:00', end: '17:00' };
            return (
              <div key={day} className={`day-row ${hours.enabled ? 'enabled' : 'disabled'}`}>
                <div className="day-toggle">
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={hours.enabled}
                      onChange={(e) => updateWorkingHours(day, 'enabled', e.target.checked)}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  <span className="day-label">{dayLabels[day]}</span>
                </div>
                {hours.enabled ? (
                  <div className="time-range">
                    <select
                      value={hours.start}
                      onChange={(e) => updateWorkingHours(day, 'start', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <span className="time-separator">to</span>
                    <select
                      value={hours.end}
                      onChange={(e) => updateWorkingHours(day, 'end', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="time-range-off">
                    <span>Unavailable</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Render booking settings tab content
  const renderBookingTab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure default booking behavior and limits.</p>
      <div className="booking-settings-form">
        <div className="form-group">
          <label>Default Duration</label>
          <select
            value={editableConfig?.default_duration_minutes || 30}
            onChange={(e) => updateConfigField('default_duration_minutes', parseInt(e.target.value))}
          >
            <option value={15}>15 minutes</option>
            <option value={20}>20 minutes</option>
            <option value={30}>30 minutes</option>
            <option value={45}>45 minutes</option>
            <option value={60}>60 minutes</option>
            <option value={90}>90 minutes</option>
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Buffer Before (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_before_minutes || 0}
              onChange={(e) => updateConfigField('buffer_before_minutes', parseInt(e.target.value) || 0)}
              min="0"
              max="60"
            />
            <span className="help-text">Time before appointments for preparation</span>
          </div>

          <div className="form-group">
            <label>Buffer After (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_after_minutes || 0}
              onChange={(e) => updateConfigField('buffer_after_minutes', parseInt(e.target.value) || 0)}
              min="0"
              max="60"
            />
            <span className="help-text">Time after appointments for follow-up</span>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Minimum Notice (hours)</label>
            <input
              type="number"
              value={editableConfig?.min_notice_hours || 1}
              onChange={(e) => updateConfigField('min_notice_hours', parseInt(e.target.value) || 1)}
              min="1"
              max="168"
            />
            <span className="help-text">How far in advance clients must book</span>
          </div>

          <div className="form-group">
            <label>Max Advance Booking (days)</label>
            <input
              type="number"
              value={editableConfig?.max_advance_days || 30}
              onChange={(e) => updateConfigField('max_advance_days', parseInt(e.target.value) || 30)}
              min="1"
              max="365"
            />
            <span className="help-text">How far in the future clients can book</span>
          </div>
        </div>

        <div className="form-group">
          <label>Max Meetings Per Day</label>
          <input
            type="number"
            value={editableConfig?.max_meetings_per_day || 8}
            onChange={(e) => updateConfigField('max_meetings_per_day', parseInt(e.target.value) || 8)}
            min="1"
            max="20"
          />
          <span className="help-text">Maximum number of appointments per day</span>
        </div>
      </div>
    </div>
  );

  // Render AI settings tab content
  const renderAITab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure AI-powered scheduling features.</p>
      <div className="ai-settings-form">
        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.ai_scheduling_enabled || false}
                onChange={(e) => updateConfigField('ai_scheduling_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">AI Smart Scheduling</span>
              <span className="toggle-description">Let AI suggest optimal meeting times based on your patterns and client preferences</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.auto_reschedule_enabled || false}
                onChange={(e) => updateConfigField('auto_reschedule_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Auto-Reschedule Suggestions</span>
              <span className="toggle-description">Automatically suggest better times when conflicts arise</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.smart_reminders_enabled || false}
                onChange={(e) => updateConfigField('smart_reminders_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Smart Reminders</span>
              <span className="toggle-description">AI-optimized reminder timing based on client engagement</span>
            </div>
          </label>
        </div>
      </div>
    </div>
  );

  // Render settings view with sub-tabs
  const renderSettingsView = () => (
    <div className="scheduler-settings-view">
      {editableConfig ? (
        <>
          <div className="settings-sub-tabs">
            <button
              className={`sub-tab ${settingsTab === 'working-hours' ? 'active' : ''}`}
              onClick={() => setSettingsTab('working-hours')}
            >
              Working Hours
            </button>
            <button
              className={`sub-tab ${settingsTab === 'booking' ? 'active' : ''}`}
              onClick={() => setSettingsTab('booking')}
            >
              Booking Settings
            </button>
            <button
              className={`sub-tab ${settingsTab === 'ai' ? 'active' : ''}`}
              onClick={() => setSettingsTab('ai')}
            >
              AI Settings
            </button>
          </div>

          {settingsTab === 'working-hours' && renderWorkingHoursTab()}
          {settingsTab === 'booking' && renderBookingTab()}
          {settingsTab === 'ai' && renderAITab()}

          <div className="settings-actions">
            <button
              className="save-settings-btn"
              onClick={handleSaveSettings}
              disabled={savingSettings}
            >
              {savingSettings ? 'Saving...' : 'Save Settings'}
            </button>
            <button
              className="reset-settings-btn"
              onClick={() => setEditableConfig(JSON.parse(JSON.stringify(config)))}
              disabled={savingSettings}
            >
              Reset Changes
            </button>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <p>No configuration found</p>
          <button onClick={handleSeedDefaults}>Initialize Scheduler</button>
        </div>
      )}
    </div>
  );

  // Render booking modal
  const renderBookingModal = () => (
    <div className="scheduler-modal-overlay" onClick={() => setShowBookingModal(false)}>
      <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Book Appointment</h3>
          <button className="close-btn" onClick={() => setShowBookingModal(false)}>&times;</button>
        </div>

        <div className="modal-content">
          {/* Appointment Type Selection */}
          {!selectedType && (
            <div className="type-selection">
              <h4>Select Appointment Type</h4>
              <div className="type-options">
                {appointmentTypes.map(type => (
                  <button
                    key={type.id || type.type_key}
                    className="type-option"
                    style={{ borderColor: type.color }}
                    onClick={() => setSelectedType(type)}
                  >
                    <span className="type-name">{type.type_name}</span>
                    <span className="type-duration">{type.default_duration_minutes}min</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Slot Selection */}
          {selectedType && !selectedSlot && (
            <div className="slot-selection">
              <h4>Select Time Slot</h4>
              <div className="selected-type-info">
                <span>{selectedType.type_name}</span>
                <button className="change-type" onClick={() => setSelectedType(null)}>Change</button>
              </div>

              {availableSlots.length === 0 ? (
                <p className="no-slots">No available slots for this date</p>
              ) : (
                <div className="slots-grid">
                  {availableSlots.filter(s => s.date === selectedDate?.toISOString().split('T')[0]).map((slot, idx) => (
                    <button
                      key={idx}
                      className="slot-btn"
                      onClick={() => setSelectedSlot(slot)}
                    >
                      {formatTime(slot.start)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Booking Form */}
          {selectedSlot && (
            <div className="booking-form">
              <h4>Appointment Details</h4>
              <div className="slot-summary">
                <span className="slot-date">{formatDate(selectedSlot.start)}</span>
                <span className="slot-time">{formatTime(selectedSlot.start)}</span>
                <span className="slot-type">{selectedType?.type_name}</span>
                <button className="change-slot" onClick={() => setSelectedSlot(null)}>Change</button>
              </div>

              <div className="form-group">
                <label>Attendee Name *</label>
                <input
                  type="text"
                  value={bookingForm.attendee_name}
                  onChange={e => setBookingForm({ ...bookingForm, attendee_name: e.target.value })}
                  placeholder="Enter name"
                  required
                />
              </div>

              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  value={bookingForm.attendee_email}
                  onChange={e => setBookingForm({ ...bookingForm, attendee_email: e.target.value })}
                  placeholder="email@example.com"
                  required
                />
              </div>

              <div className="form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  value={bookingForm.attendee_phone}
                  onChange={e => setBookingForm({ ...bookingForm, attendee_phone: e.target.value })}
                  placeholder="(555) 123-4567"
                />
              </div>

              <div className="form-group">
                <label>Meeting Mode</label>
                <select
                  value={bookingForm.meeting_mode}
                  onChange={e => setBookingForm({ ...bookingForm, meeting_mode: e.target.value })}
                >
                  <option value="video">Video Call</option>
                  <option value="phone">Phone Call</option>
                  <option value="in_person">In Person</option>
                </select>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={bookingForm.notes}
                  onChange={e => setBookingForm({ ...bookingForm, notes: e.target.value })}
                  placeholder="Any additional information..."
                  rows={3}
                />
              </div>
            </div>
          )}
        </div>

        {selectedSlot && (
          <div className="modal-footer">
            <button className="cancel-btn" onClick={() => setShowBookingModal(false)}>Cancel</button>
            <button
              className="confirm-btn"
              onClick={handleBookAppointment}
              disabled={!bookingForm.attendee_name || !bookingForm.attendee_email}
            >
              Book Appointment
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // Render new booking link modal
  const renderNewLinkModal = () => {
    return (
      <div className="scheduler-modal-overlay" onClick={() => setShowNewLinkModal(false)}>
        <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Create Booking Link</h3>
            <button className="close-btn" onClick={() => setShowNewLinkModal(false)}>&times;</button>
          </div>

          <div className="modal-content">
            <div className="form-group">
              <label>Link Name *</label>
              <input
                type="text"
                value={linkForm.link_name}
                onChange={e => setLinkForm({ ...linkForm, link_name: e.target.value })}
                placeholder="My Booking Link"
              />
            </div>

            <div className="form-group">
              <label>URL Slug *</label>
              <div className="slug-input">
                <span className="slug-prefix">/book/</span>
                <input
                  type="text"
                  value={linkForm.slug}
                  onChange={e => setLinkForm({ ...linkForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                  placeholder="my-link"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={linkForm.description}
                onChange={e => setLinkForm({ ...linkForm, description: e.target.value })}
                placeholder="Optional description..."
                rows={2}
              />
            </div>

            <div className="form-group">
              <label>Appointment Types</label>
              <div className="type-checkboxes">
                {appointmentTypes.map(type => (
                  <label key={type.id || type.type_key} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={linkForm.appointment_type_ids.includes(type.id)}
                      onChange={e => {
                        if (e.target.checked) {
                          setLinkForm({ ...linkForm, appointment_type_ids: [...linkForm.appointment_type_ids, type.id] });
                        } else {
                          setLinkForm({ ...linkForm, appointment_type_ids: linkForm.appointment_type_ids.filter(id => id !== type.id) });
                        }
                      }}
                    />
                    {type.type_name}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button className="cancel-btn" onClick={() => setShowNewLinkModal(false)}>Cancel</button>
            <button
              className="confirm-btn"
              onClick={() => handleCreateBookingLink(linkForm)}
              disabled={!linkForm.slug || !linkForm.link_name}
            >
              Create Link
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Render appointment type modal
  const renderTypeModal = () => {
    const iconOptions = [
      { value: 'phone', label: 'Phone' },
      { value: 'document', label: 'Document' },
      { value: 'clipboard', label: 'Clipboard' },
      { value: 'folder', label: 'Folder' },
      { value: 'lock', label: 'Lock' },
      { value: 'home', label: 'Home' },
      { value: 'users', label: 'Users' },
      { value: 'calendar', label: 'Calendar' }
    ];

    const colorOptions = [
      '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b',
      '#ef4444', '#ec4899', '#06b6d4', '#84cc16'
    ];

    const durationOptions = [15, 20, 30, 45, 60, 90, 120];

    const toggleDuration = (duration) => {
      const current = typeForm.allowed_durations || [];
      if (current.includes(duration)) {
        setTypeForm({ ...typeForm, allowed_durations: current.filter(d => d !== duration) });
      } else {
        setTypeForm({ ...typeForm, allowed_durations: [...current, duration].sort((a, b) => a - b) });
      }
    };

    return (
      <div className="scheduler-modal-overlay" onClick={() => {
        setShowNewTypeModal(false);
        setEditingType(null);
      }}>
        <div className="scheduler-modal type-modal" onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{editingType ? 'Edit Appointment Type' : 'New Appointment Type'}</h3>
            <button className="close-btn" onClick={() => {
              setShowNewTypeModal(false);
              setEditingType(null);
            }}>&times;</button>
          </div>

          <div className="modal-content">
            <div className="form-group">
              <label>Type Name *</label>
              <input
                type="text"
                value={typeForm.type_name}
                onChange={e => setTypeForm({ ...typeForm, type_name: e.target.value })}
                placeholder="e.g., Discovery Call"
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={typeForm.description}
                onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
                placeholder="Brief description of this appointment type..."
                rows={2}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Default Duration</label>
                <select
                  value={typeForm.default_duration_minutes}
                  onChange={e => setTypeForm({ ...typeForm, default_duration_minutes: parseInt(e.target.value) })}
                >
                  {durationOptions.map(d => (
                    <option key={d} value={d}>{d} minutes</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Icon</label>
                <select
                  value={typeForm.icon}
                  onChange={e => setTypeForm({ ...typeForm, icon: e.target.value })}
                >
                  {iconOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>Allowed Durations</label>
              <div className="duration-toggles">
                {durationOptions.map(d => (
                  <button
                    key={d}
                    type="button"
                    className={`duration-toggle ${(typeForm.allowed_durations || []).includes(d) ? 'active' : ''}`}
                    onClick={() => toggleDuration(d)}
                  >
                    {d}m
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Color</label>
              <div className="color-options">
                {colorOptions.map(color => (
                  <button
                    key={color}
                    type="button"
                    className={`color-option ${typeForm.color === color ? 'selected' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => setTypeForm({ ...typeForm, color })}
                  />
                ))}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Buffer Before (min)</label>
                <input
                  type="number"
                  value={typeForm.buffer_before_minutes}
                  onChange={e => setTypeForm({ ...typeForm, buffer_before_minutes: parseInt(e.target.value) || 0 })}
                  min="0"
                  max="60"
                />
              </div>

              <div className="form-group">
                <label>Buffer After (min)</label>
                <input
                  type="number"
                  value={typeForm.buffer_after_minutes}
                  onChange={e => setTypeForm({ ...typeForm, buffer_after_minutes: parseInt(e.target.value) || 0 })}
                  min="0"
                  max="60"
                />
              </div>
            </div>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={typeForm.is_public}
                  onChange={e => setTypeForm({ ...typeForm, is_public: e.target.checked })}
                />
                Public (visible on booking links)
              </label>
            </div>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={typeForm.requires_confirmation}
                  onChange={e => setTypeForm({ ...typeForm, requires_confirmation: e.target.checked })}
                />
                Requires confirmation before booking
              </label>
            </div>
          </div>

          <div className="modal-footer">
            {editingType && (
              <button
                className="delete-btn"
                onClick={() => {
                  handleDeleteAppointmentType(editingType.id);
                  setShowNewTypeModal(false);
                  setEditingType(null);
                }}
              >
                Delete
              </button>
            )}
            <div className="footer-right">
              <button className="cancel-btn" onClick={() => {
                setShowNewTypeModal(false);
                setEditingType(null);
              }}>Cancel</button>
              <button
                className="confirm-btn"
                onClick={handleSaveAppointmentType}
                disabled={!typeForm.type_name}
              >
                {editingType ? 'Save Changes' : 'Create Type'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Render Tutorial View
  const renderTutorialView = () => (
    <div className="scheduler-tutorial-view">
      <div className="tutorial-header">
        <h3>Smart Scheduler Tutorial</h3>
        <p className="tutorial-intro">Learn how to maximize productivity with our AI-powered scheduling system</p>
      </div>

      <div className="tutorial-sections">
        {/* Quick Start */}
        <div className="tutorial-section">
          <div className="section-icon">🚀</div>
          <h4>Quick Start Guide</h4>
          <div className="section-content">
            <ol>
              <li><strong>Create Appointment Types:</strong> Go to "Appointment Types" tab and click "Seed Defaults" to create standard mortgage appointment types (Discovery Call, Pre-Approval Review, Document Collection, etc.)</li>
              <li><strong>Set Your Hours:</strong> Navigate to "Settings" tab and configure your working hours for each day of the week</li>
              <li><strong>Book Appointments:</strong> Click on any date in the Calendar view and select "+ New Appointment" to schedule a meeting</li>
              <li><strong>Share Booking Links:</strong> Create public booking links in the "Booking Links" tab that clients can use to self-schedule</li>
            </ol>
          </div>
        </div>

        {/* Calendar Features */}
        <div className="tutorial-section">
          <div className="section-icon">📅</div>
          <h4>Calendar Features</h4>
          <div className="section-content">
            <ul>
              <li><strong>Month Navigation:</strong> Use the arrow buttons to move between months</li>
              <li><strong>Day Selection:</strong> Click on any date to see appointments for that day</li>
              <li><strong>Appointment Dots:</strong> Blue dots indicate days with scheduled appointments</li>
              <li><strong>Today Indicator:</strong> The current date is highlighted with a red circle</li>
              <li><strong>Quick Actions:</strong> Join video calls directly or cancel appointments from the day view</li>
            </ul>
          </div>
        </div>

        {/* Appointment Types */}
        <div className="tutorial-section">
          <div className="section-icon">📋</div>
          <h4>Appointment Types</h4>
          <div className="section-content">
            <p>Customize appointment types for different meeting purposes:</p>
            <ul>
              <li><strong>Discovery Call:</strong> Initial consultation with new leads (15-30 min)</li>
              <li><strong>Pre-Approval Review:</strong> Review pre-approval documents and terms (30-45 min)</li>
              <li><strong>Document Collection:</strong> Gather required mortgage documents (30-60 min)</li>
              <li><strong>Rate Lock Discussion:</strong> Review market conditions and lock options (20-30 min)</li>
              <li><strong>Closing Prep:</strong> Final walkthrough before closing (45-60 min)</li>
            </ul>
            <p className="tip">Tip: Click on any appointment type card to edit its settings, durations, and colors.</p>
          </div>
        </div>

        {/* Booking Links */}
        <div className="tutorial-section">
          <div className="section-icon">🔗</div>
          <h4>Booking Links</h4>
          <div className="section-content">
            <p>Create shareable links for clients to book directly:</p>
            <ul>
              <li><strong>Custom URL Slugs:</strong> Create memorable URLs like /book/john-smith</li>
              <li><strong>Type Filtering:</strong> Limit which appointment types are available on each link</li>
              <li><strong>Analytics:</strong> Track views and bookings for each link</li>
              <li><strong>Easy Sharing:</strong> Copy links with one click to share via email or text</li>
            </ul>
          </div>
        </div>

        {/* AI Features */}
        <div className="tutorial-section highlight">
          <div className="section-icon">🤖</div>
          <h4>AI-Powered Features</h4>
          <div className="section-content">
            <p>The Smart Scheduler includes advanced AI capabilities:</p>
            <ul>
              <li><strong>Smart Scheduling:</strong> AI suggests optimal meeting times based on your patterns and client preferences</li>
              <li><strong>Auto-Reschedule:</strong> Automatically suggests better times when conflicts arise</li>
              <li><strong>Smart Reminders:</strong> AI-optimized reminder timing based on client engagement history</li>
              <li><strong>No-Show Detection:</strong> Automatically detects missed appointments and initiates recovery workflows</li>
              <li><strong>Load Balancing:</strong> Distributes appointments evenly across team members based on capacity</li>
            </ul>
            <p className="tip">Enable AI features in Settings → AI Settings tab</p>
          </div>
        </div>

        {/* Resource Management */}
        <div className="tutorial-section">
          <div className="section-icon">👥</div>
          <h4>Resource Management (Teams)</h4>
          <div className="section-content">
            <p>For organizations with multiple loan officers:</p>
            <ul>
              <li><strong>Staff Profiles:</strong> Configure skills, languages, and licensed states for each team member</li>
              <li><strong>Capacity Management:</strong> Set daily appointment limits per person</li>
              <li><strong>Smart Routing:</strong> Automatically route appointments to available team members</li>
              <li><strong>SLA Monitoring:</strong> Track team utilization and response times</li>
            </ul>
          </div>
        </div>

        {/* Soft Holds */}
        <div className="tutorial-section">
          <div className="section-icon">⏳</div>
          <h4>Soft Hold System</h4>
          <div className="section-content">
            <p>Prevent double-booking during AI conversations:</p>
            <ul>
              <li><strong>Temporary Holds:</strong> When AI is discussing appointment times with a client, slots are temporarily reserved</li>
              <li><strong>Auto-Release:</strong> Holds automatically expire after 5 minutes if not confirmed</li>
              <li><strong>Convert to Booking:</strong> Once the client confirms, the hold converts to a real appointment</li>
            </ul>
          </div>
        </div>

        {/* Group Sessions */}
        <div className="tutorial-section">
          <div className="section-icon">🎓</div>
          <h4>Group Sessions & Workshops</h4>
          <div className="section-content">
            <p>Host educational sessions for multiple attendees:</p>
            <ul>
              <li><strong>First-Time Homebuyer Workshops:</strong> Educational seminars with capacity limits</li>
              <li><strong>Rate Watch Webinars:</strong> Group sessions on market conditions</li>
              <li><strong>Waitlist Management:</strong> Automatically manage overflow registrations</li>
              <li><strong>Virtual/In-Person:</strong> Support for both meeting formats</li>
            </ul>
          </div>
        </div>

        {/* Campaign Tracking */}
        <div className="tutorial-section">
          <div className="section-icon">📊</div>
          <h4>Campaign Attribution</h4>
          <div className="section-content">
            <p>Track the effectiveness of your outreach:</p>
            <ul>
              <li><strong>Voicemail Drops:</strong> Track appointments booked from voicemail campaigns</li>
              <li><strong>SMS Campaigns:</strong> Measure reply-to-booking conversion rates</li>
              <li><strong>Full Funnel:</strong> Track from initial contact through to funded loan</li>
              <li><strong>ROI Analysis:</strong> Understand which channels drive the most closings</li>
            </ul>
          </div>
        </div>

        {/* Analytics */}
        <div className="tutorial-section">
          <div className="section-icon">📈</div>
          <h4>Analytics & Insights</h4>
          <div className="section-content">
            <p>Data-driven scheduling optimization:</p>
            <ul>
              <li><strong>Show Rate Tracking:</strong> Monitor appointment attendance rates</li>
              <li><strong>Best Times Analysis:</strong> Discover when clients are most likely to show up</li>
              <li><strong>Channel Performance:</strong> Compare booking sources (web, phone, AI)</li>
              <li><strong>Day/Hour Heatmaps:</strong> Visualize your busiest times</li>
            </ul>
          </div>
        </div>

        {/* Best Practices */}
        <div className="tutorial-section best-practices">
          <div className="section-icon">💡</div>
          <h4>Best Practices</h4>
          <div className="section-content">
            <ul>
              <li><strong>Buffer Time:</strong> Add 5-15 minute buffers between appointments for notes and preparation</li>
              <li><strong>Minimum Notice:</strong> Require at least 2-4 hours notice for new bookings to prevent last-minute chaos</li>
              <li><strong>Confirmation Emails:</strong> Enable automatic confirmations to reduce no-shows</li>
              <li><strong>Video Links:</strong> Use integrated video meeting links for seamless virtual appointments</li>
              <li><strong>Regular Review:</strong> Check your analytics weekly to optimize your schedule</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="tutorial-footer">
        <p>Need more help? Contact support or visit our documentation.</p>
        <div className="tutorial-actions">
          <button className="start-btn" onClick={() => setView('calendar')}>
            Go to Calendar
          </button>
          <button className="setup-btn" onClick={() => setView('settings')}>
            Configure Settings
          </button>
        </div>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="smart-scheduler loading">
        <div className="loader"></div>
        <p>Loading scheduler...</p>
      </div>
    );
  }

  return (
    <div className="smart-scheduler">
      <div className="scheduler-header">
        <h2>Smart Scheduler</h2>
        <div className="scheduler-tabs">
          <button
            className={`tab ${view === 'calendar' ? 'active' : ''}`}
            onClick={() => setView('calendar')}
          >
            Calendar
          </button>
          <button
            className={`tab ${view === 'types' ? 'active' : ''}`}
            onClick={() => setView('types')}
          >
            Appointment Types
          </button>
          <button
            className={`tab ${view === 'booking-links' ? 'active' : ''}`}
            onClick={() => setView('booking-links')}
          >
            Booking Links
          </button>
          <button
            className={`tab ${view === 'settings' ? 'active' : ''}`}
            onClick={() => setView('settings')}
          >
            Settings
          </button>
          <button
            className={`tab tutorial-tab ${view === 'tutorial' ? 'active' : ''}`}
            onClick={() => setView('tutorial')}
          >
            Tutorial
          </button>
        </div>
        {onClose && (
          <button className="close-scheduler" onClick={onClose}>&times;</button>
        )}
      </div>

      {error && (
        <div className="scheduler-error">
          <p>{error}</p>
          <button onClick={fetchData}>Retry</button>
        </div>
      )}

      <div className="scheduler-content">
        {view === 'calendar' && renderCalendarView()}
        {view === 'types' && renderTypesView()}
        {view === 'booking-links' && renderBookingLinksView()}
        {view === 'settings' && renderSettingsView()}
        {view === 'tutorial' && renderTutorialView()}
      </div>

      {showBookingModal && renderBookingModal()}
      {showNewLinkModal && renderNewLinkModal()}
      {showNewTypeModal && renderTypeModal()}
    </div>
  );
};

export default SmartScheduler;
