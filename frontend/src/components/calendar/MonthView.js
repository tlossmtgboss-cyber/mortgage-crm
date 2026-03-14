import React, { useCallback } from 'react';

const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const handleInteractiveKeyDown = (e, onClick) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onClick(e);
  }
};

/**
 * MiniCalendarMonth -- Compact single-month grid with event-dot indicators on each day.
 *
 * Used in: MonthView
 *
 * @param {Object} props
 * @param {Object} props.monthData - Month layout descriptor
 * @param {number} props.monthData.daysInMonth - Total days in the month
 * @param {number} props.monthData.startingDayOfWeek - Day-of-week offset for the 1st (0=Sun, 6=Sat)
 * @param {number} props.monthData.year - Four-digit year
 * @param {number} props.monthData.month - Zero-based month index (0=Jan, 11=Dec)
 * @param {Function} props.getEventsForDate - Function(day, year, month) => Array of events for that date
 * @param {Function} props.onDayClick - Callback(day, year, month) when a day cell is clicked
 * @returns {React.ReactElement}
 *
 * @example
 * <MiniCalendarMonth monthData={{ daysInMonth: 31, startingDayOfWeek: 2, year: 2026, month: 2 }}
 *   getEventsForDate={getEvents} onDayClick={handleDayClick} />
 */
const MiniCalendarMonth = React.memo(function MiniCalendarMonth({
  monthData,
  getEventsForDate,
  onDayClick,
}) {
  const { daysInMonth, startingDayOfWeek, year, month } = monthData;

  return (
    <div className="mini-calendar">
      <div className="mini-calendar-header">
        <h3>{monthNames[month]} {year}</h3>
      </div>

      <div className="mini-calendar-weekdays">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, idx) => (
          <div key={idx} className="mini-weekday-label">{day}</div>
        ))}
      </div>

      <div className="mini-calendar-days">
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
              aria-label={`${monthNames[month]} ${day}, ${year}${dayEvents.length > 0 ? `, ${dayEvents.length} event${dayEvents.length > 1 ? 's' : ''}` : ''}`}
              onClick={() => onDayClick(day, year, month)}
              onKeyDown={(e) => handleInteractiveKeyDown(e, () => onDayClick(day, year, month))}
            >
              <div className="mini-day-number">{day}</div>
              {dayEvents.length > 0 && (
                <div className="event-dots">
                  {dayEvents.slice(0, 3).map((event, idx) => (
                    <div
                      key={idx}
                      className={`event-dot event-dot-${event.event_type || 'meeting'}`}
                    />
                  ))}
                </div>
              )}
              {dayEvents.length > 3 && (
                <div className="event-overflow">+{dayEvents.length - 3}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
});

/**
 * MonthView -- Two-month mini calendar layout with scroll-navigation arrows.
 *
 * Displays the current and next month side-by-side using MiniCalendarMonth.
 *
 * Used in: Calendar (main page, month view mode)
 *
 * @param {Object} props
 * @param {Object} props.currentMonthData - Month layout data for the primary month (see MiniCalendarMonth)
 * @param {Object} props.nextMonthData - Month layout data for the following month
 * @param {Function} props.getEventsForDate - Function(day, year, month) => Array of events for that date
 * @param {Function} props.onDayClick - Callback(day, year, month) when a day cell is clicked
 * @param {Function} props.onScrollUp - Callback() to navigate to the previous month pair
 * @param {Function} props.onScrollDown - Callback() to navigate to the next month pair
 * @returns {React.ReactElement}
 *
 * @example
 * <MonthView
 *   currentMonthData={marchData}
 *   nextMonthData={aprilData}
 *   getEventsForDate={getEvents}
 *   onDayClick={handleDayClick}
 *   onScrollUp={goToPrevMonth}
 *   onScrollDown={goToNextMonth}
 * />
 */
const MonthView = React.memo(function MonthView({
  currentMonthData,
  nextMonthData,
  getEventsForDate,
  onDayClick,
  onScrollUp,
  onScrollDown,
}) {
  return (
    <div className="calendar-scroll-container">
      <button
        className="calendar-scroll-btn scroll-up"
        onClick={onScrollUp}
        title="Previous month"
        aria-label="Previous month"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="18 15 12 9 6 15"></polyline>
        </svg>
      </button>

      <div className="two-month-view">
        <MiniCalendarMonth
          monthData={currentMonthData}
          getEventsForDate={getEventsForDate}
          onDayClick={onDayClick}
        />
        <MiniCalendarMonth
          monthData={nextMonthData}
          getEventsForDate={getEventsForDate}
          onDayClick={onDayClick}
        />
      </div>

      <button
        className="calendar-scroll-btn scroll-down"
        onClick={onScrollDown}
        title="Next month"
        aria-label="Next month"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
    </div>
  );
});

export { MiniCalendarMonth };
export default MonthView;
