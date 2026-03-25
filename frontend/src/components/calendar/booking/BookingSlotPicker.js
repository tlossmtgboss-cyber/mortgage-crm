/**
 * BookingSlotPicker - Date and time slot selection for the booking widget.
 *
 * Displays a week-based date picker with navigation and a time-slot grid.
 *
 * Props:
 *   weekDates      - Array of 7 Date objects for the current week
 *   selectedDate   - Currently selected Date (or null)
 *   onSelectDate   - Callback(date) when a date is selected
 *   onPrevWeek     - Callback to navigate to previous week
 *   onNextWeek     - Callback to navigate to next week
 *   availableSlots - Array of slot objects with { start_time, display }
 *   selectedTime   - Currently selected time string
 *   onSelectTime   - Callback(timeStr) when a time slot is selected
 *   styles         - Style objects from the parent widget
 *   accentColor    - Brand accent color
 */
import React from 'react';

// ---- Date helpers ----

function formatDayShort(date) {
  return date.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase();
}

function isPast(date) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return date < today;
}

function isToday(date) {
  return date.toDateString() === new Date().toDateString();
}

export default function BookingSlotPicker({
  weekDates,
  selectedDate,
  onSelectDate,
  onPrevWeek,
  onNextWeek,
  availableSlots,
  selectedTime,
  onSelectTime,
  styles,
  accentColor,
}) {
  // Format a date for use in aria-labels
  function formatDateLong(date) {
    return date.toLocaleDateString(undefined, {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  }

  return (
    <>
      {/* Date picker */}
      <div style={styles.section}>
        <label style={styles.label} id="bw-date-label">Select a Date</label>
        <div style={styles.weekNav} role="group" aria-labelledby="bw-date-label">
          <button
            onClick={onPrevWeek}
            disabled={isPast(weekDates[0])}
            style={styles.navBtn}
            aria-label="Previous week"
          >
            &lsaquo;
          </button>
          <div style={styles.weekDates} role="listbox" aria-labelledby="bw-date-label">
            {weekDates.map((date, idx) => {
              const disabled = isPast(date);
              const selected =
                selectedDate && date.toDateString() === selectedDate.toDateString();
              const dateLabel = formatDateLong(date);
              return (
                <button
                  key={idx}
                  onClick={() => !disabled && onSelectDate(date)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      if (!disabled) onSelectDate(date);
                    }
                  }}
                  disabled={disabled}
                  role="option"
                  aria-selected={selected}
                  aria-label={`${dateLabel}${isToday(date) ? ', today' : ''}${selected ? ', selected' : ''}`}
                  style={{
                    ...styles.dateCard,
                    ...(selected
                      ? {
                          ...styles.dateCardSelected,
                          backgroundColor: accentColor,
                          borderColor: accentColor,
                        }
                      : {}),
                    ...(disabled ? styles.dateCardDisabled : {}),
                    ...(isToday(date) && !selected ? styles.dateCardToday : {}),
                  }}
                >
                  <span style={styles.dayName} aria-hidden="true">{formatDayShort(date)}</span>
                  <span
                    aria-hidden="true"
                    style={{
                      ...styles.dayNumber,
                      ...(selected ? { color: '#fff' } : {}),
                    }}
                  >
                    {date.getDate()}
                  </span>
                </button>
              );
            })}
          </div>
          <button onClick={onNextWeek} style={styles.navBtn} aria-label="Next week">
            &rsaquo;
          </button>
        </div>
      </div>

      {/* Time slot grid */}
      <div style={styles.section}>
        <label style={styles.label} id="bw-time-label">Select a Time</label>
        {availableSlots.length === 0 ? (
          <p style={styles.noSlots} role="status">No available times for this date.</p>
        ) : (
          <div
            style={styles.timeGrid}
            role="listbox"
            aria-labelledby="bw-time-label"
          >
            {availableSlots.map((slot, idx) => {
              const selected = selectedTime === slot.start_time;
              const selectedDateStr = selectedDate
                ? selectedDate.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
                : '';
              return (
                <button
                  key={idx}
                  onClick={() => onSelectTime(slot.start_time)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectTime(slot.start_time);
                    }
                  }}
                  role="option"
                  aria-selected={selected}
                  aria-label={`Book appointment at ${slot.display} on ${selectedDateStr}${selected ? ', selected' : ''}`}
                  tabIndex={0}
                  style={{
                    ...styles.timeSlot,
                    ...(selected
                      ? {
                          ...styles.timeSlotSelected,
                          backgroundColor: accentColor,
                          borderColor: accentColor,
                        }
                      : {}),
                  }}
                >
                  {slot.display}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
