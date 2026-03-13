import React, { useMemo, useCallback } from 'react';
import { MONTH_NAMES, DAY_NAMES, isToday } from './calendarUtils';

const FULL_DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const MiniCalendar = React.memo(function MiniCalendar({
  currentDate,
  selectedDate,
  eventDateSet,
  onDateClick,
  onPreviousMonth,
  onNextMonth,
  onGoToToday,
}) {
  const days = useMemo(() => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();

    const result = [];

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startingDay; i++) {
      result.push({ day: null, date: null });
    }

    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      result.push({
        day,
        date: new Date(year, month, day)
      });
    }

    return result;
  }, [currentDate]);

  const selectedDateString = useMemo(() => selectedDate.toDateString(), [selectedDate]);

  const hasAppointmentsOnDate = useCallback((date) => {
    if (!date) return false;
    return eventDateSet.has(date.toDateString());
  }, [eventDateSet]);

  const isSelected = useCallback((date) => {
    if (!date) return false;
    return date.toDateString() === selectedDateString;
  }, [selectedDateString]);

  const monthLabel = `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;

  return (
    <div className="mini-calendar" role="region" aria-label="Mini calendar">
      <div className="calendar-header" role="toolbar" aria-label="Calendar navigation">
        <button className="nav-btn" onClick={onPreviousMonth} aria-label="Previous month">&lt;</button>
        <span
          className="month-year"
          onClick={onGoToToday}
          title="Click to go to today"
          aria-live="polite"
          aria-atomic="true"
        >
          {monthLabel}
        </span>
        <button className="nav-btn" onClick={onNextMonth} aria-label="Next month">&gt;</button>
      </div>

      <div className="calendar-grid" role="grid" aria-label={`${monthLabel} calendar`}>
        {/* Day names header */}
        <div role="row" style={{ display: 'contents' }}>
          {DAY_NAMES.map((day, index) => (
            <div key={index} className="day-name" role="columnheader" aria-label={FULL_DAY_NAMES[index]}>{day}</div>
          ))}
        </div>

        {/* Calendar days */}
        {days.map((item, index) => {
          const todayDate = item.date && isToday(item.date);
          const selected = item.date && isSelected(item.date);
          const hasEvents = item.date && hasAppointmentsOnDate(item.date);
          const fullLabel = item.date
            ? item.date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
            : undefined;

          return (
            <div
              key={index}
              className={`calendar-day ${!item.day ? 'empty' : ''} ${todayDate ? 'today' : ''} ${selected ? 'selected' : ''} ${hasEvents ? 'has-events' : ''}`}
              onClick={() => item.date && onDateClick(item.date)}
              onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && item.date) { e.preventDefault(); onDateClick(item.date); } }}
              role="gridcell"
              tabIndex={item.day ? 0 : -1}
              aria-label={fullLabel ? `${fullLabel}${hasEvents ? ', has appointments' : ''}` : undefined}
              aria-selected={selected || undefined}
              aria-current={todayDate ? 'date' : undefined}
              aria-disabled={!item.day || undefined}
            >
              {item.day && (
                <>
                  <span className="day-number">{item.day}</span>
                  {hasEvents && (
                    <span className="event-dot" aria-hidden="true"></span>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
});

export default MiniCalendar;
