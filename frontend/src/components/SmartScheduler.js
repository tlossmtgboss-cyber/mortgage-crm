import React, { useState, useEffect, useCallback } from 'react';
import './SmartScheduler.css';

const API_BASE = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function SmartScheduler({
  onSelect,
  selectedSlot,
  appointmentType = 'pre-qualification-call',
  durationMinutes = 30,
  daysAhead = 14,
  title = "Select a Date & Time",
  subtitle = "Choose a convenient time for your consultation"
}) {
  const [selectedDate, setSelectedDate] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [slotsByDate, setSlotsByDate] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Generate calendar days
  const generateCalendarDays = useCallback(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = firstDay.getDay();

    const days = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const maxDate = new Date();
    maxDate.setDate(maxDate.getDate() + daysAhead);

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startOffset; i++) {
      days.push({ empty: true });
    }

    // Add days of the month
    for (let day = 1; day <= lastDay.getDate(); day++) {
      const date = new Date(year, month, day);
      const dateStr = date.toISOString().split('T')[0];
      const isPast = date < today;
      const isTooFar = date > maxDate;
      const hasSlots = slotsByDate[dateStr] && slotsByDate[dateStr].length > 0;

      days.push({
        date,
        day,
        dateStr,
        isPast,
        isTooFar,
        hasSlots,
        isToday: date.toDateString() === today.toDateString(),
        isSelected: selectedDate && date.toDateString() === selectedDate.toDateString()
      });
    }

    return days;
  }, [currentMonth, daysAhead, selectedDate, slotsByDate]);

  // Fetch available slots
  useEffect(() => {
    const fetchSlots = async () => {
      setLoading(true);
      setError(null);

      try {
        const startDate = new Date();
        const endDate = new Date();
        endDate.setDate(endDate.getDate() + daysAhead);

        const response = await fetch(`${API_BASE}/api/v1/scheduler/public/available-slots`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            start_date: startDate.toISOString().split('T')[0],
            end_date: endDate.toISOString().split('T')[0],
            duration_minutes: durationMinutes,
            appointment_type: appointmentType
          })
        });

        if (response.ok) {
          const data = await response.json();
          const slots = data.available_slots || [];

          // Group slots by date
          const grouped = {};
          slots.forEach(slot => {
            const dateStr = new Date(slot.start_time).toISOString().split('T')[0];
            if (!grouped[dateStr]) grouped[dateStr] = [];
            grouped[dateStr].push(slot);
          });
          setSlotsByDate(grouped);
        } else {
          setError('Unable to load available times');
        }
      } catch (err) {
        console.error('Failed to fetch slots:', err);
        setError('Unable to load available times');
      } finally {
        setLoading(false);
      }
    };

    fetchSlots();
  }, [appointmentType, durationMinutes, daysAhead]);

  const handleDateClick = (dayInfo) => {
    if (dayInfo.isPast || dayInfo.isTooFar || !dayInfo.hasSlots) return;
    setSelectedDate(dayInfo.date);
  };

  const handleSlotClick = (slot) => {
    onSelect(slot);
  };

  const navigateMonth = (direction) => {
    const newMonth = new Date(currentMonth);
    newMonth.setMonth(newMonth.getMonth() + direction);
    setCurrentMonth(newMonth);
  };

  const calendarDays = generateCalendarDays();
  const selectedDateStr = selectedDate ? selectedDate.toISOString().split('T')[0] : null;
  const timeSlotsForDate = selectedDateStr ? (slotsByDate[selectedDateStr] || []) : [];

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  if (loading) {
    return (
      <div className="smart-scheduler">
        <div className="scheduler-loading">
          <div className="loading-spinner"></div>
          <p>Loading available times...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="smart-scheduler">
        <div className="scheduler-error">
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Try Again</button>
        </div>
      </div>
    );
  }

  return (
    <div className="smart-scheduler">
      <div className="scheduler-header">
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>

      <div className="scheduler-content">
        {/* Calendar View */}
        <div className="scheduler-calendar">
          <div className="calendar-nav">
            <button
              className="nav-btn"
              onClick={() => navigateMonth(-1)}
              disabled={currentMonth.getMonth() === new Date().getMonth() &&
                        currentMonth.getFullYear() === new Date().getFullYear()}
            >
              &#8249;
            </button>
            <span className="current-month">
              {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
            </span>
            <button
              className="nav-btn"
              onClick={() => navigateMonth(1)}
            >
              &#8250;
            </button>
          </div>

          <div className="calendar-grid">
            <div className="calendar-weekdays">
              {weekDays.map(day => (
                <div key={day} className="weekday">{day}</div>
              ))}
            </div>

            <div className="calendar-days">
              {calendarDays.map((dayInfo, idx) => (
                <div
                  key={idx}
                  className={`calendar-day ${dayInfo.empty ? 'empty' : ''} ${dayInfo.isPast ? 'past' : ''} ${dayInfo.isTooFar ? 'too-far' : ''} ${dayInfo.hasSlots ? 'has-slots' : 'no-slots'} ${dayInfo.isToday ? 'today' : ''} ${dayInfo.isSelected ? 'selected' : ''}`}
                  onClick={() => !dayInfo.empty && handleDateClick(dayInfo)}
                >
                  {!dayInfo.empty && (
                    <>
                      <span className="day-number">{dayInfo.day}</span>
                      {dayInfo.hasSlots && <span className="slot-indicator"></span>}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="calendar-legend">
            <span className="legend-item">
              <span className="legend-dot available"></span> Available
            </span>
            <span className="legend-item">
              <span className="legend-dot unavailable"></span> Unavailable
            </span>
          </div>
        </div>

        {/* Time Slots */}
        <div className="scheduler-times">
          {selectedDate ? (
            <>
              <h4>
                {selectedDate.toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric'
                })}
              </h4>

              {timeSlotsForDate.length > 0 ? (
                <div className="time-slots">
                  {timeSlotsForDate.map((slot, idx) => {
                    const time = new Date(slot.start_time);
                    const isSelected = selectedSlot &&
                      selectedSlot.start_time === slot.start_time;

                    return (
                      <button
                        key={idx}
                        className={`time-slot ${isSelected ? 'selected' : ''}`}
                        onClick={() => handleSlotClick(slot)}
                      >
                        {time.toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          hour12: true
                        })}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="no-times">No available times for this date</p>
              )}
            </>
          ) : (
            <div className="select-date-prompt">
              <div className="calendar-icon">&#128197;</div>
              <p>Select a date from the calendar to see available times</p>
            </div>
          )}
        </div>
      </div>

      {/* Selected Confirmation */}
      {selectedSlot && (
        <div className="scheduler-confirmation">
          <div className="confirmation-icon">&#10003;</div>
          <div className="confirmation-text">
            <strong>
              {new Date(selectedSlot.start_time).toLocaleDateString('en-US', {
                weekday: 'long',
                month: 'long',
                day: 'numeric'
              })}
            </strong>
            <span> at </span>
            <strong>
              {new Date(selectedSlot.start_time).toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
              })}
            </strong>
          </div>
        </div>
      )}
    </div>
  );
}

export default SmartScheduler;
