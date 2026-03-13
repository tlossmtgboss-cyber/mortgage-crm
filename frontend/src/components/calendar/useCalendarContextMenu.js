import { useState, useCallback, useRef, useEffect } from 'react';
import useContextMenu from '../../hooks/useContextMenu';

/**
 * useCalendarContextMenu - Encapsulates all context menu state and handlers
 * for the Calendar page.
 *
 * Uses refs for callback dependencies so it can be called before those
 * callbacks are defined (standard React hook ordering requirement).
 *
 * @param {Object} deps - Calendar dependencies
 * @param {Function} deps.setSelectedDate
 * @param {Function} deps.setSelectedTime
 * @param {Function} deps.setShowAddModal
 * @param {Function} deps.handleEditAppointment
 * @param {Function} deps.handleDeleteEvent
 * @param {Function} deps.loadEvents
 * @param {Function} deps.loadAllEvents
 * @param {Object} deps.schedulerAPI
 * @param {Object} deps.toast
 */
const useCalendarContextMenu = (deps) => {
  const contextMenu = useContextMenu();

  // Use refs for all deps that may not be stable yet at hook-call time
  const depsRef = useRef(deps);
  useEffect(() => { depsRef.current = deps; });

  // Time blocker state
  const [showTimeBlocker, setShowTimeBlocker] = useState(false);
  const [timeBlockerInitial, setTimeBlockerInitial] = useState({ date: null, hour: null });
  const [timeBlocks, setTimeBlocks] = useState([]);

  // Right-click on empty time slot
  const handleSlotContextMenu = useCallback((e, date, hour) => {
    contextMenu.openMenu(e, { type: 'slot', date, hour });
  }, [contextMenu]);

  // Right-click on an event card
  const handleEventContextMenu = useCallback((e, event) => {
    e.stopPropagation();
    contextMenu.openMenu(e, { type: 'event', event });
  }, [contextMenu]);

  // Handle menu item selection - uses ref to always get latest deps
  const handleContextMenuAction = useCallback((actionId, data) => {
    const d = depsRef.current;
    if (data.type === 'slot') {
      if (actionId === 'new-appointment') {
        d.setSelectedDate(data.date);
        d.setSelectedTime(data.hour);
        d.setShowAddModal(true);
      } else if (actionId === 'block-time') {
        setTimeBlockerInitial({ date: data.date, hour: data.hour });
        setShowTimeBlocker(true);
      } else if (actionId === 'add-note') {
        d.setSelectedDate(data.date);
        d.setSelectedTime(data.hour);
        d.setShowAddModal(true);
      }
    } else if (data.type === 'event' && data.event) {
      const evt = data.event;

      if (actionId === 'view-details' || actionId === 'edit' || actionId === 'reschedule') {
        if (evt.isAppointment && d.handleEditAppointment) d.handleEditAppointment(evt);
      } else if (actionId === 'cancel') {
        if (d.handleDeleteEvent) d.handleDeleteEvent(evt);
      } else if (actionId === 'mark-completed' && evt.isAppointment && evt.appointmentId) {
        d.schedulerAPI.updateAppointment(evt.appointmentId, { status: 'COMPLETED' })
          .then(() => {
            d.toast.success('Appointment marked as completed');
            if (d.loadEvents) d.loadEvents();
            if (d.loadAllEvents) d.loadAllEvents();
          })
          .catch((err) => {
            d.toast.error('Failed to update: ' + (err.response?.data?.detail || err.message));
          });
      } else if (actionId === 'send-reminder' && evt.isAppointment && evt.appointmentId) {
        d.schedulerAPI.sendReminder(evt.appointmentId)
          .then(() => { d.toast.success('Reminder sent'); })
          .catch((err) => {
            d.toast.error('Failed to send reminder: ' + (err.response?.data?.detail || err.message));
          });
      }
      // 'copy-clipboard' is handled inside QuickActionsMenu
    }
  }, []);

  // Save time block
  const handleSaveTimeBlock = useCallback((blockData) => {
    setTimeBlocks(prev => [...prev, {
      id: 'block-' + Date.now(),
      date: blockData.date,
      startTime: blockData.startTime,
      endTime: blockData.endTime,
      reason: blockData.reason,
      reasonLabel: blockData.reasonLabel,
      isTimeBlock: true,
    }]);
    setShowTimeBlocker(false);
    const d = depsRef.current;
    if (d.toast) d.toast.success('Time blocked successfully');
  }, []);

  return {
    contextMenu,
    handleSlotContextMenu,
    handleEventContextMenu,
    handleContextMenuAction,
    showTimeBlocker,
    setShowTimeBlocker,
    timeBlockerInitial,
    timeBlocks,
    handleSaveTimeBlock,
  };
};

export default useCalendarContextMenu;
