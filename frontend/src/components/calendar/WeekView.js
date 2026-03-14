import React, { useMemo, useCallback } from 'react';

const dayAbbreviations = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

const formatHour = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

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

const handleInteractiveKeyDown = (e, onClick) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onClick(e);
  }
};

/**
 * WeekView -- 7-day calendar grid with hourly time slots and event cards.
 *
 * Used in: Calendar (main page, week view mode)
 *
 * @param {Object} props
 * @param {Date[]} props.weekDates - Array of 7 Date objects representing the displayed week
 * @param {number[]} props.viewHours - Hour numbers to render as rows (e.g. [7, 8, ..., 20])
 * @param {Function} props.getEventsForDateAndHour - Function(dateObj, hour) => Array of events at that slot
 * @param {Function} props.onTimeSlotClick - Callback(date, hour) when an empty time slot is clicked
 * @param {Function} props.onEventClick - Callback(event) when an event card is clicked
 * @param {Function} [props.onDayHeaderClick] - Callback(date) when a day column header is clicked (switches to day view)
 * @returns {React.ReactElement}
 *
 * @example
 * <WeekView
 *   weekDates={weekDates}
 *   viewHours={[8, 9, 10, 11, 12, 13, 14, 15, 16, 17]}
 *   getEventsForDateAndHour={getEvents}
 *   onTimeSlotClick={handleSlotClick}
 *   onEventClick={handleEventClick}
 *   onDayHeaderClick={switchToDayView}
 * />
 */
const WeekView = React.memo(function WeekView({
  weekDates,
  viewHours,
  getEventsForDateAndHour,
  onTimeSlotClick,
  onEventClick,
  onDayHeaderClick,
}) {
  const today = useMemo(() => new Date(), []);

  const handleDayClick = useCallback((day) => {
    if (onDayHeaderClick) onDayHeaderClick(day);
  }, [onDayHeaderClick]);

  return (
    <div className="week-view">
      <div className="week-view-header">
        <div className="week-time-gutter" />
        {weekDates.map((day, i) => (
          <div
            key={i}
            className={`week-day-col-header ${isSameDay(day, today) ? 'today' : ''}`}
            role="button"
            tabIndex={0}
            aria-label={`View ${monthNames[day.getMonth()]} ${day.getDate()}`}
            onClick={() => handleDayClick(day)}
            onKeyDown={(e) => handleInteractiveKeyDown(e, () => handleDayClick(day))}
            style={{ cursor: 'pointer' }}
          >
            <span className="week-day-name">{dayAbbreviations[day.getDay()]}</span>
            <span className="week-day-num">{day.getDate()}</span>
          </div>
        ))}
      </div>
      <div className="week-view-body">
        {viewHours.map(hour => (
          <div className="week-hour-row" key={hour}>
            <div className="hour-label">{formatHour(hour)}</div>
            {weekDates.map((day, i) => {
              const cellEvents = getEventsForDateAndHour(day, hour);
              return (
                <div
                  key={i}
                  className="week-cell"
                  role="button"
                  tabIndex={0}
                  aria-label={`Add event on ${dayAbbreviations[day.getDay()]} at ${formatHour(hour)}`}
                  onClick={() => onTimeSlotClick(day, hour)}
                  onKeyDown={(e) => handleInteractiveKeyDown(e, () => onTimeSlotClick(day, hour))}
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
                        if (event.isAppointment) onEventClick(event);
                      }}
                      onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => onEventClick(event)) : undefined}
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
});

export default WeekView;
