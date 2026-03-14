import React, { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarAPI, schedulerAPI, unifiedCalendarAPI, teamAPI, calendarSettingsAPI } from '../services/api';
import { useCalendarKeyboard } from '../hooks/useCalendarKeyboard';
import useCalendarTour from '../hooks/useCalendarTour';
import CommandCenterHeader from '../components/calendar/CommandCenterHeader';
import CalendarToolbar from '../components/calendar/CalendarToolbar';
import OperationalSidebar from '../components/calendar/OperationalSidebar';
import InlineDayView from '../components/calendar/InlineDayView';
import WeekView from '../components/calendar/WeekView';
import MonthView from '../components/calendar/MonthView';
import AddEventModal from '../components/calendar/AddEventModal';
import EditAppointmentModal from '../components/calendar/EditAppointmentModal';
import ConfirmDialog from '../components/calendar/ConfirmDialog';
import SetupBanner from '../components/calendar/SetupBanner';
import './Calendar.css';

// Lazy load heavy modal/overlay components that are conditionally rendered
const CalendarSearch = lazy(() => import('../components/calendar/CalendarSearch'));
const KeyboardShortcutsHelp = lazy(() => import('../components/calendar/KeyboardShortcutsHelp'));
const CalendarTour = lazy(() => import('../components/calendar/setup/CalendarTour'));

// Feature flags
const hasCalendarTour = true;
const hasKeyboardShortcuts = true;

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

// Default hours for Day/Week views — overridden by user's availability settings
const DEFAULT_VIEW_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];

// Derive display hours from availability schedule (earliest start - 1hr to latest end)
function deriveViewHours(schedule) {
  if (!schedule || typeof schedule !== 'object') return DEFAULT_VIEW_HOURS;
  let earliest = 24, latest = 0;
  for (const day of Object.values(schedule)) {
    if (!day?.enabled || !Array.isArray(day.blocks)) continue;
    for (const block of day.blocks) {
      if (!block.start || !block.end) continue;
      const [sh] = block.start.split(':').map(Number);
      const [eh, em] = block.end.split(':').map(Number);
      if (!isNaN(sh)) earliest = Math.min(earliest, sh);
      if (!isNaN(eh)) latest = Math.max(latest, em > 0 ? eh + 1 : eh);
    }
  }
  if (earliest >= latest) return DEFAULT_VIEW_HOURS;
  const start = Math.max(0, earliest - 1);
  const end = Math.min(24, latest + 1);
  const hours = [];
  for (let h = start; h < end; h++) hours.push(h);
  return hours;
}

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

function Calendar() {
  const navigate = useNavigate();

  // ── Core state ──
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState('month');
  const [allEvents, setAllEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Modal/overlay state ──
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState(null);
  const [saving, setSaving] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [showSearch, setShowSearch] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

  // ── Sidebar state ──
  const [searchQuery, setSearchQuery] = useState('');

  // ── Other state ──
  const [teamMembers, setTeamMembers] = useState([]);
  const [viewHours, setViewHours] = useState(DEFAULT_VIEW_HOURS);
  const [selectedEventIndex, setSelectedEventIndex] = useState(-1);
  const liveAnnouncerRef = useRef(null);

  // ── Setup banner ──
  const [showSetupBanner, setShowSetupBanner] = useState(() => {
    try {
      const setupComplete = localStorage.getItem('calendar_setup_complete');
      const bannerDismissed = sessionStorage.getItem('calendar_setup_banner_dismissed');
      return !setupComplete && !bannerDismissed;
    } catch {
      return false;
    }
  });

  const dismissSetupBanner = useCallback(() => {
    setShowSetupBanner(false);
    try {
      sessionStorage.setItem('calendar_setup_banner_dismissed', 'true');
    } catch {
      // ignore storage errors
    }
  }, []);

  // ── Feature tour ──
  const tour = useCalendarTour();

  // ══════════════════════════════════════════════════════════
  // DATA FETCHING
  // ══════════════════════════════════════════════════════════

  const loadEvents = useCallback(async () => {
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
  }, [currentDate]);

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
      setAllEvents(mapUnifiedEvents(response.events));
      setError(null);
    } catch {
      setError('Unable to load calendar events. Please try again.');
      setAllEvents([]);
    }
  }, []);

  useEffect(() => { loadEvents(); }, [loadEvents]);
  useEffect(() => { loadAllEvents(); }, [loadAllEvents]);
  useEffect(() => {
    teamAPI.getMembers().then(members => setTeamMembers(members)).catch(() => {});
  }, []);

  // Load availability settings to derive visible hours
  useEffect(() => {
    calendarSettingsAPI.getAvailability()
      .then(res => {
        if (res?.data?.schedule) {
          setViewHours(deriveViewHours(res.data.schedule));
        }
      })
      .catch(() => {});
  }, []);

  // ══════════════════════════════════════════════════════════
  // EVENT HANDLERS
  // ══════════════════════════════════════════════════════════

  const handleAddEvent = useCallback(async (eventData) => {
    try {
      await calendarAPI.create(eventData);
      loadEvents();
      loadAllEvents();
      setShowAddModal(false);
    } catch {
      setError('Failed to create event. Please try again.');
    }
  }, [loadEvents, loadAllEvents]);

  const handleAddAppointment = useCallback(async (appointmentData) => {
    try {
      await schedulerAPI.createAppointment(appointmentData);
      loadEvents();
      loadAllEvents();
      setShowAddModal(false);
    } catch {
      setError('Failed to create appointment. Please try again.');
    }
  }, [loadEvents, loadAllEvents]);

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
  }, [loadEvents, loadAllEvents]);

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
      meeting_mode: event.meeting_mode || 'PHONE',
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

  const handleSaveAppointment = useCallback(async (e) => {
    e.preventDefault();
    if (!editingAppointment) return;

    setSaving(true);
    try {
      const startDateTime = new Date(`${editingAppointment.date}T${editingAppointment.time}`);
      const endDateTime = new Date(startDateTime.getTime() + parseInt(editingAppointment.duration) * 60000);

      await schedulerAPI.updateAppointment(editingAppointment.id, {
        title: editingAppointment.title,
        attendee_name: editingAppointment.attendee_name,
        attendee_email: editingAppointment.attendee_email,
        attendee_phone: editingAppointment.attendee_phone,
        meeting_mode: editingAppointment.meeting_mode,
        scheduled_start: startDateTime.toISOString(),
        scheduled_end: endDateTime.toISOString(),
        duration_minutes: parseInt(editingAppointment.duration),
        attendee_notes: editingAppointment.description,
      });

      setShowEditModal(false);
      setEditingAppointment(null);
      loadEvents();
      loadAllEvents();
    } catch (err) {
      setError('Failed to reschedule: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }, [editingAppointment, loadEvents, loadAllEvents]);

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
  }, [editingAppointment, loadEvents, loadAllEvents]);

  // ══════════════════════════════════════════════════════════
  // SEARCH
  // ══════════════════════════════════════════════════════════

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
    if (appointment.scheduled_start) {
      setCurrentDate(new Date(appointment.scheduled_start));
    }
    if (appointment.id && typeof appointment.id === 'number') {
      setEditingAppointment(appointment);
      setShowEditModal(true);
    }
  }, []);

  // ══════════════════════════════════════════════════════════
  // KEYBOARD NAVIGATION
  // ══════════════════════════════════════════════════════════

  const announceToScreenReader = useCallback((message) => {
    if (liveAnnouncerRef.current) {
      liveAnnouncerRef.current.textContent = message;
    }
  }, []);

  useEffect(() => { setSelectedEventIndex(-1); }, [searchQuery]);

  const hasModalOpen = showAddModal || showEditModal || showSearch || showShortcutsHelp || !!confirmAction || (tour && tour.isActive);

  const handleSelectPrevEvent = useCallback(() => {
    setSelectedEventIndex(prev => prev <= 0 ? 0 : prev - 1);
  }, []);

  const handleSelectNextEvent = useCallback(() => {
    setSelectedEventIndex(prev => prev + 1);
  }, []);

  const openSelectedEventRef = useRef(null);
  const handleOpenSelectedEvent = useCallback(() => {
    openSelectedEventRef.current?.();
  }, []);

  const handleCloseAllModals = useCallback(() => {
    if (confirmAction) { setConfirmAction(null); }
    else if (showShortcutsHelp) { setShowShortcutsHelp(false); }
    else if (showSearch) { setShowSearch(false); }
    else if (showEditModal) { setShowEditModal(false); }
    else if (showAddModal) { setShowAddModal(false); }
  }, [confirmAction, showShortcutsHelp, showSearch, showEditModal, showAddModal]);

  // Stable refs for navigation handlers
  const handlePrevRef = useRef(null);
  const handleNextRef = useRef(null);
  const handleTodayRef = useRef(null);

  useCalendarKeyboard({
    onPrev: useCallback(() => { handlePrevRef.current?.(); }, []),
    onNext: useCallback(() => { handleNextRef.current?.(); }, []),
    onToday: useCallback(() => { handleTodayRef.current?.(); announceToScreenReader('Navigated to today'); }, [announceToScreenReader]),
    onSetView: useCallback((v) => { setView(v); announceToScreenReader(`Switched to ${v} view`); }, [announceToScreenReader]),
    onNewEvent: useCallback(() => { setSelectedDate(new Date()); setSelectedTime(null); setShowAddModal(true); }, []),
    onOpenSearch: useCallback(() => { setShowSearch(true); }, []),
    onCloseModals: handleCloseAllModals,
    onToggleShortcutsHelp: useCallback(() => { setShowShortcutsHelp(prev => !prev); }, []),
    onSelectPrevEvent: handleSelectPrevEvent,
    onSelectNextEvent: handleSelectNextEvent,
    onOpenSelectedEvent: handleOpenSelectedEvent,
    hasModalOpen,
  });

  // ══════════════════════════════════════════════════════════
  // DERIVED / MEMOIZED DATA
  // ══════════════════════════════════════════════════════════

  // Sort and filter events for sidebar
  const sortedEvents = useMemo(() => {
    const filtered = allEvents.filter(event => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (event.title || '').toLowerCase().includes(q)
        || (event.attendee_name || '').toLowerCase().includes(q)
        || (event.location || '').toLowerCase().includes(q);
    });
    return [...filtered].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [allEvents, searchQuery]);

  // Clamp selectedEventIndex and sync
  const clampedSelectedIndex = sortedEvents.length === 0
    ? -1
    : Math.max(-1, Math.min(selectedEventIndex, sortedEvents.length - 1));

  useEffect(() => {
    if (clampedSelectedIndex !== selectedEventIndex) {
      setSelectedEventIndex(clampedSelectedIndex);
    }
  }, [clampedSelectedIndex, selectedEventIndex]);

  useEffect(() => {
    if (clampedSelectedIndex >= 0) {
      const el = document.querySelector(`[data-event-index="${clampedSelectedIndex}"]`);
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      const event = sortedEvents[clampedSelectedIndex];
      if (event) { announceToScreenReader(`Selected: ${event.title || 'event'}`); }
    }
  }, [clampedSelectedIndex, sortedEvents, announceToScreenReader]);

  useEffect(() => {
    openSelectedEventRef.current = () => {
      if (clampedSelectedIndex >= 0 && sortedEvents[clampedSelectedIndex]) {
        const event = sortedEvents[clampedSelectedIndex];
        if (event.isAppointment) { handleEditAppointment(event); }
      }
    };
  });

  // Pre-index events by date key for O(1) lookups
  const eventsByDateKey = useMemo(() => {
    const index = {};
    for (const event of allEvents) {
      const eventDate = new Date(event.start_time);
      const key = `${eventDate.getFullYear()}-${eventDate.getMonth()}-${eventDate.getDate()}`;
      if (!index[key]) index[key] = [];
      index[key].push(event);
    }
    return index;
  }, [allEvents]);

  const getEventsForDate = useCallback((day, year, month) => {
    return eventsByDateKey[`${year}-${month}-${day}`] || [];
  }, [eventsByDateKey]);

  const getEventsForDateObj = useCallback((dateObj) => {
    return getEventsForDate(dateObj.getDate(), dateObj.getFullYear(), dateObj.getMonth());
  }, [getEventsForDate]);

  const getEventsForDateAndHour = useCallback((dateObj, hour) => {
    const dayEvents = getEventsForDateObj(dateObj);
    return dayEvents.filter(event => new Date(event.start_time).getHours() === hour);
  }, [getEventsForDateObj]);

  const formatEventTime = useCallback((startTime, endTime) => {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const duration = Math.round((end - start) / (1000 * 60));
    return { startStr, duration };
  }, []);

  // ══════════════════════════════════════════════════════════
  // NAVIGATION
  // ══════════════════════════════════════════════════════════

  const getDaysInMonth = useCallback((date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    return { daysInMonth: lastDay.getDate(), startingDayOfWeek: firstDay.getDay(), year, month };
  }, []);

  const currentMonthData = useMemo(() => getDaysInMonth(currentDate), [currentDate, getDaysInMonth]);
  const nextMonthData = useMemo(() => {
    return getDaysInMonth(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  }, [currentDate, getDaysInMonth]);

  const weekDates = useMemo(() => {
    const weekStart = getStartOfWeek(currentDate);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [currentDate]);

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

  handlePrevRef.current = handlePrev;
  handleNextRef.current = handleNext;
  handleTodayRef.current = handleToday;

  const handleScrollUp = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  }, []);

  const handleScrollDown = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  }, []);

  const handleDayClick = useCallback((day, year, month) => {
    setSelectedDate(new Date(year, month, day));
    setSelectedTime(null);
    setShowAddModal(true);
  }, []);

  const handleTimeSlotClick = useCallback((date, hour) => {
    setSelectedDate(date);
    setSelectedTime(hour);
    setShowAddModal(true);
  }, []);

  const handleDayHeaderClick = useCallback((day) => {
    setCurrentDate(new Date(day));
    setView('day');
  }, []);

  const openAddModal = useCallback(() => {
    setSelectedDate(new Date());
    setSelectedTime(null);
    setShowAddModal(true);
  }, []);

  // ══════════════════════════════════════════════════════════
  // HEADER SUBTITLE
  // ══════════════════════════════════════════════════════════

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

  // ══════════════════════════════════════════════════════════
  // MAIN VIEW DISPATCH
  // ══════════════════════════════════════════════════════════

  const renderMainView = () => {
    if (loading) {
      return <div className="loading">Loading events...</div>;
    }

    if (view === 'day') {
      return (
        <InlineDayView
          currentDate={currentDate}
          viewHours={viewHours}
          getEventsForDateObj={getEventsForDateObj}
          onTimeSlotClick={handleTimeSlotClick}
          onEventClick={handleEditAppointment}
        />
      );
    }

    if (view === 'week') {
      return (
        <WeekView
          weekDates={weekDates}
          viewHours={viewHours}
          getEventsForDateAndHour={getEventsForDateAndHour}
          onTimeSlotClick={handleTimeSlotClick}
          onEventClick={handleEditAppointment}
          onDayHeaderClick={handleDayHeaderClick}
        />
      );
    }

    // Month view
    return (
      <MonthView
        currentMonthData={currentMonthData}
        nextMonthData={nextMonthData}
        getEventsForDate={getEventsForDate}
        onDayClick={handleDayClick}
        onScrollUp={handleScrollUp}
        onScrollDown={handleScrollDown}
      />
    );
  };

  // ══════════════════════════════════════════════════════════
  // RENDER
  // ══════════════════════════════════════════════════════════

  return (
    <div className="calendar-page calendar-page--control-center">
      {showSetupBanner && <SetupBanner onDismiss={dismissSetupBanner} />}

      <CommandCenterHeader />

      <CalendarToolbar
        headerSubtitle={headerSubtitle}
        view={view}
        onViewChange={setView}
        onPrev={handlePrev}
        onNext={handleNext}
        onToday={handleToday}
        onSearchOpen={() => setShowSearch(true)}
        onAddEvent={openAddModal}
        onShortcutsOpen={() => setShowShortcutsHelp(true)}
        onTourStart={tour?.restart}
        onSettingsClick={() => navigate('/calendar-settings')}
        hasKeyboardShortcuts={hasKeyboardShortcuts}
        hasTour={hasCalendarTour && !!tour}
      />

      {error && (
        <div className="calendar-error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => { setError(null); loadEvents(); loadAllEvents(); }}>
            Retry
          </button>
        </div>
      )}

      <div className="calendar-content">
        <OperationalSidebar
          sortedEvents={sortedEvents}
          onAddClick={openAddModal}
          onEventClick={handleEditAppointment}
          onDeleteEvent={handleDeleteEvent}
          formatEventTime={formatEventTime}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

        <div className="calendar-main">
          {renderMainView()}
        </div>
      </div>

      {/* Modals */}
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
        <EditAppointmentModal
          appointment={editingAppointment}
          onFieldChange={handleEditFieldChange}
          onSave={handleSaveAppointment}
          onCancel={handleCancelFromModal}
          onClose={() => setShowEditModal(false)}
          saving={saving}
        />
      )}

      {confirmAction && (
        <ConfirmDialog
          message={confirmAction.message}
          onConfirm={confirmAction.onConfirm}
          onCancel={() => setConfirmAction(null)}
        />
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

      {hasCalendarTour && tour && tour.isActive && (
        <Suspense fallback={null}>
          <CalendarTour
            isActive={tour.isActive}
            currentStep={tour.currentStep}
            steps={tour.steps}
            totalSteps={tour.totalSteps}
            dontShowAgain={tour.dontShowAgain}
            onNext={tour.next}
            onBack={tour.back}
            onSkip={tour.skip}
            onComplete={tour.complete}
            onToggleDontShowAgain={tour.toggleDontShowAgain}
          />
        </Suspense>
      )}

      {/* Screen reader live region */}
      <div
        ref={liveAnnouncerRef}
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
        role="status"
      />
    </div>
  );
}

export default Calendar;
