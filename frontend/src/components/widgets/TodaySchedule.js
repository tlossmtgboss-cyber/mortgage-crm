import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { unifiedCalendarAPI } from '../../services/api';
import { normalizeUTCDate, formatTime } from '../calendar/calendarUtils';
import AppointmentCard from './AppointmentCard';
import WidgetSkeleton from './WidgetSkeleton';
import './UpcomingScheduleWidget.css';

/**
 * TodaySchedule - Today-only view of the schedule widget.
 *
 * Features:
 *   - Shows only today's appointments
 *   - Progress indicator (completed / upcoming / total)
 *   - Next appointment countdown timer
 *   - Compact format for dashboard embedding
 *
 * Props:
 *   onConfirm    - Callback when a user confirms an appointment
 *   showActions   - Whether to show quick action buttons (default: true)
 */
function TodaySchedule({ onConfirm, showActions = true }) {
  const navigate = useNavigate();
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchToday = useCallback(async () => {
    try {
      const today = new Date();
      const dateStr = today.toISOString().split('T')[0];

      const response = await unifiedCalendarAPI.getAll({
        start_date: dateStr,
        end_date: dateStr,
      });

      const events = (response.events || response || [])
        .filter(evt => {
          const status = (evt.status || '').toLowerCase();
          return status !== 'cancelled' && status !== 'no_show';
        })
        .sort((a, b) => {
          const aStart = new Date(normalizeUTCDate(a.scheduled_start || a.start_time || a.start_at));
          const bStart = new Date(normalizeUTCDate(b.scheduled_start || b.start_time || b.start_at));
          return aStart - bStart;
        });

      setAppointments(events);
      setError(null);
    } catch (err) {
      console.error('Failed to load today schedule:', err);
      setError('Unable to load schedule');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchToday();

    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchToday, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchToday]);

  // Split appointments into completed, current/upcoming
  const { completed, upcoming, nextAppointment } = useMemo(() => {
    const now = new Date();
    const done = [];
    const future = [];
    let next = null;

    appointments.forEach(appt => {
      const startStr = appt.scheduled_start || appt.start_time || appt.start_at;
      const endStr = appt.scheduled_end || appt.end_time || appt.end_at;
      const status = (appt.status || '').toLowerCase();

      if (status === 'completed') {
        done.push(appt);
        return;
      }

      const endTime = endStr
        ? new Date(normalizeUTCDate(endStr))
        : startStr
          ? new Date(new Date(normalizeUTCDate(startStr)).getTime() + 30 * 60000)
          : now;

      if (endTime < now) {
        done.push(appt);
      } else {
        future.push(appt);
        if (!next) next = appt;
      }
    });

    return { completed: done, upcoming: future, nextAppointment: next };
  }, [appointments]);

  const total = appointments.length;
  const completedCount = completed.length;
  const upcomingCount = upcoming.length;
  const progressPct = total > 0 ? Math.round((completedCount / total) * 100) : 0;

  const handleViewAll = useCallback(() => {
    navigate('/calendar');
  }, [navigate]);

  const todayLabel = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="today-schedule-widget">
      {/* Header */}
      <div className="usw-header">
        <div className="usw-header__left">
          <h3 className="usw-header__title">Today's Schedule</h3>
          <span className="usw-header__count">{todayLabel}</span>
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

      {/* Progress bar */}
      {!isLoading && !error && total > 0 && (
        <div className="ts-progress">
          <div className="ts-progress__bar">
            <div
              className="ts-progress__fill"
              style={{ width: `${progressPct}%` }}
              role="progressbar"
              aria-valuenow={progressPct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${completedCount} of ${total} appointments completed`}
            />
          </div>
          <div className="ts-progress__stats">
            <span className="ts-progress__stat ts-progress__stat--completed">
              {completedCount} completed
            </span>
            <span className="ts-progress__stat ts-progress__stat--upcoming">
              {upcomingCount} upcoming
            </span>
            <span className="ts-progress__stat ts-progress__stat--total">
              {total} total
            </span>
          </div>
        </div>
      )}

      {/* Next appointment countdown */}
      {!isLoading && !error && nextAppointment && (
        <NextAppointmentBanner appointment={nextAppointment} />
      )}

      {/* Content */}
      {isLoading ? (
        <WidgetSkeleton rows={3} />
      ) : error ? (
        <div className="usw-error">
          <span className="usw-error__text">{error}</span>
          <button className="usw-error__retry" onClick={fetchToday}>
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
          <p className="usw-empty__message">No appointments today</p>
          <p className="usw-empty__hint">
            Your day is clear. Time to prospect!
          </p>
          <button
            className="usw-empty__schedule-btn"
            onClick={() => navigate('/calendar')}
          >
            Schedule an appointment
          </button>
        </div>
      ) : (
        <div className="ts-appointments">
          {/* Completed section */}
          {completed.length > 0 && (
            <div className="ts-section ts-section--completed">
              <div className="ts-section__header">
                <span className="ts-section__label">Completed</span>
                <span className="ts-section__count">{completed.length}</span>
              </div>
              <div className="ts-section__list">
                {completed.map(appt => (
                  <AppointmentCard
                    key={appt.id}
                    appointment={appt}
                    compact
                    showActions={false}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Upcoming section */}
          {upcoming.length > 0 && (
            <div className="ts-section ts-section--upcoming">
              {completed.length > 0 && (
                <div className="ts-section__header">
                  <span className="ts-section__label">Upcoming</span>
                  <span className="ts-section__count">{upcoming.length}</span>
                </div>
              )}
              <div className="ts-section__list">
                {upcoming.map(appt => (
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
          )}
        </div>
      )}
    </div>
  );
}

/**
 * NextAppointmentBanner - Shows countdown to the next upcoming appointment.
 */
function NextAppointmentBanner({ appointment }) {
  const [countdown, setCountdown] = useState('');

  const startStr = appointment.scheduled_start || appointment.start_time || appointment.start_at;

  useEffect(() => {
    if (!startStr) return;

    const updateCountdown = () => {
      const now = new Date();
      const start = new Date(normalizeUTCDate(startStr));
      const diffMs = start - now;

      if (diffMs <= 0) {
        setCountdown('Now');
        return;
      }

      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const remainMins = diffMins % 60;

      if (diffHours > 0) {
        setCountdown(`${diffHours}h ${remainMins}m`);
      } else {
        setCountdown(`${remainMins}m`);
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 30 * 1000); // Update every 30s
    return () => clearInterval(interval);
  }, [startStr]);

  const attendeeName = appointment.attendee_name || appointment.title || 'Appointment';
  const timeStr = startStr ? formatTime(startStr) : '';

  return (
    <div className="ts-next-banner">
      <div className="ts-next-banner__icon" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M8 4V8L10.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="ts-next-banner__content">
        <span className="ts-next-banner__label">Next up</span>
        <span className="ts-next-banner__title">{attendeeName}</span>
      </div>
      <div className="ts-next-banner__countdown">
        <span className="ts-next-banner__time">{timeStr}</span>
        <span className="ts-next-banner__remaining">
          {countdown === 'Now' ? 'Starting now' : `in ${countdown}`}
        </span>
      </div>
    </div>
  );
}

export default TodaySchedule;
