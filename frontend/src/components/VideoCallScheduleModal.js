import React, { useState, useEffect, useCallback } from 'react';
import './VideoCallScheduleModal.css';
import api from '../services/api';
// v2.0 - Fixed "Failed to fetch" error - build 20251215-1140

const VideoCallScheduleModal = ({ isOpen, onClose, borrower, onStartVideoCall }) => {
  // Initialize weekStart to today - will be reset when modal opens
  const [weekStart, setWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [teamMembers, setTeamMembers] = useState([]);
  const [selectedTeamMember, setSelectedTeamMember] = useState('');
  const [startingCall, setStartingCall] = useState(false);
  const [teamMemberWorkHours, setTeamMemberWorkHours] = useState({
    work_hours_start: '09:00',
    work_hours_end: '17:00',
    work_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
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

  // Get day name from date
  const getDayName = (date) => {
    return date.toLocaleDateString('en-US', { weekday: 'long' }).toLowerCase();
  };

  // Fetch team member's work hours
  const fetchTeamMemberWorkHours = useCallback(async (memberId) => {
    if (!memberId) return;

    try {
      const { data } = await api.get(`/api/v1/team/members/${memberId}/work-hours`);
      setTeamMemberWorkHours({
        work_hours_start: data.work_hours_start || '09:00',
        work_hours_end: data.work_hours_end || '17:00',
        work_days: data.work_days || ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
      });
    } catch (error) {
      // Keep default work hours
    }
  }, []);

  // Fetch team members assigned to this borrower
  const fetchTeamMembers = useCallback(async () => {
    if (!borrower?.id) return;

    try {
      // Fetch all team members directly (more reliable)
      const { data } = await api.get('/api/v1/team/members');
      const members = data.team_members || data || [];
      setTeamMembers(members);

      // Auto-select first team member if available
      if (members.length > 0) {
        const firstMemberId = members[0].member_id || members[0].user_id || members[0].id || '';
        setSelectedTeamMember(String(firstMemberId));
        if (firstMemberId) {
          fetchTeamMemberWorkHours(firstMemberId);
        }
      }
    } catch (error) {
      console.error('Error fetching team members:', error);
    }
  }, [borrower?.id, fetchTeamMemberWorkHours]);

  // Reset calendar to today whenever modal opens
  // This is a separate effect to ensure it always runs when isOpen changes
  useEffect(() => {
    if (isOpen) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      // Always start from today when modal opens
      setWeekStart(today);
      setSelectedDate(today);
    }
  }, [isOpen]);

  // Initialize other state and fetch team members when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedTime('');
      setSelectedTeamMember('');
      setError(null);
      setSuccess(false);

      fetchTeamMembers();
    }
  }, [isOpen, fetchTeamMembers]);

  // Generate slots based on team member's work hours
  const generateSlotsFromWorkHours = useCallback(() => {
    if (!selectedDate) return;

    const dayName = getDayName(selectedDate);

    if (!teamMemberWorkHours.work_days.includes(dayName)) {
      setAvailableSlots([]);
      setSelectedTime('');
      return;
    }

    const slots = [];
    const baseDate = new Date(selectedDate);

    const startHour = parseInt((teamMemberWorkHours.work_hours_start || '09:00').split(':')[0], 10);
    const endHour = parseInt((teamMemberWorkHours.work_hours_end || '17:00').split(':')[0], 10);

    for (let hour = startHour; hour < endHour; hour++) {
      for (let min = 0; min < 60; min += 30) {
        const slotDate = new Date(baseDate);
        slotDate.setHours(hour, min, 0, 0);
        slots.push({
          start_time: slotDate.toISOString(),
          display: slotDate.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        });
      }
    }

    setAvailableSlots(slots);
    if (slots.length > 0) {
      setSelectedTime(slots[0].start_time);
    } else {
      setSelectedTime('');
    }
  }, [selectedDate, teamMemberWorkHours]);

  // Fetch available slots when date changes
  const fetchSlots = useCallback(async () => {
    if (!selectedDate) return;

    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const { data } = await api.get(
        `/api/v1/scheduler/public/book/demo/slots?date=${dateStr}&appointment_type_id=1&duration_minutes=30`
      );

      const slots = (data.available_slots || []).map(slot => ({
        ...slot,
        start_time: slot.start,
        display: formatTime(slot.start)
      }));
      setAvailableSlots(slots);

      if (slots.length > 0) {
        setSelectedTime(slots[0].start_time);
      } else {
        setSelectedTime('');
      }
    } catch (err) {
      console.error('Error fetching slots:', err);
      generateSlotsFromWorkHours();
    }
  }, [selectedDate, generateSlotsFromWorkHours]);

  useEffect(() => {
    if (selectedDate) {
      fetchSlots();
    }
  }, [selectedDate, fetchSlots]);

  useEffect(() => {
    if (selectedDate && selectedTeamMember) {
      generateSlotsFromWorkHours();
    }
  }, [teamMemberWorkHours, selectedDate, selectedTeamMember, generateSlotsFromWorkHours]);

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

  // Start video call now
  const handleStartVideoNow = async () => {
    setStartingCall(true);
    setError(null);

    try {
      // Create instant video call room using the meetings API
      const borrowerName = borrower?.name || `${borrower?.first_name || ''} ${borrower?.last_name || ''}`.trim() || 'Client';
      const { data } = await api.post('/api/v1/meetings/rooms', {
        room_name: `Call with ${borrowerName}`,
        room_description: `Video call with ${borrowerName}`,
        provider: 'internal',
        duration_minutes: 30,
        waiting_room_enabled: false,
        recording_enabled: true,
        transcription_enabled: true,
        ai_assistant_enabled: true,
        password_protected: false,
        max_participants: 10,
        lead_id: borrower?.id || null,
        meeting_type: 'client_call',
      });

      // Open video call in new window using the room code
      // Backend returns: { success: true, meeting: { room_code: "..." } }
      const roomCode = data.meeting?.room_code || data.room_code || data.room?.room_code;
      if (roomCode) {
        const roomUrl = `${window.location.origin}/meeting/${roomCode}`;
        window.open(roomUrl, '_blank', 'width=1200,height=800');
        if (onStartVideoCall) {
          onStartVideoCall({ room_url: roomUrl, room_code: roomCode, ...data });
        }
        onClose();
      } else {
        throw new Error('No room code returned from server');
      }
    } catch (err) {
      console.error('Error starting video call:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to start video call. Please try again.');
    } finally {
      setStartingCall(false);
    }
  };

  // Schedule video call
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

    setSubmitting(true);
    setError(null);

    const selectedMember = teamMembers.find(m =>
      (m.member_id || m.user_id || m.id)?.toString() === selectedTeamMember?.toString()
    );
    const teamMemberName = selectedMember?.name ||
      `${selectedMember?.first_name || ''} ${selectedMember?.last_name || ''}`.trim() ||
      'Team Member';

    try {
      await api.post('/api/v1/scheduler/public/book/demo/confirm', {
        appointment_type_id: 1,
        start_time: selectedTime,
        duration_minutes: 30,
        attendee_name: borrower.name || `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim(),
        attendee_email: borrower.email || borrower.borrower_email,
        attendee_phone: borrower.phone || borrower.borrower_phone || '',
        notes: `Video Call scheduled\nAppointment with: ${teamMemberName}`,
        meeting_mode: 'video',
        team_member_id: selectedTeamMember,
        team_member_name: teamMemberName
      });

      setSuccess(true);

      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (err) {
      console.error('Error scheduling video call:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to schedule video call. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="video-schedule-modal-overlay" onClick={onClose}>
      <div className="video-schedule-modal" onClick={(e) => e.stopPropagation()}>
        <button className="video-schedule-modal-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {success ? (
          <div className="video-schedule-success">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2>Video Call Scheduled!</h2>
            <p>A confirmation email has been sent to {borrower?.email || borrower?.borrower_email}</p>
          </div>
        ) : (
          <>
            {/* Start Video Call Now Button */}
            <div className="video-start-now-section">
              <button
                className="video-start-now-btn"
                onClick={handleStartVideoNow}
                disabled={startingCall}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="5" width="14" height="14" rx="2" />
                  <path d="M22 7l-6 4 6 4V7z" />
                </svg>
                {startingCall ? 'Starting...' : 'Start Video Call Now'}
              </button>
            </div>

            <div className="video-schedule-divider">
              <span>or schedule for later</span>
            </div>

            <h2>Pick a date</h2>

            {error && <div className="video-schedule-error">{error}</div>}

            {/* Week Picker */}
            <div className="video-schedule-week-picker">
              <button
                className="video-schedule-week-nav"
                onClick={prevWeek}
                disabled={isPast(weekDates[0])}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              <div className="video-schedule-week-dates">
                {weekDates.slice(0, 5).map((date, idx) => {
                  const dayName = getDayName(date);
                  const isWorkDay = teamMemberWorkHours.work_days.includes(dayName);
                  const disabled = isPast(date) || (selectedTeamMember && !isWorkDay);
                  const selected = selectedDate && date.toDateString() === selectedDate.toDateString();

                  return (
                    <button
                      key={idx}
                      className={`video-schedule-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isToday(date) ? 'today' : ''}`}
                      onClick={() => !disabled && setSelectedDate(date)}
                      disabled={disabled}
                      title={!isWorkDay && selectedTeamMember ? 'Team member not available' : ''}
                    >
                      <span className="video-schedule-day-name">{formatDayName(date)}</span>
                      <span className="video-schedule-day-number">{formatDayNumber(date)}</span>
                      <span className="video-schedule-month">{formatMonth(date)}</span>
                    </button>
                  );
                })}
              </div>

              <button className="video-schedule-week-nav" onClick={nextWeek}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>

            {/* Time Picker */}
            <div className="video-schedule-time-section">
              <h3>Pick a time</h3>
              <p className="video-schedule-time-hint">Choose your preferred time. Reschedule anytime.</p>

              <div className="video-schedule-time-dropdown-wrapper">
                <select
                  className="video-schedule-time-dropdown"
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                >
                  {availableSlots.length === 0 ? (
                    <option value="">No times available</option>
                  ) : (
                    availableSlots.map((slot, idx) => (
                      <option key={idx} value={slot.start_time}>
                        {slot.display}
                      </option>
                    ))
                  )}
                </select>
                <svg className="video-schedule-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>

              {/* Meeting Mode Indicator */}
              <div className="video-schedule-mode-indicator">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="5" width="14" height="14" rx="2" />
                  <path d="M22 7l-6 4 6 4V7z" />
                </svg>
                Video call
              </div>
            </div>

            {/* Team Member Selection */}
            <div className="video-schedule-team-section">
              <h3>Appointment with</h3>
              <div className="video-schedule-team-dropdown-wrapper">
                <select
                  className="video-schedule-team-dropdown"
                  value={selectedTeamMember}
                  onChange={(e) => setSelectedTeamMember(e.target.value)}
                >
                  <option value="">Select team member...</option>
                  {teamMembers.map((member, idx) => {
                    const memberId = member.member_id || member.user_id || member.id;
                    const memberName = member.name || `${member.first_name || ''} ${member.last_name || ''}`.trim();
                    const memberRole = member.role || '';
                    return (
                      <option key={idx} value={memberId}>
                        {memberName}{memberRole ? ` - ${memberRole}` : ''}
                      </option>
                    );
                  })}
                </select>
                <svg className="video-schedule-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>
            </div>

            {/* Borrower Info */}
            <div className="video-schedule-borrower-info">
              <p>
                <strong>Scheduling for:</strong> {borrower?.name || `${borrower?.first_name || ''} ${borrower?.last_name || ''}`.trim() || 'Unknown'}
              </p>
              <p>
                <strong>Email:</strong> {borrower?.email || borrower?.borrower_email || 'Not available'}
              </p>
            </div>

            {/* Submit Button */}
            <button
              className="video-schedule-submit-btn"
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

export default VideoCallScheduleModal;
