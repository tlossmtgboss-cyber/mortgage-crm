import React, { useState, useRef, useCallback } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';

/**
 * TIME_BLOCK_REASONS - Pre-set reason options for blocking time.
 */
const TIME_BLOCK_REASONS = [
  { value: '', label: 'Select reason (optional)' },
  { value: 'lunch', label: 'Lunch Break' },
  { value: 'personal', label: 'Personal Time' },
  { value: 'focus', label: 'Focus Time' },
  { value: 'meeting', label: 'Internal Meeting' },
  { value: 'training', label: 'Training' },
  { value: 'other', label: 'Other' },
];

/**
 * formatTimeValue - Convert an hour number (0-23) to "HH:MM" string for input[type=time].
 */
const formatTimeValue = (hour) => {
  if (hour == null) return '09:00';
  return `${String(hour).padStart(2, '0')}:00`;
};

/**
 * formatEndTime - Default end time: 1 hour after start.
 */
const formatEndTimeValue = (hour) => {
  if (hour == null) return '10:00';
  const endHour = Math.min(hour + 1, 23);
  return `${String(endHour).padStart(2, '0')}:00`;
};

/**
 * formatDateValue - Convert a Date to YYYY-MM-DD for input[type=date].
 */
const formatDateValue = (date) => {
  if (!date) return new Date().toISOString().split('T')[0];
  return date.toISOString().split('T')[0];
};

/**
 * TimeBlocker - Quick form to block time on the calendar.
 *
 * Creates a "busy" block (not a real appointment). Renders as a modal overlay.
 *
 * Props:
 *   isOpen      - Whether the form is visible
 *   initialDate - Pre-filled date (Date object)
 *   initialHour - Pre-filled start hour (0-23)
 *   onSave      - Callback({ date, startTime, endTime, reason, customReason }) on submit
 *   onClose     - Callback to close the form
 */
const TimeBlocker = React.memo(function TimeBlocker({
  isOpen,
  initialDate,
  initialHour,
  onSave,
  onClose,
}) {
  const modalRef = useRef(null);

  const [formData, setFormData] = useState(() => ({
    date: formatDateValue(initialDate),
    startTime: formatTimeValue(initialHour),
    endTime: formatEndTimeValue(initialHour),
    reason: '',
    customReason: '',
  }));

  const [error, setError] = useState('');

  // Reset form when opening with new initial values
  React.useEffect(() => {
    if (isOpen) {
      setFormData({
        date: formatDateValue(initialDate),
        startTime: formatTimeValue(initialHour),
        endTime: formatEndTimeValue(initialHour),
        reason: '',
        customReason: '',
      });
      setError('');
    }
  }, [isOpen, initialDate, initialHour]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  // Focus trap with escape handling
  useFocusTrap(modalRef, {
    active: isOpen,
    onEscape: handleClose,
    autoFocus: true,
    restoreFocus: true,
    initialFocusSelector: '#time-block-start',
  });

  const handleFieldChange = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setError('');
  }, []);

  const handleSubmit = useCallback((e) => {
    e.preventDefault();

    // Validate time range
    if (formData.startTime >= formData.endTime) {
      setError('End time must be after start time.');
      return;
    }

    const reasonText = formData.reason === 'other'
      ? formData.customReason || 'Blocked'
      : formData.reason || '';

    const reasonLabel = formData.reason
      ? TIME_BLOCK_REASONS.find(r => r.value === formData.reason)?.label || reasonText
      : '';

    onSave({
      date: formData.date,
      startTime: formData.startTime,
      endTime: formData.endTime,
      reason: reasonText,
      reasonLabel,
    });
  }, [formData, onSave]);

  const handleOverlayClick = useCallback((e) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  }, [handleClose]);

  if (!isOpen) return null;

  return (
    <div
      className="appointment-modal-overlay"
      onClick={handleOverlayClick}
      role="presentation"
    >
      <div
        ref={modalRef}
        className="appointment-modal time-blocker-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="time-blocker-title"
      >
        {/* Header */}
        <div className="appointment-modal-header">
          <h3 id="time-blocker-title">Block Time</h3>
          <button
            className="close-btn"
            onClick={handleClose}
            aria-label="Close dialog"
            type="button"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {/* Date */}
          <div className="form-group">
            <label htmlFor="time-block-date">Date</label>
            <input
              id="time-block-date"
              type="date"
              value={formData.date}
              onChange={(e) => handleFieldChange('date', e.target.value)}
              required
              aria-required="true"
            />
          </div>

          {/* Time range */}
          <fieldset className="form-fieldset">
            <legend className="form-legend">Time range</legend>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="time-block-start">Start Time</label>
                <input
                  id="time-block-start"
                  type="time"
                  value={formData.startTime}
                  onChange={(e) => handleFieldChange('startTime', e.target.value)}
                  required
                  aria-required="true"
                />
              </div>
              <div className="form-group">
                <label htmlFor="time-block-end">End Time</label>
                <input
                  id="time-block-end"
                  type="time"
                  value={formData.endTime}
                  onChange={(e) => handleFieldChange('endTime', e.target.value)}
                  required
                  aria-required="true"
                />
              </div>
            </div>
          </fieldset>

          {/* Reason */}
          <div className="form-group">
            <label htmlFor="time-block-reason">Reason</label>
            <select
              id="time-block-reason"
              value={formData.reason}
              onChange={(e) => handleFieldChange('reason', e.target.value)}
            >
              {TIME_BLOCK_REASONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Custom reason if "Other" is selected */}
          {formData.reason === 'other' && (
            <div className="form-group">
              <label htmlFor="time-block-custom-reason">Description</label>
              <input
                id="time-block-custom-reason"
                type="text"
                value={formData.customReason}
                onChange={(e) => handleFieldChange('customReason', e.target.value)}
                placeholder="Enter reason..."
                maxLength={100}
              />
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          {/* Preview */}
          <div className="time-block-preview" aria-live="polite">
            <div className="time-block-preview-badge">
              <span className="time-block-preview-icon" aria-hidden="true">{'\u{1F6AB}'}</span>
              <span>
                {formData.startTime} - {formData.endTime}
                {formData.reason && formData.reason !== 'other' && (
                  <> &middot; {TIME_BLOCK_REASONS.find(r => r.value === formData.reason)?.label}</>
                )}
                {formData.reason === 'other' && formData.customReason && (
                  <> &middot; {formData.customReason}</>
                )}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="modal-actions">
            <div className="modal-actions-right">
              <button type="button" className="btn-cancel" onClick={handleClose}>
                Cancel
              </button>
              <button type="submit" className="btn-create">
                Block Time
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
});

export default TimeBlocker;
