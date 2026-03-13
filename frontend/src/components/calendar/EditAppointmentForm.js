import React, { useRef, useCallback } from 'react';
import { DURATION_OPTIONS, MEETING_TYPE_OPTIONS, STATUS_OPTIONS } from './calendarUtils';
import useFocusTrap from '../../hooks/useFocusTrap';

/**
 * EditAppointmentForm - Accessible edit appointment modal dialog.
 *
 * Features:
 * - role="dialog" with aria-modal="true"
 * - aria-labelledby pointing to modal title
 * - Focus trap via useFocusTrap hook
 * - Escape key closes modal
 * - Returns focus to trigger element on close
 * - aria-required on required fields
 * - fieldset/legend for grouped inputs (scheduling, meeting configuration)
 * - Proper label associations via htmlFor/id
 */
const EditAppointmentForm = React.memo(function EditAppointmentForm({
  modalRef: externalRef,
  appointment,
  onAppointmentChange,
  onSubmit,
  onClose,
  onCancel,
  saving,
  cancelConfirm,
  onCancelConfirmDismiss,
}) {
  const internalRef = useRef(null);
  const containerRef = externalRef || internalRef;

  const handleFieldChange = (field, value) => {
    onAppointmentChange({ ...appointment, [field]: value });
  };

  const handleClose = useCallback(() => {
    onCancelConfirmDismiss();
    onClose();
  }, [onCancelConfirmDismiss, onClose]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  // Focus trap with escape handling
  useFocusTrap(containerRef, {
    active: true,
    onEscape: handleClose,
    autoFocus: true,
    restoreFocus: true,
  });

  return (
    <div className="appointment-modal-overlay" onClick={handleOverlayClick} role="presentation">
      <div
        className="appointment-modal"
        onClick={(e) => e.stopPropagation()}
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-modal-title"
      >
        <div className="appointment-modal-header">
          <h3 id="edit-modal-title">Edit Appointment</h3>
          <button className="close-btn" onClick={handleClose} aria-label="Close dialog">&times;</button>
        </div>

        <form onSubmit={onSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="edit-appt-title">Title</label>
            <input
              id="edit-appt-title"
              type="text"
              value={appointment.title}
              onChange={(e) => handleFieldChange('title', e.target.value)}
              placeholder="Appointment title"
            />
          </div>

          <fieldset className="form-fieldset">
            <legend className="form-legend">Client information</legend>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="edit-appt-client-name">Client Name</label>
                <input
                  id="edit-appt-client-name"
                  type="text"
                  value={appointment.attendee_name}
                  onChange={(e) => handleFieldChange('attendee_name', e.target.value)}
                  placeholder="Client name"
                  required
                  aria-required="true"
                />
              </div>
              <div className="form-group">
                <label htmlFor="edit-appt-client-email">Client Email</label>
                <input
                  id="edit-appt-client-email"
                  type="email"
                  value={appointment.attendee_email}
                  onChange={(e) => handleFieldChange('attendee_email', e.target.value)}
                  placeholder="email@example.com"
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="form-fieldset">
            <legend className="form-legend">Scheduling</legend>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="edit-appt-date">Date</label>
                <input
                  id="edit-appt-date"
                  type="date"
                  value={appointment.date}
                  onChange={(e) => handleFieldChange('date', e.target.value)}
                  required
                  aria-required="true"
                />
              </div>
              <div className="form-group">
                <label htmlFor="edit-appt-time">Time</label>
                <input
                  id="edit-appt-time"
                  type="time"
                  value={appointment.time}
                  onChange={(e) => handleFieldChange('time', e.target.value)}
                  required
                  aria-required="true"
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="form-fieldset">
            <legend className="form-legend">Meeting configuration</legend>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="edit-appt-duration">Duration</label>
                <select
                  id="edit-appt-duration"
                  value={appointment.duration}
                  onChange={(e) => handleFieldChange('duration', e.target.value)}
                >
                  {DURATION_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="edit-appt-meeting-type">Meeting Type</label>
                <select
                  id="edit-appt-meeting-type"
                  value={appointment.meeting_mode}
                  onChange={(e) => handleFieldChange('meeting_mode', e.target.value)}
                >
                  {MEETING_TYPE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          <div className="form-group">
            <label htmlFor="edit-appt-status">Status</label>
            <select
              id="edit-appt-status"
              value={appointment.status}
              onChange={(e) => handleFieldChange('status', e.target.value)}
            >
              {STATUS_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="edit-appt-notes">Notes</label>
            <textarea
              id="edit-appt-notes"
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
