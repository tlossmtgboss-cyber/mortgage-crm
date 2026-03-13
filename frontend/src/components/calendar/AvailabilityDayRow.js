/**
 * AvailabilityDayRow
 *
 * Single day component for the weekly availability schedule.
 * Shows a toggle switch, day label, and one or more time blocks with
 * start/end time dropdowns in 15-minute increments.
 *
 * Props:
 *   dayIndex    - 0 (Monday) through 6 (Sunday)
 *   dayLabel    - Human-readable label (e.g., "Monday")
 *   enabled     - Whether this day is toggled on
 *   blocks      - Array of { start: "HH:MM", end: "HH:MM" }
 *   onToggle    - (dayIndex, enabled) => void
 *   onBlockChange - (dayIndex, blockIndex, field, value) => void
 *   onAddBlock  - (dayIndex) => void
 *   onRemoveBlock - (dayIndex, blockIndex) => void
 */

import React, { useMemo } from 'react';

// Generate time options in 15-minute increments from 00:00 to 23:45
const TIME_OPTIONS = (() => {
  const opts = [];
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += 15) {
      const hh = String(h).padStart(2, '0');
      const mm = String(m).padStart(2, '0');
      const value = `${hh}:${mm}`;
      // Display format: 9:00 AM, 1:30 PM, etc.
      const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
      const ampm = h < 12 ? 'AM' : 'PM';
      const label = `${hour12}:${mm} ${ampm}`;
      opts.push({ value, label });
    }
  }
  return opts;
})();

function AvailabilityDayRow({
  dayIndex,
  dayLabel,
  enabled,
  blocks,
  onToggle,
  onBlockChange,
  onAddBlock,
  onRemoveBlock,
}) {
  const timeOptions = useMemo(() => TIME_OPTIONS, []);

  return (
    <div className={`availability-day-row ${enabled ? '' : 'day-disabled'}`}>
      {/* Toggle switch + day label */}
      <div className="avail-day-toggle">
        <label className="avail-toggle-switch" title={`Toggle ${dayLabel}`}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onToggle(dayIndex, e.target.checked)}
            aria-label={`${dayLabel} availability toggle`}
          />
          <span className="avail-toggle-slider" />
        </label>
        <span className="day-label">{dayLabel}</span>
      </div>

      {/* Time blocks or "Unavailable" */}
      <div className="avail-blocks-container">
        {enabled ? (
          <>
            {blocks.map((block, blockIdx) => (
              <div key={blockIdx} className="avail-time-block">
                <select
                  className="avail-time-select"
                  value={block.start}
                  onChange={(e) => onBlockChange(dayIndex, blockIdx, 'start', e.target.value)}
                  aria-label={`${dayLabel} block ${blockIdx + 1} start time`}
                >
                  {timeOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <span className="avail-time-separator">to</span>
                <select
                  className="avail-time-select"
                  value={block.end}
                  onChange={(e) => onBlockChange(dayIndex, blockIdx, 'end', e.target.value)}
                  aria-label={`${dayLabel} block ${blockIdx + 1} end time`}
                >
                  {timeOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {blocks.length > 1 && (
                  <button
                    type="button"
                    className="avail-remove-block"
                    onClick={() => onRemoveBlock(dayIndex, blockIdx)}
                    title="Remove this time block"
                    aria-label={`Remove ${dayLabel} block ${blockIdx + 1}`}
                  >
                    <i className="fas fa-times" />
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              className="avail-add-block"
              onClick={() => onAddBlock(dayIndex)}
              aria-label={`Add another time block for ${dayLabel}`}
            >
              <i className="fas fa-plus" /> Add another block
            </button>
          </>
        ) : (
          <span className="avail-unavailable-label">Unavailable</span>
        )}
      </div>
    </div>
  );
}

export default React.memo(AvailabilityDayRow);
