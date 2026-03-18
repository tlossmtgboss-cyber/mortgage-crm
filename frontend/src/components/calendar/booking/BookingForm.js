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
      <button onClick={onBack} style={styles.backLink}>
        &lsaquo; Back
      </button>

      {selectedDate && selectedTime && (
        <div style={styles.summaryBadge}>
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

      <form onSubmit={onSubmit} style={styles.form}>
        <div style={styles.formRow}>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>First Name *</label>
            <input
              type="text"
              value={form.first_name}
              onChange={(e) => handleChange('first_name', e.target.value)}
              placeholder="Jane"
              style={{
                ...styles.input,
                ...(formErrors.first_name ? styles.inputError : {}),
              }}
              required
            />
            {formErrors.first_name && (
              <span style={styles.fieldError}>{formErrors.first_name}</span>
            )}
          </div>
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Last Name *</label>
            <input
              type="text"
              value={form.last_name}
              onChange={(e) => handleChange('last_name', e.target.value)}
              placeholder="Doe"
              style={{
                ...styles.input,
                ...(formErrors.last_name ? styles.inputError : {}),
              }}
              required
            />
            {formErrors.last_name && (
              <span style={styles.fieldError}>{formErrors.last_name}</span>
            )}
          </div>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.formLabel}>Email *</label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => handleChange('email', e.target.value)}
            placeholder="jane@email.com"
            style={{
              ...styles.input,
              ...(formErrors.email ? styles.inputError : {}),
            }}
            required
          />
          {formErrors.email && (
            <span style={styles.fieldError}>{formErrors.email}</span>
          )}
        </div>

        <div style={styles.formGroup}>
          <label style={styles.formLabel}>Phone</label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
            placeholder="(555) 555-5555"
            style={{
              ...styles.input,
              ...(formErrors.phone ? styles.inputError : {}),
            }}
          />
          {formErrors.phone && (
            <span style={styles.fieldError}>{formErrors.phone}</span>
          )}
        </div>

        <div style={styles.formGroup}>
          <label style={styles.formLabel}>Notes</label>
          <textarea
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
