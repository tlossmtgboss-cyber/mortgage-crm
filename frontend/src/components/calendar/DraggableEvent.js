import React, { useCallback, useRef } from 'react';

/**
 * DraggableEvent - Wraps calendar event cards with HTML5 drag-and-drop behavior.
 *
 * Accessibility:
 *   - aria-grabbed indicates drag state
 *   - aria-roledescription explains the draggable nature
 *   - aria-label describes the appointment for screen readers
 *   - Keyboard: Enter/Space to open edit (existing behavior), not drag
 *
 * Disabled for:
 *   - Past events
 *   - Cancelled / completed / no-show appointments
 *   - Non-appointment events (CRM events, calendar events)
 *
 * Props:
 *   event     - The calendar event object
 *   drag      - The useDragAppointment hook return value
 *   children  - The event card content to render inside the draggable wrapper
 *   className - Additional class names for the wrapper
 */
const DraggableEvent = React.memo(function DraggableEvent({
  event,
  drag,
  children,
  className = '',
  ...rest
}) {
  const elementRef = useRef(null);

  const disabled = !drag || drag.isDragDisabled(event);
  const isDragging = drag?.draggingEvent?.id === event?.id;

  const onDragStart = useCallback((e) => {
    if (disabled || !drag) return;
    drag.handleDragStart(e, event);
  }, [disabled, drag, event]);

  const onDragEnd = useCallback(() => {
    if (!drag) return;
    drag.handleDragEnd();
  }, [drag]);

  // Build class list
  const classes = [
    'draggable-event',
    disabled ? 'drag-disabled' : 'drag-enabled',
    isDragging ? 'drag-active' : '',
    className,
  ].filter(Boolean).join(' ');

  // Accessibility attributes
  const ariaProps = disabled
    ? {}
    : {
        'aria-grabbed': isDragging || undefined,
        'aria-roledescription': 'Draggable appointment. Drag to reschedule.',
      };

  return (
    <div
      ref={elementRef}
      className={classes}
      draggable={!disabled}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      {...ariaProps}
      {...rest}
    >
      {children}
    </div>
  );
});

export default DraggableEvent;
