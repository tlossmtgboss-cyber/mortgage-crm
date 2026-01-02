import React, { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const PortalScheduler = ({ slug, recruiterName, compact = false }) => {
  const [selectedDate, setSelectedDate] = useState('');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [appointmentType, setAppointmentType] = useState('discovery_call');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [booking, setBooking] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);

  // Generate next 14 days as available dates
  const getAvailableDates = () => {
    const dates = [];
    const today = new Date();
    for (let i = 1; i <= 14; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      // Skip weekends
      if (date.getDay() !== 0 && date.getDay() !== 6) {
        dates.push(date.toISOString().split('T')[0]);
      }
    }
    return dates;
  };

  const availableDates = getAvailableDates();

  const fetchAvailability = useCallback(async () => {
    if (!selectedDate) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_URL}/api/v1/recruit-portal/purl/${slug}/availability?date=${selectedDate}`
      );

      if (response.ok) {
        const data = await response.json();
        setAvailableSlots(data.slots || []);
      } else {
        setAvailableSlots([]);
      }
    } catch (err) {
      console.error('Error fetching availability:', err);
      setAvailableSlots([]);
    } finally {
      setLoading(false);
    }
  }, [slug, selectedDate]);

  useEffect(() => {
    fetchAvailability();
  }, [fetchAvailability]);

  const handleBooking = async () => {
    if (!selectedSlot || !selectedDate) return;

    setBooking(true);
    setError(null);

    try {
      const scheduledAt = `${selectedDate}T${selectedSlot.start_time}:00`;

      const response = await fetch(`${API_URL}/api/v1/recruit-portal/purl/${slug}/schedule`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          appointment_type: appointmentType,
          scheduled_at: scheduledAt,
          duration_minutes: 30,
          notes: notes || null,
        }),
      });

      if (response.ok) {
        setSuccess(true);
      } else {
        const data = await response.json();
        // Handle both string and object error formats (Pydantic validation errors)
        let errorMessage = 'Failed to book appointment';
        if (data.detail) {
          if (typeof data.detail === 'string') {
            errorMessage = data.detail;
          } else if (Array.isArray(data.detail)) {
            // Pydantic validation errors come as array of {loc, msg, type}
            errorMessage = data.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
          } else if (typeof data.detail === 'object') {
            errorMessage = data.detail.msg || data.detail.message || JSON.stringify(data.detail);
          }
        } else if (data.error) {
          errorMessage = data.error;
        }
        setError(errorMessage);
      }
    } catch (err) {
      console.error('Booking error:', err);
      setError('Failed to book appointment. Please try again.');
    } finally {
      setBooking(false);
    }
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr + 'T12:00:00');
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatTime = (timeStr) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours, 10);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  if (success) {
    return (
      <div className="scheduler-section">
        <div className="booking-success">
          <div className="success-icon">✅</div>
          <h3>Appointment Booked!</h3>
          <p>
            Your call with {recruiterName || 'your recruiter'} is scheduled for:
          </p>
          <div className="booking-details">
            <p className="booking-date">{formatDate(selectedDate)}</p>
            <p className="booking-time">{formatTime(selectedSlot.start_time)}</p>
          </div>
          <p className="booking-note">
            You'll receive a calendar invite and reminder email shortly.
          </p>
          <button
            className="book-another-btn"
            onClick={() => {
              setSuccess(false);
              setSelectedDate('');
              setSelectedSlot(null);
              setNotes('');
            }}
          >
            Book Another Call
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`scheduler-section ${compact ? 'compact' : ''}`}>
      <h3>Schedule a Call</h3>
      {!compact && (
        <p className="scheduler-intro">
          Book a time to speak with {recruiterName || 'our team'} about the opportunity.
          We'll discuss your goals, answer your questions, and explore how we can help you grow.
        </p>
      )}

      <div className="scheduler-form">
        {/* Appointment Type */}
        <div className="form-group">
          <label>Call Type</label>
          <div className="appointment-types">
            <button
              className={`type-btn ${appointmentType === 'discovery_call' ? 'active' : ''}`}
              onClick={() => setAppointmentType('discovery_call')}
            >
              <span className="type-icon">📞</span>
              <span className="type-label">Discovery Call</span>
              <span className="type-duration">30 min</span>
            </button>
            <button
              className={`type-btn ${appointmentType === 'deep_dive' ? 'active' : ''}`}
              onClick={() => setAppointmentType('deep_dive')}
            >
              <span className="type-icon">🔍</span>
              <span className="type-label">Deep Dive</span>
              <span className="type-duration">45 min</span>
            </button>
            <button
              className={`type-btn ${appointmentType === 'tech_demo' ? 'active' : ''}`}
              onClick={() => setAppointmentType('tech_demo')}
            >
              <span className="type-icon">💻</span>
              <span className="type-label">Tech Demo</span>
              <span className="type-duration">30 min</span>
            </button>
          </div>
        </div>

        {/* Date Selection */}
        <div className="form-group">
          <label>Select a Date</label>
          <div className="date-grid">
            {availableDates.map((date) => (
              <button
                key={date}
                className={`date-btn ${selectedDate === date ? 'active' : ''}`}
                onClick={() => {
                  setSelectedDate(date);
                  setSelectedSlot(null);
                }}
              >
                <span className="date-day">
                  {new Date(date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short' })}
                </span>
                <span className="date-num">
                  {new Date(date + 'T12:00:00').getDate()}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Time Selection */}
        {selectedDate && (
          <div className="form-group">
            <label>Select a Time</label>
            {loading ? (
              <div className="loading-slots">Loading available times...</div>
            ) : availableSlots.length > 0 ? (
              <div className="time-grid">
                {availableSlots
                  .filter((slot) => slot.is_available)
                  .map((slot, index) => (
                    <button
                      key={index}
                      className={`time-btn ${selectedSlot?.start_time === slot.start_time ? 'active' : ''}`}
                      onClick={() => setSelectedSlot(slot)}
                    >
                      {formatTime(slot.start_time)}
                    </button>
                  ))}
              </div>
            ) : (
              <div className="no-slots">
                No available times on this date. Please select another date.
              </div>
            )}
          </div>
        )}

        {/* Notes */}
        {selectedSlot && (
          <div className="form-group">
            <label>Anything specific you'd like to discuss? (Optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g., I'm interested in learning about your lead generation program..."
              rows={3}
            />
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="booking-error">
            <span>⚠️</span> {error}
          </div>
        )}

        {/* Book Button */}
        {selectedSlot && (
          <div className="booking-summary">
            <div className="summary-details">
              <p className="summary-date">{formatDate(selectedDate)}</p>
              <p className="summary-time">{formatTime(selectedSlot.start_time)}</p>
            </div>
            <button
              className="book-btn"
              onClick={handleBooking}
              disabled={booking}
            >
              {booking ? 'Booking...' : 'Confirm Booking'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default PortalScheduler;
