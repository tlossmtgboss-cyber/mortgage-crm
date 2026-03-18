/**
 * BookingWidgetConfirmation - Lightweight inline confirmation shown
 * inside the BookingWidget after a successful booking.
 *
 * This is NOT the standalone BookingConfirmation.js page component.
 * It is a minimal, self-contained confirmation view that matches
 * the widget's inline style system (no external CSS).
 *
 * Props:
 *   confirmedBooking - Object { id, date, time, type }
 *   formatTime       - Function(timeStr) -> display string
 *   formatFullDate   - Function(date) -> display string
 *   onScheduleAnother - Callback to reset the widget for another booking
 *   styles           - Style objects from the parent widget
 *   accentColor      - Brand accent color
 */
import React from 'react';

export default function BookingWidgetConfirmation({
  confirmedBooking,
  formatTime,
  formatFullDate,
  onScheduleAnother,
  styles,
  accentColor,
}) {
  if (!confirmedBooking) return null;

  return (
    <div style={styles.confirmContainer}>
      <div style={{ ...styles.checkCircle, borderColor: accentColor }}>
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke={accentColor}
          strokeWidth="3"
        >
          <path d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h3 style={styles.confirmTitle}>Appointment Confirmed</h3>
      <p style={styles.confirmSubtitle}>A confirmation email has been sent.</p>

      <div style={styles.confirmDetails}>
        <div style={styles.confirmRow}>
          <span style={styles.confirmLabel}>Date</span>
          <span style={styles.confirmValue}>
            {formatFullDate(confirmedBooking.date)}
          </span>
        </div>
        <div style={styles.confirmRow}>
          <span style={styles.confirmLabel}>Time</span>
          <span style={styles.confirmValue}>
            {formatTime(confirmedBooking.time)}
          </span>
        </div>
        {confirmedBooking.type && (
          <div style={styles.confirmRow}>
            <span style={styles.confirmLabel}>Type</span>
            <span style={styles.confirmValue}>
              {confirmedBooking.type.type_name}
            </span>
          </div>
        )}
      </div>

      <button
        onClick={onScheduleAnother}
        style={{
          ...styles.secondaryBtn,
          borderColor: accentColor,
          color: accentColor,
        }}
      >
        Schedule Another
      </button>
    </div>
  );
}
