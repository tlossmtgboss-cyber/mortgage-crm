import { useState, useEffect, useCallback, useMemo } from 'react';
import { schedulerAPI, crmCalendarAPI } from '../../services/api';
import { normalizeUTCDate, formatDateForAPI } from './calendarUtils';

/**
 * Custom hook that manages calendar data loading, event merging,
 * and derived appointment lists.
 */
export function useCalendarData({ leadId, loanId }) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [appointments, setAppointments] = useState([]);
  const [crmEvents, setCrmEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadAppointments = useCallback(async () => {
    try {
      setLoading(true);
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);

      const [appointmentsData, crmEventsData] = await Promise.all([
        schedulerAPI.getAppointments({
          start_date: formatDateForAPI(startDate),
          end_date: formatDateForAPI(endDate),
          lead_id: leadId || undefined,
          loan_id: loanId || undefined,
        }).catch(() => []),
        crmCalendarAPI.getAll({
          start_date: startDate.toISOString(),
          end_date: endDate.toISOString(),
        }).catch(() => [])
      ]);

      const filteredAppointments = (appointmentsData || [])
        .filter(appt => (appt.status || '').toLowerCase() !== 'cancelled')
        .sort((a, b) => new Date(normalizeUTCDate(a.scheduled_start)) - new Date(normalizeUTCDate(b.scheduled_start)));

      const filteredCrmEvents = (crmEventsData || [])
        .filter(event => event.status !== 'cancelled')
        .sort((a, b) => new Date(a.start_at || a.start_time) - new Date(b.start_at || b.start_time));

      setAppointments(filteredAppointments);
      setCrmEvents(filteredCrmEvents);
    } catch {
      setAppointments([]);
      setCrmEvents([]);
    } finally {
      setLoading(false);
    }
  }, [currentDate, leadId, loanId]);

  useEffect(() => { loadAppointments(); }, [loadAppointments]);

  // Pre-compute set of date strings with events for O(1) lookup
  const eventDateSet = useMemo(() => {
    const dates = new Set();
    appointments.forEach(appt => {
      dates.add(new Date(normalizeUTCDate(appt.scheduled_start)).toDateString());
    });
    crmEvents.forEach(event => {
      dates.add(new Date(event.start_at || event.start_time).toDateString());
    });
    return dates;
  }, [appointments, crmEvents]);

  // Merge scheduler + CRM events using a filter function
  const buildMergedList = useCallback((filterFn) => {
    const appts = appointments
      .filter(appt => filterFn(new Date(normalizeUTCDate(appt.scheduled_start))))
      .map(appt => ({ ...appt, sourceType: 'scheduler', displayTime: appt.scheduled_start }));

    const events = crmEvents
      .filter(event => filterFn(new Date(event.start_at || event.start_time)))
      .map(event => ({
        id: `crm-${event.id}`,
        title: event.title || event.subject || 'CRM Event',
        scheduled_start: event.start_at || event.start_time,
        scheduled_end: event.end_at || event.end_time,
        attendee_name: event.attendees?.length > 0 ? event.attendees[0].name : null,
        meeting_mode: event.event_type === 'video_call' ? 'VIDEO' :
                      event.event_type === 'phone_call' ? 'PHONE' :
                      event.event_type === 'meeting' ? 'IN_PERSON' : 'OTHER',
        sourceType: 'crm_calendar',
        crmEventId: event.id,
        sync_status: event.sync_status,
        displayTime: event.start_at || event.start_time,
      }));

    return [...appts, ...events].sort((a, b) =>
      new Date(a.displayTime) - new Date(b.displayTime)
    );
  }, [appointments, crmEvents]);

  const selectedDateAppointments = useMemo(() =>
    buildMergedList(d => d.toDateString() === selectedDate.toDateString()),
    [buildMergedList, selectedDate]
  );

  const upcomingAppointments = useMemo(() => {
    const now = new Date();
    return buildMergedList(d => d >= now).slice(0, 5);
  }, [buildMergedList]);

  // Navigation helpers
  const goToPreviousMonth = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  }, []);

  const goToNextMonth = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  }, []);

  const goToToday = useCallback(() => {
    const today = new Date();
    setCurrentDate(today);
    setSelectedDate(today);
  }, []);

  const handleDateClick = useCallback((date) => {
    if (date) setSelectedDate(date);
  }, []);

  return {
    currentDate,
    selectedDate,
    loading,
    eventDateSet,
    selectedDateAppointments,
    upcomingAppointments,
    loadAppointments,
    goToPreviousMonth,
    goToNextMonth,
    goToToday,
    handleDateClick,
  };
}
