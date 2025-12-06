import React, { useState, useEffect, useCallback } from 'react';
import './PublicBooking.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const PublicBooking = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bookingLink, setBookingLink] = useState(null);
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [meetingMode, setMeetingMode] = useState('video'); // 'video' or 'in_person'
  const [weekStart, setWeekStart] = useState(new Date());
  const [step, setStep] = useState('datetime'); // datetime, form, confirmation, manage
  const [submitting, setSubmitting] = useState(false);
  const [confirmedAppointment, setConfirmedAppointment] = useState(null);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState('');

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    notes: '',
    working_with_agent: null, // Custom question example
    custom_responses: {}
  });

  // Get slug from URL
  const slug = window.location.pathname.split('/book/')[1]?.split('/')[0] || 'demo';

  // Check if managing existing appointment
  const urlParams = new URLSearchParams(window.location.search);
  const appointmentId = urlParams.get('appointment');
  const action = urlParams.get('action'); // 'reschedule' or 'cancel'

  // Generate week dates starting from weekStart
  const getWeekDates = () => {
    const dates = [];
    const start = new Date(weekStart);
    start.setHours(0, 0, 0, 0);

    for (let i = 0; i < 7; i++) {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      dates.push(date);
    }
    return dates;
  };

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

  const formatFullDate = (date) => {
    return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
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

  // Fetch booking link info
  const fetchBookingLink = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}`);

      if (!response.ok) {
        if (response.status === 404) {
          setError('This booking link is not available.');
        } else {
          setError('Failed to load booking page.');
        }
        return;
      }

      const data = await response.json();
      setBookingLink(data.booking_page || data);
      const types = data.booking_page?.appointment_types || data.appointment_types || [];
      setAppointmentTypes(types);

      // Auto-select first type
      if (types.length > 0) {
        setSelectedType(types[0]);
      }

      // Set initial date to today or first available weekday
      const today = new Date();
      if (today.getDay() === 0 || today.getDay() === 6) {
        // If weekend, start from Monday
        const monday = new Date(today);
        monday.setDate(today.getDate() + (8 - today.getDay()) % 7);
        setWeekStart(monday);
        setSelectedDate(monday);
      } else {
        setSelectedDate(today);
      }

      setError(null);
    } catch (err) {
      console.error('Error fetching booking link:', err);
      setError('Unable to connect to the booking service.');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  // Fetch available slots for selected date
  const fetchSlots = useCallback(async () => {
    if (!selectedType || !selectedDate) return;

    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/book/${slug}/slots?date=${dateStr}&appointment_type_id=${selectedType.id}&duration_minutes=${selectedType.default_duration_minutes || 30}`
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
        if (slots.length > 0 && !selectedTime) {
          setSelectedTime(slots[0].start_time);
        }
      }
    } catch (err) {
      console.error('Error fetching slots:', err);
    }
  }, [slug, selectedType, selectedDate, selectedTime]);

  useEffect(() => {
    fetchBookingLink();
  }, [fetchBookingLink]);

  useEffect(() => {
    if (selectedType && selectedDate) {
      fetchSlots();
    }
  }, [selectedType, selectedDate, fetchSlots]);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedType || !selectedTime) {
      setError('Please select a date and time.');
      return;
    }

    if (!form.first_name || !form.last_name || !form.email) {
      setError('Please fill in all required fields.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          appointment_type_id: selectedType.id,
          start_time: selectedTime,
          duration_minutes: selectedType.default_duration_minutes || 30,
          attendee_name: `${form.first_name} ${form.last_name}`,
          attendee_email: form.email,
          attendee_phone: form.phone,
          notes: form.notes,
          meeting_mode: meetingMode,
          custom_responses: {
            working_with_agent: form.working_with_agent,
            ...form.custom_responses
          }
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to book appointment');
      }

      const result = await response.json();
      setConfirmedAppointment({
        id: result.appointment_id,
        date: selectedDate,
        time: selectedTime,
        type: selectedType,
        meetingMode: meetingMode
      });
      setStep('confirmation');
    } catch (err) {
      console.error('Error booking appointment:', err);
      setError(err.message || 'Failed to book appointment. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Navigate weeks
  const prevWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() - 7);
    // Don't go before today
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

  // Loading state
  if (loading) {
    return (
      <div className="redfin-booking">
        <div className="booking-container">
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !bookingLink) {
    return (
      <div className="redfin-booking">
        <div className="booking-container">
          <div className="error-state">
            <h2>Booking Unavailable</h2>
            <p>{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // Confirmation state
  if (step === 'confirmation' && confirmedAppointment) {
    return (
      <div className="redfin-booking">
        <div className="booking-container confirmation-container">
          <div className="confirmation-header">
            <div className="success-checkmark">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1>Your request has been made</h1>
            <p>We will attempt to schedule your appointment. You will receive an email once the time has been confirmed.</p>
          </div>

          <div className="appointment-summary">
            <h3>Appointment Details</h3>
            <div className="summary-row">
              <span className="label">Date:</span>
              <span className="value">{formatFullDate(confirmedAppointment.date)}</span>
            </div>
            <div className="summary-row">
              <span className="label">Time:</span>
              <span className="value">{formatTime(confirmedAppointment.time)}</span>
            </div>
            <div className="summary-row">
              <span className="label">Type:</span>
              <span className="value">{confirmedAppointment.type.type_name}</span>
            </div>
            <div className="summary-row">
              <span className="label">Format:</span>
              <span className="value">{confirmedAppointment.meetingMode === 'video' ? 'Video Call' : 'In Person'}</span>
            </div>
          </div>

          <button className="primary-button" onClick={() => window.location.href = '/'}>
            Go to Homepage
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="redfin-booking">
      <div className="booking-container">
        {/* Header */}
        {bookingLink && (
          <div className="booking-header">
            <h1>{bookingLink.custom_title || bookingLink.title || bookingLink.link_name || 'Schedule an Appointment'}</h1>
            {bookingLink.custom_description || bookingLink.description ? (
              <p>{bookingLink.custom_description || bookingLink.description}</p>
            ) : null}
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        {step === 'datetime' && (
          <>
            {/* Appointment Type Selector (if multiple) */}
            {appointmentTypes.length > 1 && (
              <div className="type-selector">
                <h3>Select Appointment Type</h3>
                <div className="type-pills">
                  {appointmentTypes.map(type => (
                    <button
                      key={type.id}
                      className={`type-pill ${selectedType?.id === type.id ? 'active' : ''}`}
                      onClick={() => setSelectedType(type)}
                    >
                      {type.type_name}
                      <span className="duration">{type.default_duration_minutes} min</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Date Picker */}
            <div className="date-section">
              <h2>Pick a date</h2>
              <div className="week-picker">
                <button className="week-nav prev" onClick={prevWeek} disabled={isPast(weekDates[0])}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 19l-7-7 7-7" />
                  </svg>
                </button>

                <div className="week-dates">
                  {weekDates.map((date, idx) => {
                    const disabled = isPast(date);
                    const selected = selectedDate && date.toDateString() === selectedDate.toDateString();

                    return (
                      <button
                        key={idx}
                        className={`date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isToday(date) ? 'today' : ''}`}
                        onClick={() => !disabled && setSelectedDate(date)}
                        disabled={disabled}
                      >
                        <span className="day-name">{formatDayName(date)}</span>
                        <span className="day-number">{formatDayNumber(date)}</span>
                        <span className="month">{formatMonth(date)}</span>
                      </button>
                    );
                  })}
                </div>

                <button className="week-nav next" onClick={nextWeek}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Time Picker */}
            <div className="time-section">
              <h2>Pick a time</h2>
              <p className="time-subtitle">Choose your preferred time. Reschedule anytime.</p>

              <div className="time-dropdown-wrapper">
                <select
                  className="time-dropdown"
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
                <svg className="dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>

              {/* Meeting Mode Toggle */}
              <div className="meeting-mode-toggle">
                <button
                  className={`mode-button ${meetingMode === 'in_person' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('in_person')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                  In person
                </button>
                <button
                  className={`mode-button ${meetingMode === 'video' ? 'active' : ''}`}
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

            <button
              className="primary-button next-button"
              onClick={() => setStep('form')}
              disabled={!selectedDate || !selectedTime}
            >
              Next
            </button>
          </>
        )}

        {step === 'form' && (
          <div className="form-step">
            <button className="back-link" onClick={() => setStep('datetime')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 19l-7-7 7-7" />
              </svg>
              Back
            </button>

            <h2>Tell us a little about yourself</h2>

            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={form.first_name}
                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                    placeholder="Jane"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={form.last_name}
                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                    placeholder="Doe"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email *</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    placeholder="jane@email.com"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder="(   )    -"
                  />
                  <span className="field-hint">We may call/text you about your appointment.</span>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Notes (optional)</label>
                  <textarea
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder="Are there other times that could work? Any specific topics to discuss?"
                    rows={3}
                  />
                </div>
              </div>

              {/* Custom Question Example */}
              <div className="form-row">
                <div className="form-group radio-group">
                  <label>Are you currently working with a loan officer?</label>
                  <div className="radio-options">
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="working_with_agent"
                        value="no"
                        checked={form.working_with_agent === 'no'}
                        onChange={(e) => setForm({ ...form, working_with_agent: e.target.value })}
                      />
                      <span>No</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="working_with_agent"
                        value="yes"
                        checked={form.working_with_agent === 'yes'}
                        onChange={(e) => setForm({ ...form, working_with_agent: e.target.value })}
                      />
                      <span>Yes</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="form-summary">
                <div className="summary-badge">
                  {formatFullDate(selectedDate)} at {formatTime(selectedTime)}
                </div>
              </div>

              <button
                type="submit"
                className="primary-button submit-button"
                disabled={submitting}
              >
                {submitting ? 'Scheduling...' : 'Schedule Appointment'}
              </button>
            </form>
          </div>
        )}

        {/* Reschedule Modal */}
        {showRescheduleModal && (
          <div className="modal-overlay" onClick={() => setShowRescheduleModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={() => setShowRescheduleModal(false)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <h2>Request to change your appointment time</h2>
              <p>This will cancel your existing appointment. We'll do our best to arrange the meeting during the time you are requesting.</p>

              <div className="reschedule-comparison">
                <div className="comparison-col">
                  <h4>What you previously scheduled:</h4>
                  <p><strong>Date</strong><br/>Sunday, December 7</p>
                  <p><strong>Time</strong><br/>6:00-6:45 am</p>
                </div>
                <div className="comparison-arrow">→</div>
                <div className="comparison-col">
                  <h4>We'll attempt to confirm:</h4>
                  <p><strong>Date</strong><br/>{selectedDate && formatFullDate(selectedDate)}</p>
                  <p><strong>Time</strong><br/>{selectedTime && formatTime(selectedTime)}</p>
                </div>
              </div>

              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setShowRescheduleModal(false)}>Cancel</button>
                <button className="primary-button">Request</button>
              </div>
            </div>
          </div>
        )}

        {/* Cancel Modal */}
        {showCancelModal && (
          <div className="modal-overlay" onClick={() => setShowCancelModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={() => setShowCancelModal(false)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <h2>Cancel your appointment?</h2>
              <p>Our team is working hard to book your appointment.</p>

              <div className="form-group">
                <label>Please let us know why you're canceling (optional)</label>
                <textarea
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  placeholder="Your feedback helps us improve."
                  rows={3}
                />
              </div>

              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setShowCancelModal(false)}>Close</button>
                <button className="danger-button">Cancel Appointment</button>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="booking-footer">
          <p>Powered by <strong>Perennia AI</strong></p>
        </div>
      </div>
    </div>
  );
};

export default PublicBooking;
