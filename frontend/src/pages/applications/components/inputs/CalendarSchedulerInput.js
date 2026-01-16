/**
 * CalendarSchedulerInput - Smart scheduler matching original CRM design
 * Shows time slots in card format with time/date, supports Calendly integration
 */

import React, { useState, useEffect, useMemo } from 'react';
import './CalendarSchedulerInput.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

// Generate available time slots for next 5 business days
const generateTimeSlots = () => {
  const slots = [];
  const today = new Date();

  for (let d = 1; d <= 7; d++) {
    const date = new Date(today);
    date.setDate(today.getDate() + d);

    // Skip weekends
    if (date.getDay() === 0 || date.getDay() === 6) continue;

    // Available times
    const times = ['9:00 AM', '10:30 AM', '1:00 PM', '2:30 PM', '4:00 PM'];

    times.forEach(time => {
      slots.push({
        id: `${date.toISOString().split('T')[0]}-${time}`,
        date: date.toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric'
        }),
        time: time,
        datetime: date.toISOString(),
      });
    });
  }

  // Return first 12 slots
  return slots.slice(0, 12);
};

const CalendarSchedulerInput = ({
  value,
  onChange,
  error,
  helpText,
  disabled = false,
  appointmentType = 'consultation',
  duration = 30,
  calendlyUrl = null,
}) => {
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [apiSlots, setApiSlots] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Generate time slots (use API slots if available, otherwise generate)
  const timeSlots = useMemo(() => {
    if (apiSlots && apiSlots.length > 0) {
      return apiSlots;
    }
    return generateTimeSlots();
  }, [apiSlots]);

  // Try to fetch slots from API
  useEffect(() => {
    const fetchSlots = async () => {
      if (!API_BASE_URL) return;

      setIsLoading(true);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/scheduler/available-slots?type=${appointmentType}&duration=${duration}`,
          { headers: { 'Content-Type': 'application/json' } }
        );

        if (response.ok) {
          const data = await response.json();
          if (data.slots && data.slots.length > 0) {
            setApiSlots(data.slots);
          }
        }
      } catch (err) {
        // Silently fall back to generated slots
        console.warn('Using generated time slots:', err.message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSlots();
  }, [appointmentType, duration]);

  // Parse existing value
  useEffect(() => {
    if (value && typeof value === 'object' && value.slot_id) {
      setSelectedSlot(value.slot_id);
    } else if (value && typeof value === 'string') {
      setSelectedSlot(value);
    }
  }, []);

  // Handle slot selection
  const handleSlotSelect = (slot) => {
    if (disabled) return;

    setSelectedSlot(slot.id);

    // Notify parent with selection
    onChange({
      slot_id: slot.id,
      date: slot.date,
      time: slot.time,
      datetime: slot.datetime,
      appointmentType,
      duration,
    });
  };

  // If Calendly is configured, show embed
  if (calendlyUrl) {
    return (
      <div className="calendar-scheduler-input">
        <div className="calendly-embed-container">
          <iframe
            src={`${calendlyUrl}?hide_gdpr_banner=1&hide_event_type_details=1`}
            width="100%"
            height="630"
            frameBorder="0"
            title="Schedule Consultation"
            style={{ minWidth: '320px', borderRadius: '8px' }}
          />
          <div className="calendly-skip-option">
            <p>After scheduling, click Continue to proceed with your application.</p>
          </div>
        </div>
        {helpText && <p className="help-text">{helpText}</p>}
        {error && <p className="error-text">{error}</p>}
      </div>
    );
  }

  // Default: Show time slot grid matching original design
  return (
    <div className={`calendar-scheduler-input ${disabled ? 'disabled' : ''}`}>
      <div className="calendar-placeholder">
        <div className="cal-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
            <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01" />
          </svg>
        </div>
        <h4>Pick a Time That Works For You</h4>
        <p>We want to coordinate a time to review the application with you. Choose a time that is most convenient for you.</p>

        {isLoading ? (
          <div className="loading-slots">
            <div className="spinner"></div>
            <span>Loading available times...</span>
          </div>
        ) : (
          <div className="time-slots">
            {timeSlots.map(slot => (
              <div
                key={slot.id}
                className={`time-slot ${selectedSlot === slot.id ? 'selected' : ''} ${disabled ? 'disabled' : ''}`}
                onClick={() => handleSlotSelect(slot)}
                role="button"
                tabIndex={disabled ? -1 : 0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleSlotSelect(slot);
                  }
                }}
              >
                <div className="time-slot-time">{slot.time}</div>
                <div className="time-slot-date">{slot.date}</div>
              </div>
            ))}
          </div>
        )}

        {selectedSlot && (
          <div className="selected-confirmation">
            <span className="check-icon">✓</span>
            <span>
              Appointment selected: {timeSlots.find(s => s.id === selectedSlot)?.time} on{' '}
              {timeSlots.find(s => s.id === selectedSlot)?.date}
            </span>
          </div>
        )}
      </div>

      {helpText && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
};

export default CalendarSchedulerInput;
