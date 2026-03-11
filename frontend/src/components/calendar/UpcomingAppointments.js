import React from 'react';
import {
  normalizeUTCDate,
  formatTime,
  getMeetingModeIcon,
  getMeetingModeColor,
} from './calendarUtils';

function UpcomingAppointments({ appointments, onAppointmentClick }) {
  if (appointments.length === 0) return null;

  return (
    <div className="upcoming-section">
      <h4>Upcoming</h4>
      <div className="appointments-list">
        {appointments.map((appt) => (
          <div
            key={appt.id}
            className="appointment-item compact clickable"
            style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
            onClick={() => onAppointmentClick(appt)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAppointmentClick(appt); } }}
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
        ))}
      </div>
    </div>
  );
}

export default UpcomingAppointments;
