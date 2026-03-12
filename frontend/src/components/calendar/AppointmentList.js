import React, { useCallback } from 'react';
import {
  formatTime,
  formatDuration,
  getMeetingModeIcon,
  getMeetingModeColor,
  isToday,
} from './calendarUtils';

// Memoized individual appointment row to prevent re-render of entire list
const AppointmentRow = React.memo(function AppointmentRow({ appt, onAppointmentClick }) {
  const handleClick = useCallback(() => onAppointmentClick(appt), [appt, onAppointmentClick]);
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAppointmentClick(appt); }
  }, [appt, onAppointmentClick]);

  return (
    <div
      className="appointment-item clickable"
      style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
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
  );
});

const AppointmentList = React.memo(function AppointmentList({
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
            <AppointmentRow
              key={appt.id}
              appt={appt}
              onAppointmentClick={onAppointmentClick}
            />
          ))}
        </div>
      ) : (
        <div className="no-appointments">
          No appointments scheduled
        </div>
      )}
    </div>
  );
});

export default AppointmentList;
