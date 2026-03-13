/**
 * BufferTimeSettings
 *
 * Configures buffer/transition time between appointments.
 * Controls:
 *   - Buffer before meetings (minutes)
 *   - Buffer after meetings (minutes)
 *   - Minimum booking notice (hours)
 *   - Maximum advance booking window (days)
 *
 * Props:
 *   bufferMinutes       - Number, current buffer between meetings
 *   minNoticeHours      - Number, minimum booking notice in hours
 *   maxAdvanceDays      - Number, max days in future clients can book
 *   onChange            - (field, value) => void
 */

import React from 'react';

const BUFFER_OPTIONS = [
  { value: 0, label: 'No buffer' },
  { value: 5, label: '5 minutes' },
  { value: 10, label: '10 minutes' },
  { value: 15, label: '15 minutes' },
  { value: 20, label: '20 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 45, label: '45 minutes' },
  { value: 60, label: '60 minutes' },
];

const NOTICE_OPTIONS = [
  { value: 0, label: 'No minimum' },
  { value: 1, label: '1 hour' },
  { value: 2, label: '2 hours' },
  { value: 4, label: '4 hours' },
  { value: 8, label: '8 hours' },
  { value: 12, label: '12 hours' },
  { value: 24, label: '24 hours (1 day)' },
  { value: 48, label: '48 hours (2 days)' },
  { value: 72, label: '72 hours (3 days)' },
  { value: 168, label: '1 week' },
];

const ADVANCE_OPTIONS = [
  { value: 7, label: '1 week' },
  { value: 14, label: '2 weeks' },
  { value: 30, label: '1 month' },
  { value: 60, label: '2 months' },
  { value: 90, label: '3 months' },
  { value: 180, label: '6 months' },
  { value: 365, label: '1 year' },
];

function BufferTimeSettings({
  bufferMinutes = 5,
  minNoticeHours = 2,
  maxAdvanceDays = 60,
  onChange,
}) {
  return (
    <div className="buffer-time-settings">
      <div className="buffer-settings-grid">
        <div className="buffer-setting-item">
          <div className="buffer-setting-label">
            <i className="fas fa-hourglass-half" />
            <div>
              <span className="buffer-setting-name">Buffer between meetings</span>
              <span className="buffer-setting-hint">
                Padding time before and after each appointment
              </span>
            </div>
          </div>
          <select
            value={bufferMinutes}
            onChange={(e) => onChange('buffer_minutes', parseInt(e.target.value))}
            className="buffer-select"
            aria-label="Buffer between meetings"
          >
            {BUFFER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="buffer-setting-item">
          <div className="buffer-setting-label">
            <i className="fas fa-bell" />
            <div>
              <span className="buffer-setting-name">Minimum booking notice</span>
              <span className="buffer-setting-hint">
                How far in advance clients must book
              </span>
            </div>
          </div>
          <select
            value={minNoticeHours}
            onChange={(e) => onChange('min_booking_notice_hours', parseInt(e.target.value))}
            className="buffer-select"
            aria-label="Minimum booking notice"
          >
            {NOTICE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="buffer-setting-item">
          <div className="buffer-setting-label">
            <i className="fas fa-calendar-alt" />
            <div>
              <span className="buffer-setting-name">Advance booking window</span>
              <span className="buffer-setting-hint">
                How far into the future clients can schedule
              </span>
            </div>
          </div>
          <select
            value={maxAdvanceDays}
            onChange={(e) => onChange('max_advance_booking_days', parseInt(e.target.value))}
            className="buffer-select"
            aria-label="Maximum advance booking days"
          >
            {ADVANCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

export default React.memo(BufferTimeSettings);
