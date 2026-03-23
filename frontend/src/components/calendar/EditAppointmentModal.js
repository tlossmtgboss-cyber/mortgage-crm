import React from 'react';

/**
 * EditAppointmentModal -- Modal form for editing or rescheduling an existing appointment.
 *
 * Renders fields for title, meeting type, attendee info, date/time, duration, and notes.
 * Includes both a "Cancel Appointment" (destructive) and "Save Changes" action.
 * Closes on Escape key press or overlay click.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {Object} props.appointment - The appointment data object being edited (title, meeting_mode, attendee_*, date, time, duration, description)
 * @param {Function} props.onFieldChange - Callback(fieldName, value) to update a single field on the appointment
 * @param {Function} props.onSave - Form submit handler (receives the submit event)
 * @param {Function} props.onCancel - Callback() to cancel/delete the appointment
 * @param {Function} props.onClose - Callback() to dismiss the modal without saving
 * @param {boolean} props.saving - Whether a save operation is in progress (disables buttons)
 * @returns {React.ReactElement|null} Returns null if no appointment is provided
 *
 * @example
 * <EditAppointmentModal
 *   appointment={editingAppt}
 *   onFieldChange={updateField}
 *   onSave={handleSave}
 *   onCancel={handleCancelAppt}
 *   onClose={closeModal}
 *   saving={isSaving}
 * />
 */
const EditAppointmentModal = React.memo(function EditAppointmentModal({
  appointment,
  onFieldChange,
  onSave,
  onCancel,
  onClose,
  saving,
}) {
  if (!appointment) return null;

  const handleChange = (field) => (e) => {
    onFieldChange(field, e.target.value);
  };

  return (
    <div className="modal-overlay" onClick={onClose} onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}>
      <div
        className="modal-content edit-appointment-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Edit appointment"
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Edit Appointment</h3>
        <form onSubmit={onSave}>
          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              value={appointment.title}
              onChange={handleChange('title')}
              required
            />
          </div>

          <div className="form-group">
            <label>Meeting Type</label>
            <div className="meeting-mode-group">
              {[
                { value: 'phone', label: 'Phone Call' },
                { value: 'video', label: 'Video Call' },
                { value: 'in_person', label: 'In Person' },
              ].map(opt => (
                <div className="meeting-mode-option" key={opt.value}>
                  <input
                    type="radio"
                    id={`edit-mode-${opt.value}`}
                    name="edit-meeting-mode"
                    value={opt.value}
                    checked={appointment.meeting_mode === opt.value}
                    onChange={handleChange('meeting_mode')}
                  />
                  <label htmlFor={`edit-mode-${opt.value}`}>{opt.label}</label>
                </div>
              ))}
            </div>
          </div>

          <div className="attendee-section">
            <h4>Attendee</h4>
            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                value={appointment.attendee_name}
                onChange={handleChange('attendee_name')}
                placeholder="Attendee name"
              />
            </div>
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                value={appointment.attendee_email}
                onChange={handleChange('attendee_email')}
                placeholder="attendee@email.com"
              />
            </div>
            <div className="form-group">
              <label>Phone</label>
              <input
                type="tel"
                value={appointment.attendee_phone}
                onChange={handleChange('attendee_phone')}
                placeholder="(555) 123-4567"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Date</label>
              <input
                type="date"
                value={appointment.date}
                onChange={handleChange('date')}
                required
              />
            </div>
            <div className="form-group">
              <label>Time</label>
              <input
                type="time"
                value={appointment.time}
                onChange={handleChange('time')}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label>Duration</label>
            <select
              value={appointment.duration}
              onChange={handleChange('duration')}
            >
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="45">45 minutes</option>
              <option value="60">1 hour</option>
              <option value="90">1.5 hours</option>
              <option value="120">2 hours</option>
            </select>
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={appointment.description}
              onChange={handleChange('description')}
              placeholder="Additional notes..."
              rows={3}
            />
          </div>

          <div className="form-actions modal-actions-split">
            <button
              type="button"
              className="btn-danger"
              onClick={onCancel}
              disabled={saving}
            >
              Cancel Appointment
            </button>
            <div className="modal-actions-right">
              <button type="button" onClick={onClose} disabled={saving}>
                Close
              </button>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
});

export default EditAppointmentModal;
