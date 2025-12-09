import React, { useState, useEffect } from 'react';
import './ReviewCallScheduler.css';

/**
 * ReviewCallScheduler - Mandatory call scheduling before application submission
 *
 * Features:
 * - Calendar view with available time slots
 * - LO availability integration
 * - Multiple time zone support
 * - Confirmation and reminder options
 */

const ReviewCallScheduler = ({
  applicationToken,
  loName,
  loPhone,
  loEmail,
  onScheduleComplete,
  onSkip,
  apiBaseUrl,
  existingAppointment = null,
}) => {
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [error, setError] = useState(null);
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [contactMethod, setContactMethod] = useState('phone');
  const [notes, setNotes] = useState('');
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [appointment, setAppointment] = useState(existingAppointment);

  // Generate next 14 days for date selection
  const getAvailableDates = () => {
    const dates = [];
    const today = new Date();

    for (let i = 1; i <= 14; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);

      // Skip weekends for now
      if (date.getDay() !== 0 && date.getDay() !== 6) {
        dates.push(date);
      }
    }

    return dates;
  };

  // Fetch available time slots for selected date
  useEffect(() => {
    if (selectedDate) {
      fetchAvailableSlots(selectedDate);
    }
  }, [selectedDate]);

  const fetchAvailableSlots = async (date) => {
    setLoading(true);
    setError(null);

    try {
      const dateStr = date.toISOString().split('T')[0];
      const response = await fetch(
        `${apiBaseUrl}/api/v1/apply/${applicationToken}/available-slots?date=${dateStr}&timezone=${encodeURIComponent(timezone)}`
      );

      if (!response.ok) {
        throw new Error('Failed to load available times');
      }

      const data = await response.json();
      setAvailableSlots(data.slots || generateDefaultSlots());
    } catch (err) {
      console.error('Error fetching slots:', err);
      // Use default slots if API fails
      setAvailableSlots(generateDefaultSlots());
    } finally {
      setLoading(false);
    }
  };

  // Generate default time slots (9 AM - 5 PM)
  const generateDefaultSlots = () => {
    const slots = [];
    for (let hour = 9; hour <= 17; hour++) {
      if (hour !== 12) {
        // Skip lunch hour
        slots.push({
          time: `${hour.toString().padStart(2, '0')}:00`,
          available: true,
        });
        if (hour !== 17) {
          slots.push({
            time: `${hour.toString().padStart(2, '0')}:30`,
            available: true,
          });
        }
      }
    }
    return slots;
  };

  // Format date for display
  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  // Format time for display
  const formatTime = (timeStr) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${minutes} ${ampm}`;
  };

  // Schedule the call
  const handleSchedule = async () => {
    if (!selectedDate || !selectedTime) return;

    setScheduling(true);
    setError(null);

    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/apply/${applicationToken}/schedule-review-call`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            date: selectedDate.toISOString().split('T')[0],
            time: selectedTime,
            timezone,
            contact_method: contactMethod,
            notes,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to schedule call');
      }

      const data = await response.json();
      setAppointment(data.appointment);
      setShowConfirmation(true);

      if (onScheduleComplete) {
        onScheduleComplete(data.appointment);
      }
    } catch (err) {
      setError(err.message || 'Failed to schedule call. Please try again.');
    } finally {
      setScheduling(false);
    }
  };

  // Render existing appointment
  if (appointment) {
    return (
      <div className="review-call-scheduler">
        <div className="scheduled-confirmation">
          <div className="confirmation-icon">✅</div>
          <h2>Review Call Scheduled</h2>
          <div className="appointment-details">
            <div className="detail-row">
              <span className="detail-label">Date & Time:</span>
              <span className="detail-value">
                {new Date(appointment.scheduled_at).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}{' '}
                at{' '}
                {new Date(appointment.scheduled_at).toLocaleTimeString('en-US', {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </span>
            </div>
            <div className="detail-row">
              <span className="detail-label">With:</span>
              <span className="detail-value">{loName}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Contact Method:</span>
              <span className="detail-value">
                {appointment.contact_method === 'phone' ? '📞 Phone Call' : '💻 Video Call'}
              </span>
            </div>
          </div>
          <p className="confirmation-note">
            You will receive a confirmation email and reminder before your scheduled call.
          </p>
          <button
            className="reschedule-btn"
            onClick={() => setAppointment(null)}
          >
            Reschedule
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="review-call-scheduler">
      {/* Header */}
      <div className="scheduler-header">
        <h2>Schedule Your Review Call</h2>
        <p>
          Before submitting your application, please schedule a brief call with your loan officer
          to review the information and answer any questions.
        </p>
      </div>

      {/* LO Info */}
      <div className="lo-info">
        <div className="lo-avatar">👤</div>
        <div className="lo-details">
          <span className="lo-name">{loName || 'Your Loan Officer'}</span>
          <span className="lo-contact">
            {loPhone && <span>📞 {loPhone}</span>}
            {loEmail && <span>✉️ {loEmail}</span>}
          </span>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="scheduler-error">
          {error}
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Contact Method */}
      <div className="scheduler-section">
        <h3>Preferred Contact Method</h3>
        <div className="contact-options">
          <label className={`contact-option ${contactMethod === 'phone' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="contactMethod"
              value="phone"
              checked={contactMethod === 'phone'}
              onChange={() => setContactMethod('phone')}
            />
            <span className="option-icon">📞</span>
            <span className="option-label">Phone Call</span>
          </label>
          <label className={`contact-option ${contactMethod === 'video' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="contactMethod"
              value="video"
              checked={contactMethod === 'video'}
              onChange={() => setContactMethod('video')}
            />
            <span className="option-icon">💻</span>
            <span className="option-label">Video Call</span>
          </label>
        </div>
      </div>

      {/* Date Selection */}
      <div className="scheduler-section">
        <h3>Select a Date</h3>
        <div className="date-grid">
          {getAvailableDates().map((date, index) => (
            <button
              key={index}
              className={`date-option ${
                selectedDate?.toDateString() === date.toDateString() ? 'selected' : ''
              }`}
              onClick={() => {
                setSelectedDate(date);
                setSelectedTime(null);
              }}
            >
              <span className="date-weekday">{formatDate(date).split(',')[0]}</span>
              <span className="date-day">{date.getDate()}</span>
              <span className="date-month">
                {date.toLocaleDateString('en-US', { month: 'short' })}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Time Selection */}
      {selectedDate && (
        <div className="scheduler-section">
          <h3>Select a Time</h3>
          <div className="timezone-select">
            <label>Timezone:</label>
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              <option value="America/New_York">Eastern Time</option>
              <option value="America/Chicago">Central Time</option>
              <option value="America/Denver">Mountain Time</option>
              <option value="America/Los_Angeles">Pacific Time</option>
              <option value="America/Phoenix">Arizona Time</option>
              <option value="Pacific/Honolulu">Hawaii Time</option>
            </select>
          </div>

          {loading ? (
            <div className="time-loading">
              <div className="loading-spinner"></div>
              <span>Loading available times...</span>
            </div>
          ) : (
            <div className="time-grid">
              {availableSlots.map((slot, index) => (
                <button
                  key={index}
                  className={`time-option ${
                    selectedTime === slot.time ? 'selected' : ''
                  } ${!slot.available ? 'unavailable' : ''}`}
                  onClick={() => slot.available && setSelectedTime(slot.time)}
                  disabled={!slot.available}
                >
                  {formatTime(slot.time)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Notes */}
      {selectedDate && selectedTime && (
        <div className="scheduler-section">
          <h3>Any Questions or Topics? (Optional)</h3>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Let us know if there's anything specific you'd like to discuss..."
            rows={3}
          />
        </div>
      )}

      {/* Summary & Schedule Button */}
      {selectedDate && selectedTime && (
        <div className="schedule-summary">
          <div className="summary-details">
            <span className="summary-icon">📅</span>
            <span className="summary-text">
              {formatDate(selectedDate)} at {formatTime(selectedTime)} (
              {timezone.split('/')[1]?.replace('_', ' ')})
            </span>
          </div>
          <button
            className="schedule-btn"
            onClick={handleSchedule}
            disabled={scheduling}
          >
            {scheduling ? 'Scheduling...' : 'Schedule Call'}
          </button>
        </div>
      )}

      {/* Skip Option - only if allowed */}
      {onSkip && (
        <div className="skip-option">
          <button className="skip-btn" onClick={onSkip}>
            I'll schedule later →
          </button>
          <p className="skip-note">
            Note: Your application cannot be submitted until a review call is scheduled.
          </p>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmation && (
        <div className="confirmation-overlay">
          <div className="confirmation-modal">
            <div className="confirmation-icon">🎉</div>
            <h2>Call Scheduled!</h2>
            <p>
              Your review call has been scheduled for{' '}
              <strong>
                {formatDate(selectedDate)} at {formatTime(selectedTime)}
              </strong>
            </p>
            <p>
              You will receive a confirmation email with all the details and a calendar invite.
            </p>
            <button
              className="continue-btn"
              onClick={() => setShowConfirmation(false)}
            >
              Continue with Application
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReviewCallScheduler;
