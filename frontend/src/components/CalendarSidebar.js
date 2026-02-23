import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI, crmCalendarAPI } from '../services/api';
import './CalendarSidebar.css';
import { toast } from '../utils/toast';

// v1.5 - Fixed timezone handling for appointments
console.log('[CalendarSidebar] v1.5 loaded - fixed timezone handling');

// Helper to normalize UTC date strings from backend
// Backend returns UTC times without Z suffix, so we need to add it
const normalizeUTCDate = (dateString) => {
  if (!dateString) return dateString;
  // If no timezone indicator, assume UTC and add Z
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    return dateString + 'Z';
  }
  return dateString;
};

function CalendarSidebar({ leadId, loanId, children }) {
  console.log('[CalendarSidebar] Render with leadId:', leadId, 'loanId:', loanId);
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem('calendarSidebarCollapsed');
      // Default to collapsed (true) if no preference saved
      return stored === null ? true : stored === 'true';
    } catch { return true; }
  });
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [appointments, setAppointments] = useState([]);
  const [crmEvents, setCrmEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [emailData, setEmailData] = useState(null);

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev;
      try { localStorage.setItem('calendarSidebarCollapsed', String(next)); } catch {}
      return next;
    });
  };

  // Edit appointment state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState(null);
  const [saving, setSaving] = useState(false);

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const dayNames = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  useEffect(() => {
    loadAppointments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDate, leadId, loanId]);

  // Helper to format date as YYYY-MM-DD for API
  const formatDateForAPI = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const loadAppointments = async () => {
    try {
      setLoading(true);
      // Get appointments for the current month
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);

      // Format dates as YYYY-MM-DD for backend
      const startDateStr = formatDateForAPI(startDate);
      const endDateStr = formatDateForAPI(endDate);

      console.log('[CalendarSidebar] loadAppointments called');
      console.log('[CalendarSidebar] Date range:', startDateStr, 'to', endDateStr);
      console.log('[CalendarSidebar] Filters - lead_id:', leadId, 'loan_id:', loanId);

      // Fetch both scheduler appointments and CRM calendar events
      const [appointmentsData, crmEventsData] = await Promise.all([
        schedulerAPI.getAppointments({
          start_date: startDateStr,
          end_date: endDateStr,
          lead_id: leadId || undefined,
          loan_id: loanId || undefined,
        }).catch(err => {
          console.error('[CalendarSidebar] Failed to load scheduler appointments:', err);
          return [];
        }),
        crmCalendarAPI.getAll({
          start_date: startDate.toISOString(),
          end_date: endDate.toISOString(),
        }).catch(err => {
          console.error('[CalendarSidebar] Failed to load CRM events:', err);
          return [];
        })
      ]);

      console.log('[CalendarSidebar] Appointments count:', appointmentsData?.length || 0);
      console.log('[CalendarSidebar] CRM events count:', crmEventsData?.length || 0);

      // Filter out cancelled appointments and sort by date
      const filteredAppointments = (appointmentsData || [])
        .filter(appt => appt.status !== 'CANCELLED')
        .sort((a, b) => new Date(normalizeUTCDate(a.scheduled_start)) - new Date(normalizeUTCDate(b.scheduled_start)));

      // Filter out cancelled CRM events and sort by date (API returns start_at)
      const filteredCrmEvents = (crmEventsData || [])
        .filter(event => event.status !== 'cancelled')
        .sort((a, b) => new Date(a.start_at || a.start_time) - new Date(b.start_at || b.start_time));

      setAppointments(filteredAppointments);
      setCrmEvents(filteredCrmEvents);
    } catch (error) {
      console.error('[CalendarSidebar] Failed to load appointments:', error);
      setAppointments([]);
      setCrmEvents([]);
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
    // Check scheduler appointments
    const hasAppt = appointments.some(appt => {
      const apptDate = new Date(normalizeUTCDate(appt.scheduled_start));
      return apptDate.toDateString() === date.toDateString();
    });
    // Check CRM calendar events (API returns start_at)
    const hasCrmEvent = crmEvents.some(event => {
      const eventDate = new Date(event.start_at || event.start_time);
      return eventDate.toDateString() === date.toDateString();
    });
    return hasAppt || hasCrmEvent;
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
    // Get scheduler appointments for selected date
    const appts = appointments.filter(appt => {
      const apptDate = new Date(normalizeUTCDate(appt.scheduled_start));
      return apptDate.toDateString() === selectedDate.toDateString();
    }).map(appt => ({
      ...appt,
      sourceType: 'scheduler',
      displayTime: appt.scheduled_start
    }));

    // Get CRM calendar events for selected date
    // API returns start_at/end_at fields
    const events = crmEvents.filter(event => {
      const eventDate = new Date(event.start_at || event.start_time);
      return eventDate.toDateString() === selectedDate.toDateString();
    }).map(event => ({
      id: `crm-${event.id}`,
      title: event.title || event.subject || 'CRM Event',
      scheduled_start: event.start_at || event.start_time,
      scheduled_end: event.end_at || event.end_time,
      attendee_name: event.attendees?.length > 0 ? event.attendees[0].name : null,
      meeting_mode: event.event_type === 'video_call' ? 'VIDEO' :
                    event.event_type === 'phone_call' ? 'PHONE' :
                    event.event_type === 'meeting' ? 'IN_PERSON' : 'OTHER',
      sourceType: 'crm_calendar',
      crmEventId: event.id,
      sync_status: event.sync_status,
      displayTime: event.start_at || event.start_time
    }));

    // Combine and sort by time
    return [...appts, ...events].sort((a, b) =>
      new Date(a.displayTime) - new Date(b.displayTime)
    );
  };

  const formatTime = (dateString) => {
    const date = new Date(normalizeUTCDate(dateString));
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatDuration = (start, end) => {
    const startDate = new Date(normalizeUTCDate(start));
    const endDate = new Date(normalizeUTCDate(end));
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

    // Get upcoming scheduler appointments
    const upcomingAppts = appointments
      .filter(appt => new Date(normalizeUTCDate(appt.scheduled_start)) >= now)
      .map(appt => ({
        ...appt,
        sourceType: 'scheduler',
        displayTime: appt.scheduled_start
      }));

    // Get upcoming CRM calendar events (API returns start_at/end_at)
    const upcomingCrmEvents = crmEvents
      .filter(event => new Date(event.start_at || event.start_time) >= now)
      .map(event => ({
        id: `crm-${event.id}`,
        title: event.title || event.subject || 'CRM Event',
        scheduled_start: event.start_at || event.start_time,
        scheduled_end: event.end_at || event.end_time,
        attendee_name: event.attendees?.length > 0 ? event.attendees[0].name : null,
        meeting_mode: event.event_type === 'video_call' ? 'VIDEO' :
                      event.event_type === 'phone_call' ? 'PHONE' :
                      event.event_type === 'meeting' ? 'IN_PERSON' : 'OTHER',
        sourceType: 'crm_calendar',
        crmEventId: event.id,
        sync_status: event.sync_status,
        displayTime: event.start_at || event.start_time
      }));

    // Combine, sort by time, and take first 5
    return [...upcomingAppts, ...upcomingCrmEvents]
      .sort((a, b) => new Date(a.displayTime) - new Date(b.displayTime))
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
    // Set drop effect to copy
    e.dataTransfer.dropEffect = 'copy';
    setIsDragOver(true);
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[CalendarSidebar] Drag enter - data types:', e.dataTransfer.types);
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

    console.log('[CalendarSidebar] Drop event received');
    console.log('[CalendarSidebar] Data transfer types:', Array.from(e.dataTransfer.types));
    console.log('[CalendarSidebar] Files:', e.dataTransfer.files?.length || 0);

    const emailInfo = parseEmailData(e.dataTransfer);
    console.log('[CalendarSidebar] Parsed email info:', emailInfo);

    // Default date to selected date
    const defaultDate = selectedDate.toISOString().split('T')[0];

    // Pre-fill form with email data
    setAppointmentForm(prev => ({
      ...prev,
      title: emailInfo.subject ? `Follow-up: ${emailInfo.subject}` : 'New Appointment',
      attendee_name: emailInfo.from || '',
      attendee_email: emailInfo.fromEmail || '',
      date: defaultDate,
      notes: emailInfo.body ? `From email:\n${emailInfo.body.substring(0, 500)}` : ''
    }));

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

    // Validate required fields
    if (!appointmentForm.attendee_name?.trim()) {
      toast.error('Please enter a contact name');
      return;
    }
    if (!appointmentForm.attendee_email?.trim()) {
      toast.error('Please enter a contact email');
      return;
    }
    if (!appointmentForm.date) {
      toast.error('Please select a date');
      return;
    }

    try {
      const startDateTime = new Date(`${appointmentForm.date}T${appointmentForm.time}`);

      const appointmentData = {
        contact_name: appointmentForm.attendee_name.trim(),
        contact_email: appointmentForm.attendee_email.trim(),
        appointment_time: startDateTime.toISOString(),
        duration_minutes: parseInt(appointmentForm.duration),
        appointment_type: appointmentForm.title || 'consultation',
        notes: appointmentForm.notes || null,
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
      const detail = error.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', ')
        : detail || error.message;
      toast.error('Failed to create appointment: ' + msg);
    }
  };

  // Handle clicking on an appointment to edit
  const handleAppointmentClick = (appt) => {
    const startDate = new Date(normalizeUTCDate(appt.scheduled_start));
    const endDate = new Date(normalizeUTCDate(appt.scheduled_end));
    const durationMs = endDate - startDate;
    const durationMins = Math.round(durationMs / 60000);

    setEditingAppointment({
      id: appt.id,
      title: appt.title || '',
      attendee_name: appt.attendee_name || '',
      attendee_email: appt.attendee_email || '',
      date: startDate.toISOString().split('T')[0],
      time: startDate.toTimeString().slice(0, 5),
      duration: String(durationMins),
      meeting_mode: appt.meeting_mode || 'PHONE',
      notes: appt.attendee_notes || '',
      status: appt.status || 'SCHEDULED',
      lead_id: appt.lead_id,
      loan_id: appt.loan_id
    });
    setShowEditModal(true);
  };

  // Handle saving edited appointment
  const handleSaveAppointment = async (e) => {
    e.preventDefault();
    if (!editingAppointment) return;

    setSaving(true);
    try {
      const startDateTime = new Date(`${editingAppointment.date}T${editingAppointment.time}`);
      const endDateTime = new Date(startDateTime.getTime() + parseInt(editingAppointment.duration) * 60000);

      const updateData = {
        title: editingAppointment.title,
        attendee_name: editingAppointment.attendee_name,
        attendee_email: editingAppointment.attendee_email,
        scheduled_start: startDateTime.toISOString(),
        scheduled_end: endDateTime.toISOString(),
        meeting_mode: editingAppointment.meeting_mode,
        attendee_notes: editingAppointment.notes,
        status: editingAppointment.status
      };

      await schedulerAPI.updateAppointment(editingAppointment.id, updateData);

      setShowEditModal(false);
      setEditingAppointment(null);
      loadAppointments();
    } catch (error) {
      console.error('Failed to update appointment:', error);
      toast.error('Failed to update appointment: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSaving(false);
    }
  };

  // Handle cancelling appointment
  const handleCancelAppointment = async () => {
    if (!editingAppointment || !window.confirm('Are you sure you want to cancel this appointment?')) return;

    setSaving(true);
    try {
      // Use the dedicated cancel endpoint instead of update with status
      await schedulerAPI.cancelAppointment(editingAppointment.id, 'Cancelled by user');

      setShowEditModal(false);
      setEditingAppointment(null);
      loadAppointments();
    } catch (error) {
      console.error('Failed to cancel appointment:', error);
      toast.error('Failed to cancel appointment: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSaving(false);
    }
  };

  const days = getDaysInMonth();
  const selectedDateAppointments = getAppointmentsForSelectedDate();
  const upcomingAppointments = getUpcomingAppointments();

  if (collapsed) {
    return (
      <div className="calendar-sidebar calendar-sidebar--collapsed" onClick={toggleCollapsed} title="Show calendar">
        <div className="calendar-sidebar__expand-tab">
          <span className="calendar-sidebar__expand-icon">&lsaquo;</span>
          <span className="calendar-sidebar__expand-label">Calendar</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`calendar-sidebar ${isDragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Collapse toggle */}
      <button className="calendar-sidebar__collapse-btn" onClick={toggleCollapsed} title="Hide calendar">
        Hide calendar &rsaquo;
      </button>

      {/* Quick Actions (passed as children) */}
      {children}

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
                className="appointment-item clickable"
                style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
                onClick={() => handleAppointmentClick(appt)}
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

        {/* Upcoming Appointments */}
        {upcomingAppointments.length > 0 && !isToday(selectedDate) && (
          <div className="upcoming-section">
            <h4>Upcoming</h4>
            <div className="appointments-list">
              {upcomingAppointments.map((appt) => (
                <div
                  key={appt.id}
                  className="appointment-item compact clickable"
                  style={{ borderLeftColor: getMeetingModeColor(appt.meeting_mode) }}
                  onClick={() => handleAppointmentClick(appt)}
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
        )}
      </div>

      {/* View Full Calendar Link */}
      <div className="calendar-footer">
        <button
          className="refresh-calendar-btn"
          onClick={() => {
            console.log('[CalendarSidebar] Manual refresh triggered');
            loadAppointments();
          }}
          style={{ marginRight: '10px', padding: '8px 12px', fontSize: '12px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer' }}
        >
          ↻ Refresh
        </button>
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

      {/* Edit Appointment Modal */}
      {showEditModal && editingAppointment && (
        <div className="appointment-modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="appointment-modal" onClick={(e) => e.stopPropagation()}>
            <div className="appointment-modal-header">
              <h3>Edit Appointment</h3>
              <button className="close-btn" onClick={() => setShowEditModal(false)}>×</button>
            </div>

            <form onSubmit={handleSaveAppointment}>
              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={editingAppointment.title}
                  onChange={(e) => setEditingAppointment({...editingAppointment, title: e.target.value})}
                  placeholder="Appointment title"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Client Name *</label>
                  <input
                    type="text"
                    value={editingAppointment.attendee_name}
                    onChange={(e) => setEditingAppointment({...editingAppointment, attendee_name: e.target.value})}
                    placeholder="Client name"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Client Email</label>
                  <input
                    type="email"
                    value={editingAppointment.attendee_email}
                    onChange={(e) => setEditingAppointment({...editingAppointment, attendee_email: e.target.value})}
                    placeholder="email@example.com"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date</label>
                  <input
                    type="date"
                    value={editingAppointment.date}
                    onChange={(e) => setEditingAppointment({...editingAppointment, date: e.target.value})}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Time</label>
                  <input
                    type="time"
                    value={editingAppointment.time}
                    onChange={(e) => setEditingAppointment({...editingAppointment, time: e.target.value})}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Duration</label>
                  <select
                    value={editingAppointment.duration}
                    onChange={(e) => setEditingAppointment({...editingAppointment, duration: e.target.value})}
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
                    value={editingAppointment.meeting_mode}
                    onChange={(e) => setEditingAppointment({...editingAppointment, meeting_mode: e.target.value})}
                  >
                    <option value="PHONE">📞 Phone Call</option>
                    <option value="VIDEO">📹 Video Call</option>
                    <option value="IN_PERSON">👤 In Person</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Status</label>
                <select
                  value={editingAppointment.status}
                  onChange={(e) => setEditingAppointment({...editingAppointment, status: e.target.value})}
                >
                  <option value="SCHEDULED">Scheduled</option>
                  <option value="CONFIRMED">Confirmed</option>
                  <option value="COMPLETED">Completed</option>
                  <option value="NO_SHOW">No Show</option>
                </select>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={editingAppointment.notes}
                  onChange={(e) => setEditingAppointment({...editingAppointment, notes: e.target.value})}
                  placeholder="Additional notes..."
                  rows="3"
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-danger"
                  onClick={handleCancelAppointment}
                  disabled={saving}
                >
                  Cancel Appointment
                </button>
                <div className="modal-actions-right">
                  <button type="button" className="btn-cancel" onClick={() => setShowEditModal(false)}>
                    Close
                  </button>
                  <button type="submit" className="btn-create" disabled={saving}>
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default CalendarSidebar;
