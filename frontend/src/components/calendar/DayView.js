import React, { useMemo, useCallback, useRef, useEffect, useState } from 'react';
import { EventBoundary } from './EventErrorFallback';
import { normalizeUTCDate, getUserTimezone } from './calendarUtils';

/**
 * DAY_VIEW_HOURS - Time slots from 6 AM to 9 PM (inclusive).
 */
const DAY_VIEW_HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21];

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * formatHour12 - Format a 24h hour as 12-hour string.
 */
const formatHour12 = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

/**
 * isSameDay - Check if two Date objects fall on the same calendar day.
 */
const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

/**
 * getEventColorClass - Map event type to CSS class.
 */
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

/**
 * DayView - Full single-day view with hourly time slots.
 *
 * Features:
 * - Displays hours from 6 AM to 9 PM
 * - Full event details visible (longer cards with time, title, attendee, location, notes)
 * - Current time indicator line (red horizontal line)
 * - Click a time slot to create an appointment at that hour
 * - All-day events shown in a header section above the time grid
 * - Keyboard accessible: slots are focusable and activatable
 *
 * Props:
 *   currentDate      - Date object for the day to display
 *   events           - Array of event objects (pre-filtered by tab/search if needed)
 *   onTimeSlotClick  - Callback(date, hour) when an empty time slot is clicked
 *   onEventClick     - Callback(event) when an event card is clicked (for edit)
 *   getEventsForDateAndHour - Function(dateObj, hour) => events at that hour
 *   getEventsForDate - Function(dateObj) => all events for that date
 */
const DayView = React.memo(function DayView({
  currentDate,
  events = [],
  onTimeSlotClick,
  onEventClick,
  getEventsForDateAndHour,
  getEventsForDate,
}) {
  const timelineRef = useRef(null);
  const currentTimeRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  const today = useMemo(() => new Date(), []);
  const isToday = useMemo(() => isSameDay(currentDate, today), [currentDate, today]);

  // Update the current time indicator every minute
  useEffect(() => {
    if (!isToday) return;

    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000); // 1 minute

    return () => clearInterval(interval);
  }, [isToday]);

  // Scroll to current time on mount (or to 8 AM if not today)
  useEffect(() => {
    if (currentTimeRef.current) {
      currentTimeRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } else if (timelineRef.current) {
      // Scroll to ~8 AM area (2nd hour slot from the top given we start at 6 AM)
      const hourHeight = 80; // approximate px per hour row
      timelineRef.current.scrollTop = hourHeight * 2;
    }
  }, [currentDate, isToday]);

  // Get all events for the current day
  const dayEvents = useMemo(() => {
    if (getEventsForDate) {
      return getEventsForDate(currentDate);
    }
    return events.filter(event => {
      const eventDate = new Date(event.start_time);
      return isSameDay(eventDate, currentDate);
    });
  }, [currentDate, events, getEventsForDate]);

  // Separate all-day events from timed events
  const { allDayEvents, timedEvents } = useMemo(() => {
    const allDay = [];
    const timed = [];
    for (const event of dayEvents) {
      if (event.all_day || event.is_all_day) {
        allDay.push(event);
      } else {
        timed.push(event);
      }
    }
    return { allDayEvents: allDay, timedEvents: timed };
  }, [dayEvents]);

  // Get events for a specific hour
  const getHourEvents = useCallback((hour) => {
    if (getEventsForDateAndHour) {
      return getEventsForDateAndHour(currentDate, hour);
    }
    return timedEvents.filter(event => {
      const eventDate = new Date(event.start_time);
      return eventDate.getHours() === hour;
    });
  }, [currentDate, timedEvents, getEventsForDateAndHour]);

  // Format event time range -- timezone-aware
  const formatEventTime = useCallback((startTime, endTime) => {
    const start = new Date(normalizeUTCDate(startTime));
    const end = new Date(normalizeUTCDate(endTime));
    const tz = getUserTimezone();
    const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: tz });
    const endStr = end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: tz });
    const durationMs = end - start;
    const durationMins = Math.round(durationMs / 60000);
    let durationStr;
    if (durationMins >= 60) {
      const hours = Math.floor(durationMins / 60);
      const mins = durationMins % 60;
      durationStr = mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    } else {
      durationStr = `${durationMins}m`;
    }
    return { startStr, endStr, durationMins, durationStr };
  }, []);

  // Calculate current time indicator position
  const currentTimePosition = useMemo(() => {
    if (!isToday) return null;
    const hours = currentTime.getHours();
    const minutes = currentTime.getMinutes();
    // Position relative to the first hour (6 AM)
    if (hours < DAY_VIEW_HOURS[0] || hours > DAY_VIEW_HOURS[DAY_VIEW_HOURS.length - 1]) {
      return null;
    }
    const hourIndex = hours - DAY_VIEW_HOURS[0];
    const fractionalHour = hourIndex + minutes / 60;
    return fractionalHour;
  }, [isToday, currentTime]);

  const handleSlotKeyDown = useCallback((e, date, hour) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onTimeSlotClick?.(date, hour);
    }
  }, [onTimeSlotClick]);

  const handleEventKeyDown = useCallback((e, event) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onEventClick?.(event);
    }
  }, [onEventClick]);

  const dateLabel = `${DAY_NAMES[currentDate.getDay()]}, ${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;

  return (
    <div className="cv-day-view" role="region" aria-label={`Day view: ${dateLabel}`}>
      {/* Day header */}
      <div className="cv-day-view__header">
        <h3 className="cv-day-view__title">{dateLabel}</h3>
        {isToday && <span className="cv-day-view__today-badge">Today</span>}
      </div>

      {/* All-day events section */}
      {allDayEvents.length > 0 && (
        <div className="cv-day-view__all-day" role="region" aria-label="All-day events">
          <div className="cv-day-view__all-day-label">All Day</div>
          <div className="cv-day-view__all-day-events">
            {allDayEvents.map(event => (
              <EventBoundary key={event.id} event={event}>
                <div
                  className={`cv-day-view__all-day-event ${getEventColorClass(event.event_type)}`}
                  role={event.isAppointment ? 'button' : undefined}
                  tabIndex={event.isAppointment ? 0 : undefined}
                  aria-label={event.isAppointment ? `Edit appointment: ${event.title}` : event.title}
                  onClick={() => event.isAppointment && onEventClick?.(event)}
                  onKeyDown={event.isAppointment ? (e) => handleEventKeyDown(e, event) : undefined}
                >
                  <span className="cv-day-view__all-day-event-title">{event.title}</span>
                  {event.attendee_name && (
                    <span className="cv-day-view__all-day-event-attendee">{event.attendee_name}</span>
                  )}
                </div>
              </EventBoundary>
            ))}
          </div>
        </div>
      )}

      {/* Time grid */}
      <div className="cv-day-view__timeline" ref={timelineRef}>
        {DAY_VIEW_HOURS.map((hour, hourIdx) => {
          const hourEvents = getHourEvents(hour);

          return (
            <div className="cv-day-view__hour-row" key={hour}>
              {/* Time label */}
              <div className="cv-day-view__time-label" aria-hidden="true">
                {formatHour12(hour)}
              </div>

              {/* Hour slot */}
              <div
                className="cv-day-view__hour-slot"
                role="button"
                tabIndex={0}
                aria-label={`Add event at ${formatHour12(hour)} on ${dateLabel}`}
                onClick={() => onTimeSlotClick?.(currentDate, hour)}
                onKeyDown={(e) => handleSlotKeyDown(e, currentDate, hour)}
              >
                {/* Current time indicator */}
                {isToday && currentTimePosition !== null &&
                  Math.floor(currentTimePosition) === hourIdx && (
                  <div
                    ref={currentTimeRef}
                    className="cv-day-view__current-time"
                    style={{
                      top: `${(currentTimePosition - hourIdx) * 100}%`,
                    }}
                    aria-hidden="true"
                  >
                    <div className="cv-day-view__current-time-dot" />
                    <div className="cv-day-view__current-time-line" />
                  </div>
                )}

                {/* Events in this hour */}
                {hourEvents.map(event => {
                  const { startStr, endStr, durationStr } = formatEventTime(
                    event.start_time,
                    event.end_time
                  );

                  return (
                    <EventBoundary key={event.id} event={event}>
                      <div
                        className={`cv-day-view__event ${getEventColorClass(event.event_type)} ${event.isAppointment ? 'cv-day-view__event--clickable' : ''}`}
                        role={event.isAppointment ? 'button' : undefined}
                        tabIndex={event.isAppointment ? 0 : undefined}
                        aria-label={event.isAppointment ? `Edit appointment: ${event.title}, ${startStr} - ${endStr}` : `${event.title}, ${startStr} - ${endStr}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (event.isAppointment) onEventClick?.(event);
                        }}
                        onKeyDown={event.isAppointment ? (e) => {
                          e.stopPropagation();
                          handleEventKeyDown(e, event);
                        } : undefined}
                      >
                        <div className="cv-day-view__event-header">
                          <span className="cv-day-view__event-time">
                            {startStr} - {endStr}
                          </span>
                          <span className="cv-day-view__event-duration">{durationStr}</span>
                        </div>
                        <div className="cv-day-view__event-title">{event.title}</div>
                        {event.attendee_name && (
                          <div className="cv-day-view__event-attendee">{event.attendee_name}</div>
                        )}
                        {event.location && (
                          <div className="cv-day-view__event-location">{event.location}</div>
                        )}
                        {event.description && (
                          <div className="cv-day-view__event-notes">{event.description}</div>
                        )}
                        {event.status && (
                          <div className="cv-day-view__event-status">
                            <span className={`cv-day-view__status-dot cv-day-view__status-dot--${(event.status || '').toLowerCase()}`} />
                            {event.status}
                          </div>
                        )}
                      </div>
                    </EventBoundary>
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

export default DayView;
