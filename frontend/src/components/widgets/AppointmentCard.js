import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../calendar/StatusBadge';
import {
  normalizeUTCDate,
  formatTime,
  formatDuration,
  getMeetingModeIcon,
  getMeetingModeColor,
} from '../calendar/calendarUtils';

/**
 * AppointmentCard - Compact card for a single appointment in the schedule widget.
 *
 * Features:
 *   - Color stripe on left matching appointment type (phone/video/in-person)
 *   - Time, title, attendee, status badge
 *   - Quick action buttons: confirm, join meeting, view details
 *   - Click navigates to /calendar with the appointment date selected
 *
 * Props:
 *   appointment  - Appointment data object
 *   compact      - Boolean, renders a smaller variant (default: true)
 *   onConfirm    - Callback when confirm action is clicked
 *   onJoinMeeting - Callback when join meeting action is clicked
 *   showActions  - Whether to show quick action buttons (default: true)
 */
function AppointmentCard({
  appointment,
  compact = true,
  onConfirm,
  onJoinMeeting,
  showActions = true,
}) {
  const navigate = useNavigate();

  const appt = appointment;
  const startTime = appt.scheduled_start || appt.start_time || appt.start_at;
  const endTime = appt.scheduled_end || appt.end_time || appt.end_at;
  const meetingMode = appt.meeting_mode || 'OTHER';
  const stripeColor = getMeetingModeColor(meetingMode);
  const modeIcon = getMeetingModeIcon(meetingMode);
  const status = (appt.status || 'booked').toLowerCase();
  const attendeeName = appt.attendee_name || appt.title || 'Appointment';
  const title = appt.title || appt.appointment_type_name || attendeeName;
  const duration = startTime && endTime ? formatDuration(startTime, endTime) : null;

  // Determine if this is a video meeting that can be joined
  const isVideoMeeting = meetingMode.toUpperCase() === 'VIDEO';
  const meetingLink = appt.meeting_link || appt.video_link || null;
  const canJoinMeeting = isVideoMeeting && meetingLink;

  // Is the appointment within the next 15 minutes or currently active?
  const isJoinable = (() => {
    if (!canJoinMeeting || !startTime) return false;
    const now = new Date();
    const start = new Date(normalizeUTCDate(startTime));
    const end = endTime ? new Date(normalizeUTCDate(endTime)) : new Date(start.getTime() + 30 * 60000);
    const fifteenMinBefore = new Date(start.getTime() - 15 * 60000);
    return now >= fifteenMinBefore && now <= end;
  })();

  // Can confirm (only if status is 'booked')
  const canConfirm = status === 'booked' && onConfirm;

  const handleCardClick = useCallback(() => {
    if (!startTime) {
      navigate('/calendar');
      return;
    }
    const dateStr = new Date(normalizeUTCDate(startTime)).toISOString().split('T')[0];
    navigate(`/calendar?date=${dateStr}`);
  }, [navigate, startTime]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleCardClick();
    }
  }, [handleCardClick]);

  const handleConfirm = useCallback((e) => {
    e.stopPropagation();
    if (onConfirm) onConfirm(appt);
  }, [onConfirm, appt]);

  const handleJoin = useCallback((e) => {
    e.stopPropagation();
    if (onJoinMeeting) {
      onJoinMeeting(appt);
    } else if (meetingLink) {
      window.open(meetingLink, '_blank', 'noopener');
    }
  }, [onJoinMeeting, appt, meetingLink]);

  return (
    <div
      className={`appointment-card ${compact ? 'appointment-card--compact' : ''}`}
      style={{ '--stripe-color': stripeColor }}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      title="Click to view in calendar"
    >
      {/* Left color stripe */}
      <div className="appointment-card__stripe" aria-hidden="true" />

      {/* Time column */}
      <div className="appointment-card__time">
        <span className="appointment-card__time-text">
          {startTime ? formatTime(startTime) : '--:--'}
        </span>
        {duration && (
          <span className="appointment-card__duration">{duration}</span>
        )}
      </div>

      {/* Main content */}
      <div className="appointment-card__content">
        <div className="appointment-card__title-row">
          <span className="appointment-card__mode-icon" aria-label={meetingMode}>
            {modeIcon}
          </span>
          <span className="appointment-card__title">{title}</span>
        </div>
        {attendeeName && attendeeName !== title && (
          <span className="appointment-card__attendee">{attendeeName}</span>
        )}
      </div>

      {/* Status + Actions */}
      <div className="appointment-card__actions">
        <StatusBadge status={status} size="sm" />

        {showActions && (canConfirm || isJoinable) && (
          <div className="appointment-card__quick-actions">
            {canConfirm && (
              <button
                className="appointment-card__action-btn appointment-card__action-btn--confirm"
                onClick={handleConfirm}
                title="Confirm appointment"
                aria-label="Confirm appointment"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M3 8L6.5 11.5L13 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            )}
            {isJoinable && (
              <button
                className="appointment-card__action-btn appointment-card__action-btn--join"
                onClick={handleJoin}
                title="Join meeting"
                aria-label="Join meeting"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M6 4L12 8L6 12V4Z" fill="currentColor"/>
                </svg>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AppointmentCard;
