import React, { useRef, useCallback } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';
import { formatTime, formatDuration, getMeetingModeIcon } from './calendarUtils';
import { StatusBadge } from './index';

/**
 * EventModal - Accessible modal dialog for viewing appointment/event details.
 *
 * Features:
 * - role="dialog" with aria-modal="true"
 * - aria-labelledby pointing to modal title
 * - Focus trap (tab cycles within modal)
 * - Escape key closes modal
 * - Returns focus to trigger element on close
 * - Click outside overlay closes modal
 *
 * Props:
 *   isOpen          - Whether the modal is visible
 *   event           - The event/appointment object to display
 *   onClose         - Callback to close the modal
 *   onEdit          - Callback to open edit mode
 *   onCancel        - Callback to cancel the appointment
 *   triggerRef      - Ref to the element that triggered the modal (for focus return)
 */
const EventModal = React.memo(function EventModal({
  isOpen,
  event,
  onClose,
  onEdit,
  onCancel,
  triggerRef,
}) {
  const modalRef = useRef(null);

  const handleEscape = useCallback(() => {
    onClose();
  }, [onClose]);

  // Focus trap with escape handling and focus restoration
  useFocusTrap(modalRef, {
    active: isOpen,
    onEscape: handleEscape,
    autoFocus: true,
    restoreFocus: true,
    initialFocusSelector: '.event-modal-close-btn',
  });

  if (!isOpen || !event) return null;

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="appointment-modal-overlay"
      onClick={handleOverlayClick}
      role="presentation"
    >
      <div
        ref={modalRef}
        className="appointment-modal event-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-modal-title"
      >
        {/* Header */}
        <div className="appointment-modal-header">
          <h3 id="event-modal-title">
            {getMeetingModeIcon(event.meeting_mode)} {event.title || 'Appointment Details'}
          </h3>
          <button
            className="close-btn event-modal-close-btn"
            onClick={onClose}
            aria-label="Close dialog"
            type="button"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="event-modal-body">
          {event.status && (
            <div className="event-modal-row">
              <span className="event-modal-label">Status</span>
              <StatusBadge status={event.status} size="sm" />
            </div>
          )}

          {event.scheduled_start && (
            <div className="event-modal-row">
              <span className="event-modal-label">Time</span>
              <span className="event-modal-value">
                {formatTime(event.scheduled_start)}
                {event.scheduled_end && ` - ${formatTime(event.scheduled_end)}`}
                {event.scheduled_end && (
                  <span className="event-modal-duration">
                    ({formatDuration(event.scheduled_start, event.scheduled_end)})
                  </span>
                )}
              </span>
            </div>
          )}

          {event.attendee_name && (
            <div className="event-modal-row">
              <span className="event-modal-label">Client</span>
              <span className="event-modal-value">{event.attendee_name}</span>
            </div>
          )}

          {event.attendee_email && (
            <div className="event-modal-row">
              <span className="event-modal-label">Email</span>
              <span className="event-modal-value">{event.attendee_email}</span>
            </div>
          )}

          {event.meeting_mode && (
            <div className="event-modal-row">
              <span className="event-modal-label">Format</span>
              <span className="event-modal-value">
                {getMeetingModeIcon(event.meeting_mode)}{' '}
                {event.meeting_mode.replace('_', ' ')}
              </span>
            </div>
          )}

          {event.notes && (
            <div className="event-modal-row">
              <span className="event-modal-label">Notes</span>
              <span className="event-modal-value">{event.notes}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="modal-actions">
          {onCancel && (
            <button
              type="button"
              className="btn-danger"
              onClick={() => onCancel(event)}
              aria-label="Cancel this appointment"
            >
              Cancel Appointment
            </button>
          )}
          <div className="modal-actions-right">
            <button
              type="button"
              className="btn-cancel"
              onClick={onClose}
            >
              Close
            </button>
            {onEdit && (
              <button
                type="button"
                className="btn-create"
                onClick={() => onEdit(event)}
              >
                Edit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

export default EventModal;
