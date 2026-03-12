import React, { useCallback } from 'react';
import {
  normalizeUTCDate,
  formatTime,
  getMeetingModeIcon,
  getMeetingModeColor,
} from './calendarUtils';

const UpcomingAppointmentRow = React.memo(function UpcomingAppointmentRow({ appt, onAppointmentClick }) {
  const handleClick = useCallback(() => onAppointmentClick(appt), [appt, onAppointmentClick]);
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAppointmentClick(appt); }
  }, [appt, onAppointmentClick]);

  return (
    <div
      className="appointment-item compact clickable"
      style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      title="Click to edit appointment"
    >
      <div className="appointment-date-time">
        <span className="appointment-date">
          {new Date(normalizeUTCDate(appt.scheduled_start)).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        </span>
        <span className="appointment-time">
          {formatTime(appt.scheduled_start)}
        </span>
      </div>
      <div className="appointment-details">
        <div className="appointment-title">
          {getMeetingModeIcon(appt.meeting_mode)} {appt.attendee_name || appt.title || 'Appointment'}
        </div>
      </div>
    </div>
  );
});

const UpcomingAppointments = React.memo(function UpcomingAppointments({ appointments, onAppointmentClick }) {
  if (appointments.length === 0) return null;

  return (
    <div className="upcoming-section">
      <h4>Upcoming</h4>
      <div className="appointments-list">
        {appointments.map((appt) => (
          <UpcomingAppointmentRow
            key={appt.id}
            appt={appt}
            onAppointmentClick={onAppointmentClick}
          />
        ))}
      </div>
    </div>
  );
});

export default UpcomingAppointments;
