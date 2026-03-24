import React, { lazy, Suspense } from 'react';
import InlineDayView from './InlineDayView';
import WeekView from './WeekView';
import MonthView from './MonthView';

// Lazy load dashboard views (only rendered when selected)
const CalendarAnalyticsDashboard = lazy(() => import('./CalendarAnalyticsDashboard'));
const NoShowRecoveryDashboard = lazy(() => import('./NoShowRecoveryDashboard'));
const AppointmentOutcomeDashboard = lazy(() => import('./AppointmentOutcomeDashboard'));
const WebhookHealthDashboard = lazy(() => import('./WebhookHealthDashboard'));

/**
 * CalendarMainView -- View dispatcher that renders the appropriate calendar view
 * (day, week, month) or dashboard view (analytics, no-shows, outcomes, webhooks)
 * based on the current view selection.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {string} props.view - Current calendar view key
 * @param {boolean} props.loading - Whether events are still loading
 * @param {Date} props.currentDate - Current date for day view
 * @param {number[]} props.viewHours - Hours to display in day/week views
 * @param {Function} props.getEventsForDateObj - Function(dateObj) => events for that date
 * @param {Function} props.getEventsForDateAndHour - Function(dateObj, hour) => events for that slot
 * @param {Function} props.getEventsForDate - Function(day, year, month) => events for that date
 * @param {Function} props.onTimeSlotClick - Handler for clicking an empty time slot
 * @param {Function} props.onEventClick - Handler for clicking an event
 * @param {Function} props.onDayHeaderClick - Handler for clicking a day column header in week view
 * @param {Date[]} props.weekDates - Array of 7 Date objects for the current week
 * @param {Object} props.currentMonthData - Month layout data for the primary month
 * @param {Object} props.nextMonthData - Month layout data for the following month
 * @param {Function} props.onDayClick - Handler for clicking a day cell in month view
 * @param {Function} props.onScrollUp - Navigate to previous month pair
 * @param {Function} props.onScrollDown - Navigate to next month pair
 * @returns {React.ReactElement}
 */
const CalendarMainView = React.memo(function CalendarMainView({
  view,
  loading,
  currentDate,
  viewHours,
  getEventsForDateObj,
  getEventsForDateAndHour,
  getEventsForDate,
  onTimeSlotClick,
  onEventClick,
  onDayHeaderClick,
  weekDates,
  currentMonthData,
  nextMonthData,
  onDayClick,
  onScrollUp,
  onScrollDown,
}) {
  // Dashboard views
  if (view === 'analytics') {
    return <Suspense fallback={<div className="loading">Loading analytics...</div>}><CalendarAnalyticsDashboard /></Suspense>;
  }
  if (view === 'no-shows') {
    return <Suspense fallback={<div className="loading">Loading no-show data...</div>}><NoShowRecoveryDashboard /></Suspense>;
  }
  if (view === 'outcomes') {
    return <Suspense fallback={<div className="loading">Loading outcomes...</div>}><AppointmentOutcomeDashboard /></Suspense>;
  }
  if (view === 'webhooks') {
    return <Suspense fallback={<div className="loading">Loading webhook health...</div>}><WebhookHealthDashboard /></Suspense>;
  }

  if (loading) {
    return <div className="loading">Loading events...</div>;
  }

  if (view === 'day') {
    return (
      <InlineDayView
        currentDate={currentDate}
        viewHours={viewHours}
        getEventsForDateObj={getEventsForDateObj}
        onTimeSlotClick={onTimeSlotClick}
        onEventClick={onEventClick}
      />
    );
  }

  if (view === 'week') {
    return (
      <WeekView
        weekDates={weekDates}
        viewHours={viewHours}
        getEventsForDateAndHour={getEventsForDateAndHour}
        onTimeSlotClick={onTimeSlotClick}
        onEventClick={onEventClick}
        onDayHeaderClick={onDayHeaderClick}
      />
    );
  }

  // Month view (default)
  return (
    <MonthView
      currentMonthData={currentMonthData}
      nextMonthData={nextMonthData}
      getEventsForDate={getEventsForDate}
      onDayClick={onDayClick}
      onScrollUp={onScrollUp}
      onScrollDown={onScrollDown}
    />
  );
});

export default CalendarMainView;
