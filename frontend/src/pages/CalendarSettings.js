/**
 * Perennia AI - Calendar Settings
 *
 * Comprehensive calendar settings page with six tabs:
 *   1. Availability  - Business hours per day, lunch break, buffer time, booking window
 *   2. Appointment Types - List with edit/delete/reorder, add new
 *   3. Notifications - Email/SMS reminder toggles (24h/2h/15min), quiet hours
 *   4. Booking Page  - Preview, branding (logo/colors/tagline), booking link + copy, QR code
 *   5. Integrations  - Google/Outlook connect/disconnect, sync status
 *   6. Team          - LO list, assignment strategy, capacity (managers only)
 *
 * Follows the SmartSchedulerSettings error-handling and layout patterns.
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarSettingsAPI, API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import './CalendarSettings.css';

// ============================================================================
// Constants
// ============================================================================

const DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = {
  monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday',
  thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday',
};

const TAB_DEFINITIONS = [
  { id: 'availability', label: 'Availability', icon: 'fa-clock' },
  { id: 'appointment-types', label: 'Appointment Types', icon: 'fa-list-alt' },
  { id: 'notifications', label: 'Notifications', icon: 'fa-bell' },
  { id: 'booking-page', label: 'Booking Page', icon: 'fa-palette' },
  { id: 'integrations', label: 'Integrations', icon: 'fa-plug' },
  { id: 'team', label: 'Team', icon: 'fa-users' },
];

const ASSIGNMENT_STRATEGIES = [
  { value: 'round_robin', label: 'Round Robin', description: 'Distribute appointments evenly across team members' },
  { value: 'priority', label: 'Priority', description: 'Assign to highest-priority LO first' },
  { value: 'load_balanced', label: 'Load Balanced', description: 'Assign to LO with fewest upcoming appointments' },
  { value: 'manual', label: 'Manual', description: 'Manually assign each appointment' },
];

const DEFAULT_COLORS = ['#218D8D', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

// ============================================================================
// Helper: API request wrapper
// ============================================================================

function CalendarSettings() {
  const navigate = useNavigate();

  // ========== Shared state ==========
  const [activeTab, setActiveTab] = useState('availability');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // ========== Availability state ==========
  const [availability, setAvailability] = useState({
    timezone: 'America/Chicago',
    business_hours: {
      monday: { start: '09:00', end: '17:00', enabled: true },
      tuesday: { start: '09:00', end: '17:00', enabled: true },
      wednesday: { start: '09:00', end: '17:00', enabled: true },
      thursday: { start: '09:00', end: '17:00', enabled: true },
      friday: { start: '09:00', end: '17:00', enabled: true },
      saturday: { start: '10:00', end: '14:00', enabled: false },
      sunday: { start: '10:00', end: '14:00', enabled: false },
    },
    lunch_break: { enabled: true, start: '12:00', end: '13:00' },
    buffer_minutes: 5,
    min_booking_notice_hours: 2,
    max_advance_booking_days: 60,
  });

  // ========== Appointment Types state ==========
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [editingType, setEditingType] = useState(null);
  const [showNewTypeForm, setShowNewTypeForm] = useState(false);
  const [newType, setNewType] = useState({
    type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true,
  });

  // ========== Notification state ==========
  const [notifications, setNotifications] = useState({
    email_reminder_24h: true,
    email_reminder_2h: true,
    email_reminder_15m: false,
    sms_reminder_24h: false,
    sms_reminder_2h: true,
    sms_reminder_15m: false,
    quiet_hours_enabled: false,
    quiet_hours_start: '21:00',
    quiet_hours_end: '08:00',
    notify_on_booking: true,
    notify_on_cancellation: true,
    notify_on_reschedule: true,
  });

  // ========== Booking Page state ==========
  const [bookingPage, setBookingPage] = useState({
    branding: {
      logo_url: null, primary_color: '#218D8D', secondary_color: '#e6f5f5',
      tagline: '', welcome_message: 'Schedule a time to meet with us', show_branding: true,
    },
    booking_links: [],
  });
  const [copiedLink, setCopiedLink] = useState(null);

  // ========== Integration state ==========
  const [integrations, setIntegrations] = useState({ google: { connected: false }, outlook: { connected: false } });

  // ========== Team state ==========
  const [team, setTeam] = useState({ assignment_strategy: 'round_robin', members: [], total_members: 0 });
  const [isManager, setIsManager] = useState(false);

  // ============================================================================
  // Data Loading
  // ============================================================================

  useEffect(() => {
    loadTabData(activeTab);
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadTabData = async (tab) => {
    setLoading(true);
    try {
      switch (tab) {
        case 'availability': {
          const res = await calendarSettingsAPI.getAvailability();
          if (res?.data) {
            setAvailability(prev => ({ ...prev, ...res.data }));
          }
          break;
        }
        case 'appointment-types': {
          const res = await calendarSettingsAPI.getAppointmentTypes();
          if (res?.data?.appointment_types) {
            setAppointmentTypes(res.data.appointment_types);
          }
          break;
        }
        case 'notifications': {
          const res = await calendarSettingsAPI.getNotifications();
          if (res?.data) {
            setNotifications(prev => ({ ...prev, ...res.data }));
          }
          break;
        }
        case 'booking-page': {
          const res = await calendarSettingsAPI.getBookingPage();
          if (res?.data) {
            setBookingPage(prev => ({
              branding: { ...prev.branding, ...(res.data.branding || {}) },
              booking_links: res.data.booking_links || [],
            }));
          }
          break;
        }
        case 'integrations': {
          const res = await calendarSettingsAPI.getIntegrations();
          if (res?.data) {
            setIntegrations(res.data);
          }
          break;
        }
        case 'team': {
          try {
            const res = await calendarSettingsAPI.getTeam();
            if (res?.data) {
              setTeam(res.data);
              setIsManager(true);
            }
          } catch (err) {
            if (err.response?.status === 403) {
              setIsManager(false);
            } else {
              throw err;
            }
          }
          break;
        }
        default:
          break;
      }
    } catch (err) {
      console.error(`Failed to load ${tab}:`, err);
      if (err.response?.status !== 403) {
        toast.error(`Failed to load ${tab} settings`);
      }
    } finally {
      setLoading(false);
      setHasChanges(false);
    }
  };

  // ============================================================================
  // Save handlers
  // ============================================================================

  const handleSaveAvailability = async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateAvailability(availability);
      toast.success('Availability settings saved');
      setHasChanges(false);
    } catch (err) {
      toast.error('Failed to save availability settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotifications = async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateNotifications(notifications);
      toast.success('Notification preferences saved');
      setHasChanges(false);
    } catch (err) {
      toast.error('Failed to save notification preferences');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveBookingPage = async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateBookingPage(bookingPage.branding);
      toast.success('Booking page settings saved');
      setHasChanges(false);
    } catch (err) {
      toast.error('Failed to save booking page settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTeam = async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateTeam({
        assignment_strategy: team.assignment_strategy,
        members: team.members?.map(m => ({
          user_id: m.user_id,
          max_daily_appointments: m.max_daily_appointments,
          is_accepting_appointments: m.is_accepting_appointments,
        })),
      });
      toast.success('Team settings saved');
      setHasChanges(false);
    } catch (err) {
      toast.error('Failed to save team settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    switch (activeTab) {
      case 'availability': return handleSaveAvailability();
      case 'notifications': return handleSaveNotifications();
      case 'booking-page': return handleSaveBookingPage();
      case 'team': return handleSaveTeam();
      default: return;
    }
  };

  // ============================================================================
  // Availability helpers
  // ============================================================================

  const updateBusinessHours = useCallback((day, field, value) => {
    setAvailability(prev => ({
      ...prev,
      business_hours: {
        ...prev.business_hours,
        [day]: { ...prev.business_hours[day], [field]: value },
      },
    }));
    setHasChanges(true);
  }, []);

  const updateLunchBreak = useCallback((field, value) => {
    setAvailability(prev => ({
      ...prev,
      lunch_break: { ...prev.lunch_break, [field]: value },
    }));
    setHasChanges(true);
  }, []);

  // ============================================================================
  // Appointment Type helpers
  // ============================================================================

  const handleCreateType = async () => {
    try {
      await calendarSettingsAPI.createAppointmentType(newType);
      toast.success('Appointment type created');
      setShowNewTypeForm(false);
      setNewType({ type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true });
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to create appointment type');
    }
  };

  const handleUpdateType = async (id, data) => {
    try {
      await calendarSettingsAPI.updateAppointmentType(id, data);
      toast.success('Appointment type updated');
      setEditingType(null);
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to update appointment type');
    }
  };

  const handleDeleteType = async (id) => {
    if (!window.confirm('Remove this appointment type?')) return;
    try {
      await calendarSettingsAPI.deleteAppointmentType(id);
      toast.success('Appointment type removed');
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to remove appointment type');
    }
  };

  const handleMoveType = async (index, direction) => {
    const newTypes = [...appointmentTypes];
    const swapIdx = index + direction;
    if (swapIdx < 0 || swapIdx >= newTypes.length) return;
    [newTypes[index], newTypes[swapIdx]] = [newTypes[swapIdx], newTypes[index]];
    setAppointmentTypes(newTypes);
    try {
      await calendarSettingsAPI.reorderAppointmentTypes(newTypes.map(t => t.id));
    } catch (err) {
      toast.error('Failed to reorder');
      loadTabData('appointment-types');
    }
  };

  // ============================================================================
  // Booking page helpers
  // ============================================================================

  const handleCopyLink = (url) => {
    const fullUrl = `${window.location.origin}${url}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
      setCopiedLink(url);
      toast.success('Link copied to clipboard');
      setTimeout(() => setCopiedLink(null), 2000);
    }).catch(() => {
      toast.error('Failed to copy link');
    });
  };

  // ============================================================================
  // Tab keyboard navigation
  // ============================================================================

  const handleTabKeyDown = useCallback((e, currentId) => {
    const tabIds = TAB_DEFINITIONS.map(t => t.id);
    const idx = tabIds.indexOf(currentId);
    let newIdx;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); newIdx = (idx + 1) % tabIds.length; }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); newIdx = (idx - 1 + tabIds.length) % tabIds.length; }
    else if (e.key === 'Home') { e.preventDefault(); newIdx = 0; }
    else if (e.key === 'End') { e.preventDefault(); newIdx = tabIds.length - 1; }
    else return;
    setActiveTab(tabIds[newIdx]);
    document.getElementById(`caltab-${tabIds[newIdx]}`)?.focus();
  }, []);

  // ============================================================================
  // Render: Loading
  // ============================================================================

  const renderLoading = () => (
    <div className="cal-settings-loading" role="status">
      <div className="spinner"></div>
      <p>Loading settings...</p>
    </div>
  );

  // ============================================================================
  // Render: Tab 1 - Availability
  // ============================================================================

  const renderAvailability = () => (
    <section className="cal-settings-section" role="tabpanel" id="panel-availability" aria-labelledby="caltab-availability">
      <h2>Business Hours</h2>
      <p className="section-description">Set your available hours for each day of the week.</p>

      <div className="business-hours-grid">
        {DAYS_OF_WEEK.map(day => {
          const hours = availability.business_hours[day] || { start: '09:00', end: '17:00', enabled: false };
          return (
            <div key={day} className={`day-row ${hours.enabled ? 'enabled' : 'disabled'}`}>
              <label className="day-toggle">
                <input
                  type="checkbox"
                  checked={hours.enabled}
                  onChange={(e) => updateBusinessHours(day, 'enabled', e.target.checked)}
                />
                <span className="day-name">{DAY_LABELS[day]}</span>
              </label>
              {hours.enabled && (
                <div className="time-inputs">
                  <input
                    type="time"
                    value={hours.start}
                    onChange={(e) => updateBusinessHours(day, 'start', e.target.value)}
                    aria-label={`${DAY_LABELS[day]} start time`}
                  />
                  <span className="time-separator">to</span>
                  <input
                    type="time"
                    value={hours.end}
                    onChange={(e) => updateBusinessHours(day, 'end', e.target.value)}
                    aria-label={`${DAY_LABELS[day]} end time`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <h3 className="subsection-title">Lunch Break</h3>
      <div className="lunch-break-row">
        <label className="day-toggle">
          <input
            type="checkbox"
            checked={availability.lunch_break.enabled}
            onChange={(e) => updateLunchBreak('enabled', e.target.checked)}
          />
          <span>Block lunch break</span>
        </label>
        {availability.lunch_break.enabled && (
          <div className="time-inputs">
            <input
              type="time"
              value={availability.lunch_break.start}
              onChange={(e) => updateLunchBreak('start', e.target.value)}
              aria-label="Lunch start"
            />
            <span className="time-separator">to</span>
            <input
              type="time"
              value={availability.lunch_break.end}
              onChange={(e) => updateLunchBreak('end', e.target.value)}
              aria-label="Lunch end"
            />
          </div>
        )}
      </div>

      <h3 className="subsection-title">Booking Window</h3>
      <div className="form-grid">
        <div className="form-field">
          <label htmlFor="buffer">Buffer Between Meetings (min)</label>
          <input
            id="buffer"
            type="number"
            min="0"
            max="60"
            value={availability.buffer_minutes}
            onChange={(e) => { setAvailability(prev => ({ ...prev, buffer_minutes: parseInt(e.target.value) || 0 })); setHasChanges(true); }}
          />
          <span className="field-hint">Break time between consecutive meetings</span>
        </div>
        <div className="form-field">
          <label htmlFor="min-notice">Minimum Notice (hours)</label>
          <input
            id="min-notice"
            type="number"
            min="0"
            max="168"
            value={availability.min_booking_notice_hours}
            onChange={(e) => { setAvailability(prev => ({ ...prev, min_booking_notice_hours: parseInt(e.target.value) || 0 })); setHasChanges(true); }}
          />
          <span className="field-hint">How far in advance bookings must be made</span>
        </div>
        <div className="form-field">
          <label htmlFor="max-advance">Max Advance Booking (days)</label>
          <input
            id="max-advance"
            type="number"
            min="1"
            max="365"
            value={availability.max_advance_booking_days}
            onChange={(e) => { setAvailability(prev => ({ ...prev, max_advance_booking_days: parseInt(e.target.value) || 1 })); setHasChanges(true); }}
          />
          <span className="field-hint">How far into the future clients can book</span>
        </div>
      </div>
    </section>
  );

  // ============================================================================
  // Render: Tab 2 - Appointment Types
  // ============================================================================

  const renderAppointmentTypes = () => (
    <section className="cal-settings-section" role="tabpanel" id="panel-appointment-types" aria-labelledby="caltab-appointment-types">
      <div className="section-header-row">
        <div>
          <h2>Appointment Types</h2>
          <p className="section-description">Define the types of meetings clients can book.</p>
        </div>
        <button
          className="btn-primary btn-sm"
          onClick={() => setShowNewTypeForm(true)}
        >
          <i className="fas fa-plus"></i> Add Type
        </button>
      </div>

      {showNewTypeForm && (
        <div className="type-form-card">
          <h3>New Appointment Type</h3>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input
                type="text"
                value={newType.type_name}
                onChange={(e) => setNewType(prev => ({ ...prev, type_name: e.target.value }))}
                placeholder="e.g., Initial Consultation"
              />
            </div>
            <div className="form-field">
              <label>Duration (min)</label>
              <select
                value={newType.duration_minutes}
                onChange={(e) => setNewType(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>60 minutes</option>
                <option value={90}>90 minutes</option>
              </select>
            </div>
            <div className="form-field full-width">
              <label>Description</label>
              <textarea
                value={newType.description || ''}
                onChange={(e) => setNewType(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Brief description shown to clients"
                rows={2}
              />
            </div>
            <div className="form-field">
              <label>Color</label>
              <div className="color-picker">
                {DEFAULT_COLORS.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`color-swatch ${newType.color === c ? 'selected' : ''}`}
                    style={{ backgroundColor: c }}
                    onClick={() => setNewType(prev => ({ ...prev, color: c }))}
                    aria-label={`Color ${c}`}
                  />
                ))}
              </div>
            </div>
            <div className="form-field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={newType.is_public}
                  onChange={(e) => setNewType(prev => ({ ...prev, is_public: e.target.checked }))}
                />
                Available on public booking page
              </label>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn-secondary btn-sm" onClick={() => setShowNewTypeForm(false)}>Cancel</button>
            <button
              className="btn-primary btn-sm"
              disabled={!newType.type_name.trim()}
              onClick={handleCreateType}
            >
              Create
            </button>
          </div>
        </div>
      )}

      <div className="type-list">
        {appointmentTypes.length === 0 && !loading && (
          <div className="empty-state">
            <i className="fas fa-calendar-plus"></i>
            <p>No appointment types yet. Create one to get started.</p>
          </div>
        )}
        {appointmentTypes.map((type, idx) => (
          <div key={type.id} className="type-card">
            <div className="type-color-bar" style={{ backgroundColor: type.color || '#218D8D' }} />
            <div className="type-content">
              {editingType === type.id ? (
                <EditTypeForm
                  type={type}
                  onSave={(data) => handleUpdateType(type.id, data)}
                  onCancel={() => setEditingType(null)}
                />
              ) : (
                <>
                  <div className="type-info">
                    <h4>{type.type_name}</h4>
                    <span className="type-meta">
                      {type.duration_minutes} min
                      {type.is_public && <span className="badge badge-public">Public</span>}
                    </span>
                    {type.description && <p className="type-desc">{type.description}</p>}
                  </div>
                  <div className="type-actions">
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, -1)}
                      disabled={idx === 0}
                      aria-label="Move up"
                      title="Move up"
                    >
                      <i className="fas fa-chevron-up"></i>
                    </button>
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, 1)}
                      disabled={idx === appointmentTypes.length - 1}
                      aria-label="Move down"
                      title="Move down"
                    >
                      <i className="fas fa-chevron-down"></i>
                    </button>
                    <button className="icon-btn" onClick={() => setEditingType(type.id)} aria-label="Edit" title="Edit">
                      <i className="fas fa-pen"></i>
                    </button>
                    <button className="icon-btn danger" onClick={() => handleDeleteType(type.id)} aria-label="Delete" title="Delete">
                      <i className="fas fa-trash"></i>
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );

  // ============================================================================
  // Render: Tab 3 - Notifications
  // ============================================================================

  const renderNotifications = () => {
    const updateNotif = (key, value) => {
      setNotifications(prev => ({ ...prev, [key]: value }));
      setHasChanges(true);
    };

    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-notifications" aria-labelledby="caltab-notifications">
        <h2>Reminder Notifications</h2>
        <p className="section-description">Configure when clients and you receive appointment reminders.</p>

        <div className="notification-grid">
          <div className="notif-column">
            <h3><i className="fas fa-envelope"></i> Email Reminders</h3>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.email_reminder_24h} onChange={(e) => updateNotif('email_reminder_24h', e.target.checked)} />
              <span>24 hours before</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.email_reminder_2h} onChange={(e) => updateNotif('email_reminder_2h', e.target.checked)} />
              <span>2 hours before</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.email_reminder_15m} onChange={(e) => updateNotif('email_reminder_15m', e.target.checked)} />
              <span>15 minutes before</span>
            </label>
          </div>

          <div className="notif-column">
            <h3><i className="fas fa-sms"></i> SMS Reminders</h3>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.sms_reminder_24h} onChange={(e) => updateNotif('sms_reminder_24h', e.target.checked)} />
              <span>24 hours before</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.sms_reminder_2h} onChange={(e) => updateNotif('sms_reminder_2h', e.target.checked)} />
              <span>2 hours before</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={notifications.sms_reminder_15m} onChange={(e) => updateNotif('sms_reminder_15m', e.target.checked)} />
              <span>15 minutes before</span>
            </label>
          </div>
        </div>

        <h3 className="subsection-title">Event Notifications</h3>
        <div className="event-notif-list">
          <label className="toggle-row">
            <input type="checkbox" checked={notifications.notify_on_booking} onChange={(e) => updateNotif('notify_on_booking', e.target.checked)} />
            <span>Notify me when a new appointment is booked</span>
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={notifications.notify_on_cancellation} onChange={(e) => updateNotif('notify_on_cancellation', e.target.checked)} />
            <span>Notify me when an appointment is cancelled</span>
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={notifications.notify_on_reschedule} onChange={(e) => updateNotif('notify_on_reschedule', e.target.checked)} />
            <span>Notify me when an appointment is rescheduled</span>
          </label>
        </div>

        <h3 className="subsection-title">Quiet Hours</h3>
        <p className="section-description">Suppress notifications during these hours.</p>
        <div className="quiet-hours-row">
          <label className="day-toggle">
            <input
              type="checkbox"
              checked={notifications.quiet_hours_enabled}
              onChange={(e) => updateNotif('quiet_hours_enabled', e.target.checked)}
            />
            <span>Enable quiet hours</span>
          </label>
          {notifications.quiet_hours_enabled && (
            <div className="time-inputs">
              <input
                type="time"
                value={notifications.quiet_hours_start}
                onChange={(e) => updateNotif('quiet_hours_start', e.target.value)}
                aria-label="Quiet hours start"
              />
              <span className="time-separator">to</span>
              <input
                type="time"
                value={notifications.quiet_hours_end}
                onChange={(e) => updateNotif('quiet_hours_end', e.target.value)}
                aria-label="Quiet hours end"
              />
            </div>
          )}
        </div>
      </section>
    );
  };

  // ============================================================================
  // Render: Tab 4 - Booking Page
  // ============================================================================

  const renderBookingPage = () => {
    const updateBranding = (key, value) => {
      setBookingPage(prev => ({
        ...prev,
        branding: { ...prev.branding, [key]: value },
      }));
      setHasChanges(true);
    };

    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-booking-page" aria-labelledby="caltab-booking-page">
        <h2>Booking Page</h2>
        <p className="section-description">Customize the appearance of your public booking page.</p>

        {/* Branding */}
        <div className="form-grid">
          <div className="form-field">
            <label>Logo URL</label>
            <input
              type="url"
              value={bookingPage.branding.logo_url || ''}
              onChange={(e) => updateBranding('logo_url', e.target.value || null)}
              placeholder="https://example.com/logo.png"
            />
          </div>
          <div className="form-field">
            <label>Primary Color</label>
            <div className="color-input-row">
              <input
                type="color"
                value={bookingPage.branding.primary_color}
                onChange={(e) => updateBranding('primary_color', e.target.value)}
              />
              <input
                type="text"
                value={bookingPage.branding.primary_color}
                onChange={(e) => updateBranding('primary_color', e.target.value)}
                className="color-text-input"
              />
            </div>
          </div>
          <div className="form-field">
            <label>Secondary Color</label>
            <div className="color-input-row">
              <input
                type="color"
                value={bookingPage.branding.secondary_color}
                onChange={(e) => updateBranding('secondary_color', e.target.value)}
              />
              <input
                type="text"
                value={bookingPage.branding.secondary_color}
                onChange={(e) => updateBranding('secondary_color', e.target.value)}
                className="color-text-input"
              />
            </div>
          </div>
          <div className="form-field full-width">
            <label>Tagline</label>
            <input
              type="text"
              value={bookingPage.branding.tagline || ''}
              onChange={(e) => updateBranding('tagline', e.target.value)}
              placeholder="Your trusted mortgage partner"
            />
          </div>
          <div className="form-field full-width">
            <label>Welcome Message</label>
            <textarea
              value={bookingPage.branding.welcome_message || ''}
              onChange={(e) => updateBranding('welcome_message', e.target.value)}
              rows={2}
              placeholder="Schedule a time to meet with us"
            />
          </div>
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={bookingPage.branding.show_branding}
                onChange={(e) => updateBranding('show_branding', e.target.checked)}
              />
              Show Perennia branding
            </label>
          </div>
        </div>

        {/* Preview */}
        <h3 className="subsection-title">Preview</h3>
        <div
          className="booking-preview"
          style={{
            borderColor: bookingPage.branding.primary_color,
            backgroundColor: bookingPage.branding.secondary_color,
          }}
        >
          {bookingPage.branding.logo_url && (
            <img src={bookingPage.branding.logo_url} alt="Logo" className="preview-logo" />
          )}
          <h4 style={{ color: bookingPage.branding.primary_color }}>
            {bookingPage.branding.tagline || 'Your Booking Page'}
          </h4>
          <p>{bookingPage.branding.welcome_message || 'Schedule a time to meet with us'}</p>
          <button className="preview-cta" style={{ backgroundColor: bookingPage.branding.primary_color }}>
            Book an Appointment
          </button>
        </div>

        {/* Booking Links */}
        <h3 className="subsection-title">Booking Links</h3>
        {bookingPage.booking_links.length === 0 ? (
          <p className="empty-hint">No booking links yet. Create one in the Booking Links tab of Smart Scheduler Settings.</p>
        ) : (
          <div className="booking-links-list">
            {bookingPage.booking_links.map(link => (
              <div key={link.id} className="booking-link-row">
                <div className="link-info">
                  <strong>{link.name}</strong>
                  <code>{window.location.origin}{link.url}</code>
                </div>
                <div className="link-actions">
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleCopyLink(link.url)}
                  >
                    <i className={`fas ${copiedLink === link.url ? 'fa-check' : 'fa-copy'}`}></i>
                    {copiedLink === link.url ? 'Copied' : 'Copy'}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => {
                      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(window.location.origin + link.url)}`;
                      window.open(qrUrl, '_blank');
                    }}
                    title="Generate QR Code"
                  >
                    <i className="fas fa-qrcode"></i> QR
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  };

  // ============================================================================
  // Render: Tab 5 - Integrations
  // ============================================================================

  const renderIntegrations = () => (
    <section className="cal-settings-section" role="tabpanel" id="panel-integrations" aria-labelledby="caltab-integrations">
      <h2>Calendar Integrations</h2>
      <p className="section-description">Connect your external calendars to sync events and check availability.</p>

      <div className="integration-cards">
        {/* Google Calendar */}
        <div className={`integration-card ${integrations.google?.connected ? 'connected' : ''}`}>
          <div className="integration-icon google">
            <i className="fab fa-google"></i>
          </div>
          <div className="integration-info">
            <h3>Google Calendar</h3>
            {integrations.google?.connected ? (
              <>
                <p className="connected-text">
                  <i className="fas fa-check-circle"></i> Connected as {integrations.google.email}
                </p>
                {integrations.google.last_synced && (
                  <p className="sync-time">Last synced: {new Date(integrations.google.last_synced).toLocaleString()}</p>
                )}
              </>
            ) : (
              <p className="disconnected-text">Not connected</p>
            )}
          </div>
          <div className="integration-action">
            {integrations.google?.connected ? (
              <button
                className="btn-secondary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/google-calendar/disconnect`;
                }}
              >
                Disconnect
              </button>
            ) : (
              <button
                className="btn-primary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/google-calendar/connect`;
                }}
              >
                Connect
              </button>
            )}
          </div>
        </div>

        {/* Outlook Calendar */}
        <div className={`integration-card ${integrations.outlook?.connected ? 'connected' : ''}`}>
          <div className="integration-icon outlook">
            <i className="fab fa-microsoft"></i>
          </div>
          <div className="integration-info">
            <h3>Outlook Calendar</h3>
            {integrations.outlook?.connected ? (
              <>
                <p className="connected-text">
                  <i className="fas fa-check-circle"></i> Connected as {integrations.outlook.email}
                </p>
                {integrations.outlook.last_synced && (
                  <p className="sync-time">Last synced: {new Date(integrations.outlook.last_synced).toLocaleString()}</p>
                )}
              </>
            ) : (
              <p className="disconnected-text">Not connected</p>
            )}
          </div>
          <div className="integration-action">
            {integrations.outlook?.connected ? (
              <button
                className="btn-secondary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/microsoft/calendar/disconnect`;
                }}
              >
                Disconnect
              </button>
            ) : (
              <button
                className="btn-primary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/microsoft/calendar/connect`;
                }}
              >
                Connect
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );

  // ============================================================================
  // Render: Tab 6 - Team
  // ============================================================================

  const renderTeam = () => {
    if (!isManager) {
      return (
        <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="caltab-team">
          <div className="empty-state">
            <i className="fas fa-lock"></i>
            <p>Team calendar settings are available to managers only.</p>
          </div>
        </section>
      );
    }

    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="caltab-team">
        <h2>Team Calendar</h2>
        <p className="section-description">Manage how appointments are distributed across your team.</p>

        <h3 className="subsection-title">Assignment Strategy</h3>
        <div className="strategy-options">
          {ASSIGNMENT_STRATEGIES.map(strategy => (
            <label
              key={strategy.value}
              className={`strategy-option ${team.assignment_strategy === strategy.value ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="strategy"
                value={strategy.value}
                checked={team.assignment_strategy === strategy.value}
                onChange={() => {
                  setTeam(prev => ({ ...prev, assignment_strategy: strategy.value }));
                  setHasChanges(true);
                }}
              />
              <div className="strategy-content">
                <strong>{strategy.label}</strong>
                <span>{strategy.description}</span>
              </div>
            </label>
          ))}
        </div>

        <h3 className="subsection-title">Team Members ({team.total_members})</h3>
        <div className="team-table-wrap">
          <table className="team-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Max Daily</th>
                <th>Upcoming</th>
                <th>Accepting</th>
              </tr>
            </thead>
            <tbody>
              {(team.members || []).map(member => (
                <tr key={member.user_id}>
                  <td className="member-name">{member.name}</td>
                  <td className="member-email">{member.email}</td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      max="24"
                      value={member.max_daily_appointments}
                      className="capacity-input"
                      onChange={(e) => {
                        const val = parseInt(e.target.value) || 0;
                        setTeam(prev => ({
                          ...prev,
                          members: prev.members.map(m =>
                            m.user_id === member.user_id ? { ...m, max_daily_appointments: val } : m
                          ),
                        }));
                        setHasChanges(true);
                      }}
                    />
                  </td>
                  <td className="upcoming-count">{member.upcoming_appointments}</td>
                  <td>
                    <label className="toggle-switch">
                      <input
                        type="checkbox"
                        checked={member.is_accepting_appointments}
                        onChange={(e) => {
                          setTeam(prev => ({
                            ...prev,
                            members: prev.members.map(m =>
                              m.user_id === member.user_id ? { ...m, is_accepting_appointments: e.target.checked } : m
                            ),
                          }));
                          setHasChanges(true);
                        }}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                  </td>
                </tr>
              ))}
              {(!team.members || team.members.length === 0) && (
                <tr>
                  <td colSpan={5} className="empty-row">No team members found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  // ============================================================================
  // Render: Main
  // ============================================================================

  const showSaveButton = ['availability', 'notifications', 'booking-page', 'team'].includes(activeTab);

  return (
    <div className="cal-settings-page">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button onClick={() => navigate(-1)} className="back-btn" aria-label="Go back">
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Calendar Settings</h1>
            <p className="subtitle">Configure your calendar, availability, and booking preferences</p>
          </div>
        </div>
        {showSaveButton && (
          <div className="header-actions">
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="btn-primary"
            >
              {saving ? (
                <><i className="fas fa-spinner fa-spin"></i> Saving...</>
              ) : (
                <><i className="fas fa-save"></i> Save Changes</>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="settings-tabs" role="tablist" aria-label="Calendar settings">
        {TAB_DEFINITIONS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            id={`caltab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(e) => handleTabKeyDown(e, tab.id)}
          >
            <i className={`fas ${tab.icon}`}></i> {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {loading ? renderLoading() : (
        <>
          {activeTab === 'availability' && renderAvailability()}
          {activeTab === 'appointment-types' && renderAppointmentTypes()}
          {activeTab === 'notifications' && renderNotifications()}
          {activeTab === 'booking-page' && renderBookingPage()}
          {activeTab === 'integrations' && renderIntegrations()}
          {activeTab === 'team' && renderTeam()}
        </>
      )}

      {/* Sticky Save Bar */}
      {hasChanges && showSaveButton && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button
                type="button"
                onClick={() => loadTabData(activeTab)}
                className="btn-secondary"
                disabled={saving}
              >
                Discard
              </button>
              <button
                onClick={handleSave}
                className="btn-primary"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sub-component: Edit Type Form (inline)
// ============================================================================

function EditTypeForm({ type, onSave, onCancel }) {
  const [form, setForm] = useState({
    type_name: type.type_name || '',
    description: type.description || '',
    duration_minutes: type.duration_minutes || 30,
    color: type.color || '#218D8D',
    is_public: type.is_public !== false,
  });

  return (
    <div className="edit-type-form">
      <div className="form-grid">
        <div className="form-field">
          <label>Name</label>
          <input
            type="text"
            value={form.type_name}
            onChange={(e) => setForm(prev => ({ ...prev, type_name: e.target.value }))}
          />
        </div>
        <div className="form-field">
          <label>Duration</label>
          <select
            value={form.duration_minutes}
            onChange={(e) => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
          >
            <option value={15}>15 min</option>
            <option value={30}>30 min</option>
            <option value={45}>45 min</option>
            <option value={60}>60 min</option>
            <option value={90}>90 min</option>
          </select>
        </div>
        <div className="form-field full-width">
          <label>Description</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
            rows={2}
          />
        </div>
        <div className="form-field">
          <label>Color</label>
          <div className="color-picker">
            {DEFAULT_COLORS.map(c => (
              <button
                key={c}
                type="button"
                className={`color-swatch ${form.color === c ? 'selected' : ''}`}
                style={{ backgroundColor: c }}
                onClick={() => setForm(prev => ({ ...prev, color: c }))}
                aria-label={`Color ${c}`}
              />
            ))}
          </div>
        </div>
        <div className="form-field">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_public}
              onChange={(e) => setForm(prev => ({ ...prev, is_public: e.target.checked }))}
            />
            Public
          </label>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
        <button
          className="btn-primary btn-sm"
          disabled={!form.type_name.trim()}
          onClick={() => onSave(form)}
        >
          Save
        </button>
      </div>
    </div>
  );
}

export default CalendarSettings;
