import React from 'react';
import { MONTH_NAMES, DAY_NAMES, isToday } from './calendarUtils';

function MiniCalendar({
  currentDate,
  selectedDate,
  eventDateSet,
  onDateClick,
  onPreviousMonth,
  onNextMonth,
  onGoToToday,
}) {
  const getDaysInMonth = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();

    const days = [];

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startingDay; i++) {
      days.push({ day: null, date: null });
    }

    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      days.push({
        day,
        date: new Date(year, month, day)
      });
    }

    return days;
  };

  const hasAppointmentsOnDate = (date) => {
    if (!date) return false;
    return eventDateSet.has(date.toDateString());
  };

  const isSelected = (date) => {
    if (!date) return false;
    return date.toDateString() === selectedDate.toDateString();
  };

  const days = getDaysInMonth();

  return (
    <div className="mini-calendar">
      <div className="calendar-header">
        <button className="nav-btn" onClick={onPreviousMonth}>&lt;</button>
        <span className="month-year" onClick={onGoToToday} title="Click to go to today">
          {MONTH_NAMES[currentDate.getMonth()]} {currentDate.getFullYear()}
        </span>
        <button className="nav-btn" onClick={onNextMonth}>&gt;</button>
      </div>

      <div className="calendar-grid">
        {/* Day names header */}
        {DAY_NAMES.map((day, index) => (
          <div key={index} className="day-name">{day}</div>
        ))}

        {/* Calendar days */}
        {days.map((item, index) => (
          <div
            key={index}
            className={`calendar-day ${!item.day ? 'empty' : ''} ${isToday(item.date) ? 'today' : ''} ${isSelected(item.date) ? 'selected' : ''} ${hasAppointmentsOnDate(item.date) ? 'has-events' : ''}`}
            onClick={() => onDateClick(item.date)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDateClick(item.date); } }}
            role={item.day ? "button" : undefined}
            tabIndex={item.day ? 0 : -1}
            aria-label={item.date ? `Select ${item.date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}` : undefined}
          >
            {item.day && (
              <>
                <span className="day-number">{item.day}</span>
                {hasAppointmentsOnDate(item.date) && (
                  <span className="event-dot"></span>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default MiniCalendar;
