import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI } from '../services/api';
import './CalendarSidebar.css';

function CalendarSidebar({ leadId, loanId }) {
  const navigate = useNavigate();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const dayNames = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  useEffect(() => {
    loadAppointments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDate, leadId, loanId]);

  const loadAppointments = async () => {
    try {
      setLoading(true);
      // Get appointments for the current month
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0, 23, 59, 59);

      const data = await schedulerAPI.getAppointments({
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
        lead_id: leadId || undefined,
        loan_id: loanId || undefined,
      });

      // Filter out cancelled appointments and sort by date
      const filteredAppointments = (data || [])
        .filter(appt => appt.status !== 'CANCELLED')
        .sort((a, b) => new Date(a.scheduled_start) - new Date(b.scheduled_start));

      setAppointments(filteredAppointments);
    } catch (error) {
      console.error('Failed to load appointments:', error);
      setAppointments([]);
    } finally {
      setLoading(false);
    }
  };

  const goToPreviousMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
  };

  const goToNextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  };

  const goToToday = () => {
    const today = new Date();
    setCurrentDate(today);
    setSelectedDate(today);
  };

  const getDaysInMonth = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();

    const days = [];

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startingDay; i++) {
      days.push({ day: null, date: null });
    }

    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      days.push({
        day,
        date: new Date(year, month, day)
      });
    }

    return days;
  };

  const hasAppointmentsOnDate = (date) => {
    if (!date) return false;
    return appointments.some(appt => {
      const apptDate = new Date(appt.scheduled_start);
      return apptDate.toDateString() === date.toDateString();
    });
  };

  const isToday = (date) => {
    if (!date) return false;
    const today = new Date();
    return date.toDateString() === today.toDateString();
  };

  const isSelected = (date) => {
    if (!date) return false;
    return date.toDateString() === selectedDate.toDateString();
  };

  const handleDateClick = (date) => {
    if (date) {
      setSelectedDate(date);
    }
  };

  const getAppointmentsForSelectedDate = () => {
    return appointments.filter(appt => {
      const apptDate = new Date(appt.scheduled_start);
      return apptDate.toDateString() === selectedDate.toDateString();
    });
  };

  const formatTime = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatDuration = (start, end) => {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const diffMs = endDate - startDate;
    const diffMins = Math.round(diffMs / 60000);

    if (diffMins >= 60) {
      const hours = Math.floor(diffMins / 60);
      const mins = diffMins % 60;
      return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    }
    return `${diffMins}m`;
  };

  const getMeetingModeIcon = (mode) => {
    switch (mode) {
      case 'VIDEO':
        return '📹';
      case 'PHONE':
        return '📞';
      case 'IN_PERSON':
        return '👤';
      default:
        return '📅';
    }
  };

  const getMeetingModeColor = (mode) => {
    switch (mode) {
      case 'VIDEO':
        return '#2563eb'; // Blue
      case 'PHONE':
        return '#059669'; // Green
      case 'IN_PERSON':
        return '#dc2626'; // Red
      default:
        return '#6b7280'; // Gray
    }
  };

  const getUpcomingAppointments = () => {
    const now = new Date();
    return appointments
      .filter(appt => new Date(appt.scheduled_start) >= now)
      .slice(0, 5);
  };

  const days = getDaysInMonth();
  const selectedDateAppointments = getAppointmentsForSelectedDate();
  const upcomingAppointments = getUpcomingAppointments();

  return (
    <div className="calendar-sidebar">
      {/* Mini Calendar */}
      <div className="mini-calendar">
        <div className="calendar-header">
          <button className="nav-btn" onClick={goToPreviousMonth}>&lt;</button>
          <span className="month-year" onClick={goToToday} title="Click to go to today">
            {monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}
          </span>
          <button className="nav-btn" onClick={goToNextMonth}>&gt;</button>
        </div>

        <div className="calendar-grid">
          {/* Day names header */}
          {dayNames.map((day, index) => (
            <div key={index} className="day-name">{day}</div>
          ))}

          {/* Calendar days */}
          {days.map((item, index) => (
            <div
              key={index}
              className={`calendar-day ${!item.day ? 'empty' : ''} ${isToday(item.date) ? 'today' : ''} ${isSelected(item.date) ? 'selected' : ''} ${hasAppointmentsOnDate(item.date) ? 'has-events' : ''}`}
              onClick={() => handleDateClick(item.date)}
            >
              {item.day && (
                <>
                  <span className="day-number">{item.day}</span>
                  {hasAppointmentsOnDate(item.date) && (
                    <span className="event-dot"></span>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Appointments List */}
      <div className="appointments-section">
        <div className="appointments-header">
          <h3>
            {isToday(selectedDate)
              ? 'Today'
              : selectedDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          </h3>
        </div>

        {loading ? (
          <div className="loading-appointments">Loading...</div>
        ) : selectedDateAppointments.length > 0 ? (
          <div className="appointments-list">
            {selectedDateAppointments.map((appt) => (
              <div
                key={appt.id}
                className="appointment-item"
                style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
              >
                <div className="appointment-time">
                  {formatTime(appt.scheduled_start)}
                </div>
                <div className="appointment-details">
                  <div className="appointment-title">
                    {getMeetingModeIcon(appt.meeting_mode)} {appt.title || `Meeting with ${appt.attendee_name || 'Client'}`}
                  </div>
                  <div className="appointment-meta">
                    <span className="appointment-duration">
                      {formatDuration(appt.scheduled_start, appt.scheduled_end)}
                    </span>
                    {appt.attendee_name && (
                      <span className="appointment-attendee">
                        {appt.attendee_name}
                      </span>
                    )}
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

        {/* Upcoming Appointments */}
        {upcomingAppointments.length > 0 && !isToday(selectedDate) && (
          <div className="upcoming-section">
            <h4>Upcoming</h4>
            <div className="appointments-list">
              {upcomingAppointments.map((appt) => (
                <div
                  key={appt.id}
                  className="appointment-item compact"
                  style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
                >
                  <div className="appointment-date-time">
                    <span className="appointment-date">
                      {new Date(appt.scheduled_start).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </span>
                    <span className="appointment-time">
                      {formatTime(appt.scheduled_start)}
                    </span>
                  </div>
                  <div className="appointment-details">
                    <div className="appointment-title">
                      {getMeetingModeIcon(appt.meeting_mode)} {appt.title || appt.attendee_name || 'Meeting'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* View Full Calendar Link */}
      <div className="calendar-footer">
        <button
          className="view-calendar-btn"
          onClick={() => navigate('/calendar')}
        >
          View Full Calendar
        </button>
      </div>
    </div>
  );
}

export default CalendarSidebar;
