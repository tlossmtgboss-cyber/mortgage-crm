import React, { useState, useEffect, useRef, useCallback } from 'react';
import { schedulerAPI } from '../../services/api';
import StatusBadge, { STATUS_CONFIG } from './StatusBadge';

/**
 * CalendarSearch - Advanced appointment search with typeahead, filters, and results.
 *
 * Props:
 *   onSelectAppointment(appointment) - called when a result row is clicked
 *   onClose() - called when the search overlay is dismissed
 *   visible - whether the search panel is open
 */

const STATUS_OPTIONS = Object.keys(STATUS_CONFIG).filter(
  s => !['available', 'tentative'].includes(s)
);

const SORT_OPTIONS = [
  { value: 'scheduled_start', label: 'Date' },
  { value: 'created_at', label: 'Created' },
  { value: 'attendee_name', label: 'Attendee' },
  { value: 'title', label: 'Title' },
  { value: 'status', label: 'Status' },
];

function CalendarSearch({ onSelectAppointment, onClose, visible }) {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState({
    status: [],
    dateFrom: '',
    dateTo: '',
    appointmentTypeId: '',
    assignedUserId: '',
    bookedByAi: '',
  });
  const [sortBy, setSortBy] = useState('scheduled_start');
  const [sortOrder, setSortOrder] = useState('desc');
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [results, setResults] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, page_size: 25, total_pages: 1 });
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const inputRef = useRef(null);
  const suggestionsRef = useRef(null);
  const searchTimerRef = useRef(null);
  const suggestTimerRef = useRef(null);

  // Focus input when panel opens
  useEffect(() => {
    if (visible && inputRef.current) {
      setTimeout(() => inputRef.current.focus(), 100);
    }
  }, [visible]);

  // Escape key to close
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && visible) {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [visible, onClose]);

  // Close suggestions when clicking outside
  useEffect(() => {
    const handleClick = (e) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Debounced suggestions fetch
  useEffect(() => {
    if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current);

    if (query.length >= 2) {
      suggestTimerRef.current = setTimeout(async () => {
        try {
          const resp = await schedulerAPI.searchSuggestions(query);
          if (resp?.suggestions) {
            setSuggestions(resp.suggestions);
            setShowSuggestions(true);
          }
        } catch {
          setSuggestions([]);
        }
      }, 300);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }

    return () => {
      if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current);
    };
  }, [query]);

  const executeSearch = useCallback(async (page = 1) => {
    setLoading(true);
    setSearched(true);
    setShowSuggestions(false);
    try {
      const params = {
        page,
        page_size: 25,
        sort_by: sortBy,
        sort_order: sortOrder,
      };
      if (query.trim()) params.q = query.trim();
      if (filters.status.length > 0) params.status = filters.status;
      if (filters.dateFrom) params.date_from = filters.dateFrom;
      if (filters.dateTo) params.date_to = filters.dateTo;
      if (filters.appointmentTypeId) params.appointment_type_id = parseInt(filters.appointmentTypeId, 10);
      if (filters.assignedUserId) params.assigned_user_id = parseInt(filters.assignedUserId, 10);
      if (filters.bookedByAi === 'true') params.booked_by_ai = true;
      if (filters.bookedByAi === 'false') params.booked_by_ai = false;

      const resp = await schedulerAPI.searchAppointments(params);
      setResults(resp?.data || []);
      setMeta(resp?.meta || { total: 0, page: 1, page_size: 25, total_pages: 1 });
    } catch (err) {
      console.error('Search failed:', err);
      setResults([]);
      setMeta({ total: 0, page: 1, page_size: 25, total_pages: 1 });
    } finally {
      setLoading(false);
    }
  }, [query, filters, sortBy, sortOrder]);

  const handleSubmit = (e) => {
    e.preventDefault();
    executeSearch(1);
  };

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion.value);
    setShowSuggestions(false);
    // Trigger search after a tick so state updates
    setTimeout(() => executeSearch(1), 0);
  };

  const toggleStatus = (statusValue) => {
    setFilters(prev => ({
      ...prev,
      status: prev.status.includes(statusValue)
        ? prev.status.filter(s => s !== statusValue)
        : [...prev.status, statusValue],
    }));
  };

  const clearFilters = () => {
    setFilters({
      status: [],
      dateFrom: '',
      dateTo: '',
      appointmentTypeId: '',
      assignedUserId: '',
      bookedByAi: '',
    });
    setQuery('');
    setSortBy('scheduled_start');
    setSortOrder('desc');
    setResults([]);
    setSearched(false);
  };

  const hasActiveFilters = query.trim() || filters.status.length > 0 || filters.dateFrom
    || filters.dateTo || filters.appointmentTypeId || filters.assignedUserId || filters.bookedByAi;

  const formatDate = (isoStr) => {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const formatTime = (isoStr) => {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  };

  if (!visible) return null;

  return (
    <div className="calendar-search-overlay" role="dialog" aria-label="Search appointments">
      <div className="calendar-search-panel">
        {/* Header */}
        <div className="calendar-search-header">
          <h2>Search Appointments</h2>
          <button
            className="calendar-search-close"
            onClick={onClose}
            aria-label="Close search"
          >
            &times;
          </button>
        </div>

        {/* Search Input */}
        <form onSubmit={handleSubmit} className="calendar-search-form">
          <div className="calendar-search-input-wrapper" ref={suggestionsRef}>
            <svg className="calendar-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={inputRef}
              type="text"
              className="calendar-search-input"
              placeholder="Search by name, email, title, notes..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search appointments"
              autoComplete="off"
            />
            {query && (
              <button
                type="button"
                className="calendar-search-clear-input"
                onClick={() => { setQuery(''); setSuggestions([]); }}
                aria-label="Clear search"
              >
                &times;
              </button>
            )}

            {/* Suggestions dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <ul className="calendar-search-suggestions" role="listbox">
                {suggestions.map((s, i) => (
                  <li
                    key={`${s.type}-${s.value}-${i}`}
                    role="option"
                    className="calendar-search-suggestion"
                    onClick={() => handleSuggestionClick(s)}
                  >
                    <span className="suggestion-type-badge">{s.type}</span>
                    <span className="suggestion-label">{s.label}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="calendar-search-actions">
            <button type="submit" className="btn-search-submit" disabled={loading}>
              {loading ? 'Searching...' : 'Search'}
            </button>
            <button
              type="button"
              className={`btn-search-filters ${showFilters ? 'active' : ''}`}
              onClick={() => setShowFilters(!showFilters)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filters
              {filters.status.length > 0 && (
                <span className="filter-badge">{filters.status.length}</span>
              )}
            </button>
            {hasActiveFilters && (
              <button type="button" className="btn-search-clear" onClick={clearFilters}>
                Clear All
              </button>
            )}
          </div>
        </form>

        {/* Filter Bar */}
        {showFilters && (
          <div className="calendar-search-filters">
            {/* Status multi-select */}
            <div className="filter-group">
              <label className="filter-label">Status</label>
              <div className="filter-status-chips">
                {STATUS_OPTIONS.map(s => (
                  <button
                    key={s}
                    type="button"
                    className={`filter-chip ${filters.status.includes(s) ? 'active' : ''}`}
                    onClick={() => toggleStatus(s)}
                    style={filters.status.includes(s) ? {
                      backgroundColor: STATUS_CONFIG[s]?.bg,
                      color: STATUS_CONFIG[s]?.color,
                      borderColor: STATUS_CONFIG[s]?.border,
                    } : undefined}
                  >
                    {STATUS_CONFIG[s]?.label || s}
                  </button>
                ))}
              </div>
            </div>

            {/* Date range */}
            <div className="filter-row">
              <div className="filter-group">
                <label className="filter-label" htmlFor="search-date-from">From</label>
                <input
                  id="search-date-from"
                  type="date"
                  className="filter-date-input"
                  value={filters.dateFrom}
                  onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))}
                />
              </div>
              <div className="filter-group">
                <label className="filter-label" htmlFor="search-date-to">To</label>
                <input
                  id="search-date-to"
                  type="date"
                  className="filter-date-input"
                  value={filters.dateTo}
                  onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))}
                />
              </div>
            </div>

            {/* Sort controls */}
            <div className="filter-row">
              <div className="filter-group">
                <label className="filter-label" htmlFor="search-sort-by">Sort by</label>
                <select
                  id="search-sort-by"
                  className="filter-select"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  {SORT_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="filter-group">
                <label className="filter-label" htmlFor="search-sort-order">Order</label>
                <select
                  id="search-sort-order"
                  className="filter-select"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value)}
                >
                  <option value="desc">Newest first</option>
                  <option value="asc">Oldest first</option>
                </select>
              </div>
            </div>

            {/* AI-booked filter */}
            <div className="filter-row">
              <div className="filter-group">
                <label className="filter-label" htmlFor="search-ai-booked">Booked by</label>
                <select
                  id="search-ai-booked"
                  className="filter-select"
                  value={filters.bookedByAi}
                  onChange={(e) => setFilters(prev => ({ ...prev, bookedByAi: e.target.value }))}
                >
                  <option value="">All</option>
                  <option value="true">AI only</option>
                  <option value="false">Manual only</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        <div className="calendar-search-results">
          {loading && (
            <div className="calendar-search-loading">
              <div className="search-spinner" />
              <span>Searching appointments...</span>
            </div>
          )}

          {!loading && searched && results.length === 0 && (
            <div className="calendar-search-empty">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <p>No appointments found</p>
              <span>Try different keywords or adjust your filters</span>
            </div>
          )}

          {!loading && results.length > 0 && (
            <>
              <div className="search-results-meta">
                Showing {((meta.page - 1) * meta.page_size) + 1}
                {'\u2013'}
                {Math.min(meta.page * meta.page_size, meta.total)} of {meta.total} results
              </div>

              <div className="search-results-list">
                {results.map(apt => (
                  <button
                    key={apt.id}
                    className="search-result-row"
                    onClick={() => onSelectAppointment?.(apt)}
                    type="button"
                  >
                    <div className="result-row-main">
                      <div className="result-row-title">
                        <span className="result-title">{apt.title}</span>
                        <StatusBadge status={apt.status} size="sm" />
                      </div>
                      <div className="result-row-details">
                        {apt.attendee_name && (
                          <span className="result-detail">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                              <circle cx="12" cy="7" r="4" />
                            </svg>
                            {apt.attendee_name}
                          </span>
                        )}
                        {apt.attendee_email && (
                          <span className="result-detail">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <rect x="2" y="4" width="20" height="16" rx="2" />
                              <polyline points="22,7 12,13 2,7" />
                            </svg>
                            {apt.attendee_email}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="result-row-time">
                      <span className="result-date">{formatDate(apt.scheduled_start)}</span>
                      <span className="result-time">{formatTime(apt.scheduled_start)}</span>
                      {apt.duration_minutes && (
                        <span className="result-duration">{apt.duration_minutes} min</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {/* Pagination */}
              {meta.total_pages > 1 && (
                <div className="search-pagination">
                  <button
                    className="pagination-btn"
                    disabled={!meta.has_prev}
                    onClick={() => executeSearch(meta.page - 1)}
                  >
                    &larr; Prev
                  </button>
                  <span className="pagination-info">
                    Page {meta.page} of {meta.total_pages}
                  </span>
                  <button
                    className="pagination-btn"
                    disabled={!meta.has_next}
                    onClick={() => executeSearch(meta.page + 1)}
                  >
                    Next &rarr;
                  </button>
                </div>
              )}
            </>
          )}

          {!loading && !searched && (
            <div className="calendar-search-empty">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <p>Search your appointments</p>
              <span>Find appointments by name, email, title, or notes</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default CalendarSearch;
