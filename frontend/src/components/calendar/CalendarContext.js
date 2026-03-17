import React, { createContext, useContext, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarAPI, schedulerAPI, unifiedCalendarAPI, teamAPI } from '../../services/api';
import {
  useCalendarState,
  ACTIONS,
  mapUnifiedEvents,
} from '../../hooks/useCalendarReducer';

const CalendarContext = createContext(null);

export function CalendarProvider({ children }) {
  const navigate = useNavigate();
  const calendarState = useCalendarState();
  const { state, dispatch } = calendarState;

  // ---- Data loading ----

  const loadEvents = useCallback(async () => {
    try {
      dispatch({ type: ACTIONS.SET_LOADING, payload: true });
      const startDate = new Date(state.currentDate.getFullYear(), state.currentDate.getMonth(), 1);
      const endDate = new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() + 1, 0, 23, 59, 59);

      const response = await unifiedCalendarAPI.getAll({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      dispatch({ type: ACTIONS.SET_EVENTS, payload: mapUnifiedEvents(response.events) });
      dispatch({ type: ACTIONS.CLEAR_ERROR });
    } catch {
      dispatch({ type: ACTIONS.SET_ERROR, payload: 'Unable to load calendar events. Please try again.' });
      dispatch({ type: ACTIONS.SET_EVENTS, payload: [] });
    } finally {
      dispatch({ type: ACTIONS.SET_LOADING, payload: false });
    }
  }, [state.currentDate, dispatch]);

  const loadAllEvents = useCallback(async () => {
    try {
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 6);
      const endDate = new Date();
      endDate.setMonth(endDate.getMonth() + 6);

      const response = await unifiedCalendarAPI.getAll({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      dispatch({ type: ACTIONS.SET_EVENTS, payload: mapUnifiedEvents(response.events) });
      dispatch({ type: ACTIONS.CLEAR_ERROR });
    } catch {
      dispatch({ type: ACTIONS.SET_ERROR, payload: 'Unable to load calendar events. Please try again.' });
      dispatch({ type: ACTIONS.SET_EVENTS, payload: [] });
    }
  }, [dispatch]);

  // Load events when currentDate changes
  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  // Load wider event range on mount
  useEffect(() => {
    loadAllEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load team members on mount
  useEffect(() => {
    teamAPI
      .getMembers()
      .then((members) => dispatch({ type: ACTIONS.SET_TEAM_MEMBERS, payload: members }))
      .catch(() => {});
  }, [dispatch]);

  // ---- Event handlers ----

  const handleAddEvent = useCallback(
    async (eventData) => {
      try {
        await calendarAPI.create(eventData);
        loadEvents();
        loadAllEvents();
        dispatch({ type: ACTIONS.CLOSE_ADD_MODAL });
      } catch {
        dispatch({ type: ACTIONS.SET_ERROR, payload: 'Failed to create event. Please try again.' });
      }
    },
    [loadEvents, loadAllEvents, dispatch],
  );

  const handleAddAppointment = useCallback(
    async (appointmentData) => {
      try {
        await schedulerAPI.createAppointment(appointmentData);
        loadEvents();
        loadAllEvents();
        dispatch({ type: ACTIONS.CLOSE_ADD_MODAL });
      } catch {
        dispatch({ type: ACTIONS.SET_ERROR, payload: 'Failed to create appointment. Please try again.' });
      }
    },
    [loadEvents, loadAllEvents, dispatch],
  );

  const handleDeleteEvent = useCallback(
    (event) => {
      const message =
        event.isAppointment && event.appointmentId
          ? 'Are you sure you want to cancel this appointment? The attendee will be notified.'
          : 'Are you sure you want to delete this event?';
      dispatch({
        type: ACTIONS.SET_CONFIRM_ACTION,
        payload: {
          message,
          onConfirm: async () => {
            dispatch({ type: ACTIONS.CLEAR_CONFIRM_ACTION });
            try {
              if (event.isAppointment && event.appointmentId) {
                await schedulerAPI.cancelAppointment(event.appointmentId, 'Cancelled by user');
              } else {
                const eventId = event.calendarEventId || event.id.replace('event-', '');
                await calendarAPI.delete(eventId);
              }
              loadEvents();
              loadAllEvents();
            } catch (err) {
              dispatch({
                type: ACTIONS.SET_ERROR,
                payload: 'Failed to cancel: ' + (err.response?.data?.detail || err.message),
              });
            }
          },
        },
      });
    },
    [loadEvents, loadAllEvents, dispatch],
  );

  const handleEditAppointment = useCallback(
    (event) => {
      if (!event.isAppointment || !event.start_time || !event.end_time) return;

      const startDate = new Date(event.start_time);
      const endDate = new Date(event.end_time);
      const durationMins = Math.round((endDate - startDate) / 60000);

      dispatch({
        type: ACTIONS.OPEN_EDIT_MODAL,
        payload: {
          id: event.appointmentId,
          title: event.title || '',
          attendee_name: event.attendee_name || '',
          attendee_email: event.attendee_email || '',
          attendee_phone: event.attendee_phone || '',
          meeting_mode: event.meeting_mode || 'PHONE',
          date: startDate.toISOString().split('T')[0],
          time: startDate.toTimeString().slice(0, 5),
          duration: String(durationMins),
          description: event.description || '',
          status: event.status || 'BOOKED',
        },
      });
    },
    [dispatch],
  );

  const handleSaveAppointment = useCallback(
    async (e) => {
      e.preventDefault();
      if (!state.editingAppointment) return;

      dispatch({ type: ACTIONS.SET_SAVING, payload: true });
      try {
        const startDateTime = new Date(`${state.editingAppointment.date}T${state.editingAppointment.time}`);
        const endDateTime = new Date(
          startDateTime.getTime() + parseInt(state.editingAppointment.duration) * 60000,
        );

        await schedulerAPI.updateAppointment(state.editingAppointment.id, {
          title: state.editingAppointment.title,
          attendee_name: state.editingAppointment.attendee_name,
          attendee_email: state.editingAppointment.attendee_email,
          attendee_phone: state.editingAppointment.attendee_phone,
          meeting_mode: state.editingAppointment.meeting_mode,
          scheduled_start: startDateTime.toISOString(),
          scheduled_end: endDateTime.toISOString(),
          duration_minutes: parseInt(state.editingAppointment.duration),
          attendee_notes: state.editingAppointment.description,
        });

        dispatch({ type: ACTIONS.CLOSE_EDIT_MODAL });
        loadEvents();
        loadAllEvents();
      } catch (err) {
        dispatch({
          type: ACTIONS.SET_ERROR,
          payload: 'Failed to reschedule: ' + (err.response?.data?.detail || err.message),
        });
      } finally {
        dispatch({ type: ACTIONS.SET_SAVING, payload: false });
      }
    },
    [state.editingAppointment, loadEvents, loadAllEvents, dispatch],
  );

  const handleCancelFromModal = useCallback(() => {
    if (!state.editingAppointment) return;
    dispatch({
      type: ACTIONS.SET_CONFIRM_ACTION,
      payload: {
        message: 'Are you sure you want to cancel this appointment? The attendee will be notified.',
        onConfirm: async () => {
          dispatch({ type: ACTIONS.CLEAR_CONFIRM_ACTION });
          dispatch({ type: ACTIONS.SET_SAVING, payload: true });
          try {
            await schedulerAPI.cancelAppointment(state.editingAppointment.id, 'Cancelled by user');
            dispatch({ type: ACTIONS.CLOSE_EDIT_MODAL });
            loadEvents();
            loadAllEvents();
          } catch (err) {
            dispatch({
              type: ACTIONS.SET_ERROR,
              payload: 'Failed to cancel: ' + (err.response?.data?.detail || err.message),
            });
          } finally {
            dispatch({ type: ACTIONS.SET_SAVING, payload: false });
          }
        },
      },
    });
  }, [state.editingAppointment, loadEvents, loadAllEvents, dispatch]);

  const handleRetry = useCallback(() => {
    dispatch({ type: ACTIONS.CLEAR_ERROR });
    loadEvents();
    loadAllEvents();
  }, [loadEvents, loadAllEvents, dispatch]);

  const navigateToSettings = useCallback(() => {
    navigate('/calendar-settings');
  }, [navigate]);

  const contextValue = {
    ...calendarState,
    loadEvents,
    loadAllEvents,
    handleAddEvent,
    handleAddAppointment,
    handleDeleteEvent,
    handleEditAppointment,
    handleSaveAppointment,
    handleCancelFromModal,
    handleRetry,
    navigateToSettings,
  };

  return <CalendarContext.Provider value={contextValue}>{children}</CalendarContext.Provider>;
}

export function useCalendar() {
  const context = useContext(CalendarContext);
  if (!context) {
    throw new Error('useCalendar must be used within a CalendarProvider');
  }
  return context;
}
