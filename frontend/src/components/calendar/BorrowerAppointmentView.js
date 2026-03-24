/**
 * BorrowerAppointmentView
 *
 * Shows a borrower their upcoming (and optionally past) appointments.
 * Can be embedded in the borrower portal or accessed via a unique link
 * with a borrower-specific token.
 *
 * Authentication modes:
 *   (A) Token-based  -- borrower accesses via a unique link containing a JWT
 *   (B) Email-based  -- embedded in the authenticated borrower portal, email
 *       is passed from the portal's session context
 *
 * Props:
 *   - borrowerEmail  : string  (optional) Email to look up appointments
 *   - borrowerToken  : string  (optional) JWT token for public access
 *   - loanId         : string  (optional) Scope to a specific loan's appointments
 *   - showPast       : boolean (default false) Include completed/past appointments
 *   - compact        : boolean (default false) Reduced padding for portal embed
 *   - onAppointmentClick : function (optional) Callback when an appointment is clicked
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import StatusBadge from './StatusBadge';
import {
  normalizeUTCDate,
  formatTimeWithZone,
  formatInUserTimezone,
  toUserTimezone,
} from '../../utils/timezone';
import './BorrowerAppointmentView.css';

const API_BASE =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? process.env.REACT_APP_API_URL || 'http://localhost:8000'
    : 'https://api.perenniaai.com';

// ---------------------------------------------------------------------------
// SVG icons (inline to avoid external deps, matching BookingConfirmation style)
// ---------------------------------------------------------------------------

const CalendarIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bav-icon">
    <path
      fillRule="evenodd"
      d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 011 1v3a1 1 0 01-2 0V8a1 1 0 011-1z"
      clipRule="evenodd"
    />
  </svg>
);

const VideoIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bav-icon">
    <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6zm12.553 1.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
  </svg>
);

const PhoneIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bav-icon">
    <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z" />
  </svg>
);

const LocationIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bav-icon">
    <path
      fillRule="evenodd"
      d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
      clipRule="evenodd"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatFullDate(dateStr) {
  if (!dateStr) return '';
  return formatInUserTimezone(dateStr, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  return formatTimeWithZone(dateStr);
}

function formatDurationMinutes(minutes) {
  if (!minutes) return '';
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? 's' : ''}`;
  }
  return `${minutes} min`;
}

function getMeetingModeLabel(mode) {
  const labels = {
    video: 'Video Call',
    phone: 'Phone Call',
    in_person: 'In Person',
    screen_share: 'Screen Share',
  };
  return labels[(mode || '').toLowerCase()] || 'Meeting';
}

function getMeetingModeIcon(mode) {
  const normalized = (mode || '').toLowerCase();
  if (normalized === 'video' || normalized === 'screen_share') return <VideoIcon />;
  if (normalized === 'phone') return <PhoneIcon />;
  if (normalized === 'in_person') return <LocationIcon />;
  return <CalendarIcon />;
}

/**
 * Determine if a date is today in the user's configured timezone.
 */
function isToday(dateStr) {
  if (!dateStr) return false;
  const d = toUserTimezone(dateStr);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

/**
 * Determine if a date is tomorrow in the user's configured timezone.
 */
function isTomorrow(dateStr) {
  if (!dateStr) return false;
  const d = toUserTimezone(dateStr);
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return (
    d.getFullYear() === tomorrow.getFullYear() &&
    d.getMonth() === tomorrow.getMonth() &&
    d.getDate() === tomorrow.getDate()
  );
}

/**
 * Get a relative day label for grouping.
 */
function getDayLabel(dateStr) {
  if (isToday(dateStr)) return 'Today';
  if (isTomorrow(dateStr)) return 'Tomorrow';
  return formatFullDate(dateStr);
}

/**
 * Group appointments by day for display.
 */
function groupByDay(appointments) {
  const groups = [];
  const map = new Map();
  for (const appt of appointments) {
    const key = toUserTimezone(appt.scheduled_start).toDateString();
    if (!map.has(key)) {
      const group = { label: getDayLabel(appt.scheduled_start), appointments: [] };
      map.set(key, group);
      groups.push(group);
    }
    map.get(key).appointments.push(appt);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const AppointmentCard = React.memo(function AppointmentCard({ appt, onClick }) {
  const isVirtual = ['video', 'screen_share'].includes((appt.meeting_mode || '').toLowerCase());
  const apptTitle = appt.title || appt.appointment_type_name || 'Appointment';
  const apptDateStr = formatFullDate(appt.scheduled_start);
  const apptTimeStr = formatTime(appt.scheduled_start);
  const statusLabel = (appt.status || 'unknown').charAt(0).toUpperCase() + (appt.status || 'unknown').slice(1);

  const handleClick = useCallback(() => {
    if (onClick) onClick(appt);
  }, [appt, onClick]);

  return (
    <div
      className="bav-card"
      onClick={handleClick}
      role={onClick ? 'button' : 'article'}
      tabIndex={onClick ? 0 : undefined}
      aria-label={
        onClick
          ? `View details for ${apptTitle} on ${apptDateStr} at ${apptTimeStr}`
          : `${apptTitle}, ${apptDateStr} at ${apptTimeStr}, status: ${statusLabel}`
      }
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(); } } : undefined}
    >
      {/* Time column */}
      <div className="bav-card-time">
        <span className="bav-card-time-value">{apptTimeStr}</span>
        <span className="bav-card-time-duration">{formatDurationMinutes(appt.duration_minutes)}</span>
      </div>

      {/* Details column */}
      <div className="bav-card-details">
        <div className="bav-card-title-row">
          <span className="bav-card-title">{apptTitle}</span>
          <span aria-label={`Status: ${statusLabel}`}>
            <StatusBadge status={appt.status} size="sm" />
          </span>
        </div>

        {/* Meeting mode + LO */}
        <div className="bav-card-meta">
          <span className="bav-card-mode" aria-label={getMeetingModeLabel(appt.meeting_mode)}>
            <span aria-hidden="true">{getMeetingModeIcon(appt.meeting_mode)}</span>
            {getMeetingModeLabel(appt.meeting_mode)}
          </span>
          {appt.lo_name && (
            <span className="bav-card-lo">
              with {appt.lo_name}
            </span>
          )}
        </div>

        {/* Location or meeting link */}
        {appt.location && !isVirtual && (
          <div className="bav-card-location">
            <span aria-hidden="true"><LocationIcon /></span>
            <span>{appt.location}</span>
          </div>
        )}

        {/* Actions */}
        <div className="bav-card-actions" role="group" aria-label="Appointment actions">
          {isVirtual && appt.meeting_link && (
            <a
              href={appt.meeting_link}
              target="_blank"
              rel="noopener noreferrer"
              className="bav-btn bav-btn-primary"
              aria-label={`Join video meeting for ${apptTitle} on ${apptDateStr}`}
              onClick={(e) => e.stopPropagation()}
            >
              Join Meeting
            </a>
          )}
          {appt.reschedule_url && (
            <a
              href={appt.reschedule_url}
              className="bav-btn bav-btn-secondary"
              aria-label={`Reschedule ${apptTitle} on ${apptDateStr}`}
              onClick={(e) => e.stopPropagation()}
            >
              Reschedule
            </a>
          )}
          {appt.cancel_url && (
            <a
              href={appt.cancel_url}
              className="bav-btn bav-btn-secondary"
              aria-label={`Cancel ${apptTitle} on ${apptDateStr}`}
              onClick={(e) => e.stopPropagation()}
            >
              Cancel
            </a>
          )}
        </div>
      </div>
    </div>
  );
});

const EmptyState = () => (
  <div className="bav-empty">
    <div className="bav-empty-icon">
      <CalendarIcon />
    </div>
    <h3 className="bav-empty-title">No upcoming appointments</h3>
    <p className="bav-empty-text">
      When you schedule an appointment with your loan officer, it will appear here.
    </p>
  </div>
);

const LoadingSkeleton = () => (
  <div className="bav-skeleton" aria-busy="true" role="status" aria-label="Loading appointments">
    <span className="bav-sr-only">Loading your appointments, please wait.</span>
    {[1, 2, 3].map((i) => (
      <div key={i} className="bav-skeleton-card" aria-hidden="true">
        <div className="bav-skeleton-time">
          <div className="bav-skeleton-line" style={{ width: '60px', height: '16px' }} />
          <div className="bav-skeleton-line" style={{ width: '40px', height: '12px' }} />
        </div>
        <div className="bav-skeleton-details">
          <div className="bav-skeleton-line" style={{ width: '70%', height: '16px' }} />
          <div className="bav-skeleton-line" style={{ width: '50%', height: '12px' }} />
          <div className="bav-skeleton-line" style={{ width: '40%', height: '12px' }} />
        </div>
      </div>
    ))}
  </div>
);

const ErrorState = ({ message, onRetry }) => (
  <div className="bav-error" role="alert" aria-live="polite">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="bav-error-icon" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
    <h3 className="bav-error-title">Unable to load appointments</h3>
    <p className="bav-error-text">{message}</p>
    {onRetry && (
      <button className="bav-btn bav-btn-primary" aria-label="Retry loading appointments" onClick={onRetry}>
        Try Again
      </button>
    )}
  </div>
);

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function BorrowerAppointmentView({
  borrowerEmail,
  borrowerToken,
  loanId,
  showPast = false,
  compact = false,
  onAppointmentClick,
}) {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadAppointments = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (borrowerToken) {
        params.set('token', borrowerToken);
      } else if (borrowerEmail) {
        params.set('email', borrowerEmail);
      } else {
        setError('No authentication provided');
        setLoading(false);
        return;
      }
      if (loanId) {
        params.set('loan_id', loanId);
      }
      if (showPast) {
        params.set('include_past', 'true');
      }

      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/my-appointments?${params.toString()}`,
        {
          headers: { 'Content-Type': 'application/json' },
        }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to load appointments (${response.status})`);
      }

      const data = await response.json();
      setAppointments(data.appointments || []);
    } catch (err) {
      setError(err.message || 'Connection error');
    } finally {
      setLoading(false);
    }
  }, [borrowerEmail, borrowerToken, loanId, showPast]);

  useEffect(() => {
    if (borrowerEmail || borrowerToken) {
      loadAppointments();
    }
  }, [borrowerEmail, borrowerToken, loadAppointments]);

  // Separate upcoming vs past (comparison uses raw UTC timestamps which is correct
  // for determining past vs future -- no timezone conversion needed for ordering)
  const { upcoming, past } = useMemo(() => {
    const now = new Date();
    const up = [];
    const pa = [];
    for (const appt of appointments) {
      const apptDate = new Date(normalizeUTCDate(appt.scheduled_start));
      if (apptDate >= now || ['booked', 'confirmed', 'reminded'].includes((appt.status || '').toLowerCase())) {
        up.push(appt);
      } else {
        pa.push(appt);
      }
    }
    // Upcoming sorted ascending (soonest first)
    up.sort((a, b) => new Date(normalizeUTCDate(a.scheduled_start)) - new Date(normalizeUTCDate(b.scheduled_start)));
    // Past sorted descending (most recent first)
    pa.sort((a, b) => new Date(normalizeUTCDate(b.scheduled_start)) - new Date(normalizeUTCDate(a.scheduled_start)));
    return { upcoming: up, past: pa };
  }, [appointments]);

  const upcomingGroups = useMemo(() => groupByDay(upcoming), [upcoming]);
  const pastGroups = useMemo(() => groupByDay(past), [past]);

  // Loading state
  if (loading) {
    return (
      <div className={`bav-container${compact ? ' bav-compact' : ''}`} aria-busy="true">
        <h2 className="bav-heading">Your Appointments</h2>
        <LoadingSkeleton />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={`bav-container${compact ? ' bav-compact' : ''}`}>
        <h2 className="bav-heading">Your Appointments</h2>
        <ErrorState message={error} onRetry={loadAppointments} />
      </div>
    );
  }

  // Empty state
  if (appointments.length === 0) {
    return (
      <div className={`bav-container${compact ? ' bav-compact' : ''}`}>
        <h2 className="bav-heading">Your Appointments</h2>
        <EmptyState />
      </div>
    );
  }

  return (
    <div className={`bav-container${compact ? ' bav-compact' : ''}`} aria-busy="false">
      <h2 className="bav-heading" id="bav-upcoming-heading">Your Upcoming Appointments</h2>

      {/* Live region wraps dynamic appointment content */}
      <div aria-live="polite" aria-relevant="additions removals">
        {/* Upcoming appointments grouped by day */}
        {upcomingGroups.length > 0 ? (
          <div className="bav-groups" role="region" aria-labelledby="bav-upcoming-heading">
            {upcomingGroups.map((group) => (
              <div key={group.label} className="bav-group">
                <h3 className="bav-group-label">{group.label}</h3>
                {group.appointments.map((appt) => (
                  <AppointmentCard
                    key={appt.id}
                    appt={appt}
                    onClick={onAppointmentClick}
                  />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState />
        )}
      </div>

      {/* Past appointments */}
      {showPast && pastGroups.length > 0 && (
        <>
          <h2 className="bav-heading bav-heading-past" id="bav-past-heading">Past Appointments</h2>
          <div className="bav-groups bav-groups-past" role="region" aria-labelledby="bav-past-heading">
            {pastGroups.map((group) => (
              <div key={group.label} className="bav-group">
                <h3 className="bav-group-label">{group.label}</h3>
                {group.appointments.map((appt) => (
                  <AppointmentCard
                    key={appt.id}
                    appt={appt}
                    onClick={onAppointmentClick}
                  />
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
