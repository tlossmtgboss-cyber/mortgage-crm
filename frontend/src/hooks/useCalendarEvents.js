import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { unifiedCalendarAPI, calendarSettingsAPI, teamAPI } from '../services/api';

// Default hours for Day/Week views -- overridden by user's availability settings
const DEFAULT_VIEW_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];

// Derive display hours from availability schedule (earliest start - 1hr to latest end)
// Backend returns flat format: { monday: { start: "09:00", end: "17:00", enabled: true }, ... }
function deriveViewHours(schedule) {
  if (!schedule || typeof schedule !== 'object') return DEFAULT_VIEW_HOURS;
  let earliest = 24, latest = 0;
  for (const day of Object.values(schedule)) {
    if (!day?.enabled) continue;
    const blocks = Array.isArray(day.blocks) ? day.blocks : (day.start && day.end ? [day] : []);
    for (const block of blocks) {
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

/**
 * useCalendarEvents -- Manages event data fetching, indexing, and derived data for Calendar.js.
 *
 * Handles:
 * - Loading events from the unified calendar API with abort-on-remount
 * - Loading availability settings to derive visible hours
 * - Loading team members
 * - Pre-indexing events by date key for O(1) lookups
 * - Filtering/sorting events for sidebar search
 *
 * @param {Date} currentDate - The current calendar date (drives the 3-month fetch window)
 * @returns {Object} Event data, helpers, and loading state
 */
export function useCalendarEvents(currentDate) {
  const [allEvents, setAllEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [teamMembers, setTeamMembers] = useState([]);
  const [viewHours, setViewHours] = useState(DEFAULT_VIEW_HOURS);
  const abortControllerRef = useRef(null);

  const loadEvents = useCallback(async () => {
    // Abort any in-flight fetch (prevents stale responses from rapid navigation)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      setLoading(true);
      // Fetch 3-month window around currentDate (prev month through next month)
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 2, 0);
      const response = await unifiedCalendarAPI.getAll({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      }, { signal: controller.signal });
      setAllEvents(mapUnifiedEvents(response.events));
      setError(null);
    } catch (err) {
      if (err?.name === 'AbortError' || err?.code === 'ERR_CANCELED') return;
      setError('Unable to load calendar events. Please try again.');
      setAllEvents([]);
    } finally {
      if (abortControllerRef.current === controller) {
        setLoading(false);
      }
    }
  }, [currentDate]);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  // Clean up AbortController on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Load team members once
  useEffect(() => {
    teamAPI.getMembers().then(members => setTeamMembers(members)).catch(() => {});
  }, []);

  // Load availability settings to derive visible hours
  useEffect(() => {
    calendarSettingsAPI.getAvailability()
      .then(res => {
        if (res?.data?.business_hours) {
          setViewHours(deriveViewHours(res.data.business_hours));
        }
      })
      .catch(() => {});
  }, []);

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

  return {
    allEvents,
    setAllEvents,
    loading,
    error,
    setError,
    loadEvents,
    teamMembers,
    viewHours,
    eventsByDateKey,
    getEventsForDate,
    getEventsForDateObj,
    getEventsForDateAndHour,
    formatEventTime,
  };
}

export default useCalendarEvents;
