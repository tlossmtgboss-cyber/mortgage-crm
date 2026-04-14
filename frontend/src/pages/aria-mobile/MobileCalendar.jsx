import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI } from '../../services/api';
import AriaTabNav from '../../components/mobile/AriaTabNav';
import './MobileCalendar.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAY_NAMES = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
  'Friday', 'Saturday',
];

const TABS = [
  { key: 'appointments', label: 'Appointments' },
  { key: 'closings', label: 'Closings' },
];

const BORDER_COLORS = {
  pre_purchase: '#7EB8F7',
  pre_purchase_consultation: '#7EB8F7',
  initial_discovery: '#f44336',
  annual_review: '#FBBC04',
  closing: '#34A853',
  pending: '#FBBC04',
  high_priority: '#f44336',
  default: '#7EB8F7',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isSameDay(d1, d2) {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

function isToday(date) {
  return isSameDay(date, new Date());
}

function formatDateHeader(dateStr) {
  const d = new Date(dateStr);
  const dayName = DAY_NAMES[d.getDay()];
  const month = MONTH_NAMES[d.getMonth()].slice(0, 3);
  return `${dayName}, ${month} ${d.getDate()}, ${d.getFullYear()}`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function getBorderColor(appointment) {
  if (appointment.priority === 'high' || appointment.is_urgent) {
    return BORDER_COLORS.high_priority;
  }
  if (appointment.status === 'pending') {
    return BORDER_COLORS.pending;
  }
  const type = (appointment.appointment_type || appointment.type || '').toLowerCase().replace(/\s+/g, '_');
  if (type.includes('closing')) return BORDER_COLORS.closing;
  if (type.includes('initial') || type.includes('discovery')) return BORDER_COLORS.initial_discovery;
  if (type.includes('annual') || type.includes('review')) return BORDER_COLORS.annual_review;
  if (type.includes('pre_purchase') || type.includes('consultation')) return BORDER_COLORS.pre_purchase;
  return BORDER_COLORS.default;
}

function groupByDate(items) {
  const groups = {};
  items.forEach((item) => {
    const dateKey = new Date(item.start_time || item.scheduled_date || item.date).toLocaleDateString('en-US');
    if (!groups[dateKey]) {
      groups[dateKey] = { dateKey, dateStr: item.start_time || item.scheduled_date || item.date, items: [] };
    }
    groups[dateKey].items.push(item);
  });
  // Sort groups chronologically
  return Object.values(groups).sort(
    (a, b) => new Date(a.dateStr) - new Date(b.dateStr)
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SkeletonCards() {
  return (
    <div className="mcal-skeleton">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="mcal-skeleton-group">
          <div className="mcal-skeleton-date" />
          <div className="mcal-skeleton-card" />
          {i % 2 === 0 && <div className="mcal-skeleton-card" />}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ activeTab }) {
  return (
    <div className="mcal-empty">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mcal-empty-icon">
        <rect x="6" y="10" width="36" height="32" rx="4" stroke="#ccc" strokeWidth="2" fill="none" />
        <line x1="6" y1="18" x2="42" y2="18" stroke="#ccc" strokeWidth="2" />
        <line x1="16" y1="6" x2="16" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="6" x2="32" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <circle cx="24" cy="30" r="4" stroke="#ccc" strokeWidth="1.5" fill="none" />
        <line x1="27" y1="33" x2="31" y2="37" stroke="#ccc" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="mcal-empty-text">
        No {activeTab === 'closings' ? 'closings' : 'appointments'} this month
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Appointment card
// ---------------------------------------------------------------------------

function AppointmentCard({ appointment, onClick }) {
  const borderColor = getBorderColor(appointment);
  const type = appointment.appointment_type || appointment.type || 'Appointment';
  const name =
    appointment.client_name ||
    appointment.lead_name ||
    appointment.contact_name ||
    appointment.title ||
    'Untitled';
  const timeStr = formatTime(appointment.start_time || appointment.scheduled_date);
  const endTimeStr = formatTime(appointment.end_time);

  return (
    <button
      className="mcal-card"
      style={{ borderLeftColor: borderColor }}
      onClick={onClick}
      type="button"
    >
      <div className="mcal-card-name">{name}</div>
      <div className="mcal-card-type">{type}</div>
      <div className="mcal-card-time">
        {timeStr}
        {endTimeStr ? ` - ${endTimeStr}` : ''}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// MobileCalendar component
// ---------------------------------------------------------------------------

export default function MobileCalendar() {
  const navigate = useNavigate();

  // State
  const [currentDate, setCurrentDate] = useState(new Date());
  const [activeTab, setActiveTab] = useState('appointments');
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showMonthNav, setShowMonthNav] = useState(false);

  // Derived
  const monthLabel = `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  const month = currentDate.getMonth() + 1;
  const year = currentDate.getFullYear();

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = { month, year };
      if (activeTab === 'closings') {
        params.type = 'closing';
      }
      const data = await schedulerAPI.getAppointments(params);
      const items = Array.isArray(data) ? data : (data?.appointments || data?.items || []);

      // Filter for closings tab
      let filtered = items;
      if (activeTab === 'closings') {
        filtered = items.filter((item) => {
          const t = (item.appointment_type || item.type || '').toLowerCase();
          return t.includes('closing') || t.includes('close');
        });
      }

      setAppointments(filtered);
    } catch (err) {
      console.error('Failed to fetch appointments:', err);
      setAppointments([]);
    } finally {
      setLoading(false);
    }
  }, [month, year, activeTab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // -------------------------------------------------------------------------
  // Month navigation
  // -------------------------------------------------------------------------

  const goToPrevMonth = useCallback(() => {
    setCurrentDate((prev) => {
      const d = new Date(prev);
      d.setMonth(d.getMonth() - 1);
      return d;
    });
  }, []);

  const goToNextMonth = useCallback(() => {
    setCurrentDate((prev) => {
      const d = new Date(prev);
      d.setMonth(d.getMonth() + 1);
      return d;
    });
  }, []);

  const goToToday = useCallback(() => {
    setCurrentDate(new Date());
  }, []);

  // -------------------------------------------------------------------------
  // Grouped data
  // -------------------------------------------------------------------------

  const dateGroups = useMemo(() => groupByDate(appointments), [appointments]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  const handleCardTap = useCallback(
    (appointment) => {
      navigate(`/mobile-appointment/${appointment.id}`);
    },
    [navigate]
  );

  const handleFabPress = useCallback(() => {
    navigate('/calendar');
  }, [navigate]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="mcal-page">
      {/* ===== STICKY HEADER ===== */}
      <header className="mcal-header">
        <div className="mcal-header-top">
          <div className="mcal-month-row">
            <button
              className="mcal-month-toggle"
              onClick={() => setShowMonthNav((v) => !v)}
              type="button"
            >
              <span className="mcal-month-label">{monthLabel}</span>
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                className={`mcal-month-chevron ${showMonthNav ? 'mcal-month-chevron--open' : ''}`}
              >
                <path d="M3 4.5L6 7.5L9 4.5" stroke="#333" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button className="mcal-filter-btn" type="button" aria-label="Filter">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M2 4h14M5 9h8M7 14h4" stroke="#666" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {/* Month navigation (collapsible) */}
          {showMonthNav && (
            <div className="mcal-month-nav">
              <button className="mcal-nav-arrow" onClick={goToPrevMonth} type="button" aria-label="Previous month">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M12 4L6 10L12 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <button className="mcal-today-btn" onClick={goToToday} type="button">
                Today
              </button>
              <button className="mcal-nav-arrow" onClick={goToNextMonth} type="button" aria-label="Next month">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M8 4L14 10L8 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="mcal-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`mcal-tab ${activeTab === tab.key ? 'mcal-tab--active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* ===== BODY ===== */}
      <main className="mcal-body">
        {loading ? (
          <SkeletonCards />
        ) : appointments.length === 0 ? (
          <EmptyState activeTab={activeTab} />
        ) : (
          dateGroups.map((group) => {
            const groupDate = new Date(group.dateStr);
            const todayFlag = isToday(groupDate);
            return (
              <section key={group.dateKey} className="mcal-date-group">
                <div className="mcal-date-header">
                  <span className="mcal-date-text">{formatDateHeader(group.dateStr)}</span>
                  {todayFlag && <span className="mcal-today-badge">Today</span>}
                </div>
                {group.items.map((appt) => (
                  <AppointmentCard
                    key={appt.id || `${appt.start_time}-${appt.client_name}`}
                    appointment={appt}
                    onClick={() => handleCardTap(appt)}
                  />
                ))}
              </section>
            );
          })
        )}
      </main>

      {/* ===== TAB NAV ===== */}
      <AriaTabNav
        variant="light"
        activeTab="calendar"
        showFab={true}
        onFabPress={handleFabPress}
      />
    </div>
  );
}
