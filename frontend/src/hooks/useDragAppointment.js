import { useState, useCallback, useRef } from 'react';

/**
 * useDragAppointment - Hook for drag-and-drop appointment rescheduling.
 *
 * Uses HTML5 Drag and Drop API (no external libraries).
 * Snaps to 15-minute increments.
 * Provides visual feedback state for ghost preview and drop zone highlighting.
 *
 * Usage:
 *   const drag = useDragAppointment({ onReschedule, onUndo });
 *   <DraggableEvent event={event} drag={drag} />
 *   <DroppableTimeSlot date={date} hour={hour} drag={drag} />
 */

/**
 * Snap minutes to the nearest 15-minute increment.
 */
function snapTo15(minutes) {
  return Math.round(minutes / 15) * 15;
}

/**
 * Format a Date as a human-readable time string, e.g. "Tuesday 2:00 PM".
 */
function formatDropTime(date) {
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const dayName = days[date.getDay()];
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHour = hours % 12 || 12;
  const displayMinutes = minutes.toString().padStart(2, '0');
  return `${dayName} ${displayHour}:${displayMinutes} ${ampm}`;
}

/**
 * Check if an event is in the past or cancelled (non-draggable).
 */
function isDragDisabled(event) {
  if (!event) return true;
  if (!event.isAppointment) return true;
  // Cancelled or completed appointments cannot be dragged
  const status = (event.status || '').toUpperCase();
  if (status === 'CANCELLED' || status === 'COMPLETED' || status === 'NO_SHOW') return true;
  // Past events cannot be dragged
  if (event.end_time) {
    const endTime = new Date(event.end_time);
    if (endTime < new Date()) return true;
  }
  return false;
}

export default function useDragAppointment({ onReschedule, onUndo } = {}) {
  // Currently dragging event
  const [draggingEvent, setDraggingEvent] = useState(null);
  // The time slot key currently hovered over (for highlighting)
  const [dragOverSlotKey, setDragOverSlotKey] = useState(null);
  // Confirmation dialog state
  const [pendingDrop, setPendingDrop] = useState(null);
  // Undo state
  const [undoData, setUndoData] = useState(null);
  // Loading state during API call
  const [rescheduling, setRescheduling] = useState(false);

  // Ref for tracking the drag image element
  const dragImageRef = useRef(null);
  // Timer ref for undo toast auto-dismiss
  const undoTimerRef = useRef(null);

  /**
   * onDragStart handler — called by DraggableEvent.
   * Sets drag data and creates a custom drag image.
   */
  const handleDragStart = useCallback((e, event) => {
    if (isDragDisabled(event)) {
      e.preventDefault();
      return;
    }

    // Store the event data in dataTransfer
    const dragData = {
      appointmentId: event.appointmentId,
      eventId: event.id,
      title: event.title,
      attendeeName: event.attendee_name,
      startTime: event.start_time,
      endTime: event.end_time,
      durationMinutes: event.end_time && event.start_time
        ? Math.round((new Date(event.end_time) - new Date(event.start_time)) / 60000)
        : 30,
    };

    e.dataTransfer.setData('application/json', JSON.stringify(dragData));
    e.dataTransfer.setData('text/plain', event.title || 'Appointment');
    e.dataTransfer.effectAllowed = 'move';

    // Create a custom ghost image
    const ghost = e.currentTarget.cloneNode(true);
    ghost.classList.add('drag-ghost');
    ghost.style.position = 'absolute';
    ghost.style.top = '-9999px';
    ghost.style.left = '-9999px';
    ghost.style.width = `${e.currentTarget.offsetWidth}px`;
    ghost.style.opacity = '0.85';
    ghost.style.transform = 'rotate(2deg)';
    ghost.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.2)';
    ghost.style.pointerEvents = 'none';
    document.body.appendChild(ghost);
    dragImageRef.current = ghost;

    e.dataTransfer.setDragImage(ghost, e.currentTarget.offsetWidth / 2, 20);

    setDraggingEvent(event);
  }, []);

  /**
   * onDragEnd handler — cleanup after drag finishes (drop or cancel).
   */
  const handleDragEnd = useCallback(() => {
    // Remove the custom ghost element
    if (dragImageRef.current) {
      document.body.removeChild(dragImageRef.current);
      dragImageRef.current = null;
    }
    setDraggingEvent(null);
    setDragOverSlotKey(null);
  }, []);

  /**
   * onDragOver handler — called by DroppableTimeSlot.
   * Highlights the drop target and allows drop.
   */
  const handleDragOver = useCallback((e, slotKey) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverSlotKey(slotKey);
  }, []);

  /**
   * onDragLeave handler — called when dragging leaves a slot.
   */
  const handleDragLeave = useCallback((e, slotKey) => {
    // Only clear if we're actually leaving (not entering a child)
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setDragOverSlotKey((current) => current === slotKey ? null : current);
    }
  }, []);

  /**
   * Calculate the new start time from a drop event on a time slot.
   * Snaps to 15-minute increments based on Y position within the slot.
   */
  const calculateNewTime = useCallback((e, slotDate, slotHour) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const relativeY = e.clientY - rect.top;
    const slotHeight = rect.height;

    // Calculate minute offset within the hour (0-59), snap to 15-minute increments
    const rawMinutes = Math.max(0, Math.min(59, (relativeY / slotHeight) * 60));
    const snappedMinutes = snapTo15(rawMinutes);

    const newStart = new Date(slotDate);
    newStart.setHours(slotHour, snappedMinutes, 0, 0);

    return newStart;
  }, []);

  /**
   * onDrop handler — called by DroppableTimeSlot.
   * Parses drag data, calculates new time, shows confirmation.
   */
  const handleDrop = useCallback((e, slotDate, slotHour) => {
    e.preventDefault();
    setDragOverSlotKey(null);

    let dragData;
    try {
      const raw = e.dataTransfer.getData('application/json');
      if (!raw) return;
      dragData = JSON.parse(raw);
    } catch {
      return;
    }

    const newStart = calculateNewTime(e, slotDate, slotHour);
    const durationMs = (dragData.durationMinutes || 30) * 60000;
    const newEnd = new Date(newStart.getTime() + durationMs);

    // Don't reschedule if time didn't actually change
    const oldStart = new Date(dragData.startTime);
    if (
      oldStart.getFullYear() === newStart.getFullYear() &&
      oldStart.getMonth() === newStart.getMonth() &&
      oldStart.getDate() === newStart.getDate() &&
      oldStart.getHours() === newStart.getHours() &&
      oldStart.getMinutes() === newStart.getMinutes()
    ) {
      return;
    }

    // Show confirmation
    setPendingDrop({
      dragData,
      newStart,
      newEnd,
      displayTime: formatDropTime(newStart),
    });
  }, [calculateNewTime]);

  /**
   * Confirm the pending drop and call the reschedule API.
   */
  const confirmDrop = useCallback(async () => {
    if (!pendingDrop || !onReschedule) return;

    const { dragData, newStart, newEnd } = pendingDrop;
    setPendingDrop(null);
    setRescheduling(true);

    try {
      // Store original data for undo
      const originalData = {
        appointmentId: dragData.appointmentId,
        originalStart: dragData.startTime,
        originalEnd: dragData.endTime,
      };

      await onReschedule(dragData.appointmentId, {
        scheduled_start: newStart.toISOString(),
        scheduled_end: newEnd.toISOString(),
        duration_minutes: dragData.durationMinutes,
      });

      // Set up undo with 5-second window
      setUndoData(originalData);
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current);
      undoTimerRef.current = setTimeout(() => {
        setUndoData(null);
      }, 5000);
    } catch {
      // Error is handled by the caller (onReschedule should throw)
    } finally {
      setRescheduling(false);
    }
  }, [pendingDrop, onReschedule]);

  /**
   * Cancel the pending drop confirmation.
   */
  const cancelDrop = useCallback(() => {
    setPendingDrop(null);
  }, []);

  /**
   * Undo the last reschedule within the 5-second window.
   */
  const handleUndo = useCallback(async () => {
    if (!undoData || !onUndo) return;

    if (undoTimerRef.current) clearTimeout(undoTimerRef.current);

    try {
      await onUndo(undoData.appointmentId, {
        scheduled_start: undoData.originalStart,
        scheduled_end: undoData.originalEnd,
      });
    } finally {
      setUndoData(null);
    }
  }, [undoData, onUndo]);

  /**
   * Dismiss the undo toast manually.
   */
  const dismissUndo = useCallback(() => {
    if (undoTimerRef.current) clearTimeout(undoTimerRef.current);
    setUndoData(null);
  }, []);

  /**
   * Generate a unique key for a time slot (used for highlighting).
   */
  const getSlotKey = useCallback((date, hour) => {
    return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${hour}`;
  }, []);

  return {
    // State
    draggingEvent,
    dragOverSlotKey,
    pendingDrop,
    undoData,
    rescheduling,

    // Drag handlers (passed to DraggableEvent)
    handleDragStart,
    handleDragEnd,

    // Drop handlers (passed to DroppableTimeSlot)
    handleDragOver,
    handleDragLeave,
    handleDrop,

    // Confirmation handlers
    confirmDrop,
    cancelDrop,

    // Undo handlers
    handleUndo,
    dismissUndo,

    // Utilities
    isDragDisabled,
    getSlotKey,
    formatDropTime,
  };
}
