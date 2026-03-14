import React from 'react';

/**
 * CalendarToolbar -- Page-level header with view switcher, date navigation, search, and action buttons.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {string} props.headerSubtitle - Date range or day label string displayed below the title
 * @param {string} props.view - Current calendar view ('day'|'week'|'month')
 * @param {Function} props.onViewChange - Callback(viewKey) to switch between day/week/month
 * @param {Function} props.onPrev - Navigate to the previous period
 * @param {Function} props.onNext - Navigate to the next period
 * @param {Function} props.onToday - Navigate to today
 * @param {Function} props.onSearchOpen - Open the search overlay (Ctrl+K)
 * @param {Function} props.onAddEvent - Open the add event modal
 * @param {Function} props.onShortcutsOpen - Open keyboard shortcuts help dialog
 * @param {Function} props.onTourStart - Start the guided tour
 * @param {Function} props.onSettingsClick - Navigate to calendar settings page
 * @param {boolean} [props.hasKeyboardShortcuts=true] - Whether to show the keyboard shortcuts button
 * @param {boolean} [props.hasTour=false] - Whether to show the guided tour button
 * @returns {React.ReactElement}
 *
 * @example
 * <CalendarToolbar
 *   headerSubtitle="March 10 - 16, 2026"
 *   view="week"
 *   onViewChange={setView}
 *   onPrev={goBack}
 *   onNext={goForward}
 *   onToday={goToToday}
 *   onSearchOpen={openSearch}
 *   onAddEvent={openAddModal}
 *   onShortcutsOpen={openShortcuts}
 *   onSettingsClick={goToSettings}
 * />
 */
const CalendarToolbar = React.memo(function CalendarToolbar({
  headerSubtitle,
  view,
  onViewChange,
  onPrev,
  onNext,
  onToday,
  onSearchOpen,
  onAddEvent,
  onShortcutsOpen,
  onTourStart,
  onSettingsClick,
  hasKeyboardShortcuts = true,
  hasTour = false,
}) {
  return (
    <div className="calendar-header">
      <div>
        <h1>Smart Calendar</h1>
        <p>{headerSubtitle}</p>
      </div>
      <div className="calendar-controls">
        <div className="view-switcher" role="tablist" aria-label="Calendar view">
          <button
            role="tab"
            aria-selected={view === 'day'}
            className={view === 'day' ? 'active' : ''}
            onClick={() => onViewChange('day')}
          >
            Day
          </button>
          <button
            role="tab"
            aria-selected={view === 'week'}
            className={view === 'week' ? 'active' : ''}
            onClick={() => onViewChange('week')}
          >
            Week
          </button>
          <button
            role="tab"
            aria-selected={view === 'month'}
            className={view === 'month' ? 'active' : ''}
            onClick={() => onViewChange('month')}
          >
            Month
          </button>
        </div>
        <div className="month-navigation">
          <button onClick={onPrev} aria-label={`Previous ${view}`}>&larr;</button>
          <button onClick={onToday}>Today</button>
          <button onClick={onNext} aria-label={`Next ${view}`}>&rarr;</button>
          <button
            className="btn-calendar-search"
            onClick={onSearchOpen}
            title="Search appointments (Ctrl+K)"
            aria-label="Search appointments"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            Search
            <span className="search-shortcut">{navigator.platform?.includes('Mac') ? '\u2318K' : 'Ctrl+K'}</span>
          </button>
          <button className="btn-add-event" onClick={onAddEvent}>
            + Add Event
          </button>
          {hasKeyboardShortcuts && (
            <button
              className="btn-calendar-shortcuts"
              onClick={onShortcutsOpen}
              title="Keyboard shortcuts (?)"
              aria-label="Show keyboard shortcuts"
              style={{
                background: 'none',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                padding: '6px 10px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 600,
                color: '#6b7280',
                lineHeight: 1,
              }}
            >
              ?
            </button>
          )}
          {hasTour && (
            <button
              className="btn-calendar-tour"
              onClick={onTourStart}
              title="Start guided tour"
              aria-label="Start guided tour"
              style={{
                background: 'none',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                padding: '6px 8px',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#6b7280',
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </button>
          )}
          <button className="btn-calendar-settings" onClick={onSettingsClick} title="Calendar Settings" aria-label="Calendar Settings">
            <i className="fas fa-cog"></i>
          </button>
        </div>
      </div>
    </div>
  );
});

export default CalendarToolbar;
