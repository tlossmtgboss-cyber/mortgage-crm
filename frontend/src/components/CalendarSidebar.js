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
  const [isDragOver, setIsDragOver] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [emailData, setEmailData] = useState(null);

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

  // Parse email data from various drag formats
  const parseEmailData = (dataTransfer) => {
    const emailInfo = {
      subject: '',
      from: '',
      fromEmail: '',
      body: '',
      date: new Date()
    };

    // Try to get text/plain data (most common from Outlook drag)
    const textData = dataTransfer.getData('text/plain');
    const htmlData = dataTransfer.getData('text/html');
    const uriList = dataTransfer.getData('text/uri-list');

    console.log('Drag data types:', dataTransfer.types);
    console.log('Text data:', textData);
    console.log('HTML data:', htmlData?.substring(0, 500));

    if (textData) {
      // Parse text data - could be email content or subject line
      const lines = textData.split('\n').filter(l => l.trim());

      // Try to extract email patterns
      const emailMatch = textData.match(/([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/);
      if (emailMatch) {
        emailInfo.fromEmail = emailMatch[1];
      }

      // Try to extract "From:" line
      const fromMatch = textData.match(/From:\s*([^\n<]+)(?:<([^>]+)>)?/i);
      if (fromMatch) {
        emailInfo.from = fromMatch[1].trim();
        if (fromMatch[2]) {
          emailInfo.fromEmail = fromMatch[2].trim();
        }
      }

      // Try to extract "Subject:" line
      const subjectMatch = textData.match(/Subject:\s*([^\n]+)/i);
      if (subjectMatch) {
        emailInfo.subject = subjectMatch[1].trim();
      }

      // If no subject found, use first line as subject
      if (!emailInfo.subject && lines.length > 0) {
        emailInfo.subject = lines[0].substring(0, 100);
      }

      // Use remaining content as body
      emailInfo.body = textData;
    }

    // Try to parse HTML data for more structured info
    if (htmlData) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlData, 'text/html');

      // Try to find email subject in title or headers
      const title = doc.querySelector('title');
      if (title && !emailInfo.subject) {
        emailInfo.subject = title.textContent;
      }

      // Try to find sender info
      const fromElement = doc.querySelector('[class*="from"], [class*="sender"]');
      if (fromElement && !emailInfo.from) {
        emailInfo.from = fromElement.textContent.trim();
      }
    }

    // Try to get Outlook-specific data
    const outlookData = dataTransfer.getData('application/x-moz-file') ||
                       dataTransfer.getData('text/x-moz-url') ||
                       dataTransfer.getData('application/vnd.ms-outlook');

    if (outlookData) {
      console.log('Outlook data:', outlookData);
    }

    // Check for files (dragged .msg or .eml files)
    if (dataTransfer.files && dataTransfer.files.length > 0) {
      const file = dataTransfer.files[0];
      console.log('Dropped file:', file.name, file.type);

      if (file.name.endsWith('.msg') || file.name.endsWith('.eml')) {
        emailInfo.subject = file.name.replace(/\.(msg|eml)$/i, '');
        emailInfo.fileName = file.name;
        emailInfo.file = file;
      }
    }

    return emailInfo;
  };

  // Drag and drop handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set dragOver to false if leaving the sidebar entirely
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const emailInfo = parseEmailData(e.dataTransfer);
    console.log('Parsed email info:', emailInfo);

    // Open the appointment modal with extracted email data
    setEmailData(emailInfo);
    setShowAppointmentModal(true);
  };

  // Appointment creation from email
  const [appointmentForm, setAppointmentForm] = useState({
    title: '',
    attendee_name: '',
    attendee_email: '',
    date: '',
    time: '10:00',
    duration: '30',
    meeting_mode: 'PHONE',
    notes: ''
  });

  useEffect(() => {
    if (emailData) {
      // Pre-fill form with email data
      const defaultDate = selectedDate.toISOString().split('T')[0];
      setAppointmentForm(prev => ({
        ...prev,
        title: emailData.subject ? `Follow-up: ${emailData.subject}` : 'Follow-up from email',
        attendee_name: emailData.from || '',
        attendee_email: emailData.fromEmail || '',
        date: defaultDate,
        notes: emailData.body ? `Original email:\n${emailData.body.substring(0, 500)}...` : ''
      }));
    }
  }, [emailData, selectedDate]);

  const handleCreateAppointment = async (e) => {
    e.preventDefault();

    try {
      const startDateTime = new Date(`${appointmentForm.date}T${appointmentForm.time}`);
      const endDateTime = new Date(startDateTime.getTime() + parseInt(appointmentForm.duration) * 60000);

      const appointmentData = {
        title: appointmentForm.title,
        attendee_name: appointmentForm.attendee_name,
        attendee_email: appointmentForm.attendee_email,
        scheduled_start: startDateTime.toISOString(),
        scheduled_end: endDateTime.toISOString(),
        meeting_mode: appointmentForm.meeting_mode,
        attendee_notes: appointmentForm.notes,
        lead_id: leadId || null,
        loan_id: loanId || null,
      };

      await schedulerAPI.createAppointment(appointmentData);

      // Reset and close
      setShowAppointmentModal(false);
      setEmailData(null);
      setAppointmentForm({
        title: '',
        attendee_name: '',
        attendee_email: '',
        date: '',
        time: '10:00',
        duration: '30',
        meeting_mode: 'PHONE',
        notes: ''
      });

      // Reload appointments
      loadAppointments();
    } catch (error) {
      console.error('Failed to create appointment:', error);
      alert('Failed to create appointment: ' + (error.response?.data?.detail || error.message));
    }
  };

  const days = getDaysInMonth();
  const selectedDateAppointments = getAppointmentsForSelectedDate();
  const upcomingAppointments = getUpcomingAppointments();

  return (
    <div
      className={`calendar-sidebar ${isDragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragOver && (
        <div className="drag-overlay">
          <div className="drag-overlay-content">
            <span className="drag-icon">📧</span>
            <span className="drag-text">Drop email to create appointment</span>
          </div>
        </div>
      )}

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

      {/* Drop zone hint */}
      <div className="drop-zone-hint">
        <span>📧 Drag email here to schedule</span>
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

      {/* Appointment Creation Modal */}
      {showAppointmentModal && (
        <div className="appointment-modal-overlay" onClick={() => setShowAppointmentModal(false)}>
          <div className="appointment-modal" onClick={(e) => e.stopPropagation()}>
            <div className="appointment-modal-header">
              <h3>Create Appointment from Email</h3>
              <button className="close-btn" onClick={() => setShowAppointmentModal(false)}>×</button>
            </div>

            <form onSubmit={handleCreateAppointment}>
              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={appointmentForm.title}
                  onChange={(e) => setAppointmentForm({...appointmentForm, title: e.target.value})}
                  placeholder="Appointment title"
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Contact Name</label>
                  <input
                    type="text"
                    value={appointmentForm.attendee_name}
                    onChange={(e) => setAppointmentForm({...appointmentForm, attendee_name: e.target.value})}
                    placeholder="Name"
                  />
                </div>
                <div className="form-group">
                  <label>Contact Email</label>
                  <input
                    type="email"
                    value={appointmentForm.attendee_email}
                    onChange={(e) => setAppointmentForm({...appointmentForm, attendee_email: e.target.value})}
                    placeholder="email@example.com"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date</label>
                  <input
                    type="date"
                    value={appointmentForm.date}
                    onChange={(e) => setAppointmentForm({...appointmentForm, date: e.target.value})}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Time</label>
                  <input
                    type="time"
                    value={appointmentForm.time}
                    onChange={(e) => setAppointmentForm({...appointmentForm, time: e.target.value})}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Duration</label>
                  <select
                    value={appointmentForm.duration}
                    onChange={(e) => setAppointmentForm({...appointmentForm, duration: e.target.value})}
                  >
                    <option value="15">15 minutes</option>
                    <option value="30">30 minutes</option>
                    <option value="45">45 minutes</option>
                    <option value="60">1 hour</option>
                    <option value="90">1.5 hours</option>
                    <option value="120">2 hours</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Meeting Type</label>
                  <select
                    value={appointmentForm.meeting_mode}
                    onChange={(e) => setAppointmentForm({...appointmentForm, meeting_mode: e.target.value})}
                  >
                    <option value="PHONE">📞 Phone Call</option>
                    <option value="VIDEO">📹 Video Call</option>
                    <option value="IN_PERSON">👤 In Person</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={appointmentForm.notes}
                  onChange={(e) => setAppointmentForm({...appointmentForm, notes: e.target.value})}
                  placeholder="Additional notes..."
                  rows="3"
                />
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={() => setShowAppointmentModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-create">
                  Create Appointment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default CalendarSidebar;
