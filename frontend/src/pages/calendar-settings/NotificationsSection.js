/**
 * NotificationsSection - Calendar Settings
 *
 * Handles reminder toggles, event alerts, daily digest, quiet hours, and browser notifications.
 */
import React, { useState } from 'react';
import ReminderSettings from '../../components/calendar/ReminderSettings';
import DigestSettings from '../../components/calendar/DigestSettings';
import { toast } from '../../utils/toast';

const EVENT_ALERT_TYPES = [
  { key: 'alert_new_booking', label: 'New booking received', icon: 'fa-calendar-plus' },
  { key: 'alert_cancellation', label: 'Appointment cancelled', icon: 'fa-calendar-times' },
  { key: 'alert_reschedule', label: 'Appointment rescheduled', icon: 'fa-calendar-alt' },
  { key: 'alert_no_show', label: 'No-show detected', icon: 'fa-user-slash' },
  { key: 'alert_waitlist_opened', label: 'Waitlist slot opened', icon: 'fa-list-ol' },
  { key: 'alert_survey_response', label: 'Survey response received', icon: 'fa-poll' },
];

const ALERT_CHANNEL_OPTIONS = [
  { value: 'email', label: 'Email' },
  { value: 'push', label: 'Push' },
  { value: 'both', label: 'Both' },
  { value: 'none', label: 'None' },
];

export default function NotificationsSection({
  notifications,
  setNotifications,
  markChanged,
}) {
  const [notifSections, setNotifSections] = useState({
    reminders: true,
    alerts: true,
    digest: false,
    quiet: false,
    browser: false,
  });
  const [browserPermission, setBrowserPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default'
  );

  const toggleNotifSection = (sectionId) => {
    setNotifSections(prev => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };

  const updateNotif = (key, value) => {
    setNotifications(prev => ({ ...prev, [key]: value }));
    markChanged();
  };

  const handleRequestBrowserPermission = async () => {
    if (typeof Notification === 'undefined') {
      toast.error('Browser notifications are not supported in this browser');
      return;
    }
    try {
      const result = await Notification.requestPermission();
      setBrowserPermission(result);
      if (result === 'granted') {
        updateNotif('browser_notifications_enabled', true);
        toast.success('Browser notifications enabled');
      } else if (result === 'denied') {
        toast.error('Browser notification permission was denied. You can change this in your browser settings.');
      }
    } catch (err) {
      toast.error('Failed to request notification permission');
    }
  };

  const handleTestNotification = () => {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') {
      toast.error('Browser notifications are not enabled');
      return;
    }
    new Notification('Perennia AI - Test Notification', {
      body: 'Your browser notifications are working correctly.',
      icon: '/favicon.ico',
    });
    toast.success('Test notification sent');
  };

  const computeQuietArc = () => {
    const parseTime = (t) => {
      const [h, m] = (t || '00:00').split(':').map(Number);
      return h + m / 60;
    };
    const startH = parseTime(notifications.quiet_hours_start);
    const endH = parseTime(notifications.quiet_hours_end);
    const startAngle = (startH / 24) * 360 - 90;
    const endAngle = (endH / 24) * 360 - 90;
    return { startAngle, endAngle };
  };

  const describeArc = (cx, cy, r, startAngle, endAngle) => {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const start = { x: cx + r * Math.cos(toRad(startAngle)), y: cy + r * Math.sin(toRad(startAngle)) };
    const end = { x: cx + r * Math.cos(toRad(endAngle)), y: cy + r * Math.sin(toRad(endAngle)) };
    let sweep = endAngle - startAngle;
    if (sweep < 0) sweep += 360;
    const largeArc = sweep > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  };

  const activeReminders = [
    notifications.email_reminder_24h && { label: '24h', channel: 'Email', minutes: 1440 },
    notifications.email_reminder_2h && { label: '2h', channel: 'Email', minutes: 120 },
    notifications.email_reminder_15m && { label: '15m', channel: 'Email', minutes: 15 },
    notifications.sms_reminder_24h && { label: '24h', channel: 'SMS', minutes: 1440 },
    notifications.sms_reminder_2h && { label: '2h', channel: 'SMS', minutes: 120 },
    notifications.sms_reminder_15m && { label: '15m', channel: 'SMS', minutes: 15 },
  ].filter(Boolean).sort((a, b) => b.minutes - a.minutes);

  return (
    <section className="cal-settings-section notif-enhanced-section" role="tabpanel" id="panel-notifications" aria-labelledby="calnav-notifications">
      <h2><i className="fas fa-bell" aria-hidden="true"></i> Notification Preferences</h2>
      <p className="section-description">Control how and when you receive notifications about your calendar events.</p>

      {/* ---- Section 1: Appointment Reminders ---- */}
      <div className="notif-collapsible-section">
        <button
          type="button"
          className="notif-section-header"
          onClick={() => toggleNotifSection('reminders')}
          aria-expanded={notifSections.reminders}
        >
          <div className="notif-section-header-left">
            <i className="fas fa-clock" aria-hidden="true"></i>
            <div>
              <span className="notif-section-title">Appointment Reminders</span>
              <span className="notif-section-desc">Configure automated reminders sent before each appointment</span>
            </div>
          </div>
          <i className={`fas fa-chevron-${notifSections.reminders ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
        </button>

        {notifSections.reminders && (
          <div className="notif-section-body">
            {/* Visual reminder timeline */}
            {activeReminders.length > 0 && (
              <div className="reminder-timeline">
                <div className="reminder-timeline-label">Reminder Timeline</div>
                <div className="reminder-timeline-track">
                  <div className="reminder-timeline-line"></div>
                  {activeReminders.map((r) => {
                    const maxMin = 1440;
                    const pct = Math.max(5, Math.min(95, ((maxMin - r.minutes) / maxMin) * 100));
                    return (
                      <div
                        key={`${r.channel}-${r.label}`}
                        className="reminder-timeline-marker"
                        style={{ left: `${pct}%` }}
                        title={`${r.channel} - ${r.label} before`}
                      >
                        <div className={`reminder-marker-dot ${r.channel === 'Email' ? 'marker-email' : 'marker-sms'}`}></div>
                        <div className="reminder-marker-label">{r.channel} {r.label}</div>
                      </div>
                    );
                  })}
                  <div className="reminder-timeline-marker" style={{ left: '100%' }}>
                    <div className="reminder-marker-dot marker-event"></div>
                    <div className="reminder-marker-label">Appointment</div>
                  </div>
                  <div className="reminder-timeline-start-label">24h before</div>
                  <div className="reminder-timeline-end-label">Start time</div>
                </div>
              </div>
            )}

            <ReminderSettings />
          </div>
        )}
      </div>

      {/* ---- Section 2: Event Alerts ---- */}
      <div className="notif-collapsible-section">
        <button
          type="button"
          className="notif-section-header"
          onClick={() => toggleNotifSection('alerts')}
          aria-expanded={notifSections.alerts}
        >
          <div className="notif-section-header-left">
            <i className="fas fa-exclamation-circle" aria-hidden="true"></i>
            <div>
              <span className="notif-section-title">Event Alerts</span>
              <span className="notif-section-desc">Choose how you are notified for each type of calendar event</span>
            </div>
          </div>
          <i className={`fas fa-chevron-${notifSections.alerts ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
        </button>

        {notifSections.alerts && (
          <div className="notif-section-body">
            <div className="event-alerts-grid">
              <div className="event-alerts-header">
                <span className="event-alerts-header-event">Event</span>
                <span className="event-alerts-header-channel">Notification Channel</span>
              </div>
              {EVENT_ALERT_TYPES.map(evt => (
                <div key={evt.key} className="event-alert-row">
                  <div className="event-alert-label">
                    <i className={`fas ${evt.icon}`} aria-hidden="true"></i>
                    <span>{evt.label}</span>
                  </div>
                  <div className="event-alert-channels">
                    {ALERT_CHANNEL_OPTIONS.map(ch => (
                      <label key={ch.value} className={`event-alert-chip ${notifications[evt.key] === ch.value ? 'active' : ''}`}>
                        <input
                          type="radio"
                          name={evt.key}
                          value={ch.value}
                          checked={notifications[evt.key] === ch.value}
                          onChange={() => updateNotif(evt.key, ch.value)}
                        />
                        <span>{ch.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ---- Section 3: Daily Digest ---- */}
      <div className="notif-collapsible-section">
        <button
          type="button"
          className="notif-section-header"
          onClick={() => toggleNotifSection('digest')}
          aria-expanded={notifSections.digest}
        >
          <div className="notif-section-header-left">
            <i className="fas fa-newspaper" aria-hidden="true"></i>
            <div>
              <span className="notif-section-title">Daily Digest</span>
              <span className="notif-section-desc">Receive a daily summary email of your upcoming schedule</span>
            </div>
          </div>
          <i className={`fas fa-chevron-${notifSections.digest ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
        </button>

        {notifSections.digest && (
          <div className="notif-section-body">
            <DigestSettings
              digest={notifications.digest}
              onChange={(updatedDigest) => {
                setNotifications(prev => ({ ...prev, digest: updatedDigest }));
                markChanged();
              }}
            />
          </div>
        )}
      </div>

      {/* ---- Section 4: Quiet Hours ---- */}
      <div className="notif-collapsible-section">
        <button
          type="button"
          className="notif-section-header"
          onClick={() => toggleNotifSection('quiet')}
          aria-expanded={notifSections.quiet}
        >
          <div className="notif-section-header-left">
            <i className="fas fa-moon" aria-hidden="true"></i>
            <div>
              <span className="notif-section-title">Quiet Hours</span>
              <span className="notif-section-desc">Suppress all notifications during specified hours</span>
            </div>
          </div>
          <i className={`fas fa-chevron-${notifSections.quiet ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
        </button>

        {notifSections.quiet && (
          <div className="notif-section-body">
            <div className="quiet-hours-content">
              <div className="quiet-hours-controls">
                <label className="quiet-hours-toggle-row">
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={notifications.quiet_hours_enabled}
                      onChange={(e) => updateNotif('quiet_hours_enabled', e.target.checked)}
                      aria-label="Enable quiet hours"
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  <span>Enable quiet hours</span>
                </label>

                {notifications.quiet_hours_enabled && (
                  <>
                    <div className="quiet-hours-times">
                      <div className="quiet-hours-time-field">
                        <label>Start time</label>
                        <input
                          type="time"
                          value={notifications.quiet_hours_start}
                          onChange={(e) => updateNotif('quiet_hours_start', e.target.value)}
                          aria-label="Quiet hours start"
                        />
                      </div>
                      <span className="time-separator">to</span>
                      <div className="quiet-hours-time-field">
                        <label>End time</label>
                        <input
                          type="time"
                          value={notifications.quiet_hours_end}
                          onChange={(e) => updateNotif('quiet_hours_end', e.target.value)}
                          aria-label="Quiet hours end"
                        />
                      </div>
                    </div>

                    <label className="quiet-hours-toggle-row">
                      <label className="toggle-switch">
                        <input
                          type="checkbox"
                          checked={notifications.quiet_hours_include_weekends}
                          onChange={(e) => updateNotif('quiet_hours_include_weekends', e.target.checked)}
                          aria-label="Include weekends in quiet hours"
                        />
                        <span className="toggle-slider"></span>
                      </label>
                      <span>Include weekends</span>
                    </label>
                  </>
                )}
              </div>

              {notifications.quiet_hours_enabled && (() => {
                const arc = computeQuietArc();
                return (
                  <div className="quiet-hours-clock">
                    <svg viewBox="0 0 120 120" width="140" height="140" aria-label={`Quiet hours from ${notifications.quiet_hours_start} to ${notifications.quiet_hours_end}`}>
                      <circle cx="60" cy="60" r="52" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="2" />
                      <path
                        d={describeArc(60, 60, 44, arc.startAngle, arc.endAngle)}
                        fill="none"
                        stroke="#D4AD6A"
                        strokeWidth="10"
                        strokeLinecap="round"
                        opacity="0.3"
                      />
                      {[0, 3, 6, 9, 12, 15, 18, 21].map(h => {
                        const angle = ((h / 24) * 360 - 90) * (Math.PI / 180);
                        const x1 = 60 + 48 * Math.cos(angle);
                        const y1 = 60 + 48 * Math.sin(angle);
                        const x2 = 60 + 52 * Math.cos(angle);
                        const y2 = 60 + 52 * Math.sin(angle);
                        const tx = 60 + 40 * Math.cos(angle);
                        const ty = 60 + 40 * Math.sin(angle);
                        return (
                          <g key={h}>
                            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#94a3b8" strokeWidth="1.5" />
                            <text x={tx} y={ty} textAnchor="middle" dominantBaseline="central" fontSize="8" fill="#64748b">
                              {h === 0 ? '12a' : h === 12 ? '12p' : h < 12 ? `${h}a` : `${h - 12}p`}
                            </text>
                          </g>
                        );
                      })}
                      <text x="60" y="62" textAnchor="middle" dominantBaseline="central" fontSize="16" aria-hidden="true">
                        {'\uD83C\uDF19'}
                      </text>
                    </svg>
                    <div className="quiet-clock-label">
                      {notifications.quiet_hours_start} - {notifications.quiet_hours_end}
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}
      </div>

      {/* ---- Section 5: Browser Notifications ---- */}
      <div className="notif-collapsible-section">
        <button
          type="button"
          className="notif-section-header"
          onClick={() => toggleNotifSection('browser')}
          aria-expanded={notifSections.browser}
        >
          <div className="notif-section-header-left">
            <i className="fas fa-desktop" aria-hidden="true"></i>
            <div>
              <span className="notif-section-title">Browser Notifications</span>
              <span className="notif-section-desc">Get real-time desktop notifications in your browser</span>
            </div>
          </div>
          <i className={`fas fa-chevron-${notifSections.browser ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
        </button>

        {notifSections.browser && (
          <div className="notif-section-body">
            <div className="browser-notif-content">
              <div className="browser-notif-status">
                <span className="browser-notif-status-label">Permission status:</span>
                <span className={`browser-notif-status-badge status-${browserPermission}`}>
                  {browserPermission === 'granted' ? 'Granted' : browserPermission === 'denied' ? 'Denied' : 'Not Asked'}
                </span>
              </div>

              <div className="browser-notif-actions">
                {browserPermission !== 'granted' && (
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    onClick={handleRequestBrowserPermission}
                    disabled={browserPermission === 'denied'}
                  >
                    <i className="fas fa-bell" aria-hidden="true"></i>
                    {browserPermission === 'denied' ? 'Permission Denied' : 'Enable Browser Notifications'}
                  </button>
                )}
                {browserPermission === 'granted' && (
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={handleTestNotification}
                  >
                    <i className="fas fa-paper-plane" aria-hidden="true"></i>
                    Send Test Notification
                  </button>
                )}
              </div>

              <div className="browser-notif-note">
                <i className="fas fa-info-circle" aria-hidden="true"></i>
                <span>
                  Browser notifications require your browser to be open. They work in Chrome, Firefox, Edge, and Safari.
                  {browserPermission === 'denied' && ' You previously denied permission. To re-enable, update your notification settings in your browser\'s site permissions.'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
