/**
 * BookingConfirmation - Polished confirmation page after successful booking.
 *
 * Features:
 *  - Animated success checkmark (CSS-driven SVG animation)
 *  - Appointment details card (date/time, duration, type, LO info, location)
 *  - Add-to-calendar buttons (Google, Apple/ICS, Outlook)
 *  - "Join Meeting" button for virtual appointments
 *  - Confirmation number display
 *  - Preparation checklist (contextual to meeting type)
 *  - Reschedule / cancel links
 *
 * Usage:
 *  (A) Inline after booking — pass appointment data directly:
 *      <BookingConfirmation appointmentData={...} />
 *
 *  (B) Standalone page — pass appointmentId + token to fetch from API:
 *      <BookingConfirmation appointmentId={123} token="jwt..." />
 *
 * Props:
 *  - appointmentId: number (optional) — ID for API fetch
 *  - token: string (optional) — JWT for public confirmation endpoint
 *  - appointmentData: object (optional) — pre-loaded data to skip API call
 *  - onReschedule: function (optional) — callback for reschedule action
 *  - onCancel: function (optional) — callback for cancel action
 *  - onGoHome: function (optional) — callback for "go home" action
 *  - showPreparation: boolean (default true) — show preparation checklist
 *  - compact: boolean (default false) — compact mode, hides some sections
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  generateGoogleCalendarUrl,
  generateOutlookUrl,
  generateICSFile,
  downloadICSFile,
} from '../../utils/calendarLinks';
import '../../styles/booking-confirmation.css';

const API_BASE =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? process.env.REACT_APP_API_URL || 'http://localhost:8000'
    : 'https://api.perenniaai.com';

// ---------------------------------------------------------------------------
// SVG icon components (no external dependencies)
// ---------------------------------------------------------------------------

const CalendarIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path
      fillRule="evenodd"
      d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 011 1v3a1 1 0 01-2 0V8a1 1 0 011-1z"
      clipRule="evenodd"
    />
  </svg>
);

const ClockIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.828a1 1 0 101.415-1.414L11 9.586V6z"
      clipRule="evenodd"
    />
  </svg>
);

const DurationIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm0 14a6 6 0 110-12 6 6 0 010 12z" />
    <path d="M10 5a1 1 0 011 1v3.586l2.207 2.207a1 1 0 01-1.414 1.414l-2.5-2.5A1 1 0 019 10V6a1 1 0 011-1z" />
  </svg>
);

const TypeIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
    <path
      fillRule="evenodd"
      d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z"
      clipRule="evenodd"
    />
  </svg>
);

const LocationIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path
      fillRule="evenodd"
      d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
      clipRule="evenodd"
    />
  </svg>
);

const VideoIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6zm12.553 1.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
  </svg>
);

const MeetingModeIcon = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" className="bc-detail-icon">
    <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z" />
  </svg>
);

// ---------------------------------------------------------------------------
// Animated Checkmark
// ---------------------------------------------------------------------------

const AnimatedCheckmark = () => (
  <div className="bc-success-animation">
    <div className="bc-checkmark-circle">
      <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Booking confirmed">
        {/* Background fill */}
        <circle cx="40" cy="40" r="36" className="bc-circle-fill" />
        {/* Circle outline */}
        <circle cx="40" cy="40" r="36" className="bc-circle" />
        {/* Checkmark */}
        <path d="M24 42 L34 52 L56 30" className="bc-checkmark-path" />
      </svg>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format ISO date string as a human-friendly date.
 * e.g. "Thursday, March 13, 2026"
 */
function formatFullDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Format ISO date string as time.
 * e.g. "2:30 PM"
 */
function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format duration in minutes to human string.
 * e.g. 90 -> "1h 30m"
 */
function formatDuration(minutes) {
  if (!minutes) return '';
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? 's' : ''}`;
  }
  return `${minutes} minutes`;
}

/**
 * Generate a short confirmation number from appointment ID.
 */
function generateConfirmationNumber(appointmentId) {
  if (!appointmentId) return '';
  // 6-character alphanumeric ID based on appointment ID
  const base = appointmentId.toString();
  const hash = base.split('').reduce((acc, ch) => ((acc << 5) - acc + ch.charCodeAt(0)) | 0, 0);
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let result = '';
  let h = Math.abs(hash);
  for (let i = 0; i < 6; i++) {
    result += chars[h % chars.length];
    h = Math.floor(h / chars.length) || appointmentId + i;
  }
  return `PER-${result}`;
}

/**
 * Get initials from a name string.
 */
function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Check if appointment is within N hours from now.
 */
function isWithinHours(dateStr, hours) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  const diff = d.getTime() - now.getTime();
  return diff > 0 && diff <= hours * 60 * 60 * 1000;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BookingConfirmation = ({
  appointmentId,
  token,
  appointmentData: initialData = null,
  onReschedule,
  onCancel,
  onGoHome,
  showPreparation = true,
  compact = false,
}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState(null);

  // Normalize initial data into the rich format
  useEffect(() => {
    if (initialData) {
      setData(normalizeInlineData(initialData));
      setLoading(false);
    }
  }, [initialData]);

  // Fetch from API if no inline data and we have appointmentId + token
  const fetchConfirmation = useCallback(async () => {
    if (!appointmentId || !token) return;
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/confirmation/${appointmentId}?token=${encodeURIComponent(token)}`,
        { headers: { 'Content-Type': 'application/json' } }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to load confirmation (${response.status})`);
      }

      const result = await response.json();
      setData(normalizeAPIData(result));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [appointmentId, token]);

  useEffect(() => {
    if (!initialData && appointmentId && token) {
      fetchConfirmation();
    }
  }, [initialData, appointmentId, token, fetchConfirmation]);

  // Calendar link data
  const calendarData = useMemo(() => {
    if (!data) return null;
    return {
      title: data.title || 'Mortgage Appointment',
      startTime: data.scheduledStart,
      endTime: data.scheduledEnd,
      description: data.description || `Appointment with ${data.loName || 'your loan officer'}`,
      location: data.videoLink || data.location || '',
      attendeeName: data.attendeeName,
      attendeeEmail: data.attendeeEmail,
      organizerName: data.loName || 'Perennia AI',
      organizerEmail: data.loEmail || 'noreply@perenniaai.com',
      appointmentId: data.appointmentId,
    };
  }, [data]);

  // Handlers
  const handleGoogleCalendar = useCallback(() => {
    if (!calendarData) return;
    const url = generateGoogleCalendarUrl(calendarData);
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [calendarData]);

  const handleAppleCalendar = useCallback(() => {
    if (!calendarData) return;
    const blob = generateICSFile(calendarData);
    downloadICSFile(blob, `appointment-${data.appointmentId || 'booking'}.ics`);
  }, [calendarData, data]);

  const handleOutlookCalendar = useCallback(() => {
    if (!calendarData) return;
    const url = generateOutlookUrl(calendarData);
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [calendarData]);

  const handleJoinMeeting = useCallback(() => {
    if (data?.videoLink) {
      window.open(data.videoLink, '_blank', 'noopener,noreferrer');
    }
  }, [data]);

  const handleICSDownload = useCallback(() => {
    if (data?.icsDownloadUrl) {
      window.open(data.icsDownloadUrl, '_blank', 'noopener,noreferrer');
    } else if (calendarData) {
      // Fallback to client-side generation
      const blob = generateICSFile(calendarData);
      downloadICSFile(blob, `appointment-${data.appointmentId || 'booking'}.ics`);
    }
  }, [data, calendarData]);

  // Loading state
  if (loading) {
    return (
      <div className="bc-card">
        <div className="bc-loading">
          <div className="bc-loading-spinner" />
          <div className="bc-loading-text">Loading confirmation details...</div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bc-card">
        <div className="bc-error">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="bc-error-icon">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <h2 className="bc-error-title">Could not load confirmation</h2>
          <p className="bc-error-message">{error}</p>
          {appointmentId && token && (
            <button className="bc-error-retry" onClick={fetchConfirmation}>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  // No data
  if (!data) return null;

  const confirmationNumber = generateConfirmationNumber(data.appointmentId);
  const isVirtual = data.meetingMode === 'video' || data.meetingMode === 'screen_share';
  const showJoinButton = isVirtual && data.videoLink && isWithinHours(data.scheduledStart, 24);
  const showJoinSoon = isVirtual && data.videoLink && !isWithinHours(data.scheduledStart, 24);

  return (
    <div className="bc-card">
      {/* Animated Checkmark */}
      <AnimatedCheckmark />

      {/* Title */}
      <h1 className="bc-title">Booking Confirmed</h1>
      <p className="bc-subtitle">
        A confirmation email has been sent to your inbox with all the details.
      </p>

      {/* Confirmation Number */}
      <div className="bc-confirmation-number">
        <span className="bc-conf-label">Confirmation Number</span>
        <span className="bc-conf-value">{confirmationNumber}</span>
      </div>

      {/* Appointment Details Card */}
      <div className="bc-details-card">
        <h3 className="bc-details-title">Appointment Details</h3>

        {/* LO Profile */}
        {data.loName && (
          <div className="bc-lo-profile">
            {data.loPhoto ? (
              <img
                src={data.loPhoto}
                alt={data.loName}
                className="bc-lo-avatar"
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.nextSibling.style.display = 'flex';
                }}
              />
            ) : null}
            <div
              className="bc-lo-avatar-placeholder"
              style={data.loPhoto ? { display: 'none' } : undefined}
            >
              {getInitials(data.loName)}
            </div>
            <div className="bc-lo-info">
              <span className="bc-lo-name">{data.loName}</span>
              <span className="bc-lo-role">{data.loTitle || 'Loan Officer'}</span>
              {data.loNmls && <span className="bc-lo-nmls">NMLS# {data.loNmls}</span>}
            </div>
          </div>
        )}

        {/* Date */}
        <div className="bc-detail-row">
          <CalendarIcon />
          <div className="bc-detail-content">
            <div className="bc-detail-label">Date</div>
            <div className="bc-detail-value">{formatFullDate(data.scheduledStart)}</div>
          </div>
        </div>

        {/* Time */}
        <div className="bc-detail-row">
          <ClockIcon />
          <div className="bc-detail-content">
            <div className="bc-detail-label">Time</div>
            <div className="bc-detail-value">
              {formatTime(data.scheduledStart)}
              {data.timezone && (
                <span style={{ fontSize: '12px', color: '#9ca3af', marginLeft: '6px' }}>
                  ({data.timezone.replace(/_/g, ' ')})
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Duration */}
        <div className="bc-detail-row">
          <DurationIcon />
          <div className="bc-detail-content">
            <div className="bc-detail-label">Duration</div>
            <div className="bc-detail-value">{formatDuration(data.durationMinutes)}</div>
          </div>
        </div>

        {/* Appointment Type */}
        {data.appointmentTypeName && (
          <div className="bc-detail-row">
            <TypeIcon />
            <div className="bc-detail-content">
              <div className="bc-detail-label">Appointment Type</div>
              <div className="bc-detail-value">{data.appointmentTypeName}</div>
            </div>
          </div>
        )}

        {/* Meeting Mode */}
        <div className="bc-detail-row">
          {isVirtual ? <VideoIcon /> : <MeetingModeIcon />}
          <div className="bc-detail-content">
            <div className="bc-detail-label">Format</div>
            <div className="bc-detail-value">{data.meetingModeLabel || 'Meeting'}</div>
          </div>
        </div>

        {/* Location (for in-person) */}
        {data.location && !isVirtual && (
          <div className="bc-detail-row">
            <LocationIcon />
            <div className="bc-detail-content">
              <div className="bc-detail-label">Location</div>
              <div className="bc-detail-value">{data.location}</div>
            </div>
          </div>
        )}
      </div>

      {/* Join Meeting Button */}
      {showJoinButton && (
        <>
          <button className="bc-join-meeting" onClick={handleJoinMeeting}>
            <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
              <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6zm12.553 1.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
            </svg>
            Join Meeting
          </button>
        </>
      )}

      {showJoinSoon && (
        <p className="bc-join-note">
          The meeting link will be available closer to your appointment time.
        </p>
      )}

      {/* Add to Calendar */}
      {!compact && (
        <div className="bc-calendar-section">
          <div className="bc-calendar-label">Add to Calendar</div>
          <div className="bc-calendar-buttons">
            <button className="bc-cal-btn" onClick={handleGoogleCalendar} title="Add to Google Calendar">
              <span className="bc-cal-btn-icon" aria-hidden="true">G</span>
              <span className="bc-cal-btn-label">Google Calendar</span>
            </button>
            <button className="bc-cal-btn" onClick={handleAppleCalendar} title="Add to Apple Calendar">
              <span className="bc-cal-btn-icon" aria-hidden="true">&#63743;</span>
              <span className="bc-cal-btn-label">Apple Calendar</span>
            </button>
            <button className="bc-cal-btn" onClick={handleOutlookCalendar} title="Add to Outlook">
              <span className="bc-cal-btn-icon" aria-hidden="true">O</span>
              <span className="bc-cal-btn-label">Outlook</span>
            </button>
          </div>
        </div>
      )}

      {/* Preparation Checklist */}
      {showPreparation && !compact && data.preparation && data.preparation.items && data.preparation.items.length > 0 && (
        <div className="bc-prep-section">
          <h3 className="bc-prep-title">{data.preparation.title || 'Prepare for Your Appointment'}</h3>
          {data.preparation.description && (
            <p className="bc-prep-desc">{data.preparation.description}</p>
          )}
          <ul className="bc-prep-list">
            {data.preparation.items.map((item, idx) => (
              <li key={idx} className={`bc-prep-item priority-${item.priority || 'medium'}`}>
                <span className="bc-prep-bullet" aria-hidden="true">
                  {item.priority === 'high' ? '!' : ''}
                </span>
                <span>{item.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Print QR placeholder */}
      <div className="bc-print-qr">
        <div className="bc-print-qr-label">
          Confirmation: {confirmationNumber}
        </div>
      </div>

      {/* Bottom Actions */}
      <div className="bc-actions">
        {data.rescheduleUrl && (
          <a
            href={data.rescheduleUrl}
            className="bc-reschedule-link"
            onClick={(e) => {
              if (onReschedule) {
                e.preventDefault();
                onReschedule();
              }
            }}
          >
            Need to reschedule?
          </a>
        )}
        {onReschedule && !data.rescheduleUrl && (
          <button className="bc-reschedule-link" onClick={onReschedule}>
            Need to reschedule?
          </button>
        )}
        {(onCancel || data.cancelUrl) && (
          <button
            className="bc-cancel-link"
            onClick={() => {
              if (onCancel) {
                onCancel();
              } else if (data.cancelUrl) {
                window.location.href = data.cancelUrl;
              }
            }}
          >
            Cancel appointment
          </button>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Data normalizers
// ---------------------------------------------------------------------------

/**
 * Normalize inline appointment data (from booking response) into
 * the internal format used by the component.
 */
function normalizeInlineData(raw) {
  // Support both the direct booking response format and a richer pre-loaded format
  const confirmationDetails = raw.confirmation_details || {};

  return {
    appointmentId: raw.appointment_id || raw.id,
    title: confirmationDetails.title || raw.title || 'Mortgage Appointment',
    description: raw.description || '',
    scheduledStart: raw.scheduled_start || raw.scheduledStart || raw.startTime,
    scheduledEnd: raw.scheduled_end || raw.scheduledEnd || raw.endTime,
    durationMinutes: raw.duration_minutes || raw.durationMinutes || 30,
    timezone: raw.timezone || null,
    meetingMode: raw.meeting_mode || confirmationDetails.meeting_mode || 'video',
    meetingModeLabel: confirmationDetails.meeting_mode || 'Video Call',
    appointmentTypeName: raw.appointment_type_name || confirmationDetails.type_name || raw.type?.type_name || null,
    location: raw.location || null,
    videoLink: raw.video_link || raw.videoLink || null,
    phoneNumber: raw.phone_number || null,
    attendeeName: raw.attendee_name || raw.attendeeName || '',
    attendeeEmail: raw.attendee_email || raw.attendeeEmail || '',
    loName: raw.lo_name || confirmationDetails.team_member || raw.team_member || null,
    loTitle: raw.lo_title || null,
    loPhoto: raw.lo_photo || null,
    loEmail: raw.lo_email || null,
    loNmls: raw.lo_nmls || null,
    rescheduleUrl: raw.reschedule_url || null,
    cancelUrl: raw.cancel_url || null,
    icsDownloadUrl: raw.ics_download_url || null,
    preparation: raw.preparation || null,
  };
}

/**
 * Normalize API response from GET /public/confirmation/{id} into
 * the internal format.
 */
function normalizeAPIData(apiResponse) {
  const appt = apiResponse.appointment || {};
  const lo = apiResponse.loan_officer || {};
  const links = apiResponse.calendar_links || {};
  const actions = apiResponse.actions || {};
  const preparation = apiResponse.preparation || null;

  return {
    appointmentId: appt.id,
    title: appt.title || 'Mortgage Appointment',
    description: appt.description || '',
    scheduledStart: appt.scheduled_start,
    scheduledEnd: appt.scheduled_end,
    durationMinutes: appt.duration_minutes || 30,
    timezone: appt.timezone || null,
    meetingMode: appt.meeting_mode || 'video',
    meetingModeLabel: appt.meeting_mode_label || 'Meeting',
    appointmentTypeName: appt.appointment_type_name || null,
    location: appt.location || null,
    videoLink: appt.video_link || null,
    phoneNumber: appt.phone_number || null,
    attendeeName: appt.attendee_name || '',
    attendeeEmail: appt.attendee_email || '',
    loName: lo.name || null,
    loTitle: lo.title || 'Loan Officer',
    loPhoto: lo.photo_url || null,
    loEmail: lo.email || null,
    loNmls: lo.nmls_number || null,
    rescheduleUrl: actions.reschedule_url || null,
    cancelUrl: actions.cancel_url || null,
    icsDownloadUrl: links.ics_download || null,
    googleCalendarUrl: links.google || null,
    outlookCalendarUrl: links.outlook_web || null,
    preparation: preparation,
  };
}

export default BookingConfirmation;
