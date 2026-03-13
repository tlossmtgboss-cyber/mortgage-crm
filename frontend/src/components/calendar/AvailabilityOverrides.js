/**
 * AvailabilityOverrides
 *
 * Date-specific availability overrides component.
 * Allows creating date exceptions (blocked days or custom hours)
 * and displays the list of existing overrides with remove functionality.
 *
 * Props:
 *   overrides       - Array of override objects from the API
 *   onAddOverride   - (overrideData) => void
 *   onRemoveOverride - (overrideId) => void
 *   loading         - Boolean for loading state
 */

import React, { useState, useCallback } from 'react';

const OVERRIDE_TYPES = {
  BLOCKED_ALL_DAY: 'blocked_all_day',
  BLOCKED_HOURS: 'blocked_hours',
  EXTRA_HOURS: 'extra_hours',
};

// Generate time options in 15-minute increments
const TIME_OPTIONS = (() => {
  const opts = [];
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += 15) {
      const hh = String(h).padStart(2, '0');
      const mm = String(m).padStart(2, '0');
      const value = `${hh}:${mm}`;
      const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
      const ampm = h < 12 ? 'AM' : 'PM';
      const label = `${hour12}:${mm} ${ampm}`;
      opts.push({ value, label });
    }
  }
  return opts;
})();

function formatDisplayDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T12:00:00');
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDisplayTime(timeStr) {
  if (!timeStr) return '';
  const [h, m] = timeStr.split(':').map(Number);
  const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  const ampm = h < 12 ? 'AM' : 'PM';
  return `${hour12}:${String(m).padStart(2, '0')} ${ampm}`;
}

function AvailabilityOverrides({ overrides = [], onAddOverride, onRemoveOverride, loading }) {
  const [overrideDate, setOverrideDate] = useState('');
  const [overrideType, setOverrideType] = useState(OVERRIDE_TYPES.BLOCKED_ALL_DAY);
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('17:00');
  const [reason, setReason] = useState('');

  const today = new Date().toISOString().split('T')[0];

  const handleAdd = useCallback(() => {
    if (!overrideDate) return;

    const payload = {
      date: overrideDate,
      is_blocked: overrideType !== OVERRIDE_TYPES.EXTRA_HOURS,
      reason: reason.trim() || null,
    };

    if (overrideType === OVERRIDE_TYPES.BLOCKED_ALL_DAY) {
      payload.start_time = null;
      payload.end_time = null;
    } else {
      payload.start_time = startTime;
      payload.end_time = endTime;
    }

    onAddOverride(payload);

    // Reset form
    setOverrideDate('');
    setOverrideType(OVERRIDE_TYPES.BLOCKED_ALL_DAY);
    setStartTime('09:00');
    setEndTime('17:00');
    setReason('');
  }, [overrideDate, overrideType, startTime, endTime, reason, onAddOverride]);

  const showTimeInputs = overrideType !== OVERRIDE_TYPES.BLOCKED_ALL_DAY;
  const isValid = overrideDate && overrideDate >= today && (!showTimeInputs || startTime < endTime);

  // Sort overrides by date, most recent first
  const sortedOverrides = [...overrides].sort((a, b) => {
    if (a.date < b.date) return -1;
    if (a.date > b.date) return 1;
    return 0;
  });

  // Split into past and upcoming
  const upcomingOverrides = sortedOverrides.filter((o) => o.date >= today);
  const pastOverrides = sortedOverrides.filter((o) => o.date < today);

  return (
    <div className="avail-overrides-section">
      {/* Add override form */}
      <div className="avail-override-form">
        <div className="avail-override-field">
          <label htmlFor="override-date">Date</label>
          <input
            id="override-date"
            type="date"
            value={overrideDate}
            min={today}
            onChange={(e) => setOverrideDate(e.target.value)}
          />
        </div>

        <div className="avail-override-field">
          <label>Type</label>
          <div className="avail-override-type-row">
            <label className="avail-override-type-option">
              <input
                type="radio"
                name="override-type"
                value={OVERRIDE_TYPES.BLOCKED_ALL_DAY}
                checked={overrideType === OVERRIDE_TYPES.BLOCKED_ALL_DAY}
                onChange={(e) => setOverrideType(e.target.value)}
              />
              Unavailable all day
            </label>
            <label className="avail-override-type-option">
              <input
                type="radio"
                name="override-type"
                value={OVERRIDE_TYPES.BLOCKED_HOURS}
                checked={overrideType === OVERRIDE_TYPES.BLOCKED_HOURS}
                onChange={(e) => setOverrideType(e.target.value)}
              />
              Block specific hours
            </label>
            <label className="avail-override-type-option">
              <input
                type="radio"
                name="override-type"
                value={OVERRIDE_TYPES.EXTRA_HOURS}
                checked={overrideType === OVERRIDE_TYPES.EXTRA_HOURS}
                onChange={(e) => setOverrideType(e.target.value)}
              />
              Extra availability
            </label>
          </div>
        </div>

        {showTimeInputs && (
          <div className="avail-override-field">
            <label>Hours</label>
            <div className="avail-override-times">
              <select
                className="avail-time-select"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                aria-label="Override start time"
              >
                {TIME_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <span className="avail-time-separator">to</span>
              <select
                className="avail-time-select"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                aria-label="Override end time"
              >
                {TIME_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className="avail-override-field">
          <label htmlFor="override-reason">Reason (optional)</label>
          <input
            id="override-reason"
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g., Vacation, Doctor appointment"
            maxLength={500}
          />
        </div>

        <button
          type="button"
          className="avail-add-override-btn"
          onClick={handleAdd}
          disabled={!isValid || loading}
        >
          <i className="fas fa-plus" /> Add Override
        </button>
      </div>

      {/* Overrides list */}
      {upcomingOverrides.length === 0 && pastOverrides.length === 0 ? (
        <div className="avail-overrides-empty">
          <i className="fas fa-calendar-check" />
          <p>No date overrides set. Add one above for vacation days, holidays, or special hours.</p>
        </div>
      ) : (
        <>
          {upcomingOverrides.length > 0 && (
            <div className="avail-overrides-list">
              {upcomingOverrides.map((override) => (
                <div
                  key={override.id}
                  className={`avail-override-card ${override.is_blocked ? 'is-blocked' : 'is-extra'}`}
                >
                  <div className="avail-override-info">
                    <span className="avail-override-date">
                      {formatDisplayDate(override.date)}
                    </span>
                    <span className="avail-override-detail">
                      <span className={`avail-override-badge ${override.is_blocked ? 'blocked' : 'extra'}`}>
                        {override.is_blocked ? 'Blocked' : 'Extra'}
                      </span>
                      {override.start_time && override.end_time
                        ? `${formatDisplayTime(override.start_time)} - ${formatDisplayTime(override.end_time)}`
                        : 'All day'}
                    </span>
                    {override.reason && (
                      <span className="avail-override-reason">{override.reason}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="avail-override-remove"
                    onClick={() => onRemoveOverride(override.id)}
                    title="Remove this override"
                    aria-label={`Remove override for ${formatDisplayDate(override.date)}`}
                    disabled={loading}
                  >
                    <i className="fas fa-trash-alt" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {pastOverrides.length > 0 && (
            <>
              <h4 style={{ fontSize: '13px', color: '#94a3b8', margin: '20px 0 8px', fontWeight: 500 }}>
                Past overrides ({pastOverrides.length})
              </h4>
              <div className="avail-overrides-list" style={{ opacity: 0.6 }}>
                {pastOverrides.map((override) => (
                  <div
                    key={override.id}
                    className={`avail-override-card ${override.is_blocked ? 'is-blocked' : 'is-extra'}`}
                  >
                    <div className="avail-override-info">
                      <span className="avail-override-date">
                        {formatDisplayDate(override.date)}
                      </span>
                      <span className="avail-override-detail">
                        <span className={`avail-override-badge ${override.is_blocked ? 'blocked' : 'extra'}`}>
                          {override.is_blocked ? 'Blocked' : 'Extra'}
                        </span>
                        {override.start_time && override.end_time
                          ? `${formatDisplayTime(override.start_time)} - ${formatDisplayTime(override.end_time)}`
                          : 'All day'}
                      </span>
                      {override.reason && (
                        <span className="avail-override-reason">{override.reason}</span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="avail-override-remove"
                      onClick={() => onRemoveOverride(override.id)}
                      title="Remove this override"
                      aria-label={`Remove override for ${formatDisplayDate(override.date)}`}
                      disabled={loading}
                    >
                      <i className="fas fa-trash-alt" />
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default React.memo(AvailabilityOverrides);
