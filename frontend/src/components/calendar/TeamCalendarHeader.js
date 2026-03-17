import React, { useMemo } from 'react';

/**
 * TeamCalendarHeader - Top controls for the team calendar page.
 *
 * Props:
 *   date             - Current selected Date object
 *   onDateChange     - (newDate: Date) => void
 *   viewMode         - 'day' | 'week' | 'availability'
 *   onViewModeChange - (mode: string) => void
 *   teamMembers      - Array of { id, first_name, last_name } from team API
 *   filterLoIds      - Array of selected LO ids
 *   onFilterLoChange - (ids: number[]) => void
 *   searchTerm       - String
 *   onSearchChange   - (term: string) => void
 *   filterType       - String appointment type filter
 *   onFilterTypeChange - (type: string) => void
 *   filterStatus     - String status filter
 *   onFilterStatusChange - (status: string) => void
 *   capacitySummary  - { total, booked, pct } aggregate across team for the day
 */

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function getStartOfWeek(d) {
  const out = new Date(d);
  out.setDate(out.getDate() - out.getDay());
  out.setHours(0, 0, 0, 0);
  return out;
}

function TeamCalendarHeader({
  date,
  onDateChange,
  viewMode,
  onViewModeChange,
  teamMembers = [],
  filterLoIds = [],
  onFilterLoChange,
  searchTerm = '',
  onSearchChange,
  filterType = 'all',
  onFilterTypeChange,
  filterStatus = 'all',
  onFilterStatusChange,
  capacitySummary,
}) {
  // -----------------------------------------------------------------------
  // Navigation
  // -----------------------------------------------------------------------
  const goToday = () => onDateChange(new Date());

  const goPrev = () => {
    const d = new Date(date);
    d.setDate(d.getDate() - (viewMode === 'week' ? 7 : 1));
    onDateChange(d);
  };

  const goNext = () => {
    const d = new Date(date);
    d.setDate(d.getDate() + (viewMode === 'week' ? 7 : 1));
    onDateChange(d);
  };

  const dateLabel = useMemo(() => {
    if (viewMode === 'week') {
      const start = getStartOfWeek(date);
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return `${MONTH_NAMES[start.getMonth()]} ${start.getDate()} - ${MONTH_NAMES[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
    }
    return `${DAY_NAMES[date.getDay()]}, ${MONTH_NAMES[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
  }, [date, viewMode]);

  // -----------------------------------------------------------------------
  // LO filter - multi-select via checkboxes in a dropdown
  // -----------------------------------------------------------------------
  const [loDropdownOpen, setLoDropdownOpen] = React.useState(false);
  const dropdownRef = React.useRef(null);

  React.useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setLoDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleLoFilter = (id) => {
    const numId = parseInt(id, 10);
    if (filterLoIds.includes(numId)) {
      onFilterLoChange(filterLoIds.filter((x) => x !== numId));
    } else {
      onFilterLoChange([...filterLoIds, numId]);
    }
  };

  const loFilterLabel = useMemo(() => {
    if (filterLoIds.length === 0) return 'All LOs';
    if (filterLoIds.length === 1) {
      const m = teamMembers.find((tm) => tm.id === filterLoIds[0]);
      return m ? `${m.first_name} ${m.last_name}` : '1 LO';
    }
    return `${filterLoIds.length} LOs selected`;
  }, [filterLoIds, teamMembers]);

  // -----------------------------------------------------------------------
  // Capacity summary bar
  // -----------------------------------------------------------------------
  const capPct = capacitySummary?.pct ?? 0;
  const capClass =
    capPct < 50 ? 'tc-capacity-green' : capPct < 80 ? 'tc-capacity-yellow' : 'tc-capacity-red';

  return (
    <>
      {/* Title + controls row */}
      <div className="team-calendar-header">
        <div>
          <h1>Team Calendar</h1>
          <p>Side-by-side schedule view for all loan officers</p>
        </div>
        <div className="tc-controls">
          <div className="tc-view-switcher">
            <button
              className={viewMode === 'day' ? 'active' : ''}
              onClick={() => onViewModeChange('day')}
            >
              Day
            </button>
            <button
              className={viewMode === 'week' ? 'active' : ''}
              onClick={() => onViewModeChange('week')}
            >
              Week
            </button>
            <button
              className={viewMode === 'availability' ? 'active' : ''}
              onClick={() => onViewModeChange('availability')}
            >
              Availability
            </button>
          </div>
          <div className="tc-date-nav">
            <button onClick={goPrev} aria-label="Previous">&lsaquo;</button>
            <span className="tc-date-label">{dateLabel}</span>
            <button onClick={goNext} aria-label="Next">&rsaquo;</button>
          </div>
          <button className="tc-today-btn" onClick={goToday}>
            Today
          </button>
        </div>
      </div>

      {/* Capacity summary bar */}
      {capacitySummary && (
        <div className="tc-team-capacity-summary">
          <span className="tc-team-cap-label">Team capacity:</span>
          <div className="tc-team-cap-bar">
            <div
              className={`tc-team-cap-fill ${capClass}`}
              style={{ width: `${Math.min(capPct, 100)}%` }}
            />
          </div>
          <span className={`tc-team-cap-value ${capClass}`}>
            {Math.round(capPct)}% booked ({capacitySummary.booked || 0}/{capacitySummary.total || 0} slots)
          </span>
        </div>
      )}

      {/* Filters bar */}
      <div className="tc-filters">
        <div className="tc-search">
          <span className="tc-search-icon">&#128269;</span>
          <input
            type="text"
            placeholder="Search client name, email, or phone..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        <select
          className="tc-filter-select"
          value={filterType}
          onChange={(e) => onFilterTypeChange(e.target.value)}
          aria-label="Filter by appointment type"
        >
          <option value="all">All Types</option>
          <option value="custom">Custom</option>
          <option value="pre_purchase_consultation">Pre-Purchase</option>
          <option value="purchase_consultation">Purchase</option>
          <option value="closing">Closing</option>
          <option value="call">Call</option>
          <option value="video">Video</option>
        </select>
        <select
          className="tc-filter-select"
          value={filterStatus}
          onChange={(e) => onFilterStatusChange(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="all">All Statuses</option>
          <option value="booked">Booked</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="no_show">No Show</option>
        </select>

        {/* LO multi-select dropdown */}
        {teamMembers.length > 0 && (
          <div className="tc-lo-dropdown" ref={dropdownRef}>
            <button
              className="tc-filter-select tc-lo-dropdown-trigger"
              onClick={() => setLoDropdownOpen((o) => !o)}
              aria-expanded={loDropdownOpen}
              aria-haspopup="listbox"
            >
              {loFilterLabel}
              <span className="tc-dropdown-arrow">{loDropdownOpen ? '\u25B2' : '\u25BC'}</span>
            </button>
            {loDropdownOpen && (
              <div className="tc-lo-dropdown-menu" role="listbox" aria-label="Filter team members">
                <label className="tc-lo-dropdown-item tc-lo-dropdown-all">
                  <input
                    type="checkbox"
                    checked={filterLoIds.length === 0}
                    onChange={() => onFilterLoChange([])}
                  />
                  <span>Show All</span>
                </label>
                {teamMembers.map((m) => (
                  <label key={m.id} className="tc-lo-dropdown-item">
                    <input
                      type="checkbox"
                      checked={filterLoIds.includes(m.id)}
                      onChange={() => toggleLoFilter(m.id)}
                    />
                    <span>
                      {m.first_name} {m.last_name}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default TeamCalendarHeader;
