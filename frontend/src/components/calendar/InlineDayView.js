import React, { useMemo, useCallback } from 'react';

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
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
 * InlineDayView -- Single-day timeline view with hourly slots and event cards.
 *
 * Differs from the standalone DayView component by receiving data from the parent
 * via getEventsForDateObj rather than fetching its own data.
 *
 * Used in: Calendar (main page, day view mode)
 *
 * @param {Object} props
 * @param {Date} props.currentDate - The date to display
 * @param {number[]} props.viewHours - Hour numbers to render as rows (derived from availability settings)
 * @param {Function} props.getEventsForDateObj - Function(dateObj) => Array of all events for that date
 * @param {Function} props.onTimeSlotClick - Callback(date, hour) when an empty time slot is clicked
 * @param {Function} props.onEventClick - Callback(event) when an event card is clicked
 * @returns {React.ReactElement}
 *
 * @example
 * <InlineDayView
 *   currentDate={new Date()}
 *   viewHours={[8, 9, 10, 11, 12, 13, 14, 15, 16, 17]}
 *   getEventsForDateObj={getEventsForDate}
 *   onTimeSlotClick={handleSlotClick}
 *   onEventClick={handleEventClick}
 * />
 */
const InlineDayView = React.memo(function InlineDayView({
  currentDate,
  viewHours,
  getEventsForDateObj,
  onTimeSlotClick,
  onEventClick,
}) {
  const today = useMemo(() => new Date(), []);
  const dayEvents = useMemo(() => getEventsForDateObj(currentDate), [getEventsForDateObj, currentDate]);

  const formatEventTime = useCallback((startTime, endTime) => {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const duration = Math.round((end - start) / (1000 * 60));
    return { startStr, duration };
  }, []);

  return (
    <div className="day-view">
      <div className="day-view-header">
        <h3>{dayNames[currentDate.getDay()]}, {monthNames[currentDate.getMonth()]} {currentDate.getDate()}</h3>
        {isSameDay(currentDate, today) && <span className="today-badge">Today</span>}
      </div>
      <div className="day-view-timeline">
        {viewHours.map(hour => {
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
                onClick={() => onTimeSlotClick(currentDate, hour)}
                onKeyDown={(e) => handleInteractiveKeyDown(e, () => onTimeSlotClick(currentDate, hour))}
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
                        if (event.isAppointment) onEventClick(event);
                      }}
                      onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => onEventClick(event)) : undefined}
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
});

export default InlineDayView;
