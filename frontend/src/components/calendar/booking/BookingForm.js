/**
 * BookingForm - Contact information form for the booking widget.
 *
 * Collects first name, last name, email, phone, and notes.
 * Includes a summary badge showing the selected date/time/type.
 *
 * Props:
 *   form           - Object { first_name, last_name, email, phone, notes }
 *   onFormChange   - Callback(updatedForm) when any field changes
 *   formErrors     - Object with field-name keys and error message values
 *   onSubmit       - Callback(event) for form submission
 *   onBack         - Callback to go back to datetime step
 *   submitting     - Boolean, true while the booking request is in flight
 *   selectedDate   - Selected Date object (for summary badge)
 *   selectedTime   - Selected time string (for summary badge)
 *   selectedType   - Selected appointment type object (for summary badge)
 *   formatTime     - Function(timeStr) -> display string
 *   styles         - Style objects from the parent widget
 *   accentColor    - Brand accent color
 */
import React from 'react';

export default function BookingForm({
  form,
  onFormChange,
  formErrors,
  onSubmit,
  onBack,
  submitting,
  selectedDate,
  selectedTime,
  selectedType,
  formatTime,
  styles,
  accentColor,
}) {
  const handleChange = (field, value) => {
    onFormChange({ ...form, [field]: value });
  };

  return (
    <div>
      <button
        onClick={onBack}
        style={styles.backLink}
        aria-label="Go back to date and time selection"
      >
        &lsaquo; Back
      </button>

      {selectedDate && selectedTime && (
        <div style={styles.summaryBadge} aria-live="polite">
          {selectedDate.toLocaleDateString(undefined, {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
          })}
          {' at '}
          {formatTime(selectedTime)}
          {selectedType ? ` - ${selectedType.type_name}` : ''}
        </div>
      )}

      <form onSubmit={onSubmit} style={styles.form} aria-label="Booking contact information" noValidate>
        <div style={styles.formRow}>
          <div style={styles.formGroup}>
            <label htmlFor="bw-first-name" style={styles.formLabel}>
              First Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="bw-first-name"
              type="text"
              autoComplete="given-name"
              value={form.first_name}
              onChange={(e) => handleChange('first_name', e.target.value)}
              placeholder="Jane"
              style={{
                ...styles.input,
                ...(formErrors.first_name ? styles.inputError : {}),
              }}
              required
              aria-required="true"
              aria-invalid={!!formErrors.first_name}
              aria-describedby={formErrors.first_name ? 'bw-first-name-error' : undefined}
            />
            {formErrors.first_name && (
              <span id="bw-first-name-error" style={styles.fieldError} role="alert">
                {formErrors.first_name}
              </span>
            )}
          </div>
          <div style={styles.formGroup}>
            <label htmlFor="bw-last-name" style={styles.formLabel}>
              Last Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="bw-last-name"
              type="text"
              autoComplete="family-name"
              value={form.last_name}
              onChange={(e) => handleChange('last_name', e.target.value)}
              placeholder="Doe"
              style={{
                ...styles.input,
                ...(formErrors.last_name ? styles.inputError : {}),
              }}
              required
              aria-required="true"
              aria-invalid={!!formErrors.last_name}
              aria-describedby={formErrors.last_name ? 'bw-last-name-error' : undefined}
            />
            {formErrors.last_name && (
              <span id="bw-last-name-error" style={styles.fieldError} role="alert">
                {formErrors.last_name}
              </span>
            )}
          </div>
        </div>

        <div style={styles.formGroup}>
          <label htmlFor="bw-email" style={styles.formLabel}>
            Email <span aria-hidden="true">*</span>
          </label>
          <input
            id="bw-email"
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={(e) => handleChange('email', e.target.value)}
            placeholder="jane@email.com"
            style={{
              ...styles.input,
              ...(formErrors.email ? styles.inputError : {}),
            }}
            required
            aria-required="true"
            aria-invalid={!!formErrors.email}
            aria-describedby={formErrors.email ? 'bw-email-error' : undefined}
          />
          {formErrors.email && (
            <span id="bw-email-error" style={styles.fieldError} role="alert">
              {formErrors.email}
            </span>
          )}
        </div>

        <div style={styles.formGroup}>
          <label htmlFor="bw-phone" style={styles.formLabel}>Phone</label>
          <input
            id="bw-phone"
            type="tel"
            autoComplete="tel"
            value={form.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
            placeholder="(555) 555-5555"
            style={{
              ...styles.input,
              ...(formErrors.phone ? styles.inputError : {}),
            }}
            aria-invalid={!!formErrors.phone}
            aria-describedby={formErrors.phone ? 'bw-phone-error' : undefined}
          />
          {formErrors.phone && (
            <span id="bw-phone-error" style={styles.fieldError} role="alert">
              {formErrors.phone}
            </span>
          )}
        </div>

        <div style={styles.formGroup}>
          <label htmlFor="bw-notes" style={styles.formLabel}>Notes</label>
          <textarea
            id="bw-notes"
            value={form.notes}
            onChange={(e) => handleChange('notes', e.target.value)}
            placeholder="Anything we should know?"
            rows={2}
            maxLength={500}
            style={styles.textarea}
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          aria-label={submitting ? 'Scheduling appointment, please wait' : 'Schedule appointment'}
          style={{
            ...styles.primaryBtn,
            backgroundColor: submitting ? '#ccc' : accentColor,
            cursor: submitting ? 'wait' : 'pointer',
          }}
        >
          {submitting ? 'Scheduling...' : 'Schedule Appointment'}
        </button>
      </form>
    </div>
  );
}
