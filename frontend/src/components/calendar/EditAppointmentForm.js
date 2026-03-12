import React from 'react';
import { DURATION_OPTIONS, MEETING_TYPE_OPTIONS, STATUS_OPTIONS } from './calendarUtils';

const EditAppointmentForm = React.memo(function EditAppointmentForm({
  modalRef,
  appointment,
  onAppointmentChange,
  onSubmit,
  onClose,
  onCancel,
  saving,
  cancelConfirm,
  onCancelConfirmDismiss,
}) {
  const handleFieldChange = (field, value) => {
    onAppointmentChange({ ...appointment, [field]: value });
  };

  const handleClose = () => {
    onCancelConfirmDismiss();
    onClose();
  };

  return (
    <div className="appointment-modal-overlay" onClick={handleClose} role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
      <div className="appointment-modal" onClick={(e) => e.stopPropagation()} ref={modalRef}>
        <div className="appointment-modal-header">
          <h3 id="edit-modal-title">Edit Appointment</h3>
          <button className="close-btn" onClick={handleClose} aria-label="Close dialog">&times;</button>
        </div>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              value={appointment.title}
              onChange={(e) => handleFieldChange('title', e.target.value)}
              placeholder="Appointment title"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Client Name *</label>
              <input
                type="text"
                value={appointment.attendee_name}
                onChange={(e) => handleFieldChange('attendee_name', e.target.value)}
                placeholder="Client name"
                required
              />
            </div>
            <div className="form-group">
              <label>Client Email</label>
              <input
                type="email"
                value={appointment.attendee_email}
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
                value={appointment.date}
                onChange={(e) => handleFieldChange('date', e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Time</label>
              <input
                type="time"
                value={appointment.time}
                onChange={(e) => handleFieldChange('time', e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Duration</label>
              <select
                value={appointment.duration}
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
                value={appointment.meeting_mode}
                onChange={(e) => handleFieldChange('meeting_mode', e.target.value)}
              >
                {MEETING_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Status</label>
            <select
              value={appointment.status}
              onChange={(e) => handleFieldChange('status', e.target.value)}
            >
              {STATUS_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={appointment.notes}
              onChange={(e) => handleFieldChange('notes', e.target.value)}
              placeholder="Additional notes..."
              rows="3"
            />
          </div>

          <div className="modal-actions">
            {cancelConfirm ? (
              <span style={{ display: 'flex', gap: '4px' }}>
                <button type="button" className="btn-danger" onClick={onCancel} disabled={saving}>
                  Confirm Cancel
                </button>
                <button type="button" className="btn-cancel" onClick={onCancelConfirmDismiss} style={{ fontSize: '12px' }}>
                  Nevermind
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="btn-danger"
                onClick={onCancel}
                disabled={saving}
              >
                Cancel Appointment
              </button>
            )}
            <div className="modal-actions-right">
              <button type="button" className="btn-cancel" onClick={handleClose}>
                Close
              </button>
              <button type="submit" className="btn-create" disabled={saving}>
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
});

export default EditAppointmentForm;
