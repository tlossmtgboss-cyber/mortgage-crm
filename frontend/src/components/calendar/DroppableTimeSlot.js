import React, { useCallback, useMemo } from 'react';

/**
 * DroppableTimeSlot - Drop target wrapper for calendar time slots.
 *
 * Each time slot in the day/week/3-day grid becomes a drop target.
 * On dragOver, it highlights with a blue border/background.
 * On drop, it calculates the new appointment time and triggers confirmation.
 *
 * Accessibility:
 *   - aria-dropeffect="move" when a drag is active
 *   - aria-label describes the time slot
 *
 * Props:
 *   date       - Date object for this slot's day
 *   hour       - Hour (0-23) for this time slot
 *   drag       - The useDragAppointment hook return value
 *   children   - The existing slot content (events, etc.)
 *   className  - Additional class names
 *   onClick    - Existing click handler for the slot (e.g., add event)
 *   onKeyDown  - Existing keydown handler
 *   ariaLabel  - Existing aria-label for the slot
 *   ...rest    - Any additional props passed to the slot container
 */
const DroppableTimeSlot = React.memo(function DroppableTimeSlot({
  date,
  hour,
  drag,
  children,
  className = '',
  onClick,
  onKeyDown,
  ariaLabel,
  ...rest
}) {
  const slotKey = useMemo(() => {
    if (!drag) return null;
    return drag.getSlotKey(date, hour);
  }, [drag, date, hour]);

  const isHighlighted = drag?.dragOverSlotKey === slotKey && drag?.draggingEvent != null;
  const hasDragActive = drag?.draggingEvent != null;

  const handleDragOver = useCallback((e) => {
    if (!drag || !drag.draggingEvent) return;
    drag.handleDragOver(e, slotKey);
  }, [drag, slotKey]);

  const handleDragLeave = useCallback((e) => {
    if (!drag) return;
    drag.handleDragLeave(e, slotKey);
  }, [drag, slotKey]);

  const handleDrop = useCallback((e) => {
    if (!drag || !drag.draggingEvent) return;
    drag.handleDrop(e, date, hour);
  }, [drag, date, hour]);

  // Build class list
  const classes = [
    className,
    'droppable-slot',
    isHighlighted ? 'drop-highlight' : '',
    hasDragActive ? 'drop-target-active' : '',
  ].filter(Boolean).join(' ');

  // Accessibility: indicate this is a drop target when drag is active
  const ariaDropProps = hasDragActive
    ? { 'aria-dropeffect': 'move' }
    : {};

  return (
    <div
      className={classes}
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      onClick={onClick}
      onKeyDown={onKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      {...ariaDropProps}
      {...rest}
    >
      {children}
      {isHighlighted && (
        <div className="drop-indicator" aria-hidden="true">
          <div className="drop-indicator-line" />
        </div>
      )}
    </div>
  );
});

export default DroppableTimeSlot;
