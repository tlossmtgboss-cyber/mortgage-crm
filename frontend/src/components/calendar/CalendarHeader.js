import React from 'react';
import LiveRegion from '../common/LiveRegion';

/**
 * VIEW_OPTIONS - Available calendar views with labels.
 */
const VIEW_OPTIONS = [
  { key: 'day', label: 'Day' },
  { key: '3day', label: '3-Day' },
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
];

/**
 * CalendarHeader - Accessible calendar header with navigation controls.
 *
 * Features:
 * - aria-label on navigation buttons ("Previous month", "Next month")
 * - aria-live="polite" region for month/year display (announces changes)
 * - role="toolbar" for button groups
 * - View switcher buttons with aria-pressed states
 * - Compact layout mode for tablet screens (date range text + dropdown)
 * - Navigation buttons can stack vertically when compact is true
 *
 * Props:
 *   title          - The current month/year or date range label
 *   onPrevious     - Navigate to previous period
 *   onNext         - Navigate to next period
 *   onToday        - Navigate to today
 *   view           - Current view ('day', '3day', 'week', 'month')
 *   onViewChange   - Callback to change view
 *   prevLabel      - Label for previous button (default: "Previous month")
 *   nextLabel      - Label for next button (default: "Next month")
 *   compact        - Enable compact tablet layout (default: false)
 *   stackNav       - Stack navigation buttons vertically (default: false)
 */
const CalendarHeader = React.memo(function CalendarHeader({
  title,
  onPrevious,
  onNext,
  onToday,
  view,
  onViewChange,
  prevLabel = 'Previous month',
  nextLabel = 'Next month',
  compact = false,
  stackNav = false,
}) {
  return (
    <header className={`calendar-page-header${compact ? ' calendar-header-compact' : ''}`} role="banner">
      {/* Navigation toolbar */}
      <div className={`calendar-nav-toolbar${stackNav ? ' calendar-nav-stacked' : ''}`} role="toolbar" aria-label="Calendar navigation">
        <button
          className="nav-btn"
          onClick={onPrevious}
          aria-label={prevLabel}
          type="button"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <button
          className="today-btn"
          onClick={onToday}
          aria-label="Go to today"
          type="button"
        >
          Today
        </button>

        <button
          className="nav-btn"
          onClick={onNext}
          aria-label={nextLabel}
          type="button"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Month/Year live region - announces changes to screen readers */}
      {compact ? (
        <span className="date-range-text" aria-live="polite" aria-atomic="true">
          {title}
        </span>
      ) : (
        <LiveRegion
          politeness="polite"
          message={title}
          visible={true}
          as="h1"
          className="calendar-title"
          debounceMs={150}
        />
      )}

      {/* View switcher toolbar */}
      {onViewChange && (
        <div className="calendar-view-toolbar" role="toolbar" aria-label="Calendar view">
          {VIEW_OPTIONS.map((v) => (
            <button
              key={v.key}
              className={`view-btn ${view === v.key ? 'active' : ''}`}
              onClick={() => onViewChange(v.key)}
              aria-pressed={view === v.key}
              type="button"
            >
              {v.label}
            </button>
          ))}
        </div>
      )}
    </header>
  );
});

export default CalendarHeader;
