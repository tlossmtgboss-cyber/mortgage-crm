import React, { useCallback, useRef, useEffect } from 'react';

/**
 * VIEW_OPTIONS - Available calendar views with labels and icon SVGs.
 *
 * Each view has:
 *   key   - Internal view identifier
 *   label - Display text for desktop
 *   icon  - SVG path(s) for compact/mobile mode
 *   ariaLabel - Accessible label for icon-only buttons
 */
const VIEW_OPTIONS = [
  {
    key: 'day',
    label: 'Day',
    ariaLabel: 'Day view',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <line x1="12" y1="4" x2="12" y2="10" />
      </svg>
    ),
  },
  {
    key: 'week',
    label: 'Week',
    ariaLabel: 'Week view',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <line x1="8" y1="4" x2="8" y2="22" />
        <line x1="16" y1="4" x2="16" y2="22" />
      </svg>
    ),
  },
  {
    key: 'month',
    label: 'Month',
    ariaLabel: 'Month view',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <line x1="9" y1="4" x2="9" y2="22" />
        <line x1="15" y1="4" x2="15" y2="22" />
        <line x1="3" y1="15" x2="21" y2="15" />
      </svg>
    ),
  },
  {
    key: 'agenda',
    label: 'Agenda',
    ariaLabel: 'Agenda view',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
      </svg>
    ),
  },
];

const STORAGE_KEY = 'perennia-calendar-view';

/**
 * ViewSwitcher - Button group for switching between calendar views.
 *
 * Features:
 * - Button group: Day | Week | Month | Agenda
 * - Active view highlighted with aria-pressed
 * - Compact variant for mobile (icon-only buttons)
 * - Keyboard accessible: arrow keys to move between views
 * - Persists selected view in localStorage
 *
 * Props:
 *   view        - Current active view key ('day' | 'week' | 'month' | 'agenda')
 *   onViewChange - Callback when a view is selected
 *   compact     - If true, render icon-only buttons for mobile (default: false)
 *   className   - Additional CSS class names
 */
const ViewSwitcher = React.memo(function ViewSwitcher({
  view,
  onViewChange,
  compact = false,
  className = '',
}) {
  const groupRef = useRef(null);
  const buttonRefs = useRef({});

  // Persist view selection to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, view);
    } catch {
      // localStorage may be unavailable
    }
  }, [view]);

  const currentIndex = VIEW_OPTIONS.findIndex(v => v.key === view);

  const handleKeyDown = useCallback((e) => {
    const idx = VIEW_OPTIONS.findIndex(v => v.key === view);
    let nextIdx = idx;

    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault();
        nextIdx = (idx + 1) % VIEW_OPTIONS.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault();
        nextIdx = (idx - 1 + VIEW_OPTIONS.length) % VIEW_OPTIONS.length;
        break;
      case 'Home':
        e.preventDefault();
        nextIdx = 0;
        break;
      case 'End':
        e.preventDefault();
        nextIdx = VIEW_OPTIONS.length - 1;
        break;
      default:
        return;
    }

    const nextView = VIEW_OPTIONS[nextIdx];
    onViewChange(nextView.key);
    // Focus the newly active button
    const btn = buttonRefs.current[nextView.key];
    if (btn) btn.focus();
  }, [view, onViewChange]);

  const containerClasses = [
    'cv-view-switcher',
    compact ? 'cv-view-switcher--compact' : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <div
      ref={groupRef}
      className={containerClasses}
      role="tablist"
      aria-label="Calendar view"
      onKeyDown={handleKeyDown}
    >
      {VIEW_OPTIONS.map((v, idx) => {
        const isActive = view === v.key;
        return (
          <button
            key={v.key}
            ref={(el) => { buttonRefs.current[v.key] = el; }}
            className={`cv-view-btn ${isActive ? 'cv-view-btn--active' : ''}`}
            role="tab"
            aria-selected={isActive}
            aria-label={compact ? v.ariaLabel : undefined}
            tabIndex={isActive ? 0 : -1}
            type="button"
            onClick={() => onViewChange(v.key)}
            title={compact ? v.label : undefined}
          >
            {compact ? (
              v.icon
            ) : (
              <>
                <span className="cv-view-btn__icon">{v.icon}</span>
                <span className="cv-view-btn__label">{v.label}</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
});

/**
 * getPersistedView - Read the persisted view from localStorage.
 * Falls back to defaultView if nothing is stored or localStorage is unavailable.
 */
export function getPersistedView(defaultView = 'month') {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && VIEW_OPTIONS.some(v => v.key === stored)) {
      return stored;
    }
  } catch {
    // localStorage unavailable
  }
  return defaultView;
}

export { VIEW_OPTIONS, STORAGE_KEY };
export default ViewSwitcher;
