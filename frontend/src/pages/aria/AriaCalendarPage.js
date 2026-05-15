import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI } from '../../services/api';
import MobileBottomNav from '../../components/mobile/MobileBottomNav';
import './AriaCalendarPage.css';

const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const getEventColor = (type) => {
  const colors = {
    'Initial Discovery Meeting': '#ef4444',
    'Annual Mortgage Review': '#22c55e',
    'Pre-Purchase Consultation': '#B8924A',
    'Purchase Consultation': '#B8924A',
    'Refinance Consultation': '#f59e0b',
    'Closing': '#22c55e',
  };
  return colors[type] || '#94a3b8';
};

const formatTime = (dateStr) => {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
};

const formatTimeRange = (start, end) => {
  return `${formatTime(start)} \u2013 ${formatTime(end)}`;
};

const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

const isToday = (d) => isSameDay(d, new Date());

const formatDateHeader = (d) => {
  const day = dayNames[d.getDay()];
  const month = monthNames[d.getMonth()].substring(0, 3);
  const date = d.getDate();
  const year = d.getFullYear();
  const todayLabel = isToday(d) ? '  Today' : '';
  return `${day}, ${month} ${date}, ${year}${todayLabel}`;
};

export default function AriaCalendarPage() {
  const navigate = useNavigate();
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth());
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [showMonthPicker, setShowMonthPicker] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const todayRef = useRef(null);
  const monthPickerRef = useRef(null);
  const touchStartY = useRef(0);
  const contentRef = useRef(null);

  // Fetch appointments for the selected month
  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const start = new Date(selectedYear, selectedMonth, 1);
      const end = new Date(selectedYear, selectedMonth + 1, 0, 23, 59, 59);
      const res = await schedulerAPI.getAppointments({
        start_date: start.toISOString(),
        end_date: end.toISOString(),
        limit: 200,
      });
      const items = res?.data?.items || res?.data?.appointments || res?.data || [];
      setAppointments(Array.isArray(items) ? items : []);
    } catch (err) {
      console.error('Failed to fetch appointments', err);
      if (err?.response?.status === 401) {
        navigate('/login', { replace: true });
        return;
      }
      setError('Could not load appointments');
      setAppointments([]);
    } finally {
      setLoading(false);
    }
  }, [selectedMonth, selectedYear]);

  useEffect(() => { fetchAppointments(); }, [fetchAppointments]);

  // Scroll to today on initial load
  useEffect(() => {
    if (!loading && todayRef.current) {
      setTimeout(() => todayRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200);
    }
  }, [loading]);

  // Close month picker on outside click
  useEffect(() => {
    const handler = (e) => {
      if (monthPickerRef.current && !monthPickerRef.current.contains(e.target)) {
        setShowMonthPicker(false);
      }
    };
    if (showMonthPicker) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showMonthPicker]);

  // Group appointments by date
  const groupedByDate = useMemo(() => {
    const groups = {};
    for (const appt of appointments) {
      const start = new Date(appt.scheduled_start || appt.start_time || appt.start);
      const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
      if (!groups[key]) groups[key] = { date: new Date(start.getFullYear(), start.getMonth(), start.getDate()), items: [] };
      groups[key].items.push(appt);
    }
    // Sort groups by date, items by start time
    const sorted = Object.values(groups).sort((a, b) => a.date - b.date);
    for (const g of sorted) {
      g.items.sort((a, b) => new Date(a.scheduled_start || a.start_time || a.start) - new Date(b.scheduled_start || b.start_time || b.start));
    }
    return sorted;
  }, [appointments]);

  const changeMonth = (delta) => {
    let m = selectedMonth + delta;
    let y = selectedYear;
    if (m > 11) { m = 0; y++; }
    if (m < 0) { m = 11; y--; }
    setSelectedMonth(m);
    setSelectedYear(y);
    setShowMonthPicker(false);
  };

  const goToToday = () => {
    const now = new Date();
    setSelectedMonth(now.getMonth());
    setSelectedYear(now.getFullYear());
  };

  const toggleExpand = (id) => {
    setExpandedId(prev => prev === id ? null : id);
  };

  const handleTouchStart = (e) => {
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchEnd = async (e) => {
    const diff = e.changedTouches[0].clientY - touchStartY.current;
    const atTop = contentRef.current?.scrollTop === 0;
    if (diff > 80 && atTop && !refreshing) {
      setRefreshing(true);
      await fetchAppointments();
      setRefreshing(false);
    }
  };

  return (
    <div className="aria-calendar-page">
      {/* Header */}
      <div className="aria-cal-header">
        <div className="aria-cal-header__title-row">
          <button className="aria-cal-header__month-btn" onClick={() => setShowMonthPicker(!showMonthPicker)}>
            <span className="aria-cal-header__month">{monthNames[selectedMonth]} {selectedYear}</span>
            <span className="aria-cal-header__chevron">{showMonthPicker ? '\u25B2' : '\u25BC'}</span>
          </button>
          <button className="aria-cal-header__list-btn" onClick={goToToday} aria-label="Go to today" title="Go to today">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <line x1="3" y1="10" x2="21" y2="10" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="16" y1="2" x2="16" y2="6" />
            </svg>
          </button>
        </div>

        {/* Month picker dropdown */}
        {showMonthPicker && (
          <div className="aria-cal-month-picker" ref={monthPickerRef}>
            <div className="aria-cal-month-picker__nav">
              <button onClick={() => setSelectedYear(y => y - 1)}>&laquo;</button>
              <span>{selectedYear}</span>
              <button onClick={() => setSelectedYear(y => y + 1)}>&raquo;</button>
            </div>
            <div className="aria-cal-month-picker__grid" role="grid">
              {monthNames.map((name, idx) => (
                <button
                  key={idx}
                  role="gridcell"
                  aria-label={`Select ${name}`}
                  className={`aria-cal-month-picker__item ${idx === selectedMonth ? 'aria-cal-month-picker__item--active' : ''}`}
                  onClick={() => { setSelectedMonth(idx); setShowMonthPicker(false); }}
                >
                  {name.substring(0, 3)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="aria-cal-content" ref={contentRef} onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
        {refreshing && (
          <div className="aria-cal-refresh">
            <div className="aria-cal-spinner" />
          </div>
        )}

        {loading && (
          <div className="aria-cal-loading">
            <div className="aria-cal-spinner" />
            <p>Loading appointments...</p>
          </div>
        )}

        {error && !loading && (
          <div className="aria-cal-error">
            <p>{error}</p>
            <button onClick={fetchAppointments}>Retry</button>
          </div>
        )}

        {!loading && !error && groupedByDate.length === 0 && (
          <div className="aria-cal-empty">
            <p>No appointments this month</p>
          </div>
        )}

        {!loading && !error && groupedByDate.map((group) => {
          const dateIsToday = isToday(group.date);
          return (
            <div key={group.date.toISOString()} className="aria-cal-day-group" ref={dateIsToday ? todayRef : undefined}>
              <div className={`aria-cal-day-header ${dateIsToday ? 'aria-cal-day-header--today' : ''}`}>
                {formatDateHeader(group.date)}
              </div>
              {group.items.map((appt) => {
                const id = appt.id;
                const title = appt.title || appt.appointment_type_label || 'Appointment';
                const attendee = appt.attendee_name || appt.contact_name || '';
                const loName = appt.assigned_user_name || '';
                const displayName = [attendee, loName].filter(Boolean).join(' and ');
                const startStr = appt.scheduled_start || appt.start_time || appt.start;
                const endStr = appt.scheduled_end || appt.end_time || appt.end;
                const color = getEventColor(title);
                const expanded = expandedId === id;
                const status = appt.status || 'confirmed';
                const location = appt.location || appt.meeting_location || '';
                const meetingMode = appt.meeting_mode || '';
                const notes = appt.notes || appt.description || '';

                return (
                  <div key={id} className={`aria-cal-card ${expanded ? 'aria-cal-card--expanded' : ''}`} onClick={() => toggleExpand(id)}>
                    <div className="aria-cal-card__border" style={{ backgroundColor: color }} />
                    <div className="aria-cal-card__body">
                      {displayName && <div className="aria-cal-card__attendee">{displayName}</div>}
                      <div className="aria-cal-card__title">{title}</div>
                      <div className="aria-cal-card__time">{formatTimeRange(startStr, endStr)}</div>

                      {expanded && (
                        <div className="aria-cal-card__details">
                          {status && <div className="aria-cal-card__detail-row"><span className="aria-cal-card__detail-label">Status</span><span className={`aria-cal-card__status aria-cal-card__status--${status}`}>{status}</span></div>}
                          {meetingMode && <div className="aria-cal-card__detail-row"><span className="aria-cal-card__detail-label">Meeting type</span><span>{meetingMode.replace('_', ' ')}</span></div>}
                          {location && <div className="aria-cal-card__detail-row"><span className="aria-cal-card__detail-label">Location</span><span>{location}</span></div>}
                          {notes && <div className="aria-cal-card__detail-row aria-cal-card__detail-notes"><span className="aria-cal-card__detail-label">Notes</span><p>{notes}</p></div>}
                          <div className="aria-cal-card__actions">
                            <button className="aria-cal-card__action-btn" onClick={(e) => { e.stopPropagation(); navigate(`/calendar?appointment=${id}`); }}>
                              Open in Calendar
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <MobileBottomNav />
    </div>
  );
}
