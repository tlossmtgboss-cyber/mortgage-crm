import { useState, useCallback } from 'react';
import { calendarAPI, schedulerAPI } from '../services/api';
import { toast } from '../utils/toast';

/**
 * useCalendarActions -- Manages event/appointment CRUD operations for Calendar.js.
 *
 * Handles:
 * - Creating events (with optimistic updates)
 * - Creating appointments (with optimistic updates)
 * - Editing appointments (with optimistic updates)
 * - Deleting/cancelling events and appointments (with optimistic updates)
 * - Modal state for add, edit, and confirm dialogs
 *
 * @param {Object} options
 * @param {Function} options.loadEvents - Callback to reload events from the server
 * @param {Array} options.allEvents - Current events array (for rollback snapshots)
 * @param {Function} options.setAllEvents - State setter for events array
 * @returns {Object} Action handlers and modal state
 */
export function useCalendarActions({ loadEvents, allEvents, setAllEvents }) {
  // Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState(null);
  const [saving, setSaving] = useState(false);
  const [isBooking, setIsBooking] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  // ── Create Event ──

  const handleAddEvent = useCallback(async (eventData) => {
    if (isBooking) return;
    setIsBooking(true);

    const optimisticId = `optimistic-event-${Date.now()}`;
    const optimisticEvent = {
      id: optimisticId,
      title: eventData.title || 'New Event',
      start_time: eventData.start_time,
      end_time: eventData.end_time,
      description: eventData.description,
      location: eventData.location,
      event_type: eventData.event_type,
      isAppointment: false,
      isCrmEvent: false,
      _optimistic: true,
    };

    setAllEvents(prev => [...prev, optimisticEvent]);
    setShowAddModal(false);

    try {
      await calendarAPI.create(eventData);
      toast.success('Event created');
      loadEvents();
    } catch (err) {
      setAllEvents(prev => prev.filter(e => e.id !== optimisticId));
      toast.error('Failed to create event. Please try again.');
    } finally {
      setIsBooking(false);
    }
  }, [loadEvents, isBooking, setAllEvents]);

  // ── Create Appointment ──

  const handleAddAppointment = useCallback(async (appointmentData) => {
    if (isBooking) return;
    setIsBooking(true);

    const optimisticId = `optimistic-appt-${Date.now()}`;
    const startTime = appointmentData.scheduled_start;
    const durationMs = (appointmentData.duration_minutes || 30) * 60000;
    const endTime = new Date(new Date(startTime).getTime() + durationMs).toISOString();

    const optimisticEvent = {
      id: optimisticId,
      title: appointmentData.title || 'New Appointment',
      start_time: startTime,
      end_time: endTime,
      attendee_name: appointmentData.attendee_name,
      attendee_email: appointmentData.attendee_email,
      meeting_mode: appointmentData.meeting_mode,
      status: 'BOOKED',
      isAppointment: true,
      isCrmEvent: false,
      _optimistic: true,
    };

    setAllEvents(prev => [...prev, optimisticEvent]);
    setShowAddModal(false);

    try {
      await schedulerAPI.createAppointment(appointmentData);
      toast.success('Appointment booked');
      loadEvents();
    } catch (err) {
      setAllEvents(prev => prev.filter(e => e.id !== optimisticId));
      toast.error('Failed to create appointment. Please try again.');
    } finally {
      setIsBooking(false);
    }
  }, [loadEvents, isBooking, setAllEvents]);

  // ── Delete/Cancel Event ──

  const handleDeleteEvent = useCallback((event) => {
    const message = event.isAppointment && event.appointmentId
      ? 'Are you sure you want to cancel this appointment? The attendee will be notified.'
      : 'Are you sure you want to delete this event?';
    setConfirmAction({
      message,
      onConfirm: async () => {
        setConfirmAction(null);

        const removedEvent = event;
        setAllEvents(prev => prev.filter(e => e.id !== event.id));

        try {
          if (event.isAppointment && event.appointmentId) {
            await schedulerAPI.cancelAppointment(event.appointmentId, 'Cancelled by user');
            toast.success('Appointment cancelled');
          } else {
            const eventId = event.calendarEventId || event.id.replace('event-', '');
            await calendarAPI.delete(eventId);
            toast.success('Event deleted');
          }
          loadEvents();
        } catch (err) {
          setAllEvents(prev => [...prev, removedEvent]);
          toast.error('Failed to cancel: ' + (err.response?.data?.detail || err.message));
        }
      },
    });
  }, [loadEvents, setAllEvents]);

  // ── Open Edit Modal ──

  const handleEditAppointment = useCallback((event) => {
    if (!event.isAppointment) return;
    if (!event.start_time || !event.end_time) return;

    const startDate = new Date(event.start_time);
    const endDate = new Date(event.end_time);
    const durationMins = Math.round((endDate - startDate) / 60000);

    setEditingAppointment({
      id: event.appointmentId,
      title: event.title || '',
      attendee_name: event.attendee_name || '',
      attendee_email: event.attendee_email || '',
      attendee_phone: event.attendee_phone || '',
      meeting_mode: (event.meeting_mode || 'phone').toLowerCase(),
      date: startDate.toISOString().split('T')[0],
      time: startDate.toTimeString().slice(0, 5),
      duration: String(durationMins),
      description: event.description || '',
      status: event.status || 'BOOKED',
    });
    setShowEditModal(true);
  }, []);

  const handleEditFieldChange = useCallback((field, value) => {
    setEditingAppointment(prev => prev ? { ...prev, [field]: value } : prev);
  }, []);

  // ── Save Appointment Edit ──

  const handleSaveAppointment = useCallback(async (e) => {
    e.preventDefault();
    if (!editingAppointment || saving) return;

    setSaving(true);
    const startDateTime = new Date(`${editingAppointment.date}T${editingAppointment.time}`);
    const endDateTime = new Date(startDateTime.getTime() + parseInt(editingAppointment.duration) * 60000);

    const previousEvents = allEvents;
    const apptId = editingAppointment.id;

    // Optimistically update
    setAllEvents(prev => prev.map(evt => {
      const matchId = evt.appointmentId === String(apptId) || evt.id === `appt-${apptId}`;
      if (!matchId) return evt;
      return {
        ...evt,
        title: editingAppointment.title || evt.title,
        start_time: startDateTime.toISOString(),
        end_time: endDateTime.toISOString(),
        attendee_name: editingAppointment.attendee_name || evt.attendee_name,
        meeting_mode: (editingAppointment.meeting_mode || 'phone').toLowerCase(),
        _optimistic: true,
      };
    }));

    setShowEditModal(false);
    setEditingAppointment(null);

    try {
      await schedulerAPI.updateAppointment(apptId, {
        title: editingAppointment.title || undefined,
        attendee_name: editingAppointment.attendee_name || undefined,
        attendee_email: editingAppointment.attendee_email || undefined,
        attendee_phone: editingAppointment.attendee_phone || undefined,
        meeting_mode: (editingAppointment.meeting_mode || 'phone').toLowerCase(),
        scheduled_start: startDateTime.toISOString(),
        scheduled_end: endDateTime.toISOString(),
        duration_minutes: parseInt(editingAppointment.duration),
        description: editingAppointment.description || undefined,
      });

      toast.success('Appointment updated');
      loadEvents();
    } catch (err) {
      setAllEvents(previousEvents);
      toast.error('Failed to reschedule: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }, [editingAppointment, saving, allEvents, loadEvents, setAllEvents]);

  // ── Cancel from Edit Modal ──

  const handleCancelFromModal = useCallback(() => {
    if (!editingAppointment || saving) return;
    setConfirmAction({
      message: 'Are you sure you want to cancel this appointment? The attendee will be notified.',
      onConfirm: async () => {
        setConfirmAction(null);
        setSaving(true);

        const apptId = editingAppointment.id;
        const previousEvents = allEvents;

        setAllEvents(prev => prev.filter(e => {
          return !(e.appointmentId === String(apptId) || e.id === `appt-${apptId}`);
        }));
        setShowEditModal(false);
        setEditingAppointment(null);

        try {
          await schedulerAPI.cancelAppointment(apptId, 'Cancelled by user');
          toast.success('Appointment cancelled');
          loadEvents();
        } catch (err) {
          setAllEvents(previousEvents);
          toast.error('Failed to cancel: ' + (err.response?.data?.detail || err.message));
        } finally {
          setSaving(false);
        }
      },
    });
  }, [editingAppointment, saving, allEvents, loadEvents, setAllEvents]);

  // ── Open Add Modal ──

  const openAddModal = useCallback(() => {
    setSelectedDate(new Date());
    setSelectedTime(null);
    setShowAddModal(true);
  }, []);

  return {
    // Modal state
    showAddModal,
    setShowAddModal,
    selectedDate,
    setSelectedDate,
    selectedTime,
    setSelectedTime,
    showEditModal,
    setShowEditModal,
    editingAppointment,
    setEditingAppointment,
    saving,
    isBooking,
    confirmAction,
    setConfirmAction,

    // Handlers
    handleAddEvent,
    handleAddAppointment,
    handleDeleteEvent,
    handleEditAppointment,
    handleEditFieldChange,
    handleSaveAppointment,
    handleCancelFromModal,
    openAddModal,
  };
}

export default useCalendarActions;
