import React, { useMemo } from 'react';

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const DAY_ABBR = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * formatPrintTime - Format a date/time for print display (e.g., "9:30 AM").
 */
const formatPrintTime = (dateStr) => {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
};

/**
 * formatMeetingMode - Friendly label for meeting mode values.
 */
const formatMeetingMode = (mode) => {
  const labels = {
    PHONE: 'Phone',
    VIDEO: 'Video',
    IN_PERSON: 'In Person',
  };
  return labels[mode] || mode || '';
};

/**
 * getStartOfWeek - Return Sunday of the week containing the given date.
 */
const getStartOfWeek = (date) => {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  d.setHours(0, 0, 0, 0);
  return d;
};

/**
 * PrintCalendarView - Print-optimized calendar view.
 *
 * Renders a clean, ink-friendly layout for weekly or monthly views.
 * Designed to be rendered inside the main Calendar page and made visible
 * only via CSS @media print rules (the screen UI hides it, print shows it).
 *
 * Props:
 *   events        - Array of calendar events (same shape as allEvents in Calendar.js)
 *   currentDate   - The currently displayed Date
 *   view          - 'week' or 'month' (determines print layout)
 *   loName        - Loan officer name for the header (optional)
 */
const PrintCalendarView = React.memo(function PrintCalendarView({
  events = [],
  currentDate,
  view = 'week',
  loName = '',
}) {
  // ---- Compute date range for the header ----
  const dateRange = useMemo(() => {
    if (view === 'week' || view === 'day' || view === '3day') {
      const weekStart = getStartOfWeek(currentDate);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      const startLabel = `${MONTH_NAMES[weekStart.getMonth()]} ${weekStart.getDate()}`;
      const endLabel = weekStart.getMonth() === weekEnd.getMonth()
        ? `${weekEnd.getDate()}, ${weekEnd.getFullYear()}`
        : `${MONTH_NAMES[weekEnd.getMonth()]} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
      return `${startLabel} - ${endLabel}`;
    }
    return `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  }, [currentDate, view]);

  // ---- Build weekly data: 7 days starting from Sunday ----
  const weekDays = useMemo(() => {
    const weekStart = getStartOfWeek(currentDate);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [currentDate]);

  // ---- Index events by date string for O(1) lookups ----
  const eventsByDate = useMemo(() => {
    const index = {};
    for (const event of events) {
      if (!event.start_time) continue;
      const d = new Date(event.start_time);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      if (!index[key]) index[key] = [];
      index[key].push(event);
    }
    // Sort each day's events by start time
    for (const key of Object.keys(index)) {
      index[key].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
    }
    return index;
  }, [events]);

  const getEventsForDate = (dateObj) => {
    const key = `${dateObj.getFullYear()}-${dateObj.getMonth()}-${dateObj.getDate()}`;
    return eventsByDate[key] || [];
  };

  // ---- Build monthly data ----
  const monthWeeks = useMemo(() => {
    if (view !== 'month') return [];
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startDow = firstDay.getDay();

    const allDays = [];
    // Leading blanks
    for (let i = 0; i < startDow; i++) {
      allDays.push(null);
    }
    for (let d = 1; d <= daysInMonth; d++) {
      allDays.push(new Date(year, month, d));
    }
    // Trailing blanks to fill last row
    while (allDays.length % 7 !== 0) {
      allDays.push(null);
    }
    // Chunk into weeks
    const weeks = [];
    for (let i = 0; i < allDays.length; i += 7) {
      weeks.push(allDays.slice(i, i + 7));
    }
    return weeks;
  }, [currentDate, view]);

  const printTimestamp = new Date().toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  });

  // ---- Render an event row in the weekly table ----
  const renderEventRow = (event) => {
    const startTime = formatPrintTime(event.start_time);
    const endTime = formatPrintTime(event.end_time);
    const duration = event.start_time && event.end_time
      ? Math.round((new Date(event.end_time) - new Date(event.start_time)) / 60000)
      : null;

    return (
      <tr key={event.id} className="print-event-row">
        <td className="print-event-time">
          {startTime}
          {endTime ? ` - ${endTime}` : ''}
          {duration ? ` (${duration}m)` : ''}
        </td>
        <td className="print-event-title">
          {event.title || 'Untitled'}
        </td>
        <td className="print-event-attendee">
          {event.attendee_name || ''}
        </td>
        <td className="print-event-type">
          {event.event_type
            ? event.event_type.replace(/_/g, ' ')
            : ''}
          {event.meeting_mode ? ` (${formatMeetingMode(event.meeting_mode)})` : ''}
        </td>
        <td className="print-event-location">
          {event.location || ''}
        </td>
      </tr>
    );
  };

  // ---- WEEKLY LAYOUT ----
  const renderWeekView = () => (
    <div className="print-week-layout">
      {weekDays.map((day) => {
        const dayEvents = getEventsForDate(day);
        const today = new Date();
        const isToday =
          day.getFullYear() === today.getFullYear() &&
          day.getMonth() === today.getMonth() &&
          day.getDate() === today.getDate();

        return (
          <div key={day.toISOString()} className="print-day-section">
            <h3 className="print-day-heading">
              {DAY_NAMES[day.getDay()]}, {MONTH_NAMES[day.getMonth()]} {day.getDate()}
              {isToday ? ' (Today)' : ''}
            </h3>
            {dayEvents.length === 0 ? (
              <p className="print-no-events">No appointments</p>
            ) : (
              <table className="print-events-table">
                <thead>
                  <tr>
                    <th className="print-col-time">Time</th>
                    <th className="print-col-title">Appointment</th>
                    <th className="print-col-attendee">Borrower</th>
                    <th className="print-col-type">Type</th>
                    <th className="print-col-location">Location</th>
                  </tr>
                </thead>
                <tbody>
                  {dayEvents.map(renderEventRow)}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );

  // ---- MONTHLY LAYOUT ----
  const renderMonthView = () => (
    <div className="print-month-layout">
      <table className="print-month-table">
        <thead>
          <tr>
            {DAY_ABBR.map((d) => (
              <th key={d} className="print-month-day-header">{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {monthWeeks.map((week, wi) => (
            <tr key={wi} className="print-month-week-row">
              {week.map((day, di) => {
                if (!day) {
                  return <td key={di} className="print-month-cell print-month-cell-empty" />;
                }
                const dayEvents = getEventsForDate(day);
                return (
                  <td key={di} className="print-month-cell">
                    <div className="print-month-day-number">{day.getDate()}</div>
                    {dayEvents.length > 0 && (
                      <ul className="print-month-event-list">
                        {dayEvents.slice(0, 4).map((event) => (
                          <li key={event.id} className="print-month-event-item">
                            <span className="print-month-event-time">
                              {formatPrintTime(event.start_time)}
                            </span>
                            {' '}
                            <span className="print-month-event-name">
                              {event.attendee_name || event.title || 'Event'}
                            </span>
                          </li>
                        ))}
                        {dayEvents.length > 4 && (
                          <li className="print-month-event-overflow">
                            +{dayEvents.length - 4} more
                          </li>
                        )}
                      </ul>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const isMonthLayout = view === 'month';

  return (
    <div className="print-calendar-view" aria-hidden="true">
      {/* Header */}
      <div className="print-header">
        <div className="print-header-left">
          <h1 className="print-title">Calendar</h1>
          <h2 className="print-date-range">{dateRange}</h2>
        </div>
        <div className="print-header-right">
          {loName && <div className="print-lo-name">{loName}</div>}
          <div className="print-timestamp">Printed {printTimestamp}</div>
        </div>
      </div>

      <hr className="print-divider" />

      {/* Body */}
      {isMonthLayout ? renderMonthView() : renderWeekView()}

      {/* Footer */}
      <div className="print-footer">
        <span>Perennia AI - Calendar</span>
        <span>{dateRange}</span>
      </div>
    </div>
  );
});

export default PrintCalendarView;
