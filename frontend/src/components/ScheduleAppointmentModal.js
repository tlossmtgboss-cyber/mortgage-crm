import React, { useState, useEffect, useCallback, useRef } from 'react';
import './ScheduleAppointmentModal.css';
import useFocusTrap from '../hooks/useFocusTrap';
import { getToken } from '../utils/tokenStore';
// v4.0 - Server-side availability, focus trap, phone validation, improved UX 20260309

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Phone validation: accepts formats like (555) 123-4567, 555-123-4567, +15551234567, etc.
const PHONE_REGEX = /^[+]?[\d\s().-]{7,20}$/;
const validatePhone = (phone) => {
  if (!phone) return true; // phone is optional
  return PHONE_REGEX.test(phone.trim());
};

const ScheduleAppointmentModal = ({ isOpen, onClose, onSuccess, borrower }) => {
  // Initialize weekStart to null - will be set to today when modal opens
  const [weekStart, setWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [meetingMode, setMeetingMode] = useState('phone');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [emailSent, setEmailSent] = useState(null); // Track if email was actually sent
  const [emailError, setEmailError] = useState(null); // Store email error message
  const [teamMembers, setTeamMembers] = useState([]);
  const [teamMembersError, setTeamMembersError] = useState(null);
  const [selectedTeamMember, setSelectedTeamMember] = useState('');
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [teamMemberWorkHours, setTeamMemberWorkHours] = useState({
    work_hours_start: '09:00',
    work_hours_end: '17:00',
    work_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
  });

  const modalHeadingId = 'schedule-modal-heading';

  // Ref for scrolling to today's date
  const weekDatesRef = useRef(null);

  // Focus trap: traps Tab/Shift+Tab within the modal, Escape to close
  useFocusTrap(isOpen, {
    modalSelector: '.schedule-modal',
    onEscape: onClose,
  });

  // Generate week dates starting from weekStart
  const getWeekDates = useCallback(() => {
    const dates = [];
    const start = new Date(weekStart);
    start.setHours(0, 0, 0, 0);

    for (let i = 0; i < 7; i++) {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      dates.push(date);
    }
    return dates;
  }, [weekStart]);

  const weekDates = getWeekDates();

  // Format helpers
  const formatDayName = (date) => {
    return date.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase();
  };

  const formatDayNumber = (date) => {
    return date.getDate();
  };

  const formatMonth = (date) => {
    return date.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  const isToday = (date) => {
    const today = new Date();
    return date.toDateString() === today.toDateString();
  };

  const isPast = (date) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date < today;
  };

  // Fetch team member's work hours
  const fetchTeamMemberWorkHours = useCallback(async (memberId) => {
    if (!memberId) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/team/members/${memberId}/work-hours`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTeamMemberWorkHours({
          work_hours_start: data.work_hours_start || '09:00',
          work_hours_end: data.work_hours_end || '17:00',
          work_days: data.work_days || ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        });
      }
    } catch {
      // Keep default work hours
    }
  }, []);

  // Fetch team members assigned to this borrower
  const fetchTeamMembers = useCallback(async () => {
    if (!borrower?.id) return;

    setTeamMembersError(null);

    try {
      // Fetch all team members directly (more reliable)
      const allMembersResponse = await fetch(`${API_BASE}/api/v1/team/members`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });

      if (allMembersResponse.ok) {
        const data = await allMembersResponse.json();
        const members = data.team_members || data || [];
        setTeamMembers(members);

        // Auto-select first team member (usually current user) if available
        if (members.length > 0) {
          const firstMemberId = members[0].member_id || members[0].user_id || members[0].id || '';
          setSelectedTeamMember(String(firstMemberId));
          // Fetch work hours for first team member
          if (firstMemberId) {
            fetchTeamMemberWorkHours(firstMemberId);
          }
        }
      } else {
        setTeamMembersError('Could not load team members. Please select manually or try again.');
      }
    } catch {
      setTeamMembersError('Failed to connect to server. Team member list unavailable.');
    }
  }, [borrower?.id, fetchTeamMemberWorkHours]);

  // Note: Escape key handling is now provided by useFocusTrap above.

  // Reset calendar to today whenever modal opens
  // This is a separate effect to ensure it always runs when isOpen changes
  useEffect(() => {
    if (isOpen) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      // Always start from today when modal opens
      setWeekStart(today);
      setSelectedDate(today);

      // Scroll week dates container to the start after render
      setTimeout(() => {
        if (weekDatesRef.current) {
          weekDatesRef.current.scrollLeft = 0;
        }
      }, 50);
    }
  }, [isOpen]);

  // Get day name from date
  const getDayName = (date) => {
    return date.toLocaleDateString('en-US', { weekday: 'long' }).toLowerCase();
  };

  // Fetch appointment types to get duration_minutes
  const fetchAppointmentTypes = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        const types = data.appointment_types || [];
        // Use the first active appointment type's duration, or default to 30
        if (types.length > 0) {
          const firstType = types[0];
          const duration = firstType.default_duration_minutes || 30;
          setDurationMinutes(duration);
        }
      }
    } catch {
      // Keep default duration
    }
  }, []);

  // Initialize other state and fetch team members when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedTime('');
      setSelectedTeamMember('');
      setError(null);
      setSuccess(false);
      setEmailSent(null);
      setTeamMembersError(null);
      setDurationMinutes(30);

      // Fetch team members and appointment types
      fetchTeamMembers();
      fetchAppointmentTypes();
    }
  }, [isOpen, fetchTeamMembers, fetchAppointmentTypes]);

  // Client-side fallback: generate slots from work hours (used only when API fails)
  const generateSlotsFromWorkHours = useCallback((duration) => {
    if (!selectedDate) return;

    const dayName = getDayName(selectedDate);
    const slotDuration = duration || durationMinutes;

    // Check if this day is a work day
    if (!teamMemberWorkHours.work_days.includes(dayName)) {
      setAvailableSlots([]);
      setSelectedTime('');
      return;
    }

    const slots = [];
    const baseDate = new Date(selectedDate);

    // Parse work hours (format: "09:00", "17:00")
    const startHour = parseInt(teamMemberWorkHours.work_hours_start.split(':')[0], 10);
    const startMin = parseInt(teamMemberWorkHours.work_hours_start.split(':')[1] || '0', 10);
    const endHour = parseInt(teamMemberWorkHours.work_hours_end.split(':')[0], 10);
    const endMin = parseInt(teamMemberWorkHours.work_hours_end.split(':')[1] || '0', 10);

    let currentMinutes = startHour * 60 + startMin;
    const endMinutes = endHour * 60 + endMin;

    while (currentMinutes + slotDuration <= endMinutes) {
      const hour = Math.floor(currentMinutes / 60);
      const min = currentMinutes % 60;
      const slotDate = new Date(baseDate);
      slotDate.setHours(hour, min, 0, 0);

      // Skip slots in the past
      if (slotDate > new Date()) {
        slots.push({
          start_time: slotDate.toISOString(),
          display: slotDate.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        });
      }

      currentMinutes += 30; // Advance by 30 min intervals for selection granularity
    }

    setAvailableSlots(slots);
    if (slots.length > 0) {
      setSelectedTime(slots[0].start_time);
    } else {
      setSelectedTime('');
    }
  }, [selectedDate, teamMemberWorkHours, durationMinutes]);

  // Fetch available slots from server (checks existing appointments, blocked times, PTO)
  const fetchSlotsFromServer = useCallback(async () => {
    if (!selectedDate) return;

    setLoadingSlots(true);

    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const userIds = selectedTeamMember ? [parseInt(selectedTeamMember)] : [];

      const response = await fetch(`${API_BASE}/api/v1/scheduler/available-slots`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          start_date: dateStr,
          end_date: dateStr,
          duration_minutes: durationMinutes,
          user_ids: userIds.length > 0 ? userIds : undefined,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const serverSlots = (data.available_slots || []).map((slot) => {
          const startStr = slot.start || slot.start_time;
          const slotDate = new Date(startStr);
          return {
            start_time: slotDate.toISOString(),
            display: slotDate.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }),
          };
        });

        setAvailableSlots(serverSlots);
        if (serverSlots.length > 0) {
          setSelectedTime(serverSlots[0].start_time);
        } else {
          setSelectedTime('');
        }
      } else {
        // API returned error - fall back to client-side generation
        generateSlotsFromWorkHours();
      }
    } catch {
      // Network error - fall back to client-side generation
      generateSlotsFromWorkHours();
    } finally {
      setLoadingSlots(false);
    }
  }, [selectedDate, selectedTeamMember, durationMinutes, generateSlotsFromWorkHours]);

  // Re-fetch slots when date or team member changes
  useEffect(() => {
    if (selectedDate) {
      fetchSlotsFromServer();
    }
  }, [selectedDate, selectedTeamMember, fetchSlotsFromServer]);

  // Fetch work hours when team member selection changes
  useEffect(() => {
    if (selectedTeamMember) {
      fetchTeamMemberWorkHours(selectedTeamMember);
    }
  }, [selectedTeamMember, fetchTeamMemberWorkHours]);

  // Navigate weeks
  const prevWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() - 7);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (newStart >= today) {
      setWeekStart(newStart);
    }
  };

  const nextWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() + 7);
    setWeekStart(newStart);
  };

  // Handle submit
  const handleSubmit = async () => {
    if (!selectedDate || !selectedTime) {
      setError('Please select a date and time.');
      return;
    }

    if (!borrower?.email && !borrower?.borrower_email) {
      setError('Borrower email is required to send confirmation.');
      return;
    }

    if (!selectedTeamMember) {
      setError('Please select a team member for the appointment.');
      return;
    }

    // Validate phone number if present
    const attendeePhone = borrower.phone || borrower.borrower_phone || '';
    if (attendeePhone && !validatePhone(attendeePhone)) {
      setError('Borrower phone number format is invalid. Expected format: (555) 123-4567 or similar.');
      return;
    }

    setSubmitting(true);
    setError(null);

    // Get selected team member details
    const selectedMember = teamMembers.find(m =>
      (m.member_id || m.user_id || m.id)?.toString() === selectedTeamMember?.toString()
    );
    const teamMemberName = selectedMember?.full_name || selectedMember?.name ||
      `${selectedMember?.first_name || ''} ${selectedMember?.last_name || ''}`.trim() ||
      'Team Member';

    try {
      // Use authenticated endpoint to ensure appointment is linked to current user
      const attendeeName = borrower.name || `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim();
      const appointmentUrl = `${API_BASE}/api/v1/scheduler/appointments`;
      const token = getToken();

      // Determine if borrower is a lead or loan object and set IDs correctly
      // Leads have: id (lead id), no loan_number field
      // Loans have: id (loan id), loan_number field
      const isLoan = Boolean(borrower.loan_number);
      const leadId = isLoan ? (borrower.lead_id || null) : (borrower.id || null);
      const loanId = isLoan ? (borrower.id || null) : null;

      const requestBody = {
        title: `${meetingMode === 'video' ? 'Video Call' : 'Phone Call'} with ${attendeeName}`,
        description: `Appointment with: ${teamMemberName}`,
        scheduled_start: selectedTime,
        duration_minutes: durationMinutes,
        meeting_mode: meetingMode,
        attendee_name: attendeeName,
        attendee_email: borrower.email || borrower.borrower_email,
        attendee_phone: attendeePhone,
        lead_id: leadId,
        loan_id: loanId,
        assigned_user_id: parseInt(selectedTeamMember) || null
      };

      const response = await fetch(appointmentUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(requestBody)
      });

      // Try to parse response
      let result;
      try {
        const responseText = await response.text();
        result = JSON.parse(responseText);
      } catch (parseErr) {
        throw new Error(`Server returned invalid response (status ${response.status})`);
      }

      if (!response.ok) {
        throw new Error(result.detail || `Server error: ${response.status}`);
      }

      setSuccess(true);
      setEmailSent(result.email_sent === true);
      setEmailError(result.email_error || null);

      // Call onSuccess callback if provided (to refresh calendar/data)
      if (onSuccess) {
        onSuccess();
      }

      // Close modal after 5 seconds (gives user time to read email status)
      setTimeout(() => {
        onClose();
      }, 5000);
    } catch (err) {
      // Provide more specific error messages
      let errorMessage = 'Failed to schedule appointment. Please try again.';
      if (err.name === 'TypeError' && err.message === 'Failed to fetch') {
        errorMessage = 'Unable to connect to server. Please check your internet connection or try again later.';
      } else if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={onClose}>
      <div className="schedule-modal" role="dialog" aria-modal="true" aria-labelledby={modalHeadingId} onClick={(e) => e.stopPropagation()}>
        <button className="schedule-modal-close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {success ? (
          <div className="schedule-success">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 id={modalHeadingId}>Appointment Scheduled!</h2>
            {emailSent ? (
              <p style={{ color: '#2D7A52' }}>A confirmation email has been sent to {borrower?.email || borrower?.borrower_email}</p>
            ) : (
              <div style={{ color: '#f59e0b' }}>
                <p>Appointment created, but email could not be sent.</p>
                {emailError && <p style={{ fontSize: '12px', marginTop: '4px' }}>Error: {emailError}</p>}
                <p style={{ marginTop: '8px' }}>Please manually notify the contact at {borrower?.email || borrower?.borrower_email}</p>
              </div>
            )}
            <button
              className="schedule-submit-btn"
              onClick={onClose}
              style={{ marginTop: '16px' }}
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <h2 id={modalHeadingId}>Pick a date</h2>

            {error && <div className="schedule-error">{error}</div>}

            {/* Week Picker */}
            <div className="schedule-week-picker">
              <button
                className="schedule-week-nav"
                onClick={prevWeek}
                disabled={isPast(weekDates[0])}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              <div className="schedule-week-dates" ref={weekDatesRef}>
                {weekDates.map((date, idx) => {
                  const dayName = getDayName(date);
                  const isWorkDay = teamMemberWorkHours.work_days.includes(dayName);
                  const disabled = isPast(date) || (selectedTeamMember && !isWorkDay);
                  const selected = selectedDate && date.toDateString() === selectedDate.toDateString();

                  return (
                    <button
                      key={idx}
                      className={`schedule-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isToday(date) ? 'today' : ''} ${!isWorkDay && selectedTeamMember ? 'non-work-day' : ''}`}
                      onClick={() => !disabled && setSelectedDate(date)}
                      disabled={disabled}
                      title={!isWorkDay && selectedTeamMember ? 'Team member not available' : ''}
                    >
                      <span className="schedule-day-name">{formatDayName(date)}</span>
                      <span className="schedule-day-number">{formatDayNumber(date)}</span>
                      <span className="schedule-month">{formatMonth(date)}</span>
                    </button>
                  );
                })}
              </div>

              <button className="schedule-week-nav" onClick={nextWeek}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>

            {/* Time Picker */}
            <div className="schedule-time-section">
              <h3>Pick a time</h3>
              <p className="schedule-time-hint">
                {durationMinutes !== 30
                  ? `${durationMinutes}-minute slots. Choose your preferred time. Reschedule anytime.`
                  : 'Choose your preferred time. Reschedule anytime.'}
              </p>

              <div className="schedule-time-dropdown-wrapper">
                <select
                  className="schedule-time-dropdown"
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                  disabled={loadingSlots}
                >
                  {loadingSlots ? (
                    <option value="">Loading available times...</option>
                  ) : availableSlots.length === 0 ? (
                    <option value="">No times available</option>
                  ) : (
                    availableSlots.map((slot, idx) => (
                      <option key={idx} value={slot.start_time}>
                        {slot.display}
                      </option>
                    ))
                  )}
                </select>
                <svg className="schedule-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>

              {/* Meeting Mode Toggle */}
              <div className="schedule-mode-toggle">
                <button
                  className={`schedule-mode-btn ${meetingMode === 'phone' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('phone')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  Phone call
                </button>
                <button
                  className={`schedule-mode-btn ${meetingMode === 'video' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('video')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="5" width="14" height="14" rx="2" />
                    <path d="M22 7l-6 4 6 4V7z" />
                  </svg>
                  Video call
                </button>
              </div>
            </div>

            {/* Team Member Selection */}
            <div className="schedule-team-section">
              <h3>Appointment with</h3>
              {teamMembersError && (
                <div className="schedule-error" style={{ marginBottom: '8px', fontSize: '13px' }}>
                  {teamMembersError}
                </div>
              )}
              <div className="schedule-team-dropdown-wrapper">
                <select
                  className="schedule-team-dropdown"
                  value={selectedTeamMember}
                  onChange={(e) => setSelectedTeamMember(e.target.value)}
                >
                  <option value="">Select team member...</option>
                  {teamMembers.filter(member => member != null).map((member, idx) => {
                    const memberId = member.member_id || member.user_id || member.id;
                    const memberName = member?.full_name || member?.name || `${member?.first_name || ''} ${member?.last_name || ''}`.trim() || 'Unknown';
                    const memberRole = member?.role || member?.title || '';
                    return (
                      <option key={idx} value={memberId}>
                        {memberName}{memberRole ? ` - ${memberRole}` : ''}
                      </option>
                    );
                  })}
                </select>
                <svg className="schedule-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>
            </div>

            {/* Borrower Info */}
            <div className="schedule-borrower-info">
              <p>
                <strong>Scheduling for:</strong> {borrower?.name || `${borrower?.first_name || ''} ${borrower?.last_name || ''}`.trim() || 'Unknown'}
              </p>
              <p>
                <strong>Email:</strong> {borrower?.email || borrower?.borrower_email || 'Not available'}
              </p>
            </div>

            {/* Submit Button */}
            <button
              className="schedule-submit-btn"
              onClick={handleSubmit}
              disabled={submitting || !selectedDate || !selectedTime || !selectedTeamMember}
            >
              {submitting ? 'Scheduling...' : 'Submit'}
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default ScheduleAppointmentModal;
