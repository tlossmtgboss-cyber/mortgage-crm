import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { EventBoundary } from './EventErrorFallback';
import StatusBadge from './StatusBadge';
import {
  normalizeUTCDate,
  getUserTimezone,
  getTimezoneAbbreviation,
} from './calendarUtils';

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/** Number of days to load per batch when "Load more" is clicked. */
const LOAD_MORE_DAYS = 30;

/** Initial number of days to show (from today forward). */
const INITIAL_DAYS = 14;

/**
 * formatRelativeDate - Format a date as "Today", "Tomorrow", or full date string.
 */
const formatRelativeDate = (date) => {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';

  return `${DAY_NAMES[date.getDay()]}, ${MONTH_NAMES[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
};

/**
 * formatEventTime - Format start/end times and compute duration.
 * Timezone-aware: formats in the user's configured timezone.
 */
const formatEventTime = (startTime, endTime) => {
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
};

/**
 * getEventColorClass - Map event type to CSS border color class.
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
 * AgendaView - Chronological list of upcoming appointments.
 *
 * Features:
 * - Grouped by date with sticky date headers
 * - Each item shows: time, duration, borrower name, type, status badge
 * - Click to expand/show details
 * - "Load more" button for additional past/future dates
 * - Empty state: "No upcoming appointments"
 * - Keyboard accessible
 *
 * Props:
 *   events         - Array of all event objects (already filtered by tab)
 *   currentDate    - Date object (used as the starting point for the view)
 *   onEventClick   - Callback(event) when an event is clicked (for edit)
 */
const AgendaView = React.memo(function AgendaView({
  events = [],
  currentDate,
  onEventClick,
}) {
  const [visibleDays, setVisibleDays] = useState(INITIAL_DAYS);
  const [expandedId, setExpandedId] = useState(null);
  const listRef = useRef(null);

  // Reset visible days when currentDate changes significantly
  useEffect(() => {
    setVisibleDays(INITIAL_DAYS);
    setExpandedId(null);
  }, [currentDate.getMonth(), currentDate.getFullYear()]);

  // Sort events chronologically and group by date
  const { groupedEvents, hasMore } = useMemo(() => {
    const startDate = new Date(currentDate);
    startDate.setHours(0, 0, 0, 0);

    // End date based on visibleDays
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + visibleDays);

    // Filter events within the visible window and sort
    const filtered = events
      .filter(event => {
        if (!event.start_time) return false;
        const eventDate = new Date(event.start_time);
        return eventDate >= startDate && eventDate < endDate;
      })
      .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));

    // Group by date string
    const groups = [];
    let currentGroup = null;

    for (const event of filtered) {
      const eventDate = new Date(event.start_time);
      const dateKey = eventDate.toDateString();

      if (!currentGroup || currentGroup.dateKey !== dateKey) {
        currentGroup = {
          dateKey,
          date: eventDate,
          label: formatRelativeDate(eventDate),
          events: [],
        };
        groups.push(currentGroup);
      }
      currentGroup.events.push(event);
    }

    // Check if there are events beyond the visible window
    const hasMore = events.some(event => {
      if (!event.start_time) return false;
      return new Date(event.start_time) >= endDate;
    });

    return { groupedEvents: groups, hasMore };
  }, [events, currentDate, visibleDays]);

  const handleLoadMore = useCallback(() => {
    setVisibleDays(prev => prev + LOAD_MORE_DAYS);
  }, []);

  const toggleExpand = useCallback((eventId) => {
    setExpandedId(prev => prev === eventId ? null : eventId);
  }, []);

  const handleEventKeyDown = useCallback((e, event) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleExpand(event.id);
    }
  }, [toggleExpand]);

  const handleEditKeyDown = useCallback((e, event) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      onEventClick?.(event);
    }
  }, [onEventClick]);

  const totalEvents = groupedEvents.reduce((sum, g) => sum + g.events.length, 0);

  return (
    <div className="cv-agenda-view" role="region" aria-label="Agenda view">
      {/* Summary header */}
      <div className="cv-agenda-view__header">
        <h3 className="cv-agenda-view__title">Upcoming Appointments</h3>
        {totalEvents > 0 && (
          <span className="cv-agenda-view__count">
            {totalEvents} event{totalEvents !== 1 ? 's' : ''} ({getTimezoneAbbreviation()})
          </span>
        )}
      </div>

      {/* Event list */}
      <div className="cv-agenda-view__list" ref={listRef} role="list">
        {groupedEvents.length === 0 ? (
          <div className="cv-agenda-view__empty" role="status">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <p className="cv-agenda-view__empty-text">No upcoming appointments</p>
            <p className="cv-agenda-view__empty-hint">
              Appointments scheduled within this period will appear here.
            </p>
          </div>
        ) : (
          groupedEvents.map((group) => (
            <div key={group.dateKey} className="cv-agenda-view__date-group" role="group" aria-label={group.label}>
              {/* Date header */}
              <div className="cv-agenda-view__date-header">
                <span className="cv-agenda-view__date-label">{group.label}</span>
                <span className="cv-agenda-view__date-count">
                  {group.events.length} event{group.events.length !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Events for this date */}
              {group.events.map((event) => {
                const { startStr, endStr, durationStr } = formatEventTime(
                  event.start_time,
                  event.end_time
                );
                const isExpanded = expandedId === event.id;

                return (
                  <EventBoundary key={event.id} event={event}>
                    <div
                      className={`cv-agenda-view__item ${getEventColorClass(event.event_type)} ${isExpanded ? 'cv-agenda-view__item--expanded' : ''}`}
                      role="listitem"
                      tabIndex={0}
                      aria-expanded={isExpanded}
                      aria-label={`${event.title}, ${startStr} to ${endStr}, ${durationStr}`}
                      onClick={() => toggleExpand(event.id)}
                      onKeyDown={(e) => handleEventKeyDown(e, event)}
                    >
                      {/* Time column */}
                      <div className="cv-agenda-view__item-time">
                        <span className="cv-agenda-view__time-start">{startStr}</span>
                        <span className="cv-agenda-view__time-duration">{durationStr}</span>
                      </div>

                      {/* Content column */}
                      <div className="cv-agenda-view__item-content">
                        <div className="cv-agenda-view__item-row">
                          <span className="cv-agenda-view__item-title">{event.title}</span>
                          {event.status && (
                            <StatusBadge status={event.status} size="sm" />
                          )}
                        </div>

                        {event.attendee_name && (
                          <div className="cv-agenda-view__item-attendee">
                            {event.attendee_name}
                          </div>
                        )}

                        {event.meeting_mode && (
                          <div className="cv-agenda-view__item-type">
                            {event.meeting_mode === 'VIDEO' && 'Video Call'}
                            {event.meeting_mode === 'PHONE' && 'Phone Call'}
                            {event.meeting_mode === 'IN_PERSON' && 'In Person'}
                          </div>
                        )}

                        {/* Expanded details */}
                        {isExpanded && (
                          <div className="cv-agenda-view__item-details">
                            <div className="cv-agenda-view__detail-row">
                              <span className="cv-agenda-view__detail-label">Time</span>
                              <span className="cv-agenda-view__detail-value">{startStr} - {endStr}</span>
                            </div>

                            {event.attendee_email && (
                              <div className="cv-agenda-view__detail-row">
                                <span className="cv-agenda-view__detail-label">Email</span>
                                <span className="cv-agenda-view__detail-value">{event.attendee_email}</span>
                              </div>
                            )}

                            {event.attendee_phone && (
                              <div className="cv-agenda-view__detail-row">
                                <span className="cv-agenda-view__detail-label">Phone</span>
                                <span className="cv-agenda-view__detail-value">{event.attendee_phone}</span>
                              </div>
                            )}

                            {event.location && (
                              <div className="cv-agenda-view__detail-row">
                                <span className="cv-agenda-view__detail-label">Location</span>
                                <span className="cv-agenda-view__detail-value">{event.location}</span>
                              </div>
                            )}

                            {event.description && (
                              <div className="cv-agenda-view__detail-row">
                                <span className="cv-agenda-view__detail-label">Notes</span>
                                <span className="cv-agenda-view__detail-value">{event.description}</span>
                              </div>
                            )}

                            {event.isAppointment && (
                              <button
                                className="cv-agenda-view__edit-btn"
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onEventClick?.(event);
                                }}
                                onKeyDown={(e) => handleEditKeyDown(e, event)}
                              >
                                Edit / Reschedule
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Expand indicator */}
                      <div className="cv-agenda-view__item-chevron" aria-hidden="true">
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          style={{
                            transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            transition: 'transform 200ms ease',
                          }}
                        >
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </div>
                    </div>
                  </EventBoundary>
                );
              })}
            </div>
          ))
        )}
      </div>

      {/* Load more */}
      {hasMore && (
        <div className="cv-agenda-view__load-more">
          <button
            className="cv-agenda-view__load-more-btn"
            type="button"
            onClick={handleLoadMore}
          >
            Load more appointments
          </button>
        </div>
      )}
    </div>
  );
});

export default AgendaView;
