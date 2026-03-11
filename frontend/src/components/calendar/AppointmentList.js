import React from 'react';
import {
  formatTime,
  formatDuration,
  getMeetingModeIcon,
  getMeetingModeColor,
  isToday,
} from './calendarUtils';

function AppointmentList({
  selectedDate,
  appointments,
  loading,
  onAppointmentClick,
}) {
  const dateLabel = isToday(selectedDate)
    ? 'Today'
    : selectedDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  return (
    <div className="appointments-section">
      <div className="appointments-header">
        <h3>{dateLabel}</h3>
      </div>

      {loading ? (
        <div className="loading-appointments">Loading...</div>
      ) : appointments.length > 0 ? (
        <div className="appointments-list">
          {appointments.map((appt) => (
            <div
              key={appt.id}
              className="appointment-item clickable"
              style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
              onClick={() => onAppointmentClick(appt)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAppointmentClick(appt); } }}
              role="button"
              tabIndex={0}
              title="Click to edit appointment"
            >
              <div className="appointment-time">
                {formatTime(appt.scheduled_start)}
              </div>
              <div className="appointment-details">
                <div className="appointment-title">
                  {getMeetingModeIcon(appt.meeting_mode)} {appt.title || 'Appointment'}
                </div>
                <div className="appointment-meta">
                  <span className="appointment-duration">
                    {formatDuration(appt.scheduled_start, appt.scheduled_end)}
                  </span>
                  <span className="appointment-client">
                    {appt.attendee_name || 'No client assigned'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="no-appointments">
          No appointments scheduled
        </div>
      )}
    </div>
  );
}

export default AppointmentList;
