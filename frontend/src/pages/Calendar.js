import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCalendarKeyboard } from '../hooks/useCalendarKeyboard';
import useCalendarTour from '../hooks/useCalendarTour';
import useCalendarEvents from '../hooks/useCalendarEvents';
import useCalendarActions from '../hooks/useCalendarActions';
import useCalendarNavigation from '../hooks/useCalendarNavigation';
import CommandCenterHeader from '../components/calendar/CommandCenterHeader';
import CalendarToolbar from '../components/calendar/CalendarToolbar';
import OperationalSidebar from '../components/calendar/OperationalSidebar';
import CalendarMainView from '../components/calendar/CalendarMainView';
import MobileCalendarView from '../components/calendar/MobileCalendarView';
import CalendarModals from '../components/calendar/CalendarModals';
import SetupBanner from '../components/calendar/SetupBanner';
import SchedulingAlerts from '../components/calendar/SchedulingAlerts';
import { useIsMobile } from '../hooks/useMediaQuery';
import './Calendar.css';

// Feature flags
const hasCalendarTour = true;
const hasKeyboardShortcuts = true;

function Calendar() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();

  // ── Navigation state ──
  const nav = useCalendarNavigation();

  // ── Event data ──
  const events = useCalendarEvents(nav.currentDate);

  // ── CRUD actions and modal state ──
  const actions = useCalendarActions({
    loadEvents: events.loadEvents,
    allEvents: events.allEvents,
    setAllEvents: events.setAllEvents,
  });

  // ── Sidebar search state ──
  const [searchQuery, setSearchQuery] = useState('');

  // ── Search overlay + shortcuts help state ──
  const [showSearch, setShowSearch] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

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

  // ── Search shortcut (Ctrl/Cmd+K) ──
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
      nav.setCurrentDate(new Date(appointment.scheduled_start));
    }
    if (appointment.id && typeof appointment.id === 'number') {
      actions.setEditingAppointment(appointment);
      actions.setShowEditModal(true);
    }
  }, [nav, actions]);

  // ── Keyboard navigation ──
  const [selectedEventIndex, setSelectedEventIndex] = useState(-1);
  const liveAnnouncerRef = useRef(null);

  const announceToScreenReader = useCallback((message) => {
    if (liveAnnouncerRef.current) {
      liveAnnouncerRef.current.textContent = message;
    }
  }, []);

  useEffect(() => { setSelectedEventIndex(-1); }, [searchQuery]);

  const hasModalOpen = actions.showAddModal || actions.showEditModal || showSearch || showShortcutsHelp || !!actions.confirmAction || (tour && tour.isActive);

  const handleCloseAllModals = useCallback(() => {
    if (actions.confirmAction) { actions.setConfirmAction(null); }
    else if (showShortcutsHelp) { setShowShortcutsHelp(false); }
    else if (showSearch) { setShowSearch(false); }
    else if (actions.showEditModal) { actions.setShowEditModal(false); }
    else if (actions.showAddModal) { actions.setShowAddModal(false); }
  }, [actions, showShortcutsHelp, showSearch]);

  // Stable refs for navigation handlers (keyboard hook uses refs to avoid stale closures)
  const handlePrevRef = useRef(null);
  const handleNextRef = useRef(null);
  const handleTodayRef = useRef(null);
  const openSelectedEventRef = useRef(null);

  handlePrevRef.current = nav.handlePrev;
  handleNextRef.current = nav.handleNext;
  handleTodayRef.current = nav.handleToday;

  useCalendarKeyboard({
    onPrev: useCallback(() => { handlePrevRef.current?.(); }, []),
    onNext: useCallback(() => { handleNextRef.current?.(); }, []),
    onToday: useCallback(() => { handleTodayRef.current?.(); announceToScreenReader('Navigated to today'); }, [announceToScreenReader]),
    onSetView: useCallback((v) => { nav.setView(v); announceToScreenReader(`Switched to ${v} view`); }, [nav, announceToScreenReader]),
    onNewEvent: useCallback(() => { actions.setSelectedDate(new Date()); actions.setSelectedTime(null); actions.setShowAddModal(true); }, [actions]),
    onOpenSearch: useCallback(() => { setShowSearch(true); }, []),
    onCloseModals: handleCloseAllModals,
    onToggleShortcutsHelp: useCallback(() => { setShowShortcutsHelp(prev => !prev); }, []),
    onSelectPrevEvent: useCallback(() => { setSelectedEventIndex(prev => prev <= 0 ? 0 : prev - 1); }, []),
    onSelectNextEvent: useCallback(() => { setSelectedEventIndex(prev => prev + 1); }, []),
    onOpenSelectedEvent: useCallback(() => { openSelectedEventRef.current?.(); }, []),
    hasModalOpen,
  });

  // ── Derived sidebar data ──
  const sortedEvents = useMemo(() => {
    const filtered = events.allEvents.filter(event => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (event.title || '').toLowerCase().includes(q)
        || (event.attendee_name || '').toLowerCase().includes(q)
        || (event.location || '').toLowerCase().includes(q);
    });
    return [...filtered].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [events.allEvents, searchQuery]);

  // Clamp selectedEventIndex
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
        if (event.isAppointment) { actions.handleEditAppointment(event); }
      }
    };
  });

  // ── Selected day for sidebar (shows appointments for that day) ──
  const [sidebarDate, setSidebarDate] = useState(null);

  // ── Click handlers for day/time slot selection ──
  const handleDayClick = useCallback((day, year, month) => {
    setSidebarDate(new Date(year, month, day));
  }, []);

  const handleTimeSlotClick = useCallback((date, hour) => {
    actions.setSelectedDate(date);
    actions.setSelectedTime(hour);
    actions.setShowAddModal(true);
  }, [actions]);

  // ── Render ──
  return (
    <div className="calendar-page calendar-page--control-center">
      {showSetupBanner && <SetupBanner onDismiss={dismissSetupBanner} />}

      <CommandCenterHeader />

      <SchedulingAlerts />

      <CalendarToolbar
        headerSubtitle={nav.headerSubtitle}
        view={nav.view}
        onViewChange={nav.setView}
        onPrev={nav.handlePrev}
        onNext={nav.handleNext}
        onToday={nav.handleToday}
        onSearchOpen={() => setShowSearch(true)}
        onAddEvent={actions.openAddModal}
        onShortcutsOpen={() => setShowShortcutsHelp(true)}
        onTourStart={tour?.restart}
        onSettingsClick={() => navigate('/calendar-settings')}
        hasKeyboardShortcuts={hasKeyboardShortcuts}
        hasTour={hasCalendarTour && !!tour}
      />

      {events.error && (
        <div className="calendar-error-banner" role="alert">
          <span>{events.error}</span>
          <button onClick={() => { events.setError(null); events.loadEvents(); }}>
            Retry
          </button>
        </div>
      )}

      {isMobile ? (
        <MobileCalendarView
          currentDate={nav.currentDate}
          allEvents={events.allEvents}
          onDateChange={nav.setCurrentDate}
          onEditAppointment={actions.handleEditAppointment}
          onDeleteEvent={actions.handleDeleteEvent}
          onAddEvent={actions.handleAddEvent}
          onAddAppointment={actions.handleAddAppointment}
          teamMembers={events.teamMembers}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          getFilteredEvents={events.getFilteredEvents}
          loading={events.loading}
        />
      ) : (
        <div className="calendar-content">
          {!nav.isDashboardView && (
            <OperationalSidebar
              sortedEvents={sortedEvents}
              onAddClick={actions.openAddModal}
              onEventClick={actions.handleEditAppointment}
              onDeleteEvent={actions.handleDeleteEvent}
              formatEventTime={events.formatEventTime}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              selectedDate={sidebarDate}
            />
          )}

          <div className={nav.isDashboardView ? 'calendar-main calendar-main--full-width' : 'calendar-main'}>
            <CalendarMainView
              view={nav.view}
              loading={events.loading}
              currentDate={nav.currentDate}
              viewHours={events.viewHours}
              getEventsForDateObj={events.getEventsForDateObj}
              getEventsForDateAndHour={events.getEventsForDateAndHour}
              getEventsForDate={events.getEventsForDate}
              onTimeSlotClick={handleTimeSlotClick}
              onEventClick={actions.handleEditAppointment}
              onDayHeaderClick={nav.handleDayHeaderClick}
              weekDates={nav.weekDates}
              currentMonthData={nav.currentMonthData}
              nextMonthData={nav.nextMonthData}
              onDayClick={handleDayClick}
              onScrollUp={nav.handleScrollUp}
              onScrollDown={nav.handleScrollDown}
            />
          </div>
        </div>
      )}

      <CalendarModals
        showAddModal={actions.showAddModal}
        selectedDate={actions.selectedDate}
        selectedTime={actions.selectedTime}
        onCloseAddModal={() => actions.setShowAddModal(false)}
        onAddEvent={actions.handleAddEvent}
        onAddAppointment={actions.handleAddAppointment}
        teamMembers={events.teamMembers}
        isBooking={actions.isBooking}
        showEditModal={actions.showEditModal}
        editingAppointment={actions.editingAppointment}
        onEditFieldChange={actions.handleEditFieldChange}
        onSaveAppointment={actions.handleSaveAppointment}
        onCancelAppointment={actions.handleCancelFromModal}
        onCloseEditModal={() => actions.setShowEditModal(false)}
        saving={actions.saving}
        confirmAction={actions.confirmAction}
        onDismissConfirm={() => actions.setConfirmAction(null)}
        showSearch={showSearch}
        onCloseSearch={() => setShowSearch(false)}
        onSearchSelectAppointment={handleSearchSelectAppointment}
        showShortcutsHelp={showShortcutsHelp}
        onCloseShortcutsHelp={() => setShowShortcutsHelp(false)}
        tour={tour}
        hasTour={hasCalendarTour}
      />

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
