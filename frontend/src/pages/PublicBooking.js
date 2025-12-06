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
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [step, setStep] = useState('type'); // type, date, time, form, confirmation
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const [form, setForm] = useState({
    attendee_name: '',
    attendee_email: '',
    attendee_phone: '',
    notes: ''
  });

  // Get slug from URL
  const slug = window.location.pathname.split('/book/')[1]?.split('/')[0] || 'demo';

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
      setBookingLink(data);
      setAppointmentTypes(data.appointment_types || []);

      // If only one type, auto-select it
      if (data.appointment_types?.length === 1) {
        setSelectedType(data.appointment_types[0]);
        setStep('date');
      }

      setError(null);
    } catch (err) {
      console.error('Error fetching booking link:', err);
      setError('Unable to connect to the booking service.');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  // Fetch available slots for selected date and type
  const fetchSlots = useCallback(async () => {
    if (!selectedType || !selectedDate) return;

    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/book/${slug}/slots?date=${dateStr}&appointment_type_id=${selectedType.id}&duration_minutes=${selectedType.default_duration_minutes || 30}`
      );

      if (response.ok) {
        const data = await response.json();
        // Map the slots to include start_time key for consistency
        const slots = (data.available_slots || []).map(slot => ({
          ...slot,
          start_time: slot.start
        }));
        setAvailableSlots(slots);
      }
    } catch (err) {
      console.error('Error fetching slots:', err);
    }
  }, [slug, selectedType, selectedDate]);

  useEffect(() => {
    fetchBookingLink();
  }, [fetchBookingLink]);

  useEffect(() => {
    if (selectedType && selectedDate && step === 'time') {
      fetchSlots();
    }
  }, [selectedType, selectedDate, step, fetchSlots]);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedType || !selectedSlot) {
      setError('Please select an appointment time.');
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
          start_time: selectedSlot.start_time,
          duration_minutes: selectedType.default_duration_minutes || 30,
          attendee_name: form.attendee_name,
          attendee_email: form.attendee_email,
          attendee_phone: form.attendee_phone,
          notes: form.notes
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to book appointment');
      }

      setConfirmed(true);
      setStep('confirmation');
    } catch (err) {
      console.error('Error booking appointment:', err);
      setError(err.message || 'Failed to book appointment. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Generate calendar days
  const generateCalendarDays = () => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const days = [];

    // Add empty days for start of month
    for (let i = 0; i < firstDay.getDay(); i++) {
      days.push(null);
    }

    // Add days of month
    for (let i = 1; i <= lastDay.getDate(); i++) {
      days.push(new Date(year, month, i));
    }

    return days;
  };

  const isDateDisabled = (date) => {
    if (!date) return true;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (date < today) return true;
    // Disable weekends by default
    if (date.getDay() === 0 || date.getDay() === 6) return true;
    return false;
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  };

  // Loading state
  if (loading) {
    return (
      <div className="public-booking">
        <div className="booking-container">
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading booking page...</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !bookingLink) {
    return (
      <div className="public-booking">
        <div className="booking-container">
          <div className="error-state">
            <div className="error-icon">!</div>
            <h2>Booking Unavailable</h2>
            <p>{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // Confirmation state
  if (confirmed) {
    return (
      <div className="public-booking">
        <div className="booking-container">
          <div className="confirmation-state">
            <div className="success-icon">✓</div>
            <h2>Appointment Confirmed!</h2>
            <p>Your appointment has been scheduled.</p>
            <div className="confirmation-details">
              <div className="detail-row">
                <span className="label">Date:</span>
                <span className="value">{formatDate(selectedDate)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Time:</span>
                <span className="value">{formatTime(selectedSlot.start_time)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Type:</span>
                <span className="value">{selectedType.type_name}</span>
              </div>
            </div>
            <p className="confirmation-note">A confirmation email has been sent to {form.attendee_email}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="public-booking">
      <div className="booking-container">
        {/* Header */}
        <div className="booking-header">
          <h1>{bookingLink?.link_name || 'Schedule a Meeting'}</h1>
          {bookingLink?.description && <p>{bookingLink.description}</p>}
        </div>

        {/* Progress indicator */}
        <div className="progress-steps">
          <div className={`progress-step ${step === 'type' ? 'active' : ''} ${['date', 'time', 'form'].includes(step) ? 'completed' : ''}`}>
            <span className="step-number">1</span>
            <span className="step-label">Select Type</span>
          </div>
          <div className={`progress-step ${step === 'date' ? 'active' : ''} ${['time', 'form'].includes(step) ? 'completed' : ''}`}>
            <span className="step-number">2</span>
            <span className="step-label">Pick Date</span>
          </div>
          <div className={`progress-step ${step === 'time' ? 'active' : ''} ${step === 'form' ? 'completed' : ''}`}>
            <span className="step-number">3</span>
            <span className="step-label">Pick Time</span>
          </div>
          <div className={`progress-step ${step === 'form' ? 'active' : ''}`}>
            <span className="step-number">4</span>
            <span className="step-label">Your Info</span>
          </div>
        </div>

        {error && <div className="error-message">{error}</div>}

        {/* Step 1: Select appointment type */}
        {step === 'type' && (
          <div className="step-content">
            <h2>Select Appointment Type</h2>
            <div className="appointment-types">
              {appointmentTypes.map(type => (
                <div
                  key={type.id}
                  className={`type-card ${selectedType?.id === type.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedType(type);
                    setStep('date');
                  }}
                  style={{ borderColor: type.color }}
                >
                  <div className="type-icon" style={{ backgroundColor: type.color }}>
                    {type.icon === 'phone' ? '📞' : type.icon === 'video' ? '📹' : '📅'}
                  </div>
                  <div className="type-info">
                    <h3>{type.type_name}</h3>
                    {type.description && <p>{type.description}</p>}
                    <span className="duration">{type.default_duration_minutes} minutes</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Select date */}
        {step === 'date' && (
          <div className="step-content">
            <h2>Select a Date</h2>
            <div className="selected-type-badge" style={{ backgroundColor: selectedType?.color }}>
              {selectedType?.type_name} - {selectedType?.default_duration_minutes} min
            </div>

            <div className="calendar">
              <div className="calendar-header">
                <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}>
                  ←
                </button>
                <span>{currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</span>
                <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}>
                  →
                </button>
              </div>
              <div className="calendar-weekdays">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                  <div key={day} className="weekday">{day}</div>
                ))}
              </div>
              <div className="calendar-days">
                {generateCalendarDays().map((day, idx) => (
                  <div
                    key={idx}
                    className={`calendar-day ${!day ? 'empty' : ''} ${isDateDisabled(day) ? 'disabled' : ''} ${day && selectedDate.toDateString() === day.toDateString() ? 'selected' : ''}`}
                    onClick={() => {
                      if (day && !isDateDisabled(day)) {
                        setSelectedDate(day);
                        setStep('time');
                      }
                    }}
                  >
                    {day?.getDate()}
                  </div>
                ))}
              </div>
            </div>

            <button className="back-button" onClick={() => setStep('type')}>← Back</button>
          </div>
        )}

        {/* Step 3: Select time */}
        {step === 'time' && (
          <div className="step-content">
            <h2>Select a Time</h2>
            <p className="selected-date">{formatDate(selectedDate)}</p>

            <div className="time-slots">
              {availableSlots.length === 0 ? (
                <p className="no-slots">No available times for this date. Please select another date.</p>
              ) : (
                availableSlots.map((slot, idx) => (
                  <button
                    key={idx}
                    className={`time-slot ${selectedSlot?.start_time === slot.start_time ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedSlot(slot);
                      setStep('form');
                    }}
                  >
                    {formatTime(slot.start_time)}
                  </button>
                ))
              )}
            </div>

            <button className="back-button" onClick={() => setStep('date')}>← Back</button>
          </div>
        )}

        {/* Step 4: Enter info */}
        {step === 'form' && (
          <div className="step-content">
            <h2>Your Information</h2>
            <div className="booking-summary">
              <p><strong>{selectedType?.type_name}</strong></p>
              <p>{formatDate(selectedDate)} at {formatTime(selectedSlot.start_time)}</p>
            </div>

            <form onSubmit={handleSubmit} className="booking-form">
              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={form.attendee_name}
                  onChange={(e) => setForm({ ...form, attendee_name: e.target.value })}
                  required
                  placeholder="Your full name"
                />
              </div>

              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  value={form.attendee_email}
                  onChange={(e) => setForm({ ...form, attendee_email: e.target.value })}
                  required
                  placeholder="your@email.com"
                />
              </div>

              <div className="form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  value={form.attendee_phone}
                  onChange={(e) => setForm({ ...form, attendee_phone: e.target.value })}
                  placeholder="(555) 123-4567"
                />
              </div>

              <div className="form-group">
                <label>Notes (optional)</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder="Anything you'd like us to know before the meeting?"
                  rows={3}
                />
              </div>

              <div className="form-actions">
                <button type="button" className="back-button" onClick={() => setStep('time')}>← Back</button>
                <button type="submit" className="submit-button" disabled={submitting}>
                  {submitting ? 'Scheduling...' : 'Confirm Booking'}
                </button>
              </div>
            </form>
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
