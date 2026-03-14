/**
 * Perennia AI - Smart Calendar Setup: Step 5 - Notifications
 *
 * Configure reminder timelines, event alerts, quiet hours, digest
 * settings, and browser push notifications for the calendar.
 *
 * Five collapsible accordion sections, each with a header toggle.
 * State is auto-synced to the wizard via onChange prop.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { toast } from '../../../../utils/toast';
import './NotificationsStep.css';

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_REMINDERS = [
  { id: 'r_24h', label: '24 hours before', value: 24, unit: 'hours', enabled: true, channel: 'email' },
  { id: 'r_2h', label: '2 hours before', value: 2, unit: 'hours', enabled: true, channel: 'both' },
  { id: 'r_15m', label: '15 minutes before', value: 15, unit: 'minutes', enabled: false, channel: 'sms' },
];

const UNIT_OPTIONS = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

const CHANNEL_OPTIONS = [
  { value: 'email', label: 'Email', icon: 'fa-envelope' },
  { value: 'sms', label: 'SMS', icon: 'fa-comment' },
  { value: 'both', label: 'Both', icon: 'fa-layer-group' },
];

const DEFAULT_EVENT_ALERTS = {
  newBooking: { enabled: true, channel: 'email' },
  cancellation: { enabled: true, channel: 'both' },
  reschedule: { enabled: true, channel: 'email' },
  noShow: { enabled: false, delayMinutes: 15 },
  dailySummary: { enabled: false, time: '08:00' },
};

const DEFAULT_QUIET_HOURS = {
  enabled: false,
  start: '21:00',
  end: '08:00',
  weekends: true,
};

const DEFAULT_DIGEST = {
  daily: { enabled: false, time: '08:00' },
  weekly: { enabled: false, day: 'monday', time: '09:00' },
  content: {
    upcomingAppointments: true,
    cancellations: true,
    analytics: false,
    teamActivity: false,
  },
};

const DEFAULT_BROWSER = {
  enabled: false,
  sound: true,
};

const DAYS_OF_WEEK = [
  { value: 'monday', label: 'Monday' },
  { value: 'tuesday', label: 'Tuesday' },
  { value: 'wednesday', label: 'Wednesday' },
  { value: 'thursday', label: 'Thursday' },
  { value: 'friday', label: 'Friday' },
  { value: 'saturday', label: 'Saturday' },
  { value: 'sunday', label: 'Sunday' },
];

const SECTION_DEFS = [
  { key: 'reminders', title: 'Reminder Timeline', icon: 'fa-clock', description: 'When to send appointment reminders' },
  { key: 'eventAlerts', title: 'Event Alerts', icon: 'fa-bolt', description: 'Notifications for calendar events' },
  { key: 'quietHours', title: 'Quiet Hours', icon: 'fa-moon', description: 'When NOT to send notifications' },
  { key: 'digest', title: 'Digest Settings', icon: 'fa-newspaper', description: 'Summary email preferences' },
  { key: 'browser', title: 'Browser Notifications', icon: 'fa-desktop', description: 'Desktop push notifications' },
];

// ============================================================================
// Helpers
// ============================================================================

function formatReminderLabel(value, unit) {
  if (unit === 'minutes') return `${value} min`;
  if (unit === 'hours') return `${value}h`;
  if (unit === 'days') return `${value}d`;
  return `${value} ${unit}`;
}

function formatTime12(time24) {
  if (!time24) return '';
  const [h, m] = time24.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m).padStart(2, '0')} ${period}`;
}

let nextCustomId = 1;

// ============================================================================
// Sub-components
// ============================================================================

function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`notifications-step__toggle ${disabled ? 'notifications-step__toggle--disabled' : ''}`}>
      <span className="notifications-step__toggle-track">
        <input
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          aria-label={label}
          disabled={disabled}
        />
        <span className={`notifications-step__toggle-bg ${checked ? 'on' : 'off'}`}>
          <span className={`notifications-step__toggle-thumb ${checked ? 'on' : 'off'}`} />
        </span>
      </span>
      <span className="notifications-step__toggle-text">
        <span className="notifications-step__toggle-label">{label}</span>
        {hint && <span className="notifications-step__toggle-hint">{hint}</span>}
      </span>
    </label>
  );
}

function ChannelRadio({ value, onChange, name }) {
  return (
    <div className="notifications-step__channel-group" role="radiogroup" aria-label={`${name} notification channel`}>
      {CHANNEL_OPTIONS.map(opt => (
        <label
          key={opt.value}
          className={`notifications-step__channel-option ${value === opt.value ? 'selected' : ''}`}
        >
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
          />
          <i className={`fas ${opt.icon}`} aria-hidden="true" />
          <span>{opt.label}</span>
        </label>
      ))}
    </div>
  );
}

function AccordionSection({ sectionKey, title, icon, description, expanded, onToggle, sectionEnabled, onSectionToggle, children }) {
  const contentRef = useRef(null);

  return (
    <div className={`notifications-step__section ${expanded ? 'expanded' : ''} ${sectionEnabled ? 'enabled' : 'disabled'}`}>
      <button
        type="button"
        className="notifications-step__section-header"
        onClick={() => onToggle(sectionKey)}
        aria-expanded={expanded}
        aria-controls={`ns-content-${sectionKey}`}
        id={`ns-header-${sectionKey}`}
      >
        <div className="notifications-step__section-header-left">
          <span className={`notifications-step__section-icon ${sectionEnabled ? 'active' : ''}`}>
            <i className={`fas ${icon}`} aria-hidden="true" />
          </span>
          <div className="notifications-step__section-info">
            <span className="notifications-step__section-title">{title}</span>
            <span className="notifications-step__section-desc">{description}</span>
          </div>
        </div>
        <div className="notifications-step__section-header-right">
          {onSectionToggle && (
            <label
              className="notifications-step__section-enable"
              onClick={e => e.stopPropagation()}
            >
              <span className="notifications-step__mini-toggle-track">
                <input
                  type="checkbox"
                  checked={sectionEnabled}
                  onChange={e => onSectionToggle(e.target.checked)}
                  aria-label={`Enable ${title}`}
                />
                <span className={`notifications-step__mini-toggle-bg ${sectionEnabled ? 'on' : 'off'}`}>
                  <span className={`notifications-step__mini-toggle-thumb ${sectionEnabled ? 'on' : 'off'}`} />
                </span>
              </span>
            </label>
          )}
          <span className={`notifications-step__section-chevron ${expanded ? 'rotated' : ''}`}>
            <i className="fas fa-chevron-down" aria-hidden="true" />
          </span>
        </div>
      </button>
      <div
        id={`ns-content-${sectionKey}`}
        className="notifications-step__section-content"
        ref={contentRef}
        role="region"
        aria-labelledby={`ns-header-${sectionKey}`}
        style={{
          maxHeight: expanded ? (contentRef.current ? contentRef.current.scrollHeight + 40 : 2000) : 0,
        }}
      >
        <div className="notifications-step__section-body">
          {children}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Quiet Hours Clock SVG
// ============================================================================

function QuietHoursClock({ start, end, weekends }) {
  // Convert time strings to angles (0 = 12 o'clock, clockwise)
  function timeToAngle(timeStr) {
    const [h, m] = timeStr.split(':').map(Number);
    // 24-hour clock mapped to 360 degrees
    return ((h + m / 60) / 24) * 360 - 90;
  }

  function polarToCartesian(cx, cy, radius, angleInDegrees) {
    const angleInRadians = (angleInDegrees * Math.PI) / 180;
    return {
      x: cx + radius * Math.cos(angleInRadians),
      y: cy + radius * Math.sin(angleInRadians),
    };
  }

  function describeArc(cx, cy, radius, startAngle, endAngle) {
    let adjustedEnd = endAngle;
    if (adjustedEnd <= startAngle) {
      adjustedEnd += 360;
    }
    const largeArc = adjustedEnd - startAngle > 180 ? 1 : 0;
    const s = polarToCartesian(cx, cy, radius, startAngle);
    const e = polarToCartesian(cx, cy, radius, adjustedEnd);
    return `M ${cx} ${cy} L ${s.x} ${s.y} A ${radius} ${radius} 0 ${largeArc} 1 ${e.x} ${e.y} Z`;
  }

  const cx = 60, cy = 60, r = 50;
  const startAngle = timeToAngle(start);
  const endAngle = timeToAngle(end);
  const arcPath = describeArc(cx, cy, r, startAngle, endAngle);

  // Hour markers
  const markers = [];
  for (let i = 0; i < 24; i++) {
    const angle = (i / 24) * 360 - 90;
    const inner = polarToCartesian(cx, cy, r - 4, angle);
    const outer = polarToCartesian(cx, cy, r, angle);
    markers.push(
      <line
        key={i}
        x1={inner.x} y1={inner.y}
        x2={outer.x} y2={outer.y}
        stroke={i % 6 === 0 ? '#6b7280' : '#d1d5db'}
        strokeWidth={i % 6 === 0 ? 1.5 : 0.8}
      />
    );
  }

  // Hour labels for 12AM, 6AM, 12PM, 6PM
  const hourLabels = [
    { h: 0, label: '12a' },
    { h: 6, label: '6a' },
    { h: 12, label: '12p' },
    { h: 18, label: '6p' },
  ];

  return (
    <div className="notifications-step__clock-container">
      <svg viewBox="0 0 120 120" className="notifications-step__clock-svg" aria-label={`Quiet hours from ${formatTime12(start)} to ${formatTime12(end)}`} role="img">
        {/* Background circle */}
        <circle cx={cx} cy={cy} r={r} fill="#f8fafc" stroke="#e2e8f0" strokeWidth="2" />

        {/* Quiet hours shaded arc */}
        <path d={arcPath} fill="rgba(33, 141, 141, 0.15)" stroke="none" />

        {/* Hour markers */}
        {markers}

        {/* Hour labels */}
        {hourLabels.map(({ h, label }) => {
          const angle = (h / 24) * 360 - 90;
          const pos = polarToCartesian(cx, cy, r - 14, angle);
          return (
            <text
              key={h}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="7"
              fill="#6b7280"
              fontWeight="500"
            >
              {label}
            </text>
          );
        })}

        {/* Center label */}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="7" fill="#218D8D" fontWeight="600">
          Quiet
        </text>
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize="6" fill="#6b7280">
          {formatTime12(start)}
        </text>
        <text x={cx} y={cy + 13} textAnchor="middle" fontSize="6" fill="#6b7280">
          to {formatTime12(end)}
        </text>
      </svg>
      {weekends && (
        <div className="notifications-step__clock-badge">
          <i className="fas fa-calendar-week" aria-hidden="true" />
          <span>Weekends included</span>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Digest Preview Card
// ============================================================================

function DigestPreviewCard({ digest }) {
  const today = new Date();
  const dateStr = today.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  return (
    <div className="notifications-step__digest-preview">
      <div className="notifications-step__digest-preview-label">
        <i className="fas fa-eye" aria-hidden="true" /> Preview
      </div>
      <div className="notifications-step__digest-card">
        <div className="notifications-step__digest-card-header">
          <div className="notifications-step__digest-card-logo">P</div>
          <div>
            <div className="notifications-step__digest-card-title">
              {digest.daily.enabled ? 'Daily' : 'Weekly'} Calendar Digest
            </div>
            <div className="notifications-step__digest-card-date">{dateStr}</div>
          </div>
        </div>
        <div className="notifications-step__digest-card-body">
          {digest.content.upcomingAppointments && (
            <div className="notifications-step__digest-item">
              <i className="fas fa-calendar-check" aria-hidden="true" />
              <div>
                <strong>Upcoming Appointments</strong>
                <span>3 appointments scheduled</span>
              </div>
            </div>
          )}
          {digest.content.cancellations && (
            <div className="notifications-step__digest-item">
              <i className="fas fa-times-circle" aria-hidden="true" />
              <div>
                <strong>Cancellations</strong>
                <span>1 cancellation yesterday</span>
              </div>
            </div>
          )}
          {digest.content.analytics && (
            <div className="notifications-step__digest-item">
              <i className="fas fa-chart-bar" aria-hidden="true" />
              <div>
                <strong>Analytics</strong>
                <span>85% show rate this week</span>
              </div>
            </div>
          )}
          {digest.content.teamActivity && (
            <div className="notifications-step__digest-item">
              <i className="fas fa-users" aria-hidden="true" />
              <div>
                <strong>Team Activity</strong>
                <span>12 appointments booked by team</span>
              </div>
            </div>
          )}
          {!digest.content.upcomingAppointments && !digest.content.cancellations &&
           !digest.content.analytics && !digest.content.teamActivity && (
            <div className="notifications-step__digest-empty">
              Select at least one content type to see a preview.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function NotificationsStep({ stepData = {}, onChange, allStepData, onStepComplete, onDirty, initialData }) {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [expandedSections, setExpandedSections] = useState({ reminders: true });

  const [reminders, setReminders] = useState(
    stepData.reminders || initialData?.reminders || [...DEFAULT_REMINDERS]
  );
  const [showCustomReminder, setShowCustomReminder] = useState(false);
  const [customValue, setCustomValue] = useState(30);
  const [customUnit, setCustomUnit] = useState('minutes');

  const [eventAlerts, setEventAlerts] = useState(
    stepData.eventAlerts || initialData?.eventAlerts || { ...DEFAULT_EVENT_ALERTS }
  );

  const [quietHours, setQuietHours] = useState(
    stepData.quietHours || initialData?.quietHours || { ...DEFAULT_QUIET_HOURS }
  );

  const [digest, setDigest] = useState(
    stepData.digest || initialData?.digest || JSON.parse(JSON.stringify(DEFAULT_DIGEST))
  );

  const [browser, setBrowser] = useState(
    stepData.browser || initialData?.browser || { ...DEFAULT_BROWSER }
  );

  const [browserPermission, setBrowserPermission] = useState('default');

  // Track initial mount for dirty detection
  const mountedRef = useRef(false);

  // ---------------------------------------------------------------------------
  // Check browser notification permission on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if ('Notification' in window) {
      setBrowserPermission(Notification.permission);
    } else {
      setBrowserPermission('unsupported');
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Build and sync payload to parent
  // ---------------------------------------------------------------------------
  const buildPayload = useCallback(() => {
    return { reminders, eventAlerts, quietHours, digest, browser };
  }, [reminders, eventAlerts, quietHours, digest, browser]);

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const payload = buildPayload();
    if (onChange) onChange(payload);
    if (onDirty) onDirty(true);
  }, [reminders, eventAlerts, quietHours, digest, browser, onChange, onDirty, buildPayload]);

  // ---------------------------------------------------------------------------
  // Section expand/collapse
  // ---------------------------------------------------------------------------
  const toggleSection = useCallback((key) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // ---------------------------------------------------------------------------
  // Reminder handlers
  // ---------------------------------------------------------------------------
  const toggleReminder = useCallback((id) => {
    setReminders(prev => prev.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r));
  }, []);

  const updateReminderChannel = useCallback((id, channel) => {
    setReminders(prev => prev.map(r => r.id === id ? { ...r, channel } : r));
  }, []);

  const removeReminder = useCallback((id) => {
    setReminders(prev => prev.filter(r => r.id !== id));
  }, []);

  const addCustomReminder = useCallback(() => {
    const id = `r_custom_${nextCustomId++}`;
    const label = `${customValue} ${customUnit} before`;
    setReminders(prev => [...prev, { id, label, value: customValue, unit: customUnit, enabled: true, channel: 'email' }]);
    setShowCustomReminder(false);
    setCustomValue(30);
    setCustomUnit('minutes');
  }, [customValue, customUnit]);

  // ---------------------------------------------------------------------------
  // Event alert handlers
  // ---------------------------------------------------------------------------
  const updateEventAlert = useCallback((key, field, value) => {
    setEventAlerts(prev => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }));
  }, []);

  // ---------------------------------------------------------------------------
  // Quiet hours handlers
  // ---------------------------------------------------------------------------
  const updateQuietHours = useCallback((field, value) => {
    setQuietHours(prev => ({ ...prev, [field]: value }));
  }, []);

  // ---------------------------------------------------------------------------
  // Digest handlers
  // ---------------------------------------------------------------------------
  const updateDigestToggle = useCallback((period, field, value) => {
    setDigest(prev => ({
      ...prev,
      [period]: { ...prev[period], [field]: value },
    }));
  }, []);

  const updateDigestContent = useCallback((key, value) => {
    setDigest(prev => ({
      ...prev,
      content: { ...prev.content, [key]: value },
    }));
  }, []);

  // ---------------------------------------------------------------------------
  // Browser notification handlers
  // ---------------------------------------------------------------------------
  const requestBrowserPermission = useCallback(async () => {
    if (!('Notification' in window)) {
      toast.error('Your browser does not support desktop notifications.');
      return;
    }
    try {
      const result = await Notification.requestPermission();
      setBrowserPermission(result);
      if (result === 'granted') {
        setBrowser(prev => ({ ...prev, enabled: true }));
        toast.success('Browser notifications enabled.');
      } else if (result === 'denied') {
        toast.error('Notification permission denied. You can change this in your browser settings.');
      }
    } catch (err) {
      console.error('Failed to request notification permission:', err);
      toast.error('Failed to request notification permission.');
    }
  }, []);

  const showDemoNotification = useCallback(() => {
    if (browserPermission !== 'granted') {
      toast.info('Enable browser notifications first to see a preview.');
      return;
    }
    try {
      const notification = new Notification('Perennia - Appointment Reminder', {
        body: 'You have an appointment with John Smith in 15 minutes.',
        icon: '/favicon.ico',
        tag: 'perennia-demo',
      });
      setTimeout(() => notification.close(), 5000);
    } catch (err) {
      // Fallback: show a toast instead
      toast.info('Demo: "You have an appointment with John Smith in 15 minutes."');
    }
  }, [browserPermission]);

  // ---------------------------------------------------------------------------
  // Computed section enabled states
  // ---------------------------------------------------------------------------
  const activeReminderCount = useMemo(() => reminders.filter(r => r.enabled).length, [reminders]);

  const permissionStatusLabel = useMemo(() => {
    switch (browserPermission) {
      case 'granted': return 'Granted';
      case 'denied': return 'Denied';
      case 'unsupported': return 'Not Supported';
      default: return 'Not Asked';
    }
  }, [browserPermission]);

  const permissionStatusClass = useMemo(() => {
    switch (browserPermission) {
      case 'granted': return 'granted';
      case 'denied': return 'denied';
      default: return 'default';
    }
  }, [browserPermission]);

  // ---------------------------------------------------------------------------
  // Reminder message template preview
  // ---------------------------------------------------------------------------
  const reminderPreview = useMemo(() => {
    const enabledReminders = reminders.filter(r => r.enabled);
    if (enabledReminders.length === 0) return null;
    const first = enabledReminders[0];
    return {
      time: formatReminderLabel(first.value, first.unit),
      channel: first.channel,
    };
  }, [reminders]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="notifications-step">
      {/* Header */}
      <div className="notifications-step__header">
        <div className="notifications-step__step-badge">Step 5</div>
        <h2 className="notifications-step__title">Notifications</h2>
        <p className="notifications-step__subtitle">
          Configure how and when you and your clients receive appointment notifications.
          Fine-tune reminders, event alerts, and delivery preferences.
        </p>
      </div>

      {/* ================================================================
          Section 1: Reminder Timeline
          ================================================================ */}
      <AccordionSection
        sectionKey="reminders"
        title="Reminder Timeline"
        icon="fa-clock"
        description={`${activeReminderCount} reminder${activeReminderCount !== 1 ? 's' : ''} active`}
        expanded={!!expandedSections.reminders}
        onToggle={toggleSection}
        sectionEnabled={activeReminderCount > 0}
      >
        {/* Visual timeline */}
        <div className="notifications-step__timeline">
          <div className="notifications-step__timeline-line" />
          {reminders.map((reminder) => (
            <div
              key={reminder.id}
              className={`notifications-step__timeline-item ${reminder.enabled ? 'active' : 'inactive'}`}
            >
              <div className="notifications-step__timeline-dot" />
              <div className="notifications-step__timeline-card">
                <div className="notifications-step__timeline-card-header">
                  <Toggle
                    checked={reminder.enabled}
                    onChange={() => toggleReminder(reminder.id)}
                    label={reminder.label}
                  />
                  {!DEFAULT_REMINDERS.find(d => d.id === reminder.id) && (
                    <button
                      type="button"
                      className="notifications-step__remove-btn"
                      onClick={() => removeReminder(reminder.id)}
                      aria-label={`Remove ${reminder.label} reminder`}
                      title="Remove"
                    >
                      <i className="fas fa-times" aria-hidden="true" />
                    </button>
                  )}
                </div>
                {reminder.enabled && (
                  <div className="notifications-step__timeline-card-body">
                    <span className="notifications-step__field-label">Channel:</span>
                    <ChannelRadio
                      value={reminder.channel}
                      onChange={(ch) => updateReminderChannel(reminder.id, ch)}
                      name={`reminder-channel-${reminder.id}`}
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Add custom reminder */}
        {!showCustomReminder ? (
          <button
            type="button"
            className="notifications-step__add-btn"
            onClick={() => setShowCustomReminder(true)}
          >
            <i className="fas fa-plus" aria-hidden="true" /> Add Custom Reminder
          </button>
        ) : (
          <div className="notifications-step__custom-form">
            <div className="notifications-step__custom-row">
              <input
                type="number"
                min={1}
                max={999}
                value={customValue}
                onChange={e => setCustomValue(Math.min(999, Math.max(1, parseInt(e.target.value, 10) || 1)))}
                className="notifications-step__custom-input"
                aria-label="Custom reminder value"
              />
              <select
                value={customUnit}
                onChange={e => setCustomUnit(e.target.value)}
                className="notifications-step__custom-select"
                aria-label="Custom reminder unit"
              >
                {UNIT_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <span className="notifications-step__custom-label">before</span>
            </div>
            <div className="notifications-step__custom-actions">
              <button type="button" className="notifications-step__btn-secondary" onClick={() => setShowCustomReminder(false)}>
                Cancel
              </button>
              <button type="button" className="notifications-step__btn-primary" onClick={addCustomReminder}>
                Add
              </button>
            </div>
          </div>
        )}

        {/* Reminder message preview */}
        {reminderPreview && (
          <div className="notifications-step__reminder-preview">
            <div className="notifications-step__preview-label">
              <i className="fas fa-eye" aria-hidden="true" /> Message Preview
            </div>
            <div className="notifications-step__preview-card">
              <div className="notifications-step__preview-icon">
                <i className={`fas ${reminderPreview.channel === 'sms' ? 'fa-comment' : 'fa-envelope'}`} aria-hidden="true" />
              </div>
              <div className="notifications-step__preview-body">
                <strong>Appointment Reminder</strong>
                <p>
                  Hi [Client Name], this is a reminder that you have an appointment
                  with [LO Name] in {reminderPreview.time}. Reply CONFIRM to confirm or
                  call us to reschedule.
                </p>
              </div>
            </div>
          </div>
        )}
      </AccordionSection>

      {/* ================================================================
          Section 2: Event Alerts
          ================================================================ */}
      <AccordionSection
        sectionKey="eventAlerts"
        title="Event Alerts"
        icon="fa-bolt"
        description="Notifications for calendar events"
        expanded={!!expandedSections.eventAlerts}
        onToggle={toggleSection}
        sectionEnabled={Object.values(eventAlerts).some(a => a.enabled)}
      >
        <div className="notifications-step__alerts-list">
          {/* New Booking */}
          <div className="notifications-step__alert-row">
            <div className="notifications-step__alert-config">
              <Toggle
                checked={eventAlerts.newBooking.enabled}
                onChange={v => updateEventAlert('newBooking', 'enabled', v)}
                label="New booking notification"
                hint="Get notified when a client books an appointment"
              />
              {eventAlerts.newBooking.enabled && (
                <div className="notifications-step__alert-channel">
                  <ChannelRadio
                    value={eventAlerts.newBooking.channel}
                    onChange={v => updateEventAlert('newBooking', 'channel', v)}
                    name="alert-new-booking"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Cancellation */}
          <div className="notifications-step__alert-row">
            <div className="notifications-step__alert-config">
              <Toggle
                checked={eventAlerts.cancellation.enabled}
                onChange={v => updateEventAlert('cancellation', 'enabled', v)}
                label="Cancellation notification"
                hint="Get notified when a client cancels"
              />
              {eventAlerts.cancellation.enabled && (
                <div className="notifications-step__alert-channel">
                  <ChannelRadio
                    value={eventAlerts.cancellation.channel}
                    onChange={v => updateEventAlert('cancellation', 'channel', v)}
                    name="alert-cancellation"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Reschedule */}
          <div className="notifications-step__alert-row">
            <div className="notifications-step__alert-config">
              <Toggle
                checked={eventAlerts.reschedule.enabled}
                onChange={v => updateEventAlert('reschedule', 'enabled', v)}
                label="Reschedule notification"
                hint="Get notified when a client reschedules"
              />
              {eventAlerts.reschedule.enabled && (
                <div className="notifications-step__alert-channel">
                  <ChannelRadio
                    value={eventAlerts.reschedule.channel}
                    onChange={v => updateEventAlert('reschedule', 'channel', v)}
                    name="alert-reschedule"
                  />
                </div>
              )}
            </div>
          </div>

          {/* No-Show */}
          <div className="notifications-step__alert-row">
            <div className="notifications-step__alert-config">
              <Toggle
                checked={eventAlerts.noShow.enabled}
                onChange={v => updateEventAlert('noShow', 'enabled', v)}
                label="No-show alert"
                hint="Get alerted when a client does not show up"
              />
              {eventAlerts.noShow.enabled && (
                <div className="notifications-step__alert-detail">
                  <label className="notifications-step__inline-label">
                    Alert after
                    <input
                      type="number"
                      min={5}
                      max={60}
                      step={5}
                      value={eventAlerts.noShow.delayMinutes}
                      onChange={e => updateEventAlert('noShow', 'delayMinutes', Math.min(60, Math.max(5, parseInt(e.target.value, 10) || 5)))}
                      className="notifications-step__inline-input"
                      aria-label="No-show delay minutes"
                    />
                    minutes past start
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* Daily Summary */}
          <div className="notifications-step__alert-row">
            <div className="notifications-step__alert-config">
              <Toggle
                checked={eventAlerts.dailySummary.enabled}
                onChange={v => updateEventAlert('dailySummary', 'enabled', v)}
                label="Daily summary"
                hint="Receive a summary of the day's appointments each morning"
              />
              {eventAlerts.dailySummary.enabled && (
                <div className="notifications-step__alert-detail">
                  <label className="notifications-step__inline-label">
                    Deliver at
                    <input
                      type="time"
                      value={eventAlerts.dailySummary.time}
                      onChange={e => updateEventAlert('dailySummary', 'time', e.target.value)}
                      className="notifications-step__time-input"
                      aria-label="Daily summary delivery time"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>
        </div>
      </AccordionSection>

      {/* ================================================================
          Section 3: Quiet Hours
          ================================================================ */}
      <AccordionSection
        sectionKey="quietHours"
        title="Quiet Hours"
        icon="fa-moon"
        description={quietHours.enabled ? `${formatTime12(quietHours.start)} - ${formatTime12(quietHours.end)}` : 'Off'}
        expanded={!!expandedSections.quietHours}
        onToggle={toggleSection}
        sectionEnabled={quietHours.enabled}
        onSectionToggle={v => updateQuietHours('enabled', v)}
      >
        {quietHours.enabled && (
          <div className="notifications-step__quiet-content">
            <div className="notifications-step__quiet-layout">
              <div className="notifications-step__quiet-controls">
                <div className="notifications-step__quiet-time-row">
                  <label className="notifications-step__field-label">
                    Start
                    <input
                      type="time"
                      value={quietHours.start}
                      onChange={e => updateQuietHours('start', e.target.value)}
                      className="notifications-step__time-input"
                      aria-label="Quiet hours start time"
                    />
                  </label>
                  <span className="notifications-step__quiet-separator">to</span>
                  <label className="notifications-step__field-label">
                    End
                    <input
                      type="time"
                      value={quietHours.end}
                      onChange={e => updateQuietHours('end', e.target.value)}
                      className="notifications-step__time-input"
                      aria-label="Quiet hours end time"
                    />
                  </label>
                </div>

                <div className="notifications-step__quiet-weekend">
                  <Toggle
                    checked={quietHours.weekends}
                    onChange={v => updateQuietHours('weekends', v)}
                    label="Include weekends"
                    hint="Apply quiet hours all day on Saturday and Sunday"
                  />
                </div>

                <div className="notifications-step__quiet-info">
                  <i className="fas fa-info-circle" aria-hidden="true" />
                  <span>Notifications received during quiet hours will be queued and delivered when quiet hours end.</span>
                </div>
              </div>

              <QuietHoursClock
                start={quietHours.start}
                end={quietHours.end}
                weekends={quietHours.weekends}
              />
            </div>
          </div>
        )}
        {!quietHours.enabled && (
          <div className="notifications-step__disabled-hint">
            Enable quiet hours to configure when notifications should be paused.
          </div>
        )}
      </AccordionSection>

      {/* ================================================================
          Section 4: Digest Settings
          ================================================================ */}
      <AccordionSection
        sectionKey="digest"
        title="Digest Settings"
        icon="fa-newspaper"
        description="Summary email preferences"
        expanded={!!expandedSections.digest}
        onToggle={toggleSection}
        sectionEnabled={digest.daily.enabled || digest.weekly.enabled}
      >
        <div className="notifications-step__digest-content">
          {/* Daily digest */}
          <div className="notifications-step__digest-row">
            <Toggle
              checked={digest.daily.enabled}
              onChange={v => updateDigestToggle('daily', 'enabled', v)}
              label="Daily digest"
              hint="Receive a daily summary of appointments and activity"
            />
            {digest.daily.enabled && (
              <div className="notifications-step__digest-config">
                <label className="notifications-step__inline-label">
                  Deliver at
                  <input
                    type="time"
                    value={digest.daily.time}
                    onChange={e => updateDigestToggle('daily', 'time', e.target.value)}
                    className="notifications-step__time-input"
                    aria-label="Daily digest delivery time"
                  />
                </label>
              </div>
            )}
          </div>

          {/* Weekly digest */}
          <div className="notifications-step__digest-row">
            <Toggle
              checked={digest.weekly.enabled}
              onChange={v => updateDigestToggle('weekly', 'enabled', v)}
              label="Weekly digest"
              hint="Receive a weekly summary of your calendar activity"
            />
            {digest.weekly.enabled && (
              <div className="notifications-step__digest-config">
                <label className="notifications-step__inline-label">
                  Every
                  <select
                    value={digest.weekly.day}
                    onChange={e => updateDigestToggle('weekly', 'day', e.target.value)}
                    className="notifications-step__custom-select"
                    aria-label="Weekly digest day"
                  >
                    {DAYS_OF_WEEK.map(d => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                  at
                  <input
                    type="time"
                    value={digest.weekly.time}
                    onChange={e => updateDigestToggle('weekly', 'time', e.target.value)}
                    className="notifications-step__time-input"
                    aria-label="Weekly digest delivery time"
                  />
                </label>
              </div>
            )}
          </div>

          {/* Content checkboxes */}
          {(digest.daily.enabled || digest.weekly.enabled) && (
            <>
              <div className="notifications-step__digest-section-label">Digest Content</div>
              <div className="notifications-step__digest-checks">
                <label className="notifications-step__checkbox-label">
                  <input
                    type="checkbox"
                    checked={digest.content.upcomingAppointments}
                    onChange={e => updateDigestContent('upcomingAppointments', e.target.checked)}
                  />
                  <i className="fas fa-calendar-check" aria-hidden="true" />
                  Upcoming appointments
                </label>
                <label className="notifications-step__checkbox-label">
                  <input
                    type="checkbox"
                    checked={digest.content.cancellations}
                    onChange={e => updateDigestContent('cancellations', e.target.checked)}
                  />
                  <i className="fas fa-times-circle" aria-hidden="true" />
                  Cancellations
                </label>
                <label className="notifications-step__checkbox-label">
                  <input
                    type="checkbox"
                    checked={digest.content.analytics}
                    onChange={e => updateDigestContent('analytics', e.target.checked)}
                  />
                  <i className="fas fa-chart-bar" aria-hidden="true" />
                  Analytics summary
                </label>
                <label className="notifications-step__checkbox-label">
                  <input
                    type="checkbox"
                    checked={digest.content.teamActivity}
                    onChange={e => updateDigestContent('teamActivity', e.target.checked)}
                  />
                  <i className="fas fa-users" aria-hidden="true" />
                  Team activity
                </label>
              </div>

              <DigestPreviewCard digest={digest} />
            </>
          )}
        </div>
      </AccordionSection>

      {/* ================================================================
          Section 5: Browser Notifications
          ================================================================ */}
      <AccordionSection
        sectionKey="browser"
        title="Browser Notifications"
        icon="fa-desktop"
        description={browser.enabled && browserPermission === 'granted' ? 'Enabled' : 'Off'}
        expanded={!!expandedSections.browser}
        onToggle={toggleSection}
        sectionEnabled={browser.enabled && browserPermission === 'granted'}
      >
        <div className="notifications-step__browser-content">
          <Toggle
            checked={browser.enabled}
            onChange={v => setBrowser(prev => ({ ...prev, enabled: v }))}
            label="Enable desktop notifications"
            hint="Receive push notifications in your browser for appointments and alerts"
            disabled={browserPermission === 'denied' || browserPermission === 'unsupported'}
          />

          {/* Permission status */}
          <div className="notifications-step__permission-row">
            <span className="notifications-step__field-label">Browser permission:</span>
            <span className={`notifications-step__permission-badge ${permissionStatusClass}`}>
              <i className={`fas ${browserPermission === 'granted' ? 'fa-check-circle' : browserPermission === 'denied' ? 'fa-times-circle' : 'fa-question-circle'}`} aria-hidden="true" />
              {permissionStatusLabel}
            </span>
          </div>

          {browserPermission !== 'granted' && browserPermission !== 'unsupported' && (
            <button
              type="button"
              className="notifications-step__btn-primary"
              onClick={requestBrowserPermission}
            >
              <i className="fas fa-bell" aria-hidden="true" /> Request Permission
            </button>
          )}

          {browserPermission === 'denied' && (
            <div className="notifications-step__warning">
              <i className="fas fa-exclamation-triangle" aria-hidden="true" />
              <span>Permission was denied. You can change this in your browser's site settings.</span>
            </div>
          )}

          {browser.enabled && browserPermission === 'granted' && (
            <>
              <div className="notifications-step__browser-options">
                <Toggle
                  checked={browser.sound}
                  onChange={v => setBrowser(prev => ({ ...prev, sound: v }))}
                  label="Notification sound"
                  hint="Play a sound when a notification arrives"
                />
              </div>

              <button
                type="button"
                className="notifications-step__btn-secondary notifications-step__preview-btn"
                onClick={showDemoNotification}
              >
                <i className="fas fa-eye" aria-hidden="true" /> Preview Notification
              </button>
            </>
          )}
        </div>
      </AccordionSection>

      {/* Summary info */}
      <div className="notifications-step__summary">
        <i className="fas fa-info-circle" aria-hidden="true" />
        <span>
          You can adjust notification preferences anytime from Calendar Settings.
          Changes are saved automatically as you configure.
        </span>
      </div>
    </div>
  );
}
