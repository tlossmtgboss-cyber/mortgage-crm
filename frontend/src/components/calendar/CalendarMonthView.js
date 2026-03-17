import React from 'react';
import { useCalendar } from './CalendarContext';
import {
  ACTIONS,
  MONTH_NAMES,
  getDaysInMonth,
  handleInteractiveKeyDown,
} from '../../hooks/useCalendarReducer';

/**
 * CalendarMonthView -- renders two side-by-side mini calendars (current + next month)
 * with event dots and scroll controls.
 */
export default function CalendarMonthView() {
  const { state, dispatch } = useCalendar();

  const currentMonthData = getDaysInMonth(state.currentDate);
  const nextMonthDate = new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() + 1, 1);
  const nextMonthData = getDaysInMonth(nextMonthDate);

  const handleScrollUp = () => {
    dispatch({
      type: ACTIONS.SET_CURRENT_DATE,
      payload: new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() - 1, 1),
    });
  };

  const handleScrollDown = () => {
    dispatch({
      type: ACTIONS.SET_CURRENT_DATE,
      payload: new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() + 1, 1),
    });
  };

  return (
    <div className="calendar-scroll-container">
      <button
        className="calendar-scroll-btn scroll-up"
        onClick={handleScrollUp}
        title="Previous month"
        aria-label="Previous month"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="18 15 12 9 6 15"></polyline>
        </svg>
      </button>

      <div className="two-month-view">
        <MiniCalendarMonth data={currentMonthData} />
        <MiniCalendarMonth data={nextMonthData} />
      </div>

      <button
        className="calendar-scroll-btn scroll-down"
        onClick={handleScrollDown}
        title="Next month"
        aria-label="Next month"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
    </div>
  );
}

// ---- Single month mini calendar ----

function MiniCalendarMonth({ data }) {
  const { dispatch, getEventsForDate } = useCalendar();
  const { daysInMonth, startingDayOfWeek, year, month } = data;

  const handleDayClick = (day) => {
    dispatch({ type: ACTIONS.OPEN_ADD_MODAL, payload: { date: new Date(year, month, day) } });
  };

  return (
    <div className="mini-calendar">
      <div className="mini-calendar-header">
        <h3>
          {MONTH_NAMES[month]} {year}
        </h3>
      </div>

      <div className="mini-calendar-weekdays">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, idx) => (
          <div key={idx} className="mini-weekday-label">
            {d}
          </div>
        ))}
      </div>

      <div className="mini-calendar-days">
        {/* Empty cells before first day */}
        {[...Array(startingDayOfWeek)].map((_, index) => (
          <div key={`empty-${index}`} className="mini-calendar-day empty" />
        ))}

        {[...Array(daysInMonth)].map((_, index) => {
          const day = index + 1;
          const dayEvents = getEventsForDate(day, year, month);
          const dayDate = new Date(year, month, day);
          const isToday = new Date().toDateString() === dayDate.toDateString();

          return (
            <div
              key={day}
              className={`mini-calendar-day ${isToday ? 'today' : ''} ${dayEvents.length > 0 ? 'has-events' : ''}`}
              role="button"
              tabIndex={0}
              aria-label={`${MONTH_NAMES[month]} ${day}, ${year}${dayEvents.length > 0 ? `, ${dayEvents.length} event${dayEvents.length > 1 ? 's' : ''}` : ''}`}
              onClick={() => handleDayClick(day)}
              onKeyDown={(e) => handleInteractiveKeyDown(e, () => handleDayClick(day))}
            >
              <div className="mini-day-number">{day}</div>
              {dayEvents.length > 0 && (
                <div className="event-dots">
                  {dayEvents.slice(0, 3).map((event, idx) => (
                    <div key={idx} className={`event-dot event-dot-${event.event_type || 'meeting'}`} />
                  ))}
                </div>
              )}
              {dayEvents.length > 3 && <div className="event-overflow">+{dayEvents.length - 3}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
