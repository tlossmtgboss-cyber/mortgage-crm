import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import api from '../../services/api';
import './MobileAppointmentDetail.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS = {
  scheduled: '#f44336',
  completed: '#34A853',
  in_progress: '#ff9800',
  no_show: '#9e9e9e',
  cancelled: '#9e9e9e',
};

function statusDotColor(status) {
  return STATUS_COLORS[status] || '#888';
}

function statusLabel(status) {
  if (!status) return 'Unknown';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
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
    const end = new Date(endTime);
    endTimePart = end.toLocaleTimeString('en-US', timeOpts);
  }

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  // Attempt short timezone name
  let tzAbbr = '';
  try {
    tzAbbr = start.toLocaleTimeString('en-US', { timeZoneName: 'short' }).split(' ').pop();
  } catch {
    tzAbbr = '';
  }

  if (endTimePart) {
    return `${datePart} \u00b7 ${startTime} \u2013 ${endTimePart} ${tzAbbr}`;
  }
  return `${datePart} \u00b7 ${startTime} ${tzAbbr}`;
}

function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function formatPhone(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 10) {
    return `+1 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits[0] === '1') {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return phone;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonBlock({ width, height, style }) {
  return (
    <div
      className="mad-skeleton"
      style={{ width: width || '100%', height: height || 16, borderRadius: 6, ...style }}
    />
  );
}

function LoadingSkeleton() {
  return (
    <div className="mad-container">
      <div className="mad-header">
        <SkeletonBlock width={60} height={16} />
        <SkeletonBlock width="80%" height={22} style={{ marginTop: 12 }} />
        <SkeletonBlock width="60%" height={14} style={{ marginTop: 8 }} />
      </div>
      <div className="mad-body">
        <SkeletonBlock width={100} height={13} style={{ marginTop: 16 }} />
        <SkeletonBlock width="90%" height={16} style={{ marginTop: 10 }} />
        <SkeletonBlock width={120} height={13} style={{ marginTop: 24 }} />
        <SkeletonBlock width="70%" height={16} style={{ marginTop: 10 }} />
        <SkeletonBlock width="70%" height={16} style={{ marginTop: 8 }} />
        <SkeletonBlock width="70%" height={16} style={{ marginTop: 8 }} />
      </div>
    </div>
  );
}

function ErrorState({ message }) {
  const navigate = useNavigate();
  return (
    <div className="mad-container">
      <div className="mad-header">
        <button className="mad-back-btn" onClick={() => navigate(-1)}>
          <span className="mad-back-chevron">&lsaquo;</span> Back
        </button>
      </div>
      <div className="mad-error">
        <div className="mad-error__icon">!</div>
        <p className="mad-error__text">{message || 'Appointment not found'}</p>
        <button className="mad-error__btn" onClick={() => navigate(-1)}>
          Go back
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons (inline SVG to avoid external dependencies)
// ---------------------------------------------------------------------------

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
// Main component
// ---------------------------------------------------------------------------

export default function MobileAppointmentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [appointment, setAppointment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('details');
  const [actionLoading, setActionLoading] = useState(false);

  // Fetch appointment data
  const fetchAppointment = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/api/v1/scheduler/appointments/${id}`);
      setAppointment(res.data);
    } catch (err) {
      const msg =
        err?.response?.status === 404
          ? 'Appointment not found'
          : 'Failed to load appointment details';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (id) fetchAppointment();
  }, [id, fetchAppointment]);

  // Actions
  const handleMarkNoShow = async () => {
    if (!window.confirm('Mark this appointment as no-show?')) return;
    try {
      setActionLoading(true);
      await api.patch(`/api/v1/scheduler/appointments/${id}`, { status: 'no_show' });
      navigate(-1);
    } catch {
      toast.error('Failed to update appointment status. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleBookFollowUp = () => {
    navigate('/calendar');
  };

  // Derived data
  const title = appointment?.title || appointment?.name || 'Untitled Appointment';
  const status = appointment?.status || 'scheduled';
  const dateRange = formatDateRange(appointment?.scheduled_at, appointment?.end_time);

  // Primary attendee (first non-host attendee, or fallback)
  const attendees = appointment?.attendees || [];
  const primaryAttendee = attendees[0] || null;

  const inviteeName = primaryAttendee?.name || primaryAttendee?.first_name
    ? `${primaryAttendee?.first_name || ''} ${primaryAttendee?.last_name || ''}`.trim()
    : appointment?.contact_name || '';
  const inviteeEmail = primaryAttendee?.email || appointment?.email || '';
  const inviteePhone = primaryAttendee?.phone || appointment?.phone || '';
  const inviteeTimezone = primaryAttendee?.timezone || appointment?.timezone || '';

  // Host info
  const hostName = appointment?.host_name || appointment?.loan_officer_name || '';
  const hostPhone = appointment?.host_phone || appointment?.phone || '';

  // Location
  const location = appointment?.location || '';

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="mad-container">
      {/* -- Header -- */}
      <div className="mad-header">
        <button className="mad-back-btn" onClick={() => navigate(-1)}>
          <span className="mad-back-chevron">&lsaquo;</span> Back
        </button>

        <div className="mad-title-row">
          <span
            className="mad-status-dot"
            style={{ backgroundColor: statusDotColor(status) }}
          />
          <h1 className="mad-title">{title}</h1>
        </div>

        {dateRange && <p className="mad-subtitle">{dateRange}</p>}
      </div>

      {/* -- Sub-tabs -- */}
      <div className="mad-tabs">
        {['details', 'notes', 'history'].map((tab) => (
          <button
            key={tab}
            className={`mad-tab ${activeTab === tab ? 'mad-tab--active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* -- Body -- */}
      <div className="mad-body">
        {activeTab === 'details' ? (
          <>
            {/* Location section */}
            <section className="mad-section">
              <h2 className="mad-section__title">Location</h2>
              <div className="mad-row">
                <div className="mad-row__icon">
                  <LocationIcon />
                </div>
                <div className="mad-row__content">
                  {location ? (
                    <span className="mad-row__text">{location}</span>
                  ) : hostPhone ? (
                    <span className="mad-row__text">
                      Host will call{' '}
                      <a className="mad-link" href={`tel:${hostPhone}`}>
                        {formatPhone(hostPhone)}
                      </a>
                    </span>
                  ) : (
                    <span className="mad-row__text mad-row__text--muted">
                      No location specified
                    </span>
                  )}
                </div>
              </div>
            </section>

            {/* Invitee Details section */}
            {(inviteeName || inviteeEmail || inviteePhone) && (
              <section className="mad-section">
                <h2 className="mad-section__title">Invitee Details</h2>

                {/* Name + avatar */}
                <div className="mad-row">
                  <div className="mad-avatar mad-avatar--invitee">
                    {getInitials(inviteeName)}
                  </div>
                  <div className="mad-row__content">
                    <span className="mad-invitee-name">
                      {inviteeName || 'Unknown invitee'}
                    </span>
                  </div>
                </div>

                {/* Status */}
                <div className="mad-row">
                  <div className="mad-row__icon">
                    <CheckCircleIcon />
                  </div>
                  <div className="mad-row__content">
                    <span className="mad-row__text">{statusLabel(status)}</span>
                  </div>
                </div>

                {/* Email */}
                {inviteeEmail && (
                  <div className="mad-row">
                    <div className="mad-row__icon">
                      <MailIcon />
                    </div>
                    <div className="mad-row__content">
                      <a
                        className="mad-link"
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          window.open(`mailto:${inviteeEmail}`);
                        }}
                      >
                        {inviteeEmail}
                      </a>
                    </div>
                  </div>
                )}

                {/* Phone */}
                {inviteePhone && (
                  <div className="mad-row">
                    <div className="mad-row__icon">
                      <PhoneIcon />
                    </div>
                    <div className="mad-row__content">
                      <a
                        className="mad-link"
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          window.open(`tel:${inviteePhone}`);
                        }}
                      >
                        {formatPhone(inviteePhone)}
                      </a>
                    </div>
                  </div>
                )}

                {/* Timezone */}
                {inviteeTimezone && (
                  <div className="mad-row">
                    <div className="mad-row__icon">
                      <GlobeIcon />
                    </div>
                    <div className="mad-row__content">
                      <span className="mad-row__text">{inviteeTimezone}</span>
                    </div>
                  </div>
                )}
              </section>
            )}

            {/* Host section */}
            {hostName && (
              <section className="mad-section">
                <h2 className="mad-section__title">Host</h2>
                <div className="mad-host-card">
                  <div className="mad-avatar mad-avatar--host">
                    {getInitials(hostName)}
                  </div>
                  <div className="mad-host-card__info">
                    <span className="mad-host-card__name">{hostName}</span>
                    <span className="mad-host-card__badge">Host</span>
                  </div>
                  <ChevronRightIcon />
                </div>
              </section>
            )}
          </>
        ) : (
          /* Notes / History placeholder */
          <div className="mad-placeholder">
            <p className="mad-placeholder__text">Coming soon</p>
          </div>
        )}
      </div>

      {/* -- Footer -- */}
      <div className="mad-footer">
        <button
          className="mad-action-btn mad-action-btn--ghost"
          onClick={handleMarkNoShow}
          disabled={actionLoading}
        >
          {actionLoading ? 'Updating...' : 'Mark as no-show'}
        </button>
        <button
          className="mad-action-btn mad-action-btn--primary"
          onClick={handleBookFollowUp}
        >
          Book follow-up
        </button>
      </div>
    </div>
  );
}
