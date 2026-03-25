import React, { useState, useCallback, useRef, useEffect } from 'react';
import { normalizeUTCDate, getUserTimezone } from './calendarUtils';

/**
 * ConflictIndicator - Visual indicator for calendar grid cells/events that have conflicts.
 *
 * Two usage modes:
 *
 * 1. Time slot overlay (for day/week grid cells):
 *    <ConflictIndicator mode="slot" conflicts={[...]} />
 *    Renders a red diagonal stripe overlay on the time slot.
 *
 * 2. Event card badge (for appointment cards):
 *    <ConflictIndicator mode="badge" conflicts={[...]} />
 *    Renders a small warning icon with tooltip on hover.
 *
 * Props:
 *   mode       - "slot" | "badge"
 *   conflicts  - Array of conflict objects (from conflict check API or local detection)
 *   className  - Additional CSS class
 */
const ConflictIndicator = React.memo(function ConflictIndicator({
  mode = 'badge',
  conflicts = [],
  className = '',
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = useRef(null);
  const triggerRef = useRef(null);

  // Position tooltip to avoid overflow
  useEffect(() => {
    if (showTooltip && tooltipRef.current && triggerRef.current) {
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;

      // If tooltip overflows right, shift it left
      if (tooltipRect.right > viewportWidth - 16) {
        tooltipRef.current.style.right = '0';
        tooltipRef.current.style.left = 'auto';
      }
    }
  }, [showTooltip]);

  const handleMouseEnter = useCallback(() => setShowTooltip(true), []);
  const handleMouseLeave = useCallback(() => setShowTooltip(false), []);
  const handleFocus = useCallback(() => setShowTooltip(true), []);
  const handleBlur = useCallback(() => setShowTooltip(false), []);

  if (!conflicts || conflicts.length === 0) {
    return null;
  }

  const hardConflicts = conflicts.filter(c => c.severity === 'hard');
  const softConflicts = conflicts.filter(c => c.severity === 'soft');
  const hasHard = hardConflicts.length > 0;

  const formatTime = (isoString) => {
    if (!isoString) return '';
    try {
      const tz = getUserTimezone();
      const dt = new Date(normalizeUTCDate(isoString));
      return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: tz });
    } catch {
      return '';
    }
  };

  // Slot mode: red overlay stripe on a time slot
  if (mode === 'slot') {
    return (
      <div
        className={`conflict-indicator conflict-indicator--slot ${hasHard ? 'conflict-indicator--hard' : 'conflict-indicator--soft'} ${className}`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        ref={triggerRef}
        aria-label={`${conflicts.length} conflict${conflicts.length > 1 ? 's' : ''}`}
        role="img"
      >
        <div className="conflict-indicator__stripe" aria-hidden="true" />
        {showTooltip && (
          <div className="conflict-indicator__tooltip" ref={tooltipRef} role="tooltip">
            <div className="conflict-indicator__tooltip-title">
              {hasHard ? 'Conflicting appointments' : 'Adjacent appointments (buffer overlap)'}
            </div>
            {conflicts.map((conflict, i) => (
              <div key={i} className="conflict-indicator__tooltip-item">
                <span className={`conflict-indicator__dot ${conflict.severity === 'hard' ? 'conflict-indicator__dot--hard' : 'conflict-indicator__dot--soft'}`} />
                <span>{conflict.appointment?.title || 'Untitled'}</span>
                <span className="conflict-indicator__tooltip-time">
                  {formatTime(conflict.appointment?.scheduled_start)} - {formatTime(conflict.appointment?.scheduled_end)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Badge mode: small warning icon on an event card
  return (
    <span
      className={`conflict-indicator conflict-indicator--badge ${hasHard ? 'conflict-indicator--hard' : 'conflict-indicator--soft'} ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
      ref={triggerRef}
      tabIndex={0}
      role="button"
      aria-label={`${conflicts.length} scheduling conflict${conflicts.length > 1 ? 's' : ''}`}
      aria-describedby={showTooltip ? 'conflict-tooltip' : undefined}
    >
      <svg
        className="conflict-indicator__icon"
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M8 1L15 14H1L8 1Z"
          fill={hasHard ? '#dc3545' : '#ffc107'}
          stroke={hasHard ? '#a71d2a' : '#c29200'}
          strokeWidth="1"
        />
        <text x="8" y="12" textAnchor="middle" fontSize="9" fontWeight="bold" fill={hasHard ? 'white' : '#333'}>!</text>
      </svg>

      {showTooltip && (
        <div className="conflict-indicator__tooltip" id="conflict-tooltip" ref={tooltipRef} role="tooltip">
          <div className="conflict-indicator__tooltip-title">
            {hardConflicts.length > 0 && `${hardConflicts.length} direct conflict${hardConflicts.length > 1 ? 's' : ''}`}
            {hardConflicts.length > 0 && softConflicts.length > 0 && ', '}
            {softConflicts.length > 0 && `${softConflicts.length} buffer overlap${softConflicts.length > 1 ? 's' : ''}`}
          </div>
          {conflicts.map((conflict, i) => (
            <div key={i} className="conflict-indicator__tooltip-item">
              <span className={`conflict-indicator__dot ${conflict.severity === 'hard' ? 'conflict-indicator__dot--hard' : 'conflict-indicator__dot--soft'}`} />
              <span>{conflict.appointment?.title || 'Untitled'}</span>
              {conflict.appointment?.attendee_name && (
                <span className="conflict-indicator__tooltip-attendee"> - {conflict.appointment.attendee_name}</span>
              )}
              <span className="conflict-indicator__tooltip-time">
                {formatTime(conflict.appointment?.scheduled_start)} - {formatTime(conflict.appointment?.scheduled_end)}
              </span>
            </div>
          ))}
        </div>
      )}
    </span>
  );
});

export default ConflictIndicator;
