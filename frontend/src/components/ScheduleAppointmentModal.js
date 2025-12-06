import React, { useState, useEffect, useCallback } from 'react';
import './ScheduleAppointmentModal.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const ScheduleAppointmentModal = ({ isOpen, onClose, borrower }) => {
  const [weekStart, setWeekStart] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [meetingMode, setMeetingMode] = useState('phone');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

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

  // Initialize selected date when modal opens
  useEffect(() => {
    if (isOpen) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      // Start week from today
      setWeekStart(today);
      setSelectedDate(today);
      setSelectedTime('');
      setError(null);
      setSuccess(false);
    }
  }, [isOpen]);

  // Fetch available slots when date changes
  const fetchSlots = useCallback(async () => {
    if (!selectedDate) return;

    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/book/demo/slots?date=${dateStr}&appointment_type_id=1&duration_minutes=30`
      );

      if (response.ok) {
        const data = await response.json();
        const slots = (data.available_slots || []).map(slot => ({
          ...slot,
          start_time: slot.start,
          display: formatTime(slot.start)
        }));
        setAvailableSlots(slots);

        // Auto-select first available time
        if (slots.length > 0) {
          setSelectedTime(slots[0].start_time);
        } else {
          setSelectedTime('');
        }
      }
    } catch (err) {
      console.error('Error fetching slots:', err);
      // Generate default slots if API fails
      generateDefaultSlots();
    }
  }, [selectedDate]);

  // Generate default slots (9am-5pm, 30 min intervals)
  const generateDefaultSlots = () => {
    if (!selectedDate) return;

    const slots = [];
    const baseDate = new Date(selectedDate);

    for (let hour = 9; hour < 17; hour++) {
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
    }
  };

  useEffect(() => {
    if (selectedDate) {
      fetchSlots();
    }
  }, [selectedDate, fetchSlots]);

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

    if (!borrower?.email) {
      setError('Borrower email is required to send confirmation.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/demo/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          appointment_type_id: 1,
          start_time: selectedTime,
          duration_minutes: 30,
          attendee_name: borrower.name || `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim(),
          attendee_email: borrower.email || borrower.borrower_email,
          attendee_phone: borrower.phone || borrower.borrower_phone || '',
          notes: `Meeting mode: ${meetingMode === 'video' ? 'Video Call' : 'Phone Call'}`,
          meeting_mode: meetingMode
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to schedule appointment');
      }

      setSuccess(true);

      // Close modal after 2 seconds
      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (err) {
      console.error('Error scheduling appointment:', err);
      setError(err.message || 'Failed to schedule appointment. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={onClose}>
      <div className="schedule-modal" onClick={(e) => e.stopPropagation()}>
        <button className="schedule-modal-close" onClick={onClose}>
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
            <h2>Appointment Scheduled!</h2>
            <p>A confirmation email has been sent to {borrower?.email || borrower?.borrower_email}</p>
          </div>
        ) : (
          <>
            <h2>Pick a date</h2>

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

              <div className="schedule-week-dates">
                {weekDates.map((date, idx) => {
                  const disabled = isPast(date);
                  const selected = selectedDate && date.toDateString() === selectedDate.toDateString();

                  return (
                    <button
                      key={idx}
                      className={`schedule-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isToday(date) ? 'today' : ''}`}
                      onClick={() => !disabled && setSelectedDate(date)}
                      disabled={disabled}
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
              <p className="schedule-time-hint">Choose your preferred time. Reschedule anytime.</p>

              <div className="schedule-time-dropdown-wrapper">
                <select
                  className="schedule-time-dropdown"
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
              disabled={submitting || !selectedDate || !selectedTime}
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
