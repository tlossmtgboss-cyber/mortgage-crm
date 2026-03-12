import React, { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarAPI, schedulerAPI, unifiedCalendarAPI, teamAPI } from '../services/api';
import { useCalendarKeyboard } from '../hooks/useCalendarKeyboard';
import './Calendar.css';

// Lazy load heavy modal components that are conditionally rendered
const CalendarSearch = lazy(() => import('../components/calendar/CalendarSearch'));
const KeyboardShortcutsHelp = lazy(() => import('../components/calendar/KeyboardShortcutsHelp'));

const TAB_CONFIG = [
  { key: 'all', label: 'Appointments', filterType: null },
  { key: 'pre_purchase', label: 'Pre-Purchase Consultations', filterType: 'pre_purchase_consultation' },
  { key: 'purchase', label: 'Purchase Consultations', filterType: 'purchase_consultation' },
  { key: 'closing', label: 'Closings', filterType: 'closing' },
];

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const dayAbbreviations = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

// Hours for Day/Week views (7am to 8pm)
const VIEW_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];

const formatHour = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

// DRY helper: map unified API response to frontend format
const mapUnifiedEvents = (events) => (events || []).map(event => ({
  ...event,
  isAppointment: event.is_appointment,
  isCrmEvent: event.is_crm_event,
  appointmentId: event.is_appointment ? event.id.replace('appt-', '') : undefined,
  crmEventId: event.is_crm_event ? event.id.replace('crm-', '') : undefined,
  calendarEventId: event.source === 'calendar' ? event.id.replace('event-', '') : undefined,
}));

const getStartOfWeek = (date) => {
  const d = new Date(date);
  const day = d.getDay();
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
};

const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

// Keyboard handler: triggers onClick on Enter or Space for interactive non-button elements
const handleInteractiveKeyDown = (e, onClick) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onClick(e);
  }
};

function Calendar() {
  const navigate = useNavigate();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState('month');
  const [allEvents, setAllEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Advanced search overlay state
  const [showSearch, setShowSearch] = useState(false);

  // Edit/reschedule appointment state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState(null);
  const [saving, setSaving] = useState(false);

  // Team members for appointment assignment
  const [teamMembers, setTeamMembers] = useState([]);

  // Inline confirmation dialog state
  const [confirmAction, setConfirmAction] = useState(null);

  // Keyboard navigation state
  const [selectedEventIndex, setSelectedEventIndex] = useState(-1);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const liveAnnouncerRef = useRef(null);

  useEffect(() => {
    loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDate]);

  useEffect(() => {
    loadAllEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    teamAPI.getMembers().then(members => setTeamMembers(members)).catch(() => {});
  }, []);

  // Keyboard shortcut: Ctrl/Cmd+K to open search
  useEffect(() => {
    const handleSearchShortcut = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setShowSearch(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleSearchShortcut);
    return () => window.removeEventListener('keydown', handleSearchShortcut);
  }, []);

  const handleSearchSelectAppointment = useCallback((appointment) => {
    setShowSearch(false);
    // Navigate to the appointment's date and open detail view
    if (appointment.scheduled_start) {
      setCurrentDate(new Date(appointment.scheduled_start));
    }
    // If it has a numeric ID, open the edit modal
    if (appointment.id && typeof appointment.id === 'number') {
      setEditingAppointment(appointment);
      setShowEditModal(true);
    }
  }, []);

  // Announce date changes to screen readers
  const announceToScreenReader = useCallback((message) => {
    if (liveAnnouncerRef.current) {
      liveAnnouncerRef.current.textContent = message;
    }
  }, []);

  // Reset selected event index when events change
  useEffect(() => {
    setSelectedEventIndex(-1);
  }, [activeTab, searchQuery]);

  // Determine if any modal is open (disables most keyboard shortcuts)
  const hasModalOpen = showAddModal || showEditModal || showSearch || showShortcutsHelp || !!confirmAction;

  // Keyboard navigation: select previous event in sidebar
  const handleSelectPrevEvent = useCallback(() => {
    setSelectedEventIndex(prev => {
      const newIdx = prev <= 0 ? 0 : prev - 1;
      return newIdx;
    });
  }, []);

  // Keyboard navigation: select next event in sidebar
  const handleSelectNextEvent = useCallback(() => {
    setSelectedEventIndex(prev => {
      // sortedEvents is used in the memoized computation below
      // We clamp to the last available index at render time
      return prev + 1;
    });
  }, []);

  // Keyboard navigation: open the selected event for editing (uses ref for latest data)
  const openSelectedEventRef = useRef(null);
  const handleOpenSelectedEvent = useCallback(() => {
    openSelectedEventRef.current?.();
  }, []);

  // Close all modals
  const handleCloseAllModals = useCallback(() => {
    if (confirmAction) {
      setConfirmAction(null);
    } else if (showShortcutsHelp) {
      setShowShortcutsHelp(false);
    } else if (showSearch) {
      setShowSearch(false);
    } else if (showEditModal) {
      setShowEditModal(false);
    } else if (showAddModal) {
      setShowAddModal(false);
    }
  }, [confirmAction, showShortcutsHelp, showSearch, showEditModal, showAddModal]);

  // Wire up the keyboard hook
  useCalendarKeyboard({
    onPrev: useCallback(() => {
      handlePrevRef.current?.();
    }, []),
    onNext: useCallback(() => {
      handleNextRef.current?.();
    }, []),
    onToday: useCallback(() => {
      handleTodayRef.current?.();
      announceToScreenReader('Navigated to today');
    }, [announceToScreenReader]),
    onSetView: useCallback((v) => {
      setView(v);
      announceToScreenReader(`Switched to ${v} view`);
    }, [announceToScreenReader]),
    onNewEvent: useCallback(() => {
      setSelectedDate(new Date());
      setSelectedTime(null);
      setShowAddModal(true);
    }, []),
    onOpenSearch: useCallback(() => {
      setShowSearch(true);
    }, []),
    onCloseModals: handleCloseAllModals,
    onToggleShortcutsHelp: useCallback(() => {
      setShowShortcutsHelp(prev => !prev);
    }, []),
    onSelectPrevEvent: handleSelectPrevEvent,
    onSelectNextEvent: handleSelectNextEvent,
    onOpenSelectedEvent: handleOpenSelectedEvent,
    hasModalOpen,
  });

  // Stable refs for navigation handlers (defined later in the component)
  const handlePrevRef = useRef(null);
  const handleNextRef = useRef(null);
  const handleTodayRef = useRef(null);

  const loadEvents = async () => {
    try {
      setLoading(true);
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0, 23, 59, 59);

      const response = await unifiedCalendarAPI.getAll({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      setAllEvents(mapUnifiedEvents(response.events));
      setError(null);
    } catch {
      setError('Unable to load calendar events. Please try again.');
      setAllEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const loadAllEvents = async () => {
    try {
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 6);
      const endDate = new Date();
      endDate.setMonth(endDate.getMonth() + 6);

      const response = await unifiedCalendarAPI.getAll({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      setAllEvents(mapUnifiedEvents(response.events));
      setError(null);
    } catch {
      setError('Unable to load calendar events. Please try again.');
      setAllEvents([]);
    }
  };

  const handleAddEvent = useCallback(async (eventData) => {
    try {
      await calendarAPI.create(eventData);
      loadEvents();
      loadAllEvents();
      setShowAddModal(false);
    } catch {
      setError('Failed to create event. Please try again.');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAddAppointment = useCallback(async (appointmentData) => {
    try {
      await schedulerAPI.createAppointment(appointmentData);
      loadEvents();
      loadAllEvents();
      setShowAddModal(false);
    } catch {
      setError('Failed to create appointment. Please try again.');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDeleteEvent = useCallback((event) => {
    const message = event.isAppointment && event.appointmentId
      ? 'Are you sure you want to cancel this appointment? The attendee will be notified.'
      : 'Are you sure you want to delete this event?';
    setConfirmAction({
      message,
      onConfirm: async () => {
        setConfirmAction(null);
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
          setError('Failed to cancel: ' + (err.response?.data?.detail || err.message));
        }
      },
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleEditAppointment = useCallback((event) => {
    if (!event.isAppointment) return;
    if (!event.start_time || !event.end_time) return;

    const startDate = new Date(event.start_time);
    const endDate = new Date(event.end_time);
    const durationMs = endDate - startDate;
    const durationMins = Math.round(durationMs / 60000);

    setEditingAppointment({
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
    });
    setShowEditModal(true);
  }, []);

  const handleSaveAppointment = useCallback(async (e) => {
    e.preventDefault();
    if (!editingAppointment) return;

    setSaving(true);
    try {
      const startDateTime = new Date(`${editingAppointment.date}T${editingAppointment.time}`);
      const endDateTime = new Date(startDateTime.getTime() + parseInt(editingAppointment.duration) * 60000);

      const updateData = {
        title: editingAppointment.title,
        attendee_name: editingAppointment.attendee_name,
        attendee_email: editingAppointment.attendee_email,
        attendee_phone: editingAppointment.attendee_phone,
        meeting_mode: editingAppointment.meeting_mode,
        scheduled_start: startDateTime.toISOString(),
        scheduled_end: endDateTime.toISOString(),
        duration_minutes: parseInt(editingAppointment.duration),
        attendee_notes: editingAppointment.description,
      };

      await schedulerAPI.updateAppointment(editingAppointment.id, updateData);

      setShowEditModal(false);
      setEditingAppointment(null);
      loadEvents();
      loadAllEvents();
    } catch (err) {
      setError('Failed to reschedule: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingAppointment]);

  const handleCancelFromModal = useCallback(() => {
    if (!editingAppointment) return;
    setConfirmAction({
      message: 'Are you sure you want to cancel this appointment? The attendee will be notified.',
      onConfirm: async () => {
        setConfirmAction(null);
        setSaving(true);
        try {
          await schedulerAPI.cancelAppointment(editingAppointment.id, 'Cancelled by user');
          setShowEditModal(false);
          setEditingAppointment(null);
          loadEvents();
          loadAllEvents();
        } catch (err) {
          setError('Failed to cancel: ' + (err.response?.data?.detail || err.message));
        } finally {
          setSaving(false);
        }
      },
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingAppointment]);

  // Pre-filter events by active tab (memoized to avoid recomputation in renders)
  const filteredByTab = useMemo(() => {
    const tab = TAB_CONFIG.find(t => t.key === activeTab);
    if (!tab || !tab.filterType) return allEvents;
    return allEvents.filter(event => event.event_type === tab.filterType);
  }, [allEvents, activeTab]);

  // Also keep the getFilteredEvents helper for view renderers that need it
  const getFilteredEvents = useCallback((eventList) => {
    const tab = TAB_CONFIG.find(t => t.key === activeTab);
    if (!tab || !tab.filterType) return eventList;
    return eventList.filter(event => event.event_type === tab.filterType);
  }, [activeTab]);

  // Sort and group events by date, with search filter (memoized)
  const sortedEvents = useMemo(() => {
    const filtered = filteredByTab.filter(event => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (event.title || '').toLowerCase().includes(q)
        || (event.attendee_name || '').toLowerCase().includes(q)
        || (event.location || '').toLowerCase().includes(q);
    });
    return [...filtered].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [filteredByTab, searchQuery]);

  // Clamp selectedEventIndex to valid range and scroll into view
  const clampedSelectedIndex = sortedEvents.length === 0
    ? -1
    : Math.max(-1, Math.min(selectedEventIndex, sortedEvents.length - 1));

  // Keep clampedSelectedIndex in sync with state
  useEffect(() => {
    if (clampedSelectedIndex !== selectedEventIndex) {
      setSelectedEventIndex(clampedSelectedIndex);
    }
  }, [clampedSelectedIndex, selectedEventIndex]);

  // Scroll selected event into view
  useEffect(() => {
    if (clampedSelectedIndex >= 0) {
      const el = document.querySelector(`[data-event-index="${clampedSelectedIndex}"]`);
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      // Announce for screen readers
      const event = sortedEvents[clampedSelectedIndex];
      if (event) {
        announceToScreenReader(`Selected: ${event.title || 'event'}`);
      }
    }
  }, [clampedSelectedIndex, sortedEvents, announceToScreenReader]);

  // Handle Enter key on selected event (wired via ref to avoid stale closure)
  // The keyboard hook calls onOpenSelectedEvent -> openSelectedEventRef.current()
  useEffect(() => {
    openSelectedEventRef.current = () => {
      if (clampedSelectedIndex >= 0 && sortedEvents[clampedSelectedIndex]) {
        const event = sortedEvents[clampedSelectedIndex];
        if (event.isAppointment) {
          handleEditAppointment(event);
        }
      }
    };
  });


  const formatEventTime = useCallback((startTime, endTime) => {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const endStr = end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const duration = Math.round((end - start) / (1000 * 60));
    return { startStr, endStr, duration };
  }, []);

  const formatEventDate = useCallback((dateStr) => {
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return 'Tomorrow';
    } else {
      return `${dayNames[date.getDay()]} \u2022 ${monthNames[date.getMonth()]} ${date.getDate()}`;
    }
  }, []);

  const getDaysInMonth = useCallback((date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = firstDay.getDay();

    return { daysInMonth, startingDayOfWeek, year, month };
  }, []);

  // Mini calendar months derived from currentDate (memoized to avoid recomputation)
  const currentMonthData = useMemo(() => getDaysInMonth(currentDate), [currentDate, getDaysInMonth]);
  const nextMonthData = useMemo(() => {
    const nextMonthDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1);
    return getDaysInMonth(nextMonthDate);
  }, [currentDate, getDaysInMonth]);

  // View-aware navigation
  const handlePrev = useCallback(() => {
    if (view === 'day') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() - 1));
    } else if (view === 'week') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() - 7));
    } else {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1));
    }
    announceToScreenReader(`Navigated to previous ${view}`);
  }, [view, announceToScreenReader]);

  const handleNext = useCallback(() => {
    if (view === 'day') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + 1));
    } else if (view === 'week') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + 7));
    } else {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1));
    }
    announceToScreenReader(`Navigated to next ${view}`);
  }, [view, announceToScreenReader]);

  const handleToday = useCallback(() => {
    setCurrentDate(new Date());
    announceToScreenReader('Navigated to today');
  }, [announceToScreenReader]);

  // Keep refs in sync for the keyboard hook
  handlePrevRef.current = handlePrev;
  handleNextRef.current = handleNext;
  handleTodayRef.current = handleToday;

  // Scroll mini calendar (same as prev/next in month mode)
  const handleScrollUp = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  }, []);

  const handleScrollDown = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  }, []);

  const handleDayClick = useCallback((day, year, month) => {
    // year and month are always passed explicitly from the mini calendar renderers
    const date = new Date(year, month, day);
    setSelectedDate(date);
    setSelectedTime(null);
    setShowAddModal(true);
  }, []);

  const handleTimeSlotClick = useCallback((date, hour) => {
    setSelectedDate(date);
    setSelectedTime(hour);
    setShowAddModal(true);
  }, []);

  // Pre-index filtered events by date key for O(1) lookups in day/week/month views
  const eventsByDateKey = useMemo(() => {
    const index = {};
    for (const event of filteredByTab) {
      const eventDate = new Date(event.start_time);
      const key = `${eventDate.getFullYear()}-${eventDate.getMonth()}-${eventDate.getDate()}`;
      if (!index[key]) index[key] = [];
      index[key].push(event);
    }
    return index;
  }, [filteredByTab]);

  const getEventsForDate = useCallback((day, year, month) => {
    const key = `${year}-${month}-${day}`;
    return eventsByDateKey[key] || [];
  }, [eventsByDateKey]);

  const getEventsForDateObj = useCallback((dateObj) => {
    return getEventsForDate(dateObj.getDate(), dateObj.getFullYear(), dateObj.getMonth());
  }, [getEventsForDate]);

  const getEventsForDateAndHour = useCallback((dateObj, hour) => {
    const dayEvents = getEventsForDateObj(dateObj);
    return dayEvents.filter(event => {
      const eventDate = new Date(event.start_time);
      return eventDate.getHours() === hour;
    });
  }, [getEventsForDateObj]);

  // Get header subtitle based on view (memoized)
  const headerSubtitle = useMemo(() => {
    if (view === 'day') {
      return `${dayNames[currentDate.getDay()]}, ${monthNames[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;
    } else if (view === 'week') {
      const weekStart = getStartOfWeek(currentDate);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      const startMonth = monthNames[weekStart.getMonth()].slice(0, 3);
      const endMonth = monthNames[weekEnd.getMonth()].slice(0, 3);
      if (weekStart.getMonth() === weekEnd.getMonth()) {
        return `${startMonth} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
      }
      return `${startMonth} ${weekStart.getDate()} - ${endMonth} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
    }
    return `${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  }, [view, currentDate]);

  // Memoize week dates to avoid recomputing on every render
  const weekDates = useMemo(() => {
    const weekStart = getStartOfWeek(currentDate);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [currentDate]);

  // Get event color class
  const getEventColorClass = (eventType) => {
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

  // ===== DAY VIEW =====
  const renderDayView = () => {
    const dayEvents = getEventsForDateObj(currentDate);
    const today = new Date();

    return (
      <div className="day-view">
        <div className="day-view-header">
          <h3>{dayNames[currentDate.getDay()]}, {monthNames[currentDate.getMonth()]} {currentDate.getDate()}</h3>
          {isSameDay(currentDate, today) && <span className="today-badge">Today</span>}
        </div>
        <div className="day-view-timeline">
          {VIEW_HOURS.map(hour => {
            const hourEvents = dayEvents.filter(event => {
              const eventDate = new Date(event.start_time);
              return eventDate.getHours() === hour;
            });
            return (
              <div className="day-view-hour" key={hour}>
                <div className="hour-label">{formatHour(hour)}</div>
                <div
                  className="hour-slot"
                  role="button"
                  tabIndex={0}
                  aria-label={`Add event at ${formatHour(hour)}`}
                  onClick={() => handleTimeSlotClick(currentDate, hour)}
                  onKeyDown={(e) => handleInteractiveKeyDown(e, () => handleTimeSlotClick(currentDate, hour))}
                >
                  {hourEvents.map(event => {
                    const { startStr, duration } = formatEventTime(event.start_time, event.end_time);
                    return (
                      <div
                        key={event.id}
                        className={`day-event ${getEventColorClass(event.event_type)} ${event.isAppointment ? 'clickable' : ''}`}
                        role={event.isAppointment ? 'button' : undefined}
                        tabIndex={event.isAppointment ? 0 : undefined}
                        aria-label={event.isAppointment ? `Edit appointment: ${event.title}` : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (event.isAppointment) handleEditAppointment(event);
                        }}
                        onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => handleEditAppointment(event)) : undefined}
                        title={event.title}
                      >
                        <div className="day-event-time">{startStr} ({duration}m)</div>
                        <div className="day-event-title">{event.title}</div>
                        {event.attendee_name && (
                          <div className="day-event-attendee" title={event.attendee_name}>{event.attendee_name}</div>
                        )}
                        {event.location && (
                          <div className="day-event-location" title={event.location}>{event.location}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ===== WEEK VIEW =====
  const renderWeekView = () => {
    const weekDays = weekDates;
    const today = new Date();

    return (
      <div className="week-view">
        <div className="week-view-header">
          <div className="week-time-gutter" />
          {weekDays.map((day, i) => (
            <div
              key={i}
              className={`week-day-col-header ${isSameDay(day, today) ? 'today' : ''}`}
              role="button"
              tabIndex={0}
              aria-label={`View ${dayNames[day.getDay()]}, ${monthNames[day.getMonth()]} ${day.getDate()}`}
              onClick={() => {
                setCurrentDate(new Date(day));
                setView('day');
              }}
              onKeyDown={(e) => handleInteractiveKeyDown(e, () => {
                setCurrentDate(new Date(day));
                setView('day');
              })}
              style={{ cursor: 'pointer' }}
            >
              <span className="week-day-name">{dayAbbreviations[day.getDay()]}</span>
              <span className="week-day-num">{day.getDate()}</span>
            </div>
          ))}
        </div>
        <div className="week-view-body">
          {VIEW_HOURS.map(hour => (
            <div className="week-hour-row" key={hour}>
              <div className="hour-label">{formatHour(hour)}</div>
              {weekDays.map((day, i) => {
                const cellEvents = getEventsForDateAndHour(day, hour);
                return (
                  <div
                    key={i}
                    className="week-cell"
                    role="button"
                    tabIndex={0}
                    aria-label={`Add event on ${dayAbbreviations[day.getDay()]} at ${formatHour(hour)}`}
                    onClick={() => handleTimeSlotClick(day, hour)}
                    onKeyDown={(e) => handleInteractiveKeyDown(e, () => handleTimeSlotClick(day, hour))}
                  >
                    {cellEvents.map(event => (
                      <div
                        key={event.id}
                        className={`week-event ${getEventColorClass(event.event_type)} ${event.isAppointment ? 'clickable' : ''}`}
                        role={event.isAppointment ? 'button' : undefined}
                        tabIndex={event.isAppointment ? 0 : undefined}
                        aria-label={event.isAppointment ? `Edit appointment: ${event.title}` : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (event.isAppointment) handleEditAppointment(event);
                        }}
                        onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => handleEditAppointment(event)) : undefined}
                        title={event.title}
                      >
                        {event.title}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ===== MONTH VIEW (mini calendar) =====
  const renderMiniCalendar = (monthData) => {
    const { daysInMonth, startingDayOfWeek, year, month } = monthData;

    return (
      <div className="mini-calendar">
        <div className="mini-calendar-header">
          <h3>{monthNames[month]} {year}</h3>
        </div>

        <div className="mini-calendar-weekdays">
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, idx) => (
            <div key={idx} className="mini-weekday-label">{day}</div>
          ))}
        </div>

        <div className="mini-calendar-days">
          {[...Array(startingDayOfWeek)].map((_, index) => (
            <div key={`empty-${index}`} className="mini-calendar-day empty" />
          ))}

          {[...Array(daysInMonth)].map((_, index) => {
            const day = index + 1;
            const dayEvents = getEventsForDate(day, year, month);
            const dayDate = new Date(year, month, day);
            const isToday = new Date().toDateString() === dayDate.toDateString();

            return (
              <div
                key={day}
                className={`mini-calendar-day ${isToday ? 'today' : ''} ${dayEvents.length > 0 ? 'has-events' : ''}`}
                role="button"
                tabIndex={0}
                aria-label={`${monthNames[month]} ${day}, ${year}${dayEvents.length > 0 ? `, ${dayEvents.length} event${dayEvents.length > 1 ? 's' : ''}` : ''}`}
                onClick={() => handleDayClick(day, year, month)}
                onKeyDown={(e) => handleInteractiveKeyDown(e, () => handleDayClick(day, year, month))}
              >
                <div className="mini-day-number">{day}</div>
                {dayEvents.length > 0 && (
                  <div className="event-dots">
                    {dayEvents.slice(0, 3).map((event, idx) => (
                      <div
                        key={idx}
                        className={`event-dot event-dot-${event.event_type || 'meeting'}`}
                      />
                    ))}
                  </div>
                )}
                {dayEvents.length > 3 && (
                  <div className="event-overflow">+{dayEvents.length - 3}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Render main view area
  const renderMainView = () => {
    if (loading) {
      return <div className="loading">Loading events...</div>;
    }

    if (view === 'day') {
      return renderDayView();
    }

    if (view === 'week') {
      return renderWeekView();
    }

    // Month view (two mini calendars)
    return (
      <div className="calendar-scroll-container">
        <button
          className="calendar-scroll-btn scroll-up"
          onClick={handleScrollUp}
          title="Previous month"
          aria-label="Previous month"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="18 15 12 9 6 15"></polyline>
          </svg>
        </button>

        <div className="two-month-view">
          {renderMiniCalendar(currentMonthData)}
          {renderMiniCalendar(nextMonthData)}
        </div>

        <button
          className="calendar-scroll-btn scroll-down"
          onClick={handleScrollDown}
          title="Next month"
          aria-label="Next month"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
      </div>
    );
  };

  return (
    <div className="calendar-page">
      <div className="calendar-header">
        <div>
          <h1>Calendar</h1>
          <p>{headerSubtitle}</p>
        </div>
        <div className="calendar-controls">
          <div className="view-switcher" role="tablist" aria-label="Calendar view">
            <button
              role="tab"
              aria-selected={view === 'day'}
              className={view === 'day' ? 'active' : ''}
              onClick={() => setView('day')}
            >
              Day
            </button>
            <button
              role="tab"
              aria-selected={view === 'week'}
              className={view === 'week' ? 'active' : ''}
              onClick={() => setView('week')}
            >
              Week
            </button>
            <button
              role="tab"
              aria-selected={view === 'month'}
              className={view === 'month' ? 'active' : ''}
              onClick={() => setView('month')}
            >
              Month
            </button>
          </div>
          <div className="month-navigation">
            <button onClick={handlePrev} aria-label={`Previous ${view}`}>&larr;</button>
            <button onClick={handleToday}>Today</button>
            <button onClick={handleNext} aria-label={`Next ${view}`}>&rarr;</button>
            <button
              className="btn-calendar-search"
              onClick={() => setShowSearch(true)}
              title="Search appointments (Ctrl+K)"
              aria-label="Search appointments"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              Search
              <span className="search-shortcut">{navigator.platform?.includes('Mac') ? '\u2318K' : 'Ctrl+K'}</span>
            </button>
            <button className="btn-add-event" onClick={() => { setSelectedDate(new Date()); setSelectedTime(null); setShowAddModal(true); }}>
              + Add Event
            </button>
            <button className="btn-calendar-settings" onClick={() => navigate('/calendar-settings')} title="Calendar Settings" aria-label="Calendar Settings">
              <i className="fas fa-cog"></i>
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="calendar-error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => { setError(null); loadEvents(); loadAllEvents(); }}>
            Retry
          </button>
        </div>
      )}

      <div className="calendar-content">
        {/* Appointments Sidebar */}
        <div className="appointments-sidebar">
          <div className="appointments-sidebar-header">
            <h2>{TAB_CONFIG.find(t => t.key === activeTab)?.label || 'Appointments'}</h2>
            <button
              className="btn-add-appointment"
              onClick={() => { setSelectedDate(new Date()); setSelectedTime(null); setShowAddModal(true); }}
              title="Add new appointment"
            >
              + Add
            </button>
          </div>
          <div className="calendar-tabs" role="tablist" aria-label="Appointment filters">
            {TAB_CONFIG.map(tab => (
              <button
                key={tab.key}
                role="tab"
                aria-selected={activeTab === tab.key}
                className={`calendar-tab ${activeTab === tab.key ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="search-container">
            <label htmlFor="calendar-search" className="sr-only">Search events</label>
            <input
              id="calendar-search"
              type="text"
              className="search-input"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="appointments-list">
            {sortedEvents.length === 0 ? (
              <div className="empty-appointments">
                <p>{searchQuery ? 'No matching events' : 'No appointments scheduled'}</p>
              </div>
            ) : (
              sortedEvents.map((event, index) => {
                const { startStr, duration } = formatEventTime(event.start_time, event.end_time);
                const dateLabel = formatEventDate(event.start_time);
                const showDateHeader = index === 0 || formatEventDate(sortedEvents[index - 1].start_time) !== dateLabel;

                return (
                  <div key={event.id}>
                    {showDateHeader && (
                      <div className="appointment-date-header">{dateLabel}</div>
                    )}
                    <div
                      className={`appointment-item appointment-${event.event_type || 'meeting'} ${event.isAppointment ? 'clickable' : ''}`}
                      role={event.isAppointment ? 'button' : undefined}
                      tabIndex={event.isAppointment ? 0 : undefined}
                      aria-label={event.isAppointment ? `Edit appointment: ${event.title}` : undefined}
                      onClick={() => event.isAppointment && handleEditAppointment(event)}
                      onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => handleEditAppointment(event)) : undefined}
                      style={{ cursor: event.isAppointment ? 'pointer' : 'default' }}
                    >
                      <div className="appointment-time">
                        <div className="time-start">{startStr}</div>
                        <div className="time-duration">{duration}m</div>
                      </div>
                      <div className="appointment-details">
                        <div className="appointment-title" title={event.title}>{event.title}</div>
                        {event.attendee_name && (
                          <div className="appointment-attendee" title={event.attendee_name}>{event.attendee_name}</div>
                        )}
                        {event.location && (
                          <div className="appointment-location" title={event.location}>{event.location}</div>
                        )}
                        {event.description && (
                          <div className="appointment-description" title={event.description}>{event.description}</div>
                        )}
                        {event.isAppointment && (
                          <div className="appointment-edit-hint">Click to edit/reschedule</div>
                        )}
                      </div>
                      <button
                        className="delete-appointment"
                        onClick={(e) => { e.stopPropagation(); handleDeleteEvent(event); }}
                        title={event.isAppointment ? "Cancel appointment" : "Delete event"}
                        aria-label={event.isAppointment ? `Cancel appointment: ${event.title}` : `Delete event: ${event.title}`}
                      >
                        &times;
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Main View Area */}
        <div className="calendar-main">
          {renderMainView()}
        </div>
      </div>

      {showAddModal && (
        <AddEventModal
          selectedDate={selectedDate}
          selectedTime={selectedTime}
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddEvent}
          onAddAppointment={handleAddAppointment}
          teamMembers={teamMembers}
        />
      )}

      {showEditModal && editingAppointment && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)} onKeyDown={(e) => { if (e.key === 'Escape') setShowEditModal(false); }}>
          <div className="modal-content edit-appointment-modal" role="dialog" aria-modal="true" aria-label="Edit appointment" onClick={(e) => e.stopPropagation()}>
            <h3>Edit Appointment</h3>
            <form onSubmit={handleSaveAppointment}>
              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={editingAppointment.title}
                  onChange={(e) => setEditingAppointment({...editingAppointment, title: e.target.value})}
                  required
                />
              </div>

              <div className="form-group">
                <label>Meeting Type</label>
                <div className="meeting-mode-group">
                  {[
                    { value: 'PHONE', label: 'Phone Call' },
                    { value: 'VIDEO', label: 'Video Call' },
                    { value: 'IN_PERSON', label: 'In Person' },
                  ].map(opt => (
                    <div className="meeting-mode-option" key={opt.value}>
                      <input
                        type="radio"
                        id={`edit-mode-${opt.value}`}
                        name="edit-meeting-mode"
                        value={opt.value}
                        checked={editingAppointment.meeting_mode === opt.value}
                        onChange={(e) => setEditingAppointment({...editingAppointment, meeting_mode: e.target.value})}
                      />
                      <label htmlFor={`edit-mode-${opt.value}`}>{opt.label}</label>
                    </div>
                  ))}
                </div>
              </div>

              <div className="attendee-section">
                <h4>Attendee</h4>
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={editingAppointment.attendee_name}
                    onChange={(e) => setEditingAppointment({...editingAppointment, attendee_name: e.target.value})}
                    placeholder="Attendee name"
                  />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={editingAppointment.attendee_email}
                    onChange={(e) => setEditingAppointment({...editingAppointment, attendee_email: e.target.value})}
                    placeholder="attendee@email.com"
                  />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={editingAppointment.attendee_phone}
                    onChange={(e) => setEditingAppointment({...editingAppointment, attendee_phone: e.target.value})}
                    placeholder="(555) 123-4567"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date</label>
                  <input
                    type="date"
                    value={editingAppointment.date}
                    onChange={(e) => setEditingAppointment({...editingAppointment, date: e.target.value})}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Time</label>
                  <input
                    type="time"
                    value={editingAppointment.time}
                    onChange={(e) => setEditingAppointment({...editingAppointment, time: e.target.value})}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Duration</label>
                <select
                  value={editingAppointment.duration}
                  onChange={(e) => setEditingAppointment({...editingAppointment, duration: e.target.value})}
                >
                  <option value="15">15 minutes</option>
                  <option value="30">30 minutes</option>
                  <option value="45">45 minutes</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                  <option value="120">2 hours</option>
                </select>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={editingAppointment.description}
                  onChange={(e) => setEditingAppointment({...editingAppointment, description: e.target.value})}
                  placeholder="Additional notes..."
                  rows={3}
                />
              </div>

              <div className="form-actions modal-actions-split">
                <button
                  type="button"
                  className="btn-danger"
                  onClick={handleCancelFromModal}
                  disabled={saving}
                >
                  Cancel Appointment
                </button>
                <div className="modal-actions-right">
                  <button type="button" onClick={() => setShowEditModal(false)} disabled={saving}>
                    Close
                  </button>
                  <button type="submit" className="btn-primary" disabled={saving}>
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {confirmAction && (
        <div className="modal-overlay" onClick={() => setConfirmAction(null)}>
          <div className="modal-content confirm-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Confirm action">
            <p>{confirmAction.message}</p>
            <div className="modal-actions">
              <button type="button" onClick={() => setConfirmAction(null)}>No, go back</button>
              <button type="button" className="btn-danger" onClick={confirmAction.onConfirm}>Yes, confirm</button>
            </div>
          </div>
        </div>
      )}

      {showSearch && (
        <Suspense fallback={null}>
          <CalendarSearch
            visible={showSearch}
            onClose={() => setShowSearch(false)}
            onSelectAppointment={handleSearchSelectAppointment}
          />
        </Suspense>
      )}

      {showShortcutsHelp && (
        <Suspense fallback={null}>
          <KeyboardShortcutsHelp onClose={() => setShowShortcutsHelp(false)} />
        </Suspense>
      )}
    </div>
  );
}

function AddEventModal({ selectedDate, selectedTime, onClose, onAdd, onAddAppointment, teamMembers }) {
  const defaultStart = selectedDate || new Date();
  // If a specific hour was selected (from Day/Week view), use it
  if (selectedTime != null) {
    defaultStart.setHours(selectedTime, 0, 0, 0);
  }
  const defaultEnd = new Date(defaultStart.getTime() + 3600000);

  const [mode, setMode] = useState('event');

  // Close on ESC key
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    event_type: 'meeting',
    location: '',
    all_day: false,
    start_time: defaultStart.toISOString().slice(0, 16),
    end_time: defaultEnd.toISOString().slice(0, 16),
    // Appointment-specific fields
    meeting_mode: 'PHONE',
    duration: '30',
    attendee_name: '',
    attendee_email: '',
    attendee_phone: '',
    team_member_id: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (mode === 'appointment') {
      const startTime = new Date(formData.start_time);
      onAddAppointment({
        title: formData.title,
        description: formData.description,
        meeting_mode: formData.meeting_mode.toLowerCase(),
        scheduled_start: startTime.toISOString(),
        duration_minutes: parseInt(formData.duration),
        attendee_name: formData.attendee_name || undefined,
        attendee_email: formData.attendee_email || undefined,
        attendee_phone: formData.attendee_phone || undefined,
        assigned_user_id: formData.team_member_id ? parseInt(formData.team_member_id) : undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
    } else {
      onAdd({
        ...formData,
        start_time: new Date(formData.start_time).toISOString(),
        end_time: new Date(formData.end_time).toISOString(),
      });
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" aria-label="Add event" onClick={(e) => e.stopPropagation()}>
        <div className="modal-mode-toggle" role="tablist" aria-label="Event type">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'event'}
            className={mode === 'event' ? 'active' : ''}
            onClick={() => setMode('event')}
          >
            Calendar Event
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'appointment'}
            className={mode === 'appointment' ? 'active' : ''}
            onClick={() => setMode('appointment')}
          >
            Appointment
          </button>
        </div>

        <h3>{mode === 'event' ? 'Add Event' : 'Add Appointment'}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Title *</label>
            <input
              type="text"
              required
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            />
          </div>

          {mode === 'event' && (
            <>
              <div className="form-group">
                <label>Type</label>
                <select
                  value={formData.event_type}
                  onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}
                >
                  <option value="meeting">Meeting</option>
                  <option value="call">Call</option>
                  <option value="pre_purchase_consultation">Pre-Purchase Consultation</option>
                  <option value="purchase_consultation">Purchase Consultation</option>
                  <option value="appraisal">Appraisal</option>
                  <option value="closing">Closing</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="form-group">
                <label>Start Time *</label>
                <input
                  type="datetime-local"
                  required
                  value={formData.start_time}
                  onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>End Time *</label>
                <input
                  type="datetime-local"
                  required
                  value={formData.end_time}
                  onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Location</label>
                <input
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                />
              </div>
            </>
          )}

          {mode === 'appointment' && (
            <>
              <div className="form-group">
                <label>Meeting Type</label>
                <div className="meeting-mode-group">
                  {[
                    { value: 'PHONE', label: 'Phone Call' },
                    { value: 'VIDEO', label: 'Video Call' },
                    { value: 'IN_PERSON', label: 'In Person' },
                  ].map(opt => (
                    <div className="meeting-mode-option" key={opt.value}>
                      <input
                        type="radio"
                        id={`add-mode-${opt.value}`}
                        name="add-meeting-mode"
                        value={opt.value}
                        checked={formData.meeting_mode === opt.value}
                        onChange={(e) => setFormData({ ...formData, meeting_mode: e.target.value })}
                      />
                      <label htmlFor={`add-mode-${opt.value}`}>{opt.label}</label>
                    </div>
                  ))}
                </div>
              </div>
              <div className="form-group">
                <label>Start Time *</label>
                <input
                  type="datetime-local"
                  required
                  value={formData.start_time}
                  onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Duration</label>
                <select
                  value={formData.duration}
                  onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
                >
                  <option value="15">15 minutes</option>
                  <option value="30">30 minutes</option>
                  <option value="45">45 minutes</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                  <option value="120">2 hours</option>
                </select>
              </div>
              <div className="attendee-section">
                <h4>Attendee</h4>
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={formData.attendee_name}
                    onChange={(e) => setFormData({ ...formData, attendee_name: e.target.value })}
                    placeholder="Attendee name"
                  />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={formData.attendee_email}
                    onChange={(e) => setFormData({ ...formData, attendee_email: e.target.value })}
                    placeholder="attendee@email.com"
                  />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={formData.attendee_phone}
                    onChange={(e) => setFormData({ ...formData, attendee_phone: e.target.value })}
                    placeholder="(555) 123-4567"
                  />
                </div>
              </div>
              {teamMembers.length > 0 && (
                <div className="form-group">
                  <label>Assign To</label>
                  <select
                    className="team-select"
                    value={formData.team_member_id}
                    onChange={(e) => setFormData({ ...formData, team_member_id: e.target.value })}
                  >
                    <option value="">Myself</option>
                    {teamMembers.map(m => (
                      <option key={m.id} value={m.id}>{m.full_name || m.email}</option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">
              {mode === 'event' ? 'Add Event' : 'Add Appointment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Calendar;
