import React from 'react';
import { DURATION_OPTIONS, MEETING_TYPE_OPTIONS } from './calendarUtils';

function CreateAppointmentForm({
  modalRef,
  form,
  onFormChange,
  onSubmit,
  onClose,
}) {
  const handleFieldChange = (field, value) => {
    onFormChange({ ...form, [field]: value });
  };

  return (
    <div className="appointment-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="create-modal-title">
      <div className="appointment-modal" onClick={(e) => e.stopPropagation()} ref={modalRef}>
        <div className="appointment-modal-header">
          <h3 id="create-modal-title">Create Appointment from Email</h3>
          <button className="close-btn" onClick={onClose} aria-label="Close dialog">&times;</button>
        </div>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => handleFieldChange('title', e.target.value)}
              placeholder="Appointment title"
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Contact Name</label>
              <input
                type="text"
                value={form.attendee_name}
                onChange={(e) => handleFieldChange('attendee_name', e.target.value)}
                placeholder="Name"
              />
            </div>
            <div className="form-group">
              <label>Contact Email</label>
              <input
                type="email"
                value={form.attendee_email}
                onChange={(e) => handleFieldChange('attendee_email', e.target.value)}
                placeholder="email@example.com"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Date</label>
              <input
                type="date"
                value={form.date}
                onChange={(e) => handleFieldChange('date', e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Time</label>
              <input
                type="time"
                value={form.time}
                onChange={(e) => handleFieldChange('time', e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Duration</label>
              <select
                value={form.duration}
                onChange={(e) => handleFieldChange('duration', e.target.value)}
              >
                {DURATION_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Meeting Type</label>
              <select
                value={form.meeting_mode}
                onChange={(e) => handleFieldChange('meeting_mode', e.target.value)}
              >
                {MEETING_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => handleFieldChange('notes', e.target.value)}
              placeholder="Additional notes..."
              rows="3"
            />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-create">
              Create Appointment
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateAppointmentForm;
