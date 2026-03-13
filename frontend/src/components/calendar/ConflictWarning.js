import React, { useState, useCallback } from 'react';

/**
 * ConflictWarning - Shows when creating/editing an appointment that overlaps existing ones.
 *
 * Props:
 *   conflicts        - Array of conflict objects from the /conflicts/check API
 *   alternatives     - Array of alternative time slot objects
 *   onPickAlternative - Callback when user selects an alternative slot ({ start, end })
 *   onBookAnyway     - Callback when user chooses to override and book despite conflicts
 *   onDismiss        - Callback to dismiss the warning
 *   loading          - Boolean, true while conflict check is in progress
 */
const ConflictWarning = React.memo(function ConflictWarning({
  conflicts = [],
  alternatives = [],
  onPickAlternative,
  onBookAnyway,
  onDismiss,
  loading = false,
}) {
  const [showOverrideConfirm, setShowOverrideConfirm] = useState(false);

  const hardConflicts = conflicts.filter(c => c.severity === 'hard');
  const softConflicts = conflicts.filter(c => c.severity === 'soft');

  const handleBookAnyway = useCallback(() => {
    if (!showOverrideConfirm) {
      setShowOverrideConfirm(true);
      return;
    }
    setShowOverrideConfirm(false);
    if (onBookAnyway) onBookAnyway();
  }, [showOverrideConfirm, onBookAnyway]);

  const handleCancelOverride = useCallback(() => {
    setShowOverrideConfirm(false);
  }, []);

  if (loading) {
    return (
      <div className="conflict-warning conflict-warning--loading" role="status" aria-live="polite">
        <div className="conflict-warning__spinner" />
        <span>Checking for conflicts...</span>
      </div>
    );
  }

  if (conflicts.length === 0) {
    return null;
  }

  const formatTime = (isoString) => {
    if (!isoString) return '';
    try {
      const dt = new Date(isoString);
      return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    } catch {
      return isoString;
    }
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    try {
      const dt = new Date(isoString);
      return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    } catch {
      return isoString;
    }
  };

  return (
    <div
      className={`conflict-warning ${hardConflicts.length > 0 ? 'conflict-warning--hard' : 'conflict-warning--soft'}`}
      role="alert"
      aria-live="assertive"
    >
      {/* Header */}
      <div className="conflict-warning__header">
        <span className="conflict-warning__icon" aria-hidden="true">
          {hardConflicts.length > 0 ? '\u26A0' : '\u24D8'}
        </span>
        <span className="conflict-warning__title">
          {hardConflicts.length > 0
            ? `This time conflicts with ${hardConflicts.length} appointment${hardConflicts.length > 1 ? 's' : ''}`
            : `${softConflicts.length} appointment${softConflicts.length > 1 ? 's are' : ' is'} very close to this time`
          }
        </span>
        {onDismiss && (
          <button
            type="button"
            className="conflict-warning__close"
            onClick={onDismiss}
            aria-label="Dismiss conflict warning"
          >
            &times;
          </button>
        )}
      </div>

      {/* Conflicting appointments */}
      <div className="conflict-warning__conflicts">
        {hardConflicts.map((conflict, i) => (
          <div key={`hard-${i}`} className="conflict-warning__item conflict-warning__item--hard">
            <div className="conflict-warning__item-badge">Overlap</div>
            <div className="conflict-warning__item-details">
              <strong>{conflict.appointment?.title || 'Untitled'}</strong>
              {conflict.appointment?.attendee_name && (
                <span className="conflict-warning__attendee"> with {conflict.appointment.attendee_name}</span>
              )}
              <div className="conflict-warning__item-time">
                {formatTime(conflict.appointment?.scheduled_start)} - {formatTime(conflict.appointment?.scheduled_end)}
                {conflict.overlap_minutes > 0 && (
                  <span className="conflict-warning__overlap-duration">
                    ({Math.round(conflict.overlap_minutes)} min overlap)
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
        {softConflicts.map((conflict, i) => (
          <div key={`soft-${i}`} className="conflict-warning__item conflict-warning__item--soft">
            <div className="conflict-warning__item-badge conflict-warning__item-badge--soft">Buffer</div>
            <div className="conflict-warning__item-details">
              <strong>{conflict.appointment?.title || 'Untitled'}</strong>
              {conflict.appointment?.attendee_name && (
                <span className="conflict-warning__attendee"> with {conflict.appointment.attendee_name}</span>
              )}
              <div className="conflict-warning__item-time">
                {formatTime(conflict.appointment?.scheduled_start)} - {formatTime(conflict.appointment?.scheduled_end)}
                <span className="conflict-warning__overlap-duration">(too close, needs buffer)</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Suggested alternatives */}
      {alternatives.length > 0 && (
        <div className="conflict-warning__alternatives">
          <h4 className="conflict-warning__alt-title">Suggested alternatives</h4>
          <div className="conflict-warning__alt-slots">
            {alternatives.map((slot, i) => (
              <button
                key={i}
                type="button"
                className="conflict-warning__alt-slot"
                onClick={() => onPickAlternative && onPickAlternative(slot)}
                aria-label={`Pick alternative: ${formatDate(slot.start)} at ${formatTime(slot.start)}`}
              >
                <span className="conflict-warning__alt-date">{formatDate(slot.start)}</span>
                <span className="conflict-warning__alt-time">
                  {formatTime(slot.start)} - {formatTime(slot.end)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="conflict-warning__actions">
        {alternatives.length > 0 && onPickAlternative && (
          <button
            type="button"
            className="conflict-warning__btn conflict-warning__btn--primary"
            onClick={() => onPickAlternative(alternatives[0])}
          >
            Pick best alternative
          </button>
        )}

        {showOverrideConfirm ? (
          <div className="conflict-warning__override-confirm">
            <span>Are you sure? This will create a double-booking.</span>
            <button
              type="button"
              className="conflict-warning__btn conflict-warning__btn--danger"
              onClick={handleBookAnyway}
            >
              Yes, book anyway
            </button>
            <button
              type="button"
              className="conflict-warning__btn conflict-warning__btn--secondary"
              onClick={handleCancelOverride}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="conflict-warning__btn conflict-warning__btn--outline"
            onClick={handleBookAnyway}
          >
            Book anyway
          </button>
        )}
      </div>
    </div>
  );
});

export default ConflictWarning;
