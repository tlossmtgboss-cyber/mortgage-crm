/**
 * CalendarSchedulerInput - Integrated calendar scheduler for appointment booking
 * Uses the CRM's scheduler API to show available slots
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './CalendarSchedulerInput.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

// Days of the week
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Generate time slots for a day
const generateTimeSlots = (date) => {
  const slots = [];
  const baseDate = new Date(date);

  // Generate slots from 9 AM to 5 PM
  for (let hour = 9; hour < 17; hour++) {
    for (let minute of [0, 30]) {
      const slotTime = new Date(baseDate);
      slotTime.setHours(hour, minute, 0, 0);

      // Skip past times for today
      if (slotTime > new Date()) {
        slots.push({
          time: slotTime,
          label: slotTime.toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
          }),
          value: slotTime.toISOString(),
        });
      }
    }
  }

  return slots;
};

// Get calendar days for a month
const getCalendarDays = (year, month) => {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const days = [];

  // Add padding for days before first of month
  for (let i = 0; i < firstDay.getDay(); i++) {
    days.push(null);
  }

  // Add all days of month
  for (let day = 1; day <= lastDay.getDate(); day++) {
    days.push(new Date(year, month, day));
  }

  return days;
};

const CalendarSchedulerInput = ({
  value,
  onChange,
  error,
  helpText,
  workspaceSlug,
  appointmentType = 'consultation',
  duration = 30,
}) => {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState(null);

  // Parse existing value
  useEffect(() => {
    if (value) {
      const dateValue = typeof value === 'string' ? new Date(value) : value.datetime ? new Date(value.datetime) : null;
      if (dateValue && !isNaN(dateValue)) {
        setSelectedDate(new Date(dateValue.getFullYear(), dateValue.getMonth(), dateValue.getDate()));
        setSelectedTime(dateValue.toISOString());
      }
    }
  }, []);

  // Fetch available slots from API
  const fetchAvailableSlots = useCallback(async (date) => {
    if (!date) return;

    const dateStr = date.toISOString().split('T')[0];

    // If we have a workspace, try to fetch from API
    if (workspaceSlug && API_BASE_URL) {
      setIsLoading(true);
      setFetchError(null);

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/scheduler/available-slots?date=${dateStr}&type=${appointmentType}&duration=${duration}`,
          {
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );

        if (response.ok) {
          const data = await response.json();
          setAvailableSlots(data.slots || []);
        } else {
          // Fallback to generated slots
          setAvailableSlots(generateTimeSlots(date));
        }
      } catch (err) {
        console.warn('Failed to fetch slots, using defaults:', err);
        setAvailableSlots(generateTimeSlots(date));
      } finally {
        setIsLoading(false);
      }
    } else {
      // Use generated slots
      setAvailableSlots(generateTimeSlots(date));
    }
  }, [workspaceSlug, appointmentType, duration]);

  // Fetch slots when date changes
  useEffect(() => {
    if (selectedDate) {
      fetchAvailableSlots(selectedDate);
    }
  }, [selectedDate, fetchAvailableSlots]);

  // Get calendar days for current month
  const calendarDays = useMemo(
    () => getCalendarDays(currentMonth.getFullYear(), currentMonth.getMonth()),
    [currentMonth]
  );

  // Check if a date is selectable (not in past, not weekend for business hours)
  const isDateSelectable = useCallback((date) => {
    if (!date) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date >= today;
  }, []);

  // Check if date is selected
  const isDateSelected = useCallback((date) => {
    if (!date || !selectedDate) return false;
    return (
      date.getDate() === selectedDate.getDate() &&
      date.getMonth() === selectedDate.getMonth() &&
      date.getFullYear() === selectedDate.getFullYear()
    );
  }, [selectedDate]);

  // Handle month navigation
  const goToPrevMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
  };

  const goToNextMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));
  };

  // Handle date selection
  const handleDateSelect = (date) => {
    if (isDateSelectable(date)) {
      setSelectedDate(date);
      setSelectedTime(null); // Reset time when date changes
    }
  };

  // Handle time selection
  const handleTimeSelect = (slot) => {
    setSelectedTime(slot.value);

    // Notify parent with full selection
    onChange({
      date: selectedDate.toISOString().split('T')[0],
      time: slot.label,
      datetime: slot.value,
      duration,
      appointmentType,
    });
  };

  const monthYear = currentMonth.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="calendar-scheduler-input">
      {/* Calendar Section */}
      <div className="calendar-section">
        <div className="calendar-header">
          <button
            type="button"
            className="nav-arrow"
            onClick={goToPrevMonth}
            aria-label="Previous month"
          >
            ←
          </button>
          <span className="month-year">{monthYear}</span>
          <button
            type="button"
            className="nav-arrow"
            onClick={goToNextMonth}
            aria-label="Next month"
          >
            →
          </button>
        </div>

        <div className="calendar-grid">
          {/* Day headers */}
          {DAYS.map((day) => (
            <div key={day} className="day-header">
              {day}
            </div>
          ))}

          {/* Calendar days */}
          {calendarDays.map((date, index) => (
            <button
              key={index}
              type="button"
              className={`calendar-day ${
                !date ? 'empty' : ''
              } ${
                date && isDateSelected(date) ? 'selected' : ''
              } ${
                date && !isDateSelectable(date) ? 'disabled' : ''
              } ${
                date && date.toDateString() === new Date().toDateString() ? 'today' : ''
              }`}
              onClick={() => date && handleDateSelect(date)}
              disabled={!date || !isDateSelectable(date)}
            >
              {date ? date.getDate() : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Time Slots Section */}
      {selectedDate && (
        <div className="time-slots-section">
          <h4 className="time-slots-title">
            Available Times for {selectedDate.toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'short',
              day: 'numeric',
            })}
          </h4>

          {isLoading ? (
            <div className="loading-slots">
              <div className="spinner"></div>
              <span>Loading available times...</span>
            </div>
          ) : availableSlots.length > 0 ? (
            <div className="time-slots-grid">
              {availableSlots.map((slot, index) => (
                <button
                  key={index}
                  type="button"
                  className={`time-slot ${selectedTime === slot.value ? 'selected' : ''}`}
                  onClick={() => handleTimeSelect(slot)}
                >
                  {slot.label}
                </button>
              ))}
            </div>
          ) : (
            <div className="no-slots">
              <p>No available times for this date.</p>
              <p className="hint">Try selecting a different date.</p>
            </div>
          )}
        </div>
      )}

      {/* Selected Appointment Summary */}
      {selectedDate && selectedTime && (
        <div className="appointment-summary">
          <span className="summary-icon">✓</span>
          <span className="summary-text">
            Selected: {selectedDate.toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })} at {availableSlots.find(s => s.value === selectedTime)?.label}
          </span>
        </div>
      )}

      {helpText && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
};

export default CalendarSchedulerInput;
