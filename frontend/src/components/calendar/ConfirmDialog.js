import React from 'react';

/**
 * ConfirmDialog -- Generic confirmation modal with "No, go back" and "Yes, confirm" buttons.
 *
 * Closes on overlay click. Used for destructive actions like deleting events or
 * cancelling appointments.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {string} props.message - The confirmation question/message to display
 * @param {Function} props.onConfirm - Callback() invoked when the user clicks "Yes, confirm"
 * @param {Function} props.onCancel - Callback() invoked when the user clicks "No, go back" or the overlay
 * @returns {React.ReactElement}
 *
 * @example
 * <ConfirmDialog
 *   message="Are you sure you want to cancel this appointment?"
 *   onConfirm={handleDelete}
 *   onCancel={() => setShowConfirm(false)}
 * />
 */
const ConfirmDialog = React.memo(function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal-content confirm-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Confirm action"
      >
        <p>{message}</p>
        <div className="modal-actions">
          <button type="button" onClick={onCancel}>No, go back</button>
          <button type="button" className="btn-danger" onClick={onConfirm}>Yes, confirm</button>
        </div>
      </div>
    </div>
  );
});

export default ConfirmDialog;
