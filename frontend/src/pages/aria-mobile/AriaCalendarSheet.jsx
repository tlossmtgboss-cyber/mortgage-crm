import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI } from '../../services/api';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import PullToRefreshContainer from '../../components/mobile/PullToRefreshContainer';
import './AriaCalendarSheet.css';

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

const STATUS_COLORS = {
  scheduled: '#f44336',
  completed: '#34A853',
  in_progress: '#ff9800',
  no_show: '#9e9e9e',
  cancelled: '#9e9e9e',
};

const MAX_CACHE_SIZE = 6;

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

function formatDateRange(scheduledAt, endTime) {
  if (!scheduledAt) return '';
  const start = new Date(scheduledAt);
  const opts = { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' };
  const datePart = start.toLocaleDateString('en-US', opts);
  const timeOpts = { hour: 'numeric', minute: '2-digit', hour12: true };
  const startTime = start.toLocaleTimeString('en-US', timeOpts);
  let endTimePart = '';
  if (endTime) {
    endTimePart = new Date(endTime).toLocaleTimeString('en-US', timeOpts);
  }
  let tzAbbr = '';
  try {
    tzAbbr = start.toLocaleTimeString('en-US', { timeZoneName: 'short' }).split(' ').pop();
  } catch { /* noop */ }
  if (endTimePart) {
    return `${datePart}\n${startTime} – ${endTimePart} ${tzAbbr}`;
  }
  return `${datePart}\n${startTime} ${tzAbbr}`;
}

function getBorderColor(appointment) {
  if (appointment.priority === 'high' || appointment.is_urgent) return BORDER_COLORS.high_priority;
  if (appointment.status === 'pending') return BORDER_COLORS.pending;
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
  return Object.values(groups).sort((a, b) => new Date(a.dateStr) - new Date(b.dateStr));
}

function getInitials(name) {
  if (!name) return '?';
  return name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);
}

function formatPhone(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 10) return `+1 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  if (digits.length === 11 && digits[0] === '1') return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  return phone;
}

function statusLabel(status) {
  if (!status) return 'Unknown';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Icons (inline SVG)
// ---------------------------------------------------------------------------

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M4.5 4.5L13.5 13.5M13.5 4.5L4.5 13.5" stroke="#666" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const PhoneIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.362 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0122 16.92z" />
  </svg>
);

const MailIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="M22 7l-10 7L2 7" />
  </svg>
);

const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#34A853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
    <path d="M22 4L12 14.01l-3-3" />
  </svg>
);

const ChevronRightIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 18l6-6-6-6" />
  </svg>
);

const LocationIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);

// ---------------------------------------------------------------------------
// Sub-components: Loading skeletons
// ---------------------------------------------------------------------------

function ListSkeleton() {
  return (
    <div className="acs-skeleton">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="acs-skeleton-group">
          <div className="acs-skeleton-date" />
          <div className="acs-skeleton-card" />
          {i % 2 === 0 && <div className="acs-skeleton-card" />}
        </div>
      ))}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="acs-detail-skeleton">
      <div className="acs-detail-skeleton__block" style={{ width: 60, height: 16 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '80%', height: 22, marginTop: 12 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '60%', height: 14, marginTop: 8 }} />
      <div className="acs-detail-skeleton__block" style={{ width: 100, height: 13, marginTop: 24 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '90%', height: 16, marginTop: 10 }} />
      <div className="acs-detail-skeleton__block" style={{ width: 120, height: 13, marginTop: 24 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '70%', height: 16, marginTop: 10 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '70%', height: 16, marginTop: 8 }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Empty state
// ---------------------------------------------------------------------------

function EmptyState({ activeTab }) {
  return (
    <div className="acs-empty">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="acs-empty-icon">
        <rect x="6" y="10" width="36" height="32" rx="4" stroke="#ccc" strokeWidth="2" fill="none" />
        <line x1="6" y1="18" x2="42" y2="18" stroke="#ccc" strokeWidth="2" />
        <line x1="16" y1="6" x2="16" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="6" x2="32" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <circle cx="24" cy="30" r="4" stroke="#ccc" strokeWidth="1.5" fill="none" />
        <line x1="27" y1="33" x2="31" y2="37" stroke="#ccc" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="acs-empty-text">
        No {activeTab === 'closings' ? 'closings' : 'appointments'} this month
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Appointment card
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
      className="acs-card"
      style={{ borderLeftColor: borderColor }}
      onClick={onClick}
      type="button"
    >
      <div className="acs-card-name">{name}</div>
      <div className="acs-card-type">{type}</div>
      <div className="acs-card-time">
        {timeStr}
        {endTimeStr ? ` – ${endTimeStr}` : ''}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Confirm modal
// ---------------------------------------------------------------------------

function ConfirmModal({ open, title, message, confirmLabel, cancelLabel, destructive, onConfirm, onCancel }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="acs-confirm-overlay" onClick={onCancel}>
      <div
        className="acs-confirm-dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="acs-confirm-dialog__title">{title}</h2>
        <p className="acs-confirm-dialog__message">{message}</p>
        <div className="acs-confirm-dialog__actions">
          <button
            ref={cancelRef}
            className="acs-confirm-dialog__btn acs-confirm-dialog__btn--cancel"
            onClick={onCancel}
          >
            {cancelLabel || 'Cancel'}
          </button>
          <button
            className={`acs-confirm-dialog__btn ${destructive ? 'acs-confirm-dialog__btn--destructive' : ''}`}
            onClick={onConfirm}
          >
            {confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Detail view
// ---------------------------------------------------------------------------

function DetailView({ appointmentId, onBack }) {
  const navigate = useNavigate();
  const [appointment, setAppointment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('details');
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmModal, setConfirmModal] = useState({ open: false });

  const fetchAppointment = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/api/v1/scheduler/appointments/${appointmentId}`);
      setAppointment(res.data);
    } catch (err) {
      setError(err?.response?.status === 404 ? 'Appointment not found' : 'Failed to load details');
    } finally {
      setLoading(false);
    }
  }, [appointmentId]);

  useEffect(() => {
    if (appointmentId) fetchAppointment();
  }, [appointmentId, fetchAppointment]);

  const handleMarkNoShow = () => {
    setConfirmModal({
      open: true,
      title: 'Mark as No-Show',
      message: 'Are you sure you want to mark this appointment as no-show? This action cannot be undone.',
      confirmLabel: 'Mark No-Show',
      cancelLabel: 'Cancel',
      destructive: true,
      onConfirm: async () => {
        setConfirmModal({ open: false });
        try {
          setActionLoading(true);
          await api.patch(`/api/v1/scheduler/appointments/${appointmentId}`, { status: 'no_show' });
          toast.success('Marked as no-show');
          onBack();
        } catch {
          toast.error('Failed to update appointment status.');
        } finally {
          setActionLoading(false);
        }
      },
    });
  };

  const handleBookFollowUp = () => {
    navigate('/calendar');
  };

  if (loading) {
    return (
      <div className="acs-detail">
        <div className="acs-detail-header">
          <button className="acs-back-btn" onClick={onBack} type="button">
            <span className="acs-back-chevron">&lsaquo;</span> Back
          </button>
        </div>
        <DetailSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="acs-detail">
        <div className="acs-detail-header">
          <button className="acs-back-btn" onClick={onBack} type="button">
            <span className="acs-back-chevron">&lsaquo;</span> Back
          </button>
        </div>
        <div className="acs-placeholder">
          <p className="acs-placeholder__text">{error}</p>
        </div>
      </div>
    );
  }

  const title = appointment?.title || appointment?.name || 'Untitled Appointment';
  const status = appointment?.status || 'scheduled';
  const dateRange = formatDateRange(appointment?.scheduled_at, appointment?.end_time);

  const attendees = appointment?.attendees || [];
  const primaryAttendee = attendees[0] || null;
  const inviteeName = primaryAttendee?.name || primaryAttendee?.first_name
    ? `${primaryAttendee?.first_name || ''} ${primaryAttendee?.last_name || ''}`.trim()
    : appointment?.contact_name || '';
  const inviteeEmail = primaryAttendee?.email || appointment?.email || '';
  const inviteePhone = primaryAttendee?.phone || appointment?.phone || '';
  const inviteeTimezone = primaryAttendee?.timezone || appointment?.timezone || '';
  const hostName = appointment?.host_name || appointment?.loan_officer_name || '';
  const hostPhone = appointment?.host_phone || appointment?.phone || '';
  const location = appointment?.location || '';

  return (
    <div className="acs-detail">
      <div className="acs-detail-header">
        <button className="acs-back-btn" onClick={onBack} type="button">
          <span className="acs-back-chevron">&lsaquo;</span> Back
        </button>
        <div className="acs-detail-title-row">
          <span className="acs-detail-status-dot" style={{ backgroundColor: STATUS_COLORS[status] || '#888' }} />
          <h1 className="acs-detail-title">{title}</h1>
        </div>
        {dateRange && <p className="acs-detail-subtitle" style={{ whiteSpace: 'pre-line' }}>{dateRange}</p>}
      </div>

      <div className="acs-detail-tabs">
        {['details', 'notes', 'history'].map((tab) => (
          <button
            key={tab}
            className={`acs-detail-tab ${activeTab === tab ? 'acs-detail-tab--active' : ''}`}
            onClick={() => setActiveTab(tab)}
            type="button"
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="acs-detail-body">
        {activeTab === 'details' ? (
          <>
            <section className="acs-section">
              <h2 className="acs-section__title">Location</h2>
              <div className="acs-row">
                <div className="acs-row__icon"><LocationIcon /></div>
                <div className="acs-row__content">
                  {location ? (
                    <span className="acs-row__text">{location}</span>
                  ) : hostPhone ? (
                    <span className="acs-row__text">
                      Host will call{' '}
                      <a className="acs-link" href={`tel:${hostPhone}`}>{formatPhone(hostPhone)}</a>
                    </span>
                  ) : (
                    <span className="acs-row__text acs-row__text--muted">No location specified</span>
                  )}
                </div>
              </div>
            </section>

            {(inviteeName || inviteeEmail || inviteePhone) && (
              <section className="acs-section">
                <h2 className="acs-section__title">Invitee Details</h2>
                <div className="acs-row">
                  <div className="acs-avatar acs-avatar--invitee">{getInitials(inviteeName)}</div>
                  <div className="acs-row__content">
                    <span className="acs-invitee-name">{inviteeName || 'Unknown invitee'}</span>
                  </div>
                </div>
                <div className="acs-row">
                  <div className="acs-row__icon"><CheckCircleIcon /></div>
                  <div className="acs-row__content">
                    <span className="acs-row__text">{statusLabel(status)}</span>
                  </div>
                </div>
                {inviteeEmail && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><MailIcon /></div>
                    <div className="acs-row__content">
                      <a className="acs-link" href={`mailto:${inviteeEmail}`}>{inviteeEmail}</a>
                    </div>
                  </div>
                )}
                {inviteePhone && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><PhoneIcon /></div>
                    <div className="acs-row__content">
                      <a className="acs-link" href={`tel:${inviteePhone}`}>{formatPhone(inviteePhone)}</a>
                    </div>
                  </div>
                )}
                {inviteeTimezone && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><GlobeIcon /></div>
                    <div className="acs-row__content">
                      <span className="acs-row__text">{inviteeTimezone}</span>
                    </div>
                  </div>
                )}
              </section>
            )}

            {hostName && (
              <section className="acs-section">
                <h2 className="acs-section__title">Host</h2>
                <div className="acs-host-card">
                  <div className="acs-avatar acs-avatar--host">{getInitials(hostName)}</div>
                  <div className="acs-host-card__info">
                    <span className="acs-host-card__name">{hostName}</span>
                    <span className="acs-host-card__badge">Host</span>
                  </div>
                  <ChevronRightIcon />
                </div>
              </section>
            )}
          </>
        ) : (
          <div className="acs-placeholder">
            <p className="acs-placeholder__text">Coming soon</p>
          </div>
        )}
      </div>

      <div className="acs-detail-footer">
        <button
          className="acs-action-btn acs-action-btn--ghost"
          onClick={handleMarkNoShow}
          disabled={actionLoading}
          type="button"
        >
          {actionLoading ? 'Updating...' : 'Mark as no-show'}
        </button>
        <button
          className="acs-action-btn acs-action-btn--primary"
          onClick={handleBookFollowUp}
          type="button"
        >
          Book follow-up
        </button>
      </div>

      <ConfirmModal
        open={confirmModal.open}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        cancelLabel={confirmModal.cancelLabel}
        destructive={confirmModal.destructive}
        onConfirm={confirmModal.onConfirm || (() => setConfirmModal({ open: false }))}
        onCancel={() => setConfirmModal({ open: false })}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component: AriaCalendarSheet
// ---------------------------------------------------------------------------

export default function AriaCalendarSheet({ open, onClose }) {
  const [view, setView] = useState('list');
  const [selectedAppointmentId, setSelectedAppointmentId] = useState(null);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [activeTab, setActiveTab] = useState('appointments');
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showMonthNav, setShowMonthNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const cacheRef = useRef(new Map());

  const monthLabel = `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  const month = currentDate.getMonth() + 1;
  const year = currentDate.getFullYear();

  // Lock body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  // Reset to list view when panel closes
  useEffect(() => {
    if (!open) {
      const timer = setTimeout(() => {
        setView('list');
        setSelectedAppointmentId(null);
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Cache helpers
  const getCacheKey = useCallback((m, y, tab) => `${y}-${String(m).padStart(2, '0')}:${tab}`, []);

  const trimCache = useCallback(() => {
    const cache = cacheRef.current;
    while (cache.size > MAX_CACHE_SIZE) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }
  }, []);

  // Data fetching
  const processResponse = useCallback((data, tab) => {
    const items = Array.isArray(data) ? data : (data?.appointments || data?.items || []);
    if (tab === 'closings') {
      return items.filter((item) => {
        const t = (item.appointment_type || item.type || '').toLowerCase();
        return t.includes('closing') || t.includes('close');
      });
    }
    return items;
  }, []);

  const fetchData = useCallback(async () => {
    const key = getCacheKey(month, year, activeTab);
    const cached = cacheRef.current.get(key);

    if (cached) {
      setAppointments(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }

    try {
      const params = { month, year };
      if (activeTab === 'closings') params.type = 'closing';
      const data = await schedulerAPI.getAppointments(params);
      const filtered = processResponse(data, activeTab);
      cacheRef.current.set(key, filtered);
      trimCache();
      setAppointments((prev) => {
        const prevJson = JSON.stringify(prev);
        const newJson = JSON.stringify(filtered);
        return prevJson === newJson ? prev : filtered;
      });
    } catch (err) {
      console.error('Failed to fetch appointments:', err);
      if (!cached) setAppointments([]);
    } finally {
      setLoading(false);
    }
  }, [month, year, activeTab, getCacheKey, processResponse, trimCache]);

  useEffect(() => {
    if (open) fetchData();
  }, [open, fetchData]);

  // Pull-to-refresh
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await fetchData(); } finally { setRefreshing(false); }
  }, [fetchData]);

  // Month navigation
  const goToPrevMonth = useCallback(() => {
    setCurrentDate((prev) => { const d = new Date(prev); d.setMonth(d.getMonth() - 1); return d; });
  }, []);
  const goToNextMonth = useCallback(() => {
    setCurrentDate((prev) => { const d = new Date(prev); d.setMonth(d.getMonth() + 1); return d; });
  }, []);
  const goToToday = useCallback(() => { setCurrentDate(new Date()); }, []);

  // Grouped data
  const dateGroups = useMemo(() => groupByDate(appointments), [appointments]);

  // Card tap -> detail
  const handleCardTap = useCallback((appointment) => {
    setSelectedAppointmentId(appointment.id);
    setView('detail');
  }, []);

  // Detail -> back to list
  const handleBackToList = useCallback(() => {
    setView('list');
    setSelectedAppointmentId(null);
  }, []);

  const showDetail = view === 'detail';

  return (
    <div className={`acs-overlay ${open ? 'acs-overlay--open' : ''}`}>
      <div className="acs-panel">
        <div className="acs-views">
          {/* === List View === */}
          <div className={`acs-view ${showDetail ? 'acs-view--list-pushed' : 'acs-view--list'}`}>
            <header className="acs-header">
              <div className="acs-header-top">
                <div className="acs-month-row">
                  <button
                    className="acs-month-toggle"
                    onClick={() => setShowMonthNav((v) => !v)}
                    type="button"
                  >
                    <span className="acs-month-label">{monthLabel}</span>
                    <svg
                      width="12" height="12" viewBox="0 0 12 12" fill="none"
                      className={`acs-month-chevron ${showMonthNav ? 'acs-month-chevron--open' : ''}`}
                    >
                      <path d="M3 4.5L6 7.5L9 4.5" stroke="#333" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <button className="acs-close-btn" onClick={onClose} type="button" aria-label="Close calendar">
                    <CloseIcon />
                  </button>
                </div>
                {showMonthNav && (
                  <div className="acs-month-nav">
                    <button className="acs-nav-arrow" onClick={goToPrevMonth} type="button" aria-label="Previous month">
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M12 4L6 10L12 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                    <button className="acs-today-btn" onClick={goToToday} type="button">Today</button>
                    <button className="acs-nav-arrow" onClick={goToNextMonth} type="button" aria-label="Next month">
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M8 4L14 10L8 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
              <div className="acs-tabs">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    className={`acs-tab ${activeTab === tab.key ? 'acs-tab--active' : ''}`}
                    onClick={() => setActiveTab(tab.key)}
                    type="button"
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </header>

            <PullToRefreshContainer onRefresh={handleRefresh} className="acs-body">
              {loading ? (
                <ListSkeleton />
              ) : appointments.length === 0 ? (
                <EmptyState activeTab={activeTab} />
              ) : (
                dateGroups.map((group) => {
                  const groupDate = new Date(group.dateStr);
                  const todayFlag = isToday(groupDate);
                  return (
                    <section key={group.dateKey} className="acs-date-group">
                      <div className="acs-date-header">
                        <span className="acs-date-text">{formatDateHeader(group.dateStr)}</span>
                        {todayFlag && <span className="acs-today-badge">Today</span>}
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
            </PullToRefreshContainer>
          </div>

          {/* === Detail View === */}
          <div className={`acs-view ${showDetail ? 'acs-view--detail' : 'acs-view--detail-offscreen'}`}>
            {selectedAppointmentId && (
              <DetailView
                appointmentId={selectedAppointmentId}
                onBack={handleBackToList}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
