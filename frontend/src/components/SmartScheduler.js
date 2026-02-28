import React, { useState, useEffect, useCallback } from 'react';
import './SmartScheduler.css';

const API_BASE = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function SmartScheduler({
  onSelect,
  selectedSlot,
  slug = 'demo',
  appointmentTypeId,
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
  const [resolvedTypeId, setResolvedTypeId] = useState(appointmentTypeId);

  // On mount, fetch booking link to resolve the appointment type ID if not provided
  useEffect(() => {
    if (resolvedTypeId) return;
    const resolveType = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}`);
        if (res.ok) {
          const data = await res.json();
          const types = data.booking_page?.appointment_types || data.appointment_types || [];
          if (types.length > 0) {
            setResolvedTypeId(types[0].id);
          }
        }
      } catch (err) {
        console.error('Failed to resolve booking link:', err);
      }
    };
    resolveType();
  }, [slug, resolvedTypeId]);

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

  // Fetch available slots for the visible month using real booking API
  useEffect(() => {
    if (!resolvedTypeId) return;

    const fetchSlots = async () => {
      setLoading(true);
      setError(null);

      try {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const maxDate = new Date();
        maxDate.setDate(maxDate.getDate() + daysAhead);

        // Determine the date range for the current month view
        const monthStart = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1);
        const monthEnd = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 0);
        const rangeStart = monthStart < today ? today : monthStart;
        const rangeEnd = monthEnd > maxDate ? maxDate : monthEnd;

        if (rangeStart > rangeEnd) {
          setSlotsByDate({});
          setLoading(false);
          return;
        }

        // Fetch slots day-by-day using the real booking link API
        const grouped = {};
        const fetchPromises = [];
        const currentDate = new Date(rangeStart);

        while (currentDate <= rangeEnd) {
          const dateStr = currentDate.toISOString().split('T')[0];
          const fetchDate = dateStr;
          fetchPromises.push(
            fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}/slots?date=${fetchDate}&appointment_type_id=${resolvedTypeId}&duration_minutes=${durationMinutes}`)
              .then(res => res.ok ? res.json() : { available_slots: [] })
              .then(data => {
                const daySlots = (data.available_slots || []).map(s => ({
                  start_time: s.start,
                  end_time: s.end,
                  ...s
                }));
                if (daySlots.length > 0) {
                  grouped[fetchDate] = daySlots;
                }
              })
              .catch(() => {})
          );
          currentDate.setDate(currentDate.getDate() + 1);
        }

        await Promise.all(fetchPromises);
        setSlotsByDate(grouped);
      } catch (err) {
        console.error('Failed to fetch slots:', err);
        setError('Unable to load available times');
      } finally {
        setLoading(false);
      }
    };

    fetchSlots();
  }, [slug, resolvedTypeId, durationMinutes, daysAhead, currentMonth]);

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
