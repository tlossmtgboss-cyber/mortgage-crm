import React, { useCallback } from 'react';

/**
 * DigestSettings - Configure daily/weekly email digest of upcoming appointments.
 *
 * Props:
 *   digest          - Object: { enabled, frequency, send_time, include_cancelled, include_no_shows, day_of_week }
 *   onChange        - Callback(updatedDigest) when any field changes
 */

const FREQUENCY_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekdays', label: 'Weekdays only (Mon-Fri)' },
  { value: 'weekly', label: 'Weekly' },
];

const DAY_OPTIONS = [
  { value: 'monday', label: 'Monday' },
  { value: 'tuesday', label: 'Tuesday' },
  { value: 'wednesday', label: 'Wednesday' },
  { value: 'thursday', label: 'Thursday' },
  { value: 'friday', label: 'Friday' },
  { value: 'saturday', label: 'Saturday' },
  { value: 'sunday', label: 'Sunday' },
];

export default function DigestSettings({ digest, onChange }) {
  const d = digest || {
    enabled: false,
    frequency: 'daily',
    send_time: '07:00',
    include_cancelled: false,
    include_no_shows: true,
    day_of_week: 'monday',
  };

  const update = useCallback((field, value) => {
    onChange({ ...d, [field]: value });
  }, [d, onChange]);

  return (
    <div className="digest-settings">
      {/* Enable toggle */}
      <label className="digest-toggle-row">
        <label className="toggle-switch">
          <input
            type="checkbox"
            checked={d.enabled}
            onChange={e => update('enabled', e.target.checked)}
            aria-label="Enable daily digest"
          />
          <span className="toggle-slider"></span>
        </label>
        <div className="digest-toggle-label">
          <span className="digest-toggle-title">Enable email digest</span>
          <span className="digest-toggle-desc">Receive a summary of your upcoming appointments</span>
        </div>
      </label>

      {d.enabled && (
        <div className="digest-options">
          {/* Frequency */}
          <div className="digest-field">
            <label className="digest-field-label">Frequency</label>
            <select
              value={d.frequency}
              onChange={e => update('frequency', e.target.value)}
              className="digest-select"
            >
              {FREQUENCY_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Day of week (only for weekly) */}
          {d.frequency === 'weekly' && (
            <div className="digest-field">
              <label className="digest-field-label">Send on</label>
              <select
                value={d.day_of_week}
                onChange={e => update('day_of_week', e.target.value)}
                className="digest-select"
              >
                {DAY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Send time */}
          <div className="digest-field">
            <label className="digest-field-label">Send time</label>
            <input
              type="time"
              value={d.send_time}
              onChange={e => update('send_time', e.target.value)}
              className="digest-time-input"
              aria-label="Digest send time"
            />
            <span className="field-hint">You'll receive the digest at this time each day</span>
          </div>

          {/* Include toggles */}
          <div className="digest-include-options">
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={d.include_cancelled}
                onChange={e => update('include_cancelled', e.target.checked)}
              />
              <span>Include cancelled appointments in digest</span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={d.include_no_shows}
                onChange={e => update('include_no_shows', e.target.checked)}
              />
              <span>Include no-show reports in digest</span>
            </label>
          </div>

          {/* Preview */}
          <div className="digest-preview">
            <div className="digest-preview-header">
              <i className="fas fa-envelope" aria-hidden="true"></i>
              <span>Preview</span>
            </div>
            <div className="digest-preview-body">
              <strong>Your {d.frequency === 'daily' ? 'Daily' : d.frequency === 'weekdays' ? 'Weekday' : 'Weekly'} Calendar Digest</strong>
              <p>Sent {d.frequency === 'weekly' ? `every ${DAY_OPTIONS.find(o => o.value === d.day_of_week)?.label || 'Monday'}` : d.frequency === 'weekdays' ? 'Mon-Fri' : 'every day'} at {formatTime(d.send_time)}</p>
              <div className="digest-preview-items">
                <div className="digest-preview-item">
                  <span className="digest-dot" style={{ background: '#1F3D2E' }}></span>
                  <span>3 upcoming appointments</span>
                </div>
                {d.include_cancelled && (
                  <div className="digest-preview-item">
                    <span className="digest-dot" style={{ background: '#ef4444' }}></span>
                    <span>1 cancellation</span>
                  </div>
                )}
                {d.include_no_shows && (
                  <div className="digest-preview-item">
                    <span className="digest-dot" style={{ background: '#f59e0b' }}></span>
                    <span>0 no-shows</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatTime(timeStr) {
  if (!timeStr) return '';
  const [h, m] = timeStr.split(':').map(Number);
  const ampm = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m).padStart(2, '0')} ${ampm}`;
}
