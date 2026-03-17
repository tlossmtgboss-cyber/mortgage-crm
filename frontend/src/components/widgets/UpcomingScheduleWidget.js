import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { unifiedCalendarAPI } from '../../services/api';
import { normalizeUTCDate } from '../calendar/calendarUtils';
import AppointmentCard from './AppointmentCard';
import WidgetSkeleton from './WidgetSkeleton';
import './UpcomingScheduleWidget.css';

/**
 * UpcomingScheduleWidget - Compact widget showing the next 7 days of appointments.
 * Designed to be embedded in any dashboard page.
 *
 * Features:
 *   - Groups appointments by date with date separator headers
 *   - Highlights today's date
 *   - "Now" indicator line showing current time position
 *   - Auto-refreshes every 5 minutes
 *   - "View All" link navigates to full calendar
 *   - Empty state when no upcoming appointments
 *
 * Props:
 *   maxItems   - Maximum number of appointments to show (default: 10)
 *   daysAhead  - Number of days ahead to look (default: 7)
 *   onConfirm  - Callback when a user confirms an appointment
 *   showActions - Whether to show quick action buttons on cards (default: true)
 */
function UpcomingScheduleWidget({
  maxItems = 10,
  daysAhead = 7,
  onConfirm,
  showActions = true,
}) {
  const navigate = useNavigate();
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchUpcoming = useCallback(async () => {
    try {
      const now = new Date();
      const endDate = new Date();
      endDate.setDate(endDate.getDate() + daysAhead);

      const response = await unifiedCalendarAPI.getAll({
        start_date: now.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      // Normalize and filter: only future events, exclude cancelled
      const events = (response.events || response || [])
        .filter(evt => {
          const status = (evt.status || '').toLowerCase();
          if (status === 'cancelled' || status === 'no_show') return false;
          const start = new Date(normalizeUTCDate(evt.scheduled_start || evt.start_time || evt.start_at));
          return start >= new Date(now.getFullYear(), now.getMonth(), now.getDate());
        })
        .sort((a, b) => {
          const aStart = new Date(normalizeUTCDate(a.scheduled_start || a.start_time || a.start_at));
          const bStart = new Date(normalizeUTCDate(b.scheduled_start || b.start_time || b.start_at));
          return aStart - bStart;
        })
        .slice(0, maxItems);

      setAppointments(events);
      setError(null);
    } catch (err) {
      console.error('Failed to load upcoming schedule:', err);
      setError('Unable to load schedule');
    } finally {
      setIsLoading(false);
    }
  }, [daysAhead, maxItems]);

  useEffect(() => {
    fetchUpcoming();

    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchUpcoming, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchUpcoming]);

  // Group appointments by date
  const groupedByDate = useMemo(() => {
    const groups = new Map();

    appointments.forEach(appt => {
      const startStr = appt.scheduled_start || appt.start_time || appt.start_at;
      if (!startStr) return;
      const date = new Date(normalizeUTCDate(startStr));
      const dateKey = date.toDateString();

      if (!groups.has(dateKey)) {
        groups.set(dateKey, { date, appointments: [] });
      }
      groups.get(dateKey).appointments.push(appt);
    });

    return Array.from(groups.values());
  }, [appointments]);

  const handleViewAll = useCallback(() => {
    navigate('/calendar');
  }, [navigate]);

  const today = new Date();
  const todayStr = today.toDateString();

  // Format date label (Today, Tomorrow, or weekday + date)
  const formatDateLabel = (date) => {
    const dateStr = date.toDateString();
    if (dateStr === todayStr) return 'Today';

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (dateStr === tomorrow.toDateString()) return 'Tomorrow';

    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatFullDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <div className="upcoming-schedule-widget">
      {/* Header */}
      <div className="usw-header">
        <div className="usw-header__left">
          <h3 className="usw-header__title">Upcoming Schedule</h3>
          <span className="usw-header__count">
            {!isLoading && `${appointments.length} appointment${appointments.length !== 1 ? 's' : ''}`}
          </span>
        </div>
        <button
          className="usw-header__view-all"
          onClick={handleViewAll}
          title="View full calendar"
        >
          View All
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      {/* Content */}
      {isLoading ? (
        <WidgetSkeleton rows={3} />
      ) : error ? (
        <div className="usw-error">
          <span className="usw-error__text">{error}</span>
          <button className="usw-error__retry" onClick={fetchUpcoming}>
            Retry
          </button>
        </div>
      ) : appointments.length === 0 ? (
        <div className="usw-empty">
          <div className="usw-empty__icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 48 48" fill="none">
              <rect x="6" y="10" width="36" height="32" rx="4" stroke="#d1d5db" strokeWidth="2"/>
              <path d="M6 18H42" stroke="#d1d5db" strokeWidth="2"/>
              <path d="M16 6V14" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <path d="M32 6V14" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="24" cy="30" r="4" stroke="#d1d5db" strokeWidth="2"/>
            </svg>
          </div>
          <p className="usw-empty__message">No upcoming appointments</p>
          <p className="usw-empty__hint">
            Your next {daysAhead} days are clear.
          </p>
          <button
            className="usw-empty__schedule-btn"
            onClick={() => navigate('/calendar')}
          >
            Schedule an appointment
          </button>
        </div>
      ) : (
        <div className="usw-timeline">
          {groupedByDate.map(({ date, appointments: dateAppts }) => {
            const isToday = date.toDateString() === todayStr;

            return (
              <div
                key={date.toDateString()}
                className={`usw-date-group ${isToday ? 'usw-date-group--today' : ''}`}
              >
                {/* Date separator */}
                <div className="usw-date-separator">
                  <span
                    className={`usw-date-label ${isToday ? 'usw-date-label--today' : ''}`}
                    title={formatFullDate(date)}
                  >
                    {formatDateLabel(date)}
                  </span>
                  <div className="usw-date-line" aria-hidden="true" />
                </div>

                {/* "Now" indicator for today */}
                {isToday && <NowIndicator />}

                {/* Appointments for this date */}
                <div className="usw-appointments-list">
                  {dateAppts.map(appt => (
                    <AppointmentCard
                      key={appt.id}
                      appointment={appt}
                      compact
                      onConfirm={onConfirm}
                      showActions={showActions}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * NowIndicator - A line showing the current time position within today's group.
 * Only renders if the current time is between 6am and 10pm.
 */
function NowIndicator() {
  const [, setTick] = useState(0);

  useEffect(() => {
    // Update every minute to keep the indicator current
    const interval = setInterval(() => setTick(t => t + 1), 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const now = new Date();
  const hour = now.getHours();

  // Only show during reasonable hours
  if (hour < 6 || hour > 22) return null;

  const timeStr = now.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  return (
    <div className="usw-now-indicator" aria-label={`Current time: ${timeStr}`}>
      <div className="usw-now-indicator__dot" />
      <div className="usw-now-indicator__line" />
      <span className="usw-now-indicator__label">{timeStr}</span>
    </div>
  );
}

export default UpcomingScheduleWidget;
