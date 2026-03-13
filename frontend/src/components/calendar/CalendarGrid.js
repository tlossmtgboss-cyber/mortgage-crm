import React, { useMemo, useCallback, useRef, useEffect, useState } from 'react';
import { MONTH_NAMES, isToday } from './calendarUtils';
import ScreenReaderOnly from '../common/ScreenReaderOnly';
import { useIsTablet, useScreenOrientation } from '../common/ResponsiveContainer';

/**
 * FULL_DAY_NAMES - Full day names for aria-labels on column headers.
 */
const FULL_DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const SHORT_DAY_NAMES = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const ABBREVIATED_DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/**
 * formatFullDateLabel - Format a date as "Monday, March 11, 2026" for aria-label.
 */
const formatFullDateLabel = (date) => {
  if (!date) return '';
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
};

/**
 * CalendarGrid - Accessible calendar grid with ARIA roles and keyboard navigation.
 *
 * Features:
 * - role="grid" on the table, role="gridcell" on day cells
 * - aria-label with full date on each cell ("Monday, March 11, 2026")
 * - aria-selected for the currently selected day
 * - aria-current="date" for today's date
 * - Arrow key navigation (up/down/left/right) between cells
 * - Home/End keys to navigate to first/last day of the week (row)
 * - Enter/Space to select a date
 * - Roving tabindex for grid navigation
 *
 * Props:
 *   currentDate    - Date object representing the displayed month
 *   selectedDate   - Date object representing the selected date
 *   eventDateSet   - Set of date strings (toDateString()) that have events
 *   onDateClick    - Callback when a date is clicked/selected
 *   onPreviousMonth - Navigate to previous month
 *   onNextMonth    - Navigate to next month
 *   onGoToToday    - Navigate to today
 *   visibleDays    - Number of days to show (3 for tablet 3-day view, 7 for week, default 7)
 *   abbreviateLabels - Use abbreviated time/day labels (e.g., "9a" instead of "9:00 AM")
 *   compact        - Force compact rendering (auto-detected on tablet if not specified)
 */
const CalendarGrid = React.memo(function CalendarGrid({
  currentDate,
  selectedDate,
  eventDateSet,
  onDateClick,
  onPreviousMonth,
  onNextMonth,
  onGoToToday,
  visibleDays = 7,
  abbreviateLabels = false,
  compact,
}) {
  const gridRef = useRef(null);
  const cellRefs = useRef({});
  const [focusedIndex, setFocusedIndex] = useState(null);

  // Responsive detection for tablet-specific class switching
  const isTablet = useIsTablet();
  const orientation = useScreenOrientation();
  const isTabletPortrait = isTablet && orientation === 'portrait';

  // Auto-detect compact mode: tablet portrait uses abbreviated labels
  const effectiveAbbreviate = abbreviateLabels || isTabletPortrait;
  // In compact mode (tablet), use abbreviated day names even for 7-day grid
  const effectiveCompact = compact !== undefined ? compact : isTablet;

  // Build the calendar day matrix
  const { days, weeks } = useMemo(() => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();

    const dayList = [];

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startingDay; i++) {
      dayList.push({ day: null, date: null, index: i });
    }

    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      dayList.push({
        day,
        date: new Date(year, month, day),
        index: startingDay + day - 1,
      });
    }

    // Pad to complete the last week
    const remainder = dayList.length % 7;
    if (remainder !== 0) {
      for (let i = 0; i < 7 - remainder; i++) {
        dayList.push({ day: null, date: null, index: dayList.length });
      }
    }

    // Group into weeks (rows of 7)
    const weekList = [];
    for (let i = 0; i < dayList.length; i += 7) {
      weekList.push(dayList.slice(i, i + 7));
    }

    return { days: dayList, weeks: weekList };
  }, [currentDate]);

  const selectedDateString = useMemo(() => selectedDate?.toDateString(), [selectedDate]);

  const hasAppointmentsOnDate = useCallback((date) => {
    if (!date) return false;
    return eventDateSet?.has(date.toDateString()) || false;
  }, [eventDateSet]);

  const isSelected = useCallback((date) => {
    if (!date) return false;
    return date.toDateString() === selectedDateString;
  }, [selectedDateString]);

  // Initialize focused index to the selected date or today
  useEffect(() => {
    const targetDate = selectedDate || new Date();
    const idx = days.findIndex(d => d.date && d.date.toDateString() === targetDate.toDateString());
    if (idx >= 0) {
      setFocusedIndex(idx);
    } else {
      // Focus first valid day
      const firstValid = days.findIndex(d => d.day !== null);
      setFocusedIndex(firstValid >= 0 ? firstValid : null);
    }
  }, [days, selectedDate]);

  // Focus the cell when focusedIndex changes
  useEffect(() => {
    if (focusedIndex !== null && cellRefs.current[focusedIndex]) {
      cellRefs.current[focusedIndex].focus();
    }
  }, [focusedIndex]);

  // Find the next valid cell in a direction
  const findNextValidIndex = useCallback((currentIdx, direction) => {
    let nextIdx;
    switch (direction) {
      case 'left':
        nextIdx = currentIdx - 1;
        break;
      case 'right':
        nextIdx = currentIdx + 1;
        break;
      case 'up':
        nextIdx = currentIdx - 7;
        break;
      case 'down':
        nextIdx = currentIdx + 7;
        break;
      case 'home': {
        // First day in the current row
        const rowStart = Math.floor(currentIdx / 7) * 7;
        for (let i = rowStart; i < rowStart + 7; i++) {
          if (days[i] && days[i].day !== null) return i;
        }
        return currentIdx;
      }
      case 'end': {
        // Last day in the current row
        const rowEnd = Math.floor(currentIdx / 7) * 7 + 6;
        for (let i = rowEnd; i >= Math.floor(currentIdx / 7) * 7; i--) {
          if (days[i] && days[i].day !== null) return i;
        }
        return currentIdx;
      }
      default:
        return currentIdx;
    }

    // Bounds check
    if (nextIdx < 0 || nextIdx >= days.length) return currentIdx;
    // Skip empty cells
    if (days[nextIdx] && days[nextIdx].day === null) return currentIdx;
    return nextIdx;
  }, [days]);

  const handleCellKeyDown = useCallback((e, index) => {
    let newIndex = index;
    let handled = false;

    switch (e.key) {
      case 'ArrowLeft':
        newIndex = findNextValidIndex(index, 'left');
        handled = true;
        break;
      case 'ArrowRight':
        newIndex = findNextValidIndex(index, 'right');
        handled = true;
        break;
      case 'ArrowUp':
        newIndex = findNextValidIndex(index, 'up');
        handled = true;
        break;
      case 'ArrowDown':
        newIndex = findNextValidIndex(index, 'down');
        handled = true;
        break;
      case 'Home':
        newIndex = findNextValidIndex(index, 'home');
        handled = true;
        break;
      case 'End':
        newIndex = findNextValidIndex(index, 'end');
        handled = true;
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (days[index] && days[index].date) {
          onDateClick(days[index].date);
        }
        return;
      default:
        return;
    }

    if (handled) {
      e.preventDefault();
      if (newIndex !== index) {
        setFocusedIndex(newIndex);
      }
    }
  }, [days, findNextValidIndex, onDateClick]);

  const monthLabel = `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;

  // Build responsive CSS class list
  const containerClasses = [
    'mini-calendar',
    effectiveCompact ? 'calendar-grid-tablet' : '',
    isTabletPortrait ? 'calendar-grid-portrait' : '',
  ].filter(Boolean).join(' ');

  // Choose day name labels based on responsive state
  const dayNameLabels = effectiveAbbreviate ? ABBREVIATED_DAY_NAMES : SHORT_DAY_NAMES;

  return (
    <div className={containerClasses} role="region" aria-label="Calendar">
      <div className="calendar-header" role="toolbar" aria-label="Calendar navigation">
        <button
          className="nav-btn"
          onClick={onPreviousMonth}
          aria-label="Previous month"
        >
          {'<'}
        </button>
        <span
          className="month-year"
          onClick={onGoToToday}
          title="Click to go to today"
          role="heading"
          aria-level={2}
          aria-live="polite"
          aria-atomic="true"
        >
          {monthLabel}
        </span>
        <button
          className="nav-btn"
          onClick={onNextMonth}
          aria-label="Next month"
        >
          {'>'}
        </button>
      </div>

      <table
        ref={gridRef}
        className={`calendar-grid${visibleDays !== 7 ? ` calendar-grid-days-${visibleDays}` : ''}${effectiveCompact ? ' calendar-grid-compact' : ''}`}
        role="grid"
        aria-label={`${monthLabel} calendar`}
        style={visibleDays !== 7 ? { '--visible-cols': visibleDays } : undefined}
      >
        <thead>
          <tr role="row">
            {dayNameLabels.slice(0, visibleDays).map((day, index) => (
              <th
                key={index}
                className="day-name"
                role="columnheader"
                scope="col"
                aria-label={FULL_DAY_NAMES[index]}
              >
                {day}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, weekIndex) => (
            <tr key={weekIndex} role="row">
              {week.map((item) => {
                if (!item.day) {
                  return (
                    <td
                      key={item.index}
                      className="calendar-day empty"
                      role="gridcell"
                      aria-disabled="true"
                    >
                      <ScreenReaderOnly>Empty</ScreenReaderOnly>
                    </td>
                  );
                }

                const todayDate = isToday(item.date);
                const selected = isSelected(item.date);
                const hasEvents = hasAppointmentsOnDate(item.date);
                const isFocused = focusedIndex === item.index;
                const fullDateLabel = formatFullDateLabel(item.date);

                return (
                  <td
                    key={item.index}
                    ref={(el) => { cellRefs.current[item.index] = el; }}
                    className={`calendar-day${todayDate ? ' today' : ''}${selected ? ' selected' : ''}${hasEvents ? ' has-events' : ''}`}
                    role="gridcell"
                    tabIndex={isFocused ? 0 : -1}
                    aria-label={`${fullDateLabel}${hasEvents ? ', has appointments' : ''}`}
                    aria-selected={selected || undefined}
                    aria-current={todayDate ? 'date' : undefined}
                    onClick={() => onDateClick(item.date)}
                    onKeyDown={(e) => handleCellKeyDown(e, item.index)}
                  >
                    <span className="day-number">{item.day}</span>
                    {hasEvents && (
                      <span className="event-dot" aria-hidden="true" />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

export default CalendarGrid;
