/**
 * CloseOnTimeCalendar Component
 *
 * Calendar visualization for Close-On-Time tracking with countdown,
 * business day calculation, and milestone deadlines.
 */

import React, { useState, useMemo, useCallback } from 'react';
import { useCloseCountdown, useCloseCalendar } from '../../hooks/usePortalData';
import { closeOnTimeApi } from '../../services/portalApi';
import './CloseOnTimeCalendar.css';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const URGENCY_CONFIG = {
  normal: {
    color: '#2D7A52',
    bgColor: '#d1fae5',
    label: 'On Track',
  },
  attention: {
    color: '#f59e0b',
    bgColor: '#fef3c7',
    label: 'Attention',
  },
  warning: {
    color: '#f97316',
    bgColor: '#ffedd5',
    label: 'Warning',
  },
  critical: {
    color: '#ef4444',
    bgColor: '#fee2e2',
    label: 'Critical',
  },
  overdue: {
    color: '#dc2626',
    bgColor: '#fecaca',
    label: 'Overdue',
  },
};

export default function CloseOnTimeCalendar({
  loanId,
  onMilestoneComplete,
  showCountdown = true,
  showCalendar = true,
  compact = false,
}) {
  const { data: countdownData, loading: countdownLoading, refetch: refetchCountdown } = useCloseCountdown(loanId);
  const { data: calendarData, loading: calendarLoading, refetch: refetchCalendar } = useCloseCalendar(loanId);
  const [completingMilestone, setCompletingMilestone] = useState(null);
  const [downloadingCalendar, setDownloadingCalendar] = useState(false);

  const handleDownloadCalendar = useCallback(async () => {
    if (!loanId) return;

    try {
      setDownloadingCalendar(true);

      // Get auth token from localStorage
      const token = getToken();

      const response = await fetch(`${API_BASE_URL}/api/portal/loans/${loanId}/milestone-calendar.ics`, {
        method: 'GET',
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to generate calendar' }));
        throw new Error(error.detail || 'Failed to generate calendar');
      }

      // Get the blob and create download link
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `loan-${loanId}-milestones.ics`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to download calendar:', err);
      toast.error(err.message || 'Failed to download milestone calendar');
    } finally {
      setDownloadingCalendar(false);
    }
  }, [loanId]);

  const handleCompleteMilestone = async (milestoneId) => {
    try {
      setCompletingMilestone(milestoneId);
      await closeOnTimeApi.completeCloseMilestone(milestoneId);
      refetchCountdown();
      refetchCalendar();
      if (onMilestoneComplete) {
        onMilestoneComplete(milestoneId);
      }
    } catch (err) {
      console.error('Failed to complete milestone:', err);
    } finally {
      setCompletingMilestone(null);
    }
  };

  if (countdownLoading && calendarLoading) {
    return <CalendarSkeleton compact={compact} />;
  }

  if (!countdownData?.has_schedule) {
    return (
      <div className="close-calendar-empty">
        <span className="empty-icon">📅</span>
        <p>No closing date scheduled</p>
        <span className="empty-hint">A closing schedule will be created once a target close date is set</span>
      </div>
    );
  }

  const urgency = URGENCY_CONFIG[countdownData.urgency] || URGENCY_CONFIG.normal;

  return (
    <div className={`close-on-time-calendar ${compact ? 'compact' : ''}`}>
      {/* Countdown Section */}
      {showCountdown && (
        <CountdownDisplay countdown={countdownData} urgency={urgency} compact={compact} />
      )}

      {/* Upcoming Deadlines */}
      {countdownData.upcoming_deadlines && countdownData.upcoming_deadlines.length > 0 && (
        <UpcomingDeadlines
          deadlines={countdownData.upcoming_deadlines}
          onComplete={handleCompleteMilestone}
          completingId={completingMilestone}
        />
      )}

      {/* Calendar View */}
      {showCalendar && calendarData && (
        <CalendarGrid
          weeks={calendarData.weeks}
          targetCloseDate={calendarData.target_close_date}
        />
      )}

      {/* Overdue Alert */}
      {countdownData.overdue_count > 0 && (
        <div className="overdue-alert">
          <span className="alert-icon">⚠️</span>
          <span>
            {countdownData.overdue_count} milestone{countdownData.overdue_count > 1 ? 's' : ''} overdue
          </span>
        </div>
      )}

      {/* Download Calendar Button */}
      {!compact && (
        <div className="calendar-actions">
          <button
            className="download-calendar-btn"
            onClick={handleDownloadCalendar}
            disabled={downloadingCalendar}
            title="Download milestones as calendar file (.ics)"
          >
            <span className="btn-icon">📅</span>
            <span className="btn-text">
              {downloadingCalendar ? 'Generating...' : 'Download Milestone Calendar'}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Countdown Display Component
 */
function CountdownDisplay({ countdown, urgency, compact }) {
  return (
    <div
      className={`countdown-section ${compact ? 'compact' : ''}`}
      style={{ borderColor: urgency.color }}
    >
      <div className="countdown-main">
        <div className="countdown-number">
          <span className="number" style={{ color: urgency.color }}>
            {countdown.business_days_remaining}
          </span>
          <span className="label">Business Days</span>
        </div>

        {!compact && (
          <div className="countdown-details">
            <div className="detail-item">
              <span className="detail-value">{countdown.calendar_days_remaining}</span>
              <span className="detail-label">Calendar Days</span>
            </div>
            <div className="detail-item">
              <span className="detail-value">{countdown.target_close_day}</span>
              <span className="detail-label">Close Day</span>
            </div>
          </div>
        )}
      </div>

      <div className="countdown-target">
        <span className="target-label">Target Close Date</span>
        <span className="target-date">{countdown.target_close_date_formatted}</span>
        <span
          className="urgency-badge"
          style={{ backgroundColor: urgency.bgColor, color: urgency.color }}
        >
          {urgency.label}
        </span>
      </div>

      {countdown.urgency_message && (
        <div
          className="urgency-message"
          style={{ backgroundColor: urgency.bgColor, color: urgency.color }}
        >
          {countdown.urgency_message}
        </div>
      )}
    </div>
  );
}

/**
 * Upcoming Deadlines Component
 */
function UpcomingDeadlines({ deadlines, onComplete, completingId }) {
  return (
    <div className="upcoming-deadlines">
      <h4>Upcoming Deadlines</h4>
      <ul className="deadlines-list">
        {deadlines.map((deadline) => (
          <li
            key={deadline.id}
            className={`deadline-item ${deadline.is_completed ? 'completed' : ''} ${deadline.is_overdue ? 'overdue' : ''}`}
          >
            <div className="deadline-info">
              <span className="deadline-name">{deadline.name}</span>
              <span className="deadline-date">
                {formatDeadlineDate(deadline.deadline_date)}
                {deadline.business_days_before_close > 0 && (
                  <span className="days-before">
                    ({deadline.business_days_before_close} days before close)
                  </span>
                )}
              </span>
            </div>

            {!deadline.is_completed && (
              <button
                className="complete-btn"
                onClick={() => onComplete(deadline.id)}
                disabled={completingId === deadline.id}
              >
                {completingId === deadline.id ? 'Completing...' : 'Complete'}
              </button>
            )}

            {deadline.is_completed && (
              <span className="completed-badge">✓ Done</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Calendar Grid Component
 */
function CalendarGrid({ weeks, targetCloseDate }) {
  const today = new Date().toISOString().split('T')[0];

  return (
    <div className="calendar-grid">
      {/* Day Headers */}
      <div className="calendar-header">
        {DAY_NAMES.map((day) => (
          <div key={day} className="day-header">
            {day}
          </div>
        ))}
      </div>

      {/* Calendar Weeks */}
      <div className="calendar-body">
        {weeks.map((week, weekIndex) => (
          <div key={weekIndex} className="calendar-week">
            {week.map((day) => (
              <div
                key={day.date}
                className={`calendar-day ${getDayClasses(day, today)}`}
              >
                <span className="day-number">{day.day}</span>

                {day.is_holiday && (
                  <span className="holiday-indicator" title={day.holiday_name}>
                    🏖
                  </span>
                )}

                {day.is_close_date && (
                  <span className="close-indicator" title="Closing Day">
                    🎯
                  </span>
                )}

                {day.milestones && day.milestones.length > 0 && (
                  <div className="day-milestones">
                    {day.milestones.map((m, i) => (
                      <span
                        key={i}
                        className={`milestone-dot ${m.completed ? 'completed' : ''}`}
                        title={m.name}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="calendar-legend">
        <span className="legend-item">
          <span className="legend-dot business-day" /> Business Day
        </span>
        <span className="legend-item">
          <span className="legend-dot weekend" /> Weekend
        </span>
        <span className="legend-item">
          <span className="legend-dot holiday" /> Holiday
        </span>
        <span className="legend-item">
          <span className="legend-dot milestone" /> Milestone Due
        </span>
      </div>
    </div>
  );
}

/**
 * Get CSS classes for a calendar day
 */
function getDayClasses(day, today) {
  const classes = [];

  if (day.is_today) classes.push('today');
  if (day.is_weekend) classes.push('weekend');
  if (day.is_holiday) classes.push('holiday');
  if (!day.is_business_day) classes.push('non-business');
  if (day.is_close_date) classes.push('close-date');
  if (day.date < today) classes.push('past');
  if (day.milestones && day.milestones.length > 0) classes.push('has-milestones');

  return classes.join(' ');
}

/**
 * Format deadline date for display
 */
function formatDeadlineDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Skeleton Loader
 */
function CalendarSkeleton({ compact }) {
  return (
    <div className={`close-on-time-calendar skeleton ${compact ? 'compact' : ''}`}>
      <div className="countdown-section skeleton">
        <div className="skeleton-number" />
        <div className="skeleton-text" />
      </div>
      <div className="calendar-grid skeleton">
        <div className="calendar-header">
          {DAY_NAMES.map((day) => (
            <div key={day} className="day-header skeleton-text" />
          ))}
        </div>
        <div className="calendar-body">
          {[1, 2, 3, 4].map((week) => (
            <div key={week} className="calendar-week">
              {[1, 2, 3, 4, 5, 6, 7].map((day) => (
                <div key={day} className="calendar-day skeleton-day" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Compact Countdown Widget
 */
export function CloseCountdownWidget({ loanId }) {
  const { data, loading } = useCloseCountdown(loanId);

  if (loading) {
    return (
      <div className="countdown-widget skeleton">
        <div className="skeleton-circle" />
        <div className="skeleton-text" />
      </div>
    );
  }

  if (!data?.has_schedule) {
    return null;
  }

  const urgency = URGENCY_CONFIG[data.urgency] || URGENCY_CONFIG.normal;

  return (
    <div
      className="countdown-widget"
      style={{ borderColor: urgency.color }}
    >
      <div
        className="widget-number"
        style={{ color: urgency.color }}
      >
        {data.business_days_remaining}
      </div>
      <div className="widget-label">
        <span className="days-text">Business Days</span>
        <span className="close-date">{data.target_close_date_formatted}</span>
      </div>
      <span
        className="widget-badge"
        style={{ backgroundColor: urgency.bgColor, color: urgency.color }}
      >
        {urgency.label}
      </span>
    </div>
  );
}
