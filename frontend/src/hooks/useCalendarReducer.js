import { useReducer, useMemo, useCallback } from 'react';

// ---- Constants ----

export const TAB_CONFIG = [
  { key: 'all', label: 'Appointments', filterType: null },
  { key: 'pre_purchase', label: 'Pre-Purchase Consultations', filterType: 'pre_purchase_consultation' },
  { key: 'purchase', label: 'Purchase Consultations', filterType: 'purchase_consultation' },
  { key: 'closing', label: 'Closings', filterType: 'closing' },
];

export const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export const DAY_ABBREVIATIONS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
export const VIEW_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];

// ---- Action types ----

export const ACTIONS = {
  SET_VIEW: 'SET_VIEW',
  NAVIGATE_DATE: 'NAVIGATE_DATE',
  SET_CURRENT_DATE: 'SET_CURRENT_DATE',
  SELECT_DATE: 'SELECT_DATE',
  SELECT_EVENT: 'SELECT_EVENT',
  SET_EVENTS: 'SET_EVENTS',
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
  SET_ACTIVE_TAB: 'SET_ACTIVE_TAB',
  SET_SEARCH_QUERY: 'SET_SEARCH_QUERY',
  SET_TIMEZONE: 'SET_TIMEZONE',
  OPEN_ADD_MODAL: 'OPEN_ADD_MODAL',
  CLOSE_ADD_MODAL: 'CLOSE_ADD_MODAL',
  OPEN_EDIT_MODAL: 'OPEN_EDIT_MODAL',
  CLOSE_EDIT_MODAL: 'CLOSE_EDIT_MODAL',
  SET_EDITING_APPOINTMENT: 'SET_EDITING_APPOINTMENT',
  SET_SAVING: 'SET_SAVING',
  SET_CONFIRM_ACTION: 'SET_CONFIRM_ACTION',
  CLEAR_CONFIRM_ACTION: 'CLEAR_CONFIRM_ACTION',
  SET_TEAM_MEMBERS: 'SET_TEAM_MEMBERS',
};

// ---- Initial state ----

const initialState = {
  view: 'month', // day, week, month
  currentDate: new Date(),
  selectedDate: null,
  selectedTime: null,
  events: [],
  isLoading: true,
  error: null,
  activeTab: 'all',
  searchQuery: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  addModalOpen: false,
  editModalOpen: false,
  editingAppointment: null,
  saving: false,
  confirmAction: null,
  teamMembers: [],
};

// ---- Reducer ----

function calendarReducer(state, action) {
  switch (action.type) {
    case ACTIONS.SET_VIEW:
      return { ...state, view: action.payload };

    case ACTIONS.NAVIGATE_DATE: {
      const { direction } = action.payload; // 'prev', 'next', 'today'
      if (direction === 'today') {
        return { ...state, currentDate: new Date() };
      }
      const delta = direction === 'prev' ? -1 : 1;
      const d = new Date(state.currentDate);
      if (state.view === 'day') {
        d.setDate(d.getDate() + delta);
      } else if (state.view === 'week') {
        d.setDate(d.getDate() + delta * 7);
      } else {
        d.setMonth(d.getMonth() + delta);
      }
      return { ...state, currentDate: d };
    }

    case ACTIONS.SET_CURRENT_DATE:
      return { ...state, currentDate: action.payload };

    case ACTIONS.SELECT_DATE:
      return { ...state, selectedDate: action.payload.date, selectedTime: action.payload.time ?? null };

    case ACTIONS.SELECT_EVENT:
      return { ...state, selectedEvent: action.payload };

    case ACTIONS.SET_EVENTS:
      return { ...state, events: action.payload };

    case ACTIONS.SET_LOADING:
      return { ...state, isLoading: action.payload };

    case ACTIONS.SET_ERROR:
      return { ...state, error: action.payload };

    case ACTIONS.CLEAR_ERROR:
      return { ...state, error: null };

    case ACTIONS.SET_ACTIVE_TAB:
      return { ...state, activeTab: action.payload };

    case ACTIONS.SET_SEARCH_QUERY:
      return { ...state, searchQuery: action.payload };

    case ACTIONS.SET_TIMEZONE:
      return { ...state, timezone: action.payload };

    case ACTIONS.OPEN_ADD_MODAL:
      return {
        ...state,
        addModalOpen: true,
        selectedDate: action.payload?.date || new Date(),
        selectedTime: action.payload?.time ?? null,
      };

    case ACTIONS.CLOSE_ADD_MODAL:
      return { ...state, addModalOpen: false };

    case ACTIONS.OPEN_EDIT_MODAL:
      return { ...state, editModalOpen: true, editingAppointment: action.payload };

    case ACTIONS.CLOSE_EDIT_MODAL:
      return { ...state, editModalOpen: false, editingAppointment: null };

    case ACTIONS.SET_EDITING_APPOINTMENT:
      return { ...state, editingAppointment: action.payload };

    case ACTIONS.SET_SAVING:
      return { ...state, saving: action.payload };

    case ACTIONS.SET_CONFIRM_ACTION:
      return { ...state, confirmAction: action.payload };

    case ACTIONS.CLEAR_CONFIRM_ACTION:
      return { ...state, confirmAction: null };

    case ACTIONS.SET_TEAM_MEMBERS:
      return { ...state, teamMembers: action.payload };

    default:
      return state;
  }
}

// ---- Helpers ----

export const formatHour = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

export const getStartOfWeek = (date) => {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  d.setHours(0, 0, 0, 0);
  return d;
};

export const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

/** Keyboard handler for interactive non-button elements (Enter/Space) */
export const handleInteractiveKeyDown = (e, onClick) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onClick(e);
  }
};

/** Map unified API response events to frontend format */
export const mapUnifiedEvents = (events) =>
  (events || []).map((event) => ({
    ...event,
    isAppointment: event.is_appointment,
    isCrmEvent: event.is_crm_event,
    appointmentId: event.is_appointment ? event.id.replace('appt-', '') : undefined,
    crmEventId: event.is_crm_event ? event.id.replace('crm-', '') : undefined,
    calendarEventId: event.source === 'calendar' ? event.id.replace('event-', '') : undefined,
  }));

export const formatEventTime = (startTime, endTime) => {
  const start = new Date(startTime);
  const end = new Date(endTime);
  const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  const endStr = end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  const duration = Math.round((end - start) / (1000 * 60));
  return { startStr, endStr, duration };
};

export const formatEventDate = (dateStr) => {
  const date = new Date(dateStr);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
  return `${DAY_NAMES[date.getDay()]} \u2022 ${MONTH_NAMES[date.getMonth()]} ${date.getDate()}`;
};

export const getDaysInMonth = (date) => {
  const year = date.getFullYear();
  const month = date.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  return {
    daysInMonth: lastDay.getDate(),
    startingDayOfWeek: firstDay.getDay(),
    year,
    month,
  };
};

export const getEventColorClass = (eventType) => {
  const typeMap = {
    meeting: 'event-color-meeting',
    call: 'event-color-call',
    appraisal: 'event-color-appraisal',
    closing: 'event-color-closing',
    pre_purchase_consultation: 'event-color-pre-purchase',
    purchase_consultation: 'event-color-purchase',
  };
  return typeMap[eventType] || 'event-color-other';
};

// ---- Hook ----

export function useCalendarState() {
  const [state, dispatch] = useReducer(calendarReducer, initialState);

  /** Filter events by the active tab */
  const getFilteredEvents = useCallback(
    (eventList) => {
      const tab = TAB_CONFIG.find((t) => t.key === state.activeTab);
      if (!tab || !tab.filterType) return eventList;
      return eventList.filter((event) => event.event_type === tab.filterType);
    },
    [state.activeTab],
  );

  /** Events filtered by tab + search, sorted chronologically */
  const sortedEvents = useMemo(() => {
    const filtered = getFilteredEvents(state.events).filter((event) => {
      if (!state.searchQuery) return true;
      const q = state.searchQuery.toLowerCase();
      return (
        (event.title || '').toLowerCase().includes(q) ||
        (event.attendee_name || '').toLowerCase().includes(q) ||
        (event.location || '').toLowerCase().includes(q)
      );
    });
    return [...filtered].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [state.events, state.searchQuery, getFilteredEvents]);

  /** Get events for a specific calendar date */
  const getEventsForDate = useCallback(
    (day, year, month) => {
      const dateStart = new Date(year, month, day);
      const dateEnd = new Date(year, month, day, 23, 59, 59);
      return getFilteredEvents(state.events).filter((event) => {
        const eventDate = new Date(event.start_time);
        return eventDate >= dateStart && eventDate <= dateEnd;
      });
    },
    [state.events, getFilteredEvents],
  );

  const getEventsForDateObj = useCallback(
    (dateObj) => getEventsForDate(dateObj.getDate(), dateObj.getFullYear(), dateObj.getMonth()),
    [getEventsForDate],
  );

  const getEventsForDateAndHour = useCallback(
    (dateObj, hour) =>
      getEventsForDateObj(dateObj).filter((event) => new Date(event.start_time).getHours() === hour),
    [getEventsForDateObj],
  );

  /** Build human-readable header subtitle based on current view + date */
  const headerSubtitle = useMemo(() => {
    if (state.view === 'day') {
      return `${DAY_NAMES[state.currentDate.getDay()]}, ${MONTH_NAMES[state.currentDate.getMonth()]} ${state.currentDate.getDate()}, ${state.currentDate.getFullYear()}`;
    }
    if (state.view === 'week') {
      const weekStart = getStartOfWeek(state.currentDate);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      const startMonth = MONTH_NAMES[weekStart.getMonth()].slice(0, 3);
      const endMonth = MONTH_NAMES[weekEnd.getMonth()].slice(0, 3);
      if (weekStart.getMonth() === weekEnd.getMonth()) {
        return `${startMonth} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
      }
      return `${startMonth} ${weekStart.getDate()} - ${endMonth} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
    }
    return `${MONTH_NAMES[state.currentDate.getMonth()]} ${state.currentDate.getFullYear()}`;
  }, [state.view, state.currentDate]);

  return {
    state,
    dispatch,
    sortedEvents,
    getEventsForDate,
    getEventsForDateObj,
    getEventsForDateAndHour,
    headerSubtitle,
  };
}
