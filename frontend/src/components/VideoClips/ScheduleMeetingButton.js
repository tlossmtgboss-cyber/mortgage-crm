import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import './ScheduleMeetingButton.css';

// API base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

/**
 * ScheduleMeetingButton - Embeddable scheduling component for UVIP
 *
 * Can be used in:
 * - Video clip share pages (public view)
 * - Clip player (authenticated view)
 * - Meeting room CTA
 * - Email/message links
 */
const ScheduleMeetingButton = ({
  // Display options
  buttonText = 'Schedule a Meeting',
  buttonStyle = 'primary', // primary, secondary, outline, link
  buttonSize = 'medium', // small, medium, large
  showIcon = true,

  // Context
  clipId = null,
  leadId = null,
  loanId = null,
  contactId = null,

  // Booking link (if using pre-created link)
  bookingSlug = null,

  // Pre-fill data
  attendeeName = '',
  attendeeEmail = '',
  attendeePhone = '',

  // Callback
  onScheduled = null,
  onClose = null,

  // Public mode (no auth required)
  isPublic = false
}) => {
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [step, setStep] = useState('type'); // type, date, time, form, confirm

  // Data
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [bookingLinkData, setBookingLinkData] = useState(null);

  // Selections
  const [selectedType, setSelectedType] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(new Date());

  // Form data
  const [formData, setFormData] = useState({
    name: attendeeName,
    email: attendeeEmail,
    phone: attendeePhone,
    notes: ''
  });

  // Confirmation
  const [confirmedAppointment, setConfirmedAppointment] = useState(null);

  // Load appointment types or booking link data
  useEffect(() => {
    if (showModal) {
      if (bookingSlug) {
        loadBookingLink();
      } else if (!isPublic) {
        loadAppointmentTypes();
      }
    }
  }, [showModal, bookingSlug, isPublic]);

  // Load available slots when date/type selected
  useEffect(() => {
    if (selectedDate && selectedType) {
      loadAvailableSlots();
    }
  }, [selectedDate, selectedType]);

  const loadBookingLink = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${bookingSlug}`, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (response.ok) {
        const data = await response.json();
        setBookingLinkData(data);
        setAppointmentTypes(data.appointment_types || []);
        if (data.appointment_types?.length === 1) {
          setSelectedType(data.appointment_types[0]);
          setStep('date');
        }
      } else {
        setError('Booking link not found');
      }
    } catch (err) {
      setError('Failed to load booking options');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadAppointmentTypes = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        const publicTypes = (data.appointment_types || []).filter(t => t.is_public);
        setAppointmentTypes(publicTypes);
      }
    } catch (err) {
      setError('Failed to load appointment types');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableSlots = async () => {
    if (!selectedDate || !selectedType) return;

    setLoading(true);
    try {
      const dateStr = selectedDate.toISOString().split('T')[0];

      const endpoint = bookingSlug
        ? `${API_BASE}/api/v1/scheduler/public/book/${bookingSlug}/slots`
        : `${API_BASE}/api/v1/scheduler/available-slots`;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: bookingSlug ? { 'Content-Type': 'application/json' } : getAuthHeaders(),
        body: JSON.stringify({
          date: dateStr,
          appointment_type_id: selectedType.id
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAvailableSlots(data.slots || []);
      }
    } catch (err) {
      console.error('Error loading slots:', err);
      setAvailableSlots([]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmBooking = async () => {
    if (!selectedSlot || !formData.name || !formData.email) {
      setError('Please fill in required fields');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const endpoint = bookingSlug
        ? `${API_BASE}/api/v1/scheduler/public/book/${bookingSlug}/confirm`
        : `${API_BASE}/api/v1/scheduler/appointments`;

      const bookingData = {
        appointment_type_id: selectedType.id,
        scheduled_start: selectedSlot.start,
        scheduled_end: selectedSlot.end,
        attendee_name: formData.name,
        attendee_email: formData.email,
        attendee_phone: formData.phone || null,
        notes: formData.notes || null,
        meeting_mode: selectedType.allowed_modes?.[0] || 'video',
        // Link to context
        lead_id: leadId,
        loan_id: loanId,
        // Track source
        source: clipId ? 'video_clip' : 'direct',
        source_clip_id: clipId
      };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: bookingSlug ? { 'Content-Type': 'application/json' } : getAuthHeaders(),
        body: JSON.stringify(bookingData)
      });

      if (response.ok) {
        const data = await response.json();
        setConfirmedAppointment(data.appointment || data);
        setStep('confirm');

        if (onScheduled) {
          onScheduled(data.appointment || data);
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to book appointment');
      }
    } catch (err) {
      setError('Failed to book appointment');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setShowModal(false);
    setStep('type');
    setSelectedType(null);
    setSelectedDate(null);
    setSelectedSlot(null);
    setError(null);
    setConfirmedAppointment(null);
    if (onClose) onClose();
  };

  // Calendar helpers
  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const days = [];

    // Add empty slots for days before first day
    for (let i = 0; i < firstDay.getDay(); i++) {
      days.push(null);
    }

    // Add days of month
    for (let i = 1; i <= lastDay.getDate(); i++) {
      days.push(new Date(year, month, i));
    }

    return days;
  };

  const isDateSelectable = (date) => {
    if (!date) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date >= today;
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric'
    });
  };

  // Button classes
  const buttonClasses = [
    'schedule-meeting-btn',
    `style-${buttonStyle}`,
    `size-${buttonSize}`
  ].join(' ');

  return (
    <>
      {/* Trigger Button */}
      <button className={buttonClasses} onClick={() => setShowModal(true)}>
        {showIcon && <span className="btn-icon">📅</span>}
        {buttonText}
      </button>

      {/* Modal */}
      {showModal && (
        <div className="schedule-modal-overlay" onClick={handleClose}>
          <div className="schedule-modal" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="modal-header">
              <h2>
                {step === 'confirm' ? 'Confirmed!' : 'Schedule a Meeting'}
              </h2>
              <button className="close-btn" onClick={handleClose}>×</button>
            </div>

            {/* Progress */}
            {step !== 'confirm' && (
              <div className="booking-progress">
                <div className={`progress-step ${step === 'type' ? 'active' : selectedType ? 'complete' : ''}`}>
                  <span>1</span> Type
                </div>
                <div className={`progress-step ${step === 'date' ? 'active' : selectedDate ? 'complete' : ''}`}>
                  <span>2</span> Date
                </div>
                <div className={`progress-step ${step === 'time' ? 'active' : selectedSlot ? 'complete' : ''}`}>
                  <span>3</span> Time
                </div>
                <div className={`progress-step ${step === 'form' ? 'active' : ''}`}>
                  <span>4</span> Details
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="booking-error">{error}</div>
            )}

            {/* Loading */}
            {loading && (
              <div className="booking-loading">
                <div className="spinner"></div>
                <p>Loading...</p>
              </div>
            )}

            {/* Content */}
            <div className="modal-content">
              {/* Step 1: Select Type */}
              {step === 'type' && !loading && (
                <div className="type-selection">
                  <h3>What would you like to discuss?</h3>
                  <div className="type-grid">
                    {appointmentTypes.map(type => (
                      <div
                        key={type.id}
                        className={`type-card ${selectedType?.id === type.id ? 'selected' : ''}`}
                        onClick={() => {
                          setSelectedType(type);
                          setStep('date');
                        }}
                      >
                        <div className="type-icon" style={{ backgroundColor: type.color + '20', color: type.color }}>
                          {type.icon === 'phone' ? '📞' : type.icon === 'video' ? '🎥' : '📅'}
                        </div>
                        <h4>{type.type_name}</h4>
                        <p>{type.description}</p>
                        <span className="type-duration">{type.default_duration_minutes} min</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 2: Select Date */}
              {step === 'date' && !loading && (
                <div className="date-selection">
                  <div className="selection-summary">
                    <span className="summary-label">Meeting Type:</span>
                    <span className="summary-value">{selectedType?.type_name}</span>
                    <button className="change-btn" onClick={() => setStep('type')}>Change</button>
                  </div>

                  <h3>Select a Date</h3>

                  <div className="calendar-nav">
                    <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}>
                      ←
                    </button>
                    <span>
                      {currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                    </span>
                    <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}>
                      →
                    </button>
                  </div>

                  <div className="calendar-grid">
                    {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                      <div key={day} className="calendar-header">{day}</div>
                    ))}
                    {getDaysInMonth(currentMonth).map((date, idx) => (
                      <div
                        key={idx}
                        className={`calendar-day ${!date ? 'empty' : ''} ${date && !isDateSelectable(date) ? 'disabled' : ''} ${selectedDate && date && date.toDateString() === selectedDate.toDateString() ? 'selected' : ''}`}
                        onClick={() => {
                          if (date && isDateSelectable(date)) {
                            setSelectedDate(date);
                            setStep('time');
                          }
                        }}
                      >
                        {date?.getDate()}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 3: Select Time */}
              {step === 'time' && !loading && (
                <div className="time-selection">
                  <div className="selection-summary">
                    <span className="summary-label">Date:</span>
                    <span className="summary-value">{selectedDate && formatDate(selectedDate)}</span>
                    <button className="change-btn" onClick={() => setStep('date')}>Change</button>
                  </div>

                  <h3>Select a Time</h3>

                  {availableSlots.length === 0 ? (
                    <div className="no-slots">
                      <p>No available times on this date.</p>
                      <button onClick={() => setStep('date')}>Choose Another Date</button>
                    </div>
                  ) : (
                    <div className="time-grid">
                      {availableSlots.map((slot, idx) => (
                        <button
                          key={idx}
                          className={`time-slot ${selectedSlot === slot ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedSlot(slot);
                            setStep('form');
                          }}
                        >
                          {formatTime(slot.start)}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Step 4: Contact Form */}
              {step === 'form' && !loading && (
                <div className="booking-form">
                  <div className="selection-summary">
                    <div>
                      <span className="summary-label">Meeting:</span>
                      <span className="summary-value">{selectedType?.type_name}</span>
                    </div>
                    <div>
                      <span className="summary-label">When:</span>
                      <span className="summary-value">
                        {selectedDate && formatDate(selectedDate)} at {selectedSlot && formatTime(selectedSlot.start)}
                      </span>
                    </div>
                    <button className="change-btn" onClick={() => setStep('time')}>Change</button>
                  </div>

                  <h3>Your Details</h3>

                  <div className="form-fields">
                    <div className="form-group">
                      <label>Name *</label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                        placeholder="Your full name"
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Email *</label>
                      <input
                        type="email"
                        value={formData.email}
                        onChange={e => setFormData(prev => ({ ...prev, email: e.target.value }))}
                        placeholder="your@email.com"
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Phone (optional)</label>
                      <input
                        type="tel"
                        value={formData.phone}
                        onChange={e => setFormData(prev => ({ ...prev, phone: e.target.value }))}
                        placeholder="(555) 123-4567"
                      />
                    </div>

                    <div className="form-group">
                      <label>Notes (optional)</label>
                      <textarea
                        value={formData.notes}
                        onChange={e => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                        placeholder="Anything you'd like to discuss?"
                        rows={3}
                      />
                    </div>
                  </div>

                  <button
                    className="confirm-btn"
                    onClick={handleConfirmBooking}
                    disabled={!formData.name || !formData.email}
                  >
                    Confirm Booking
                  </button>
                </div>
              )}

              {/* Step 5: Confirmation */}
              {step === 'confirm' && confirmedAppointment && (
                <div className="booking-confirmed">
                  <div className="confirm-icon">✓</div>
                  <h3>You're all set!</h3>
                  <p>Your meeting has been scheduled.</p>

                  <div className="confirm-details">
                    <div className="detail-row">
                      <span className="detail-label">Meeting:</span>
                      <span className="detail-value">{selectedType?.type_name}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Date:</span>
                      <span className="detail-value">{formatDate(new Date(confirmedAppointment.scheduled_start))}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Time:</span>
                      <span className="detail-value">{formatTime(confirmedAppointment.scheduled_start)}</span>
                    </div>
                  </div>

                  <p className="confirm-email">
                    A confirmation email has been sent to <strong>{formData.email}</strong>
                  </p>

                  <button className="done-btn" onClick={handleClose}>
                    Done
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ScheduleMeetingButton;
