// ─────────────────────────────────────────────────────────────
// RECEPTIONIST CARD
// src/components/callIntelligence/ReceptionistCard.jsx
// ─────────────────────────────────────────────────────────────

import React from 'react';
import './ReceptionistCard.css';

const STATUS_COLORS = {
  confirmed: '#34A853',
  sent: '#FBBC04',
  declined: '#FF6B6B',
  pending: 'rgba(255,255,255,0.3)',
};

const STATUS_LABELS = {
  confirmed: 'Confirmed',
  sent: 'Invite Sent',
  declined: 'Declined',
  pending: 'Pending',
};

function formatDate(isoString) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const day = days[d.getDay()];
    const month = months[d.getMonth()];
    const date = d.getDate();
    let hours = d.getHours();
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    return `${day}, ${month} ${date} \u00B7 ${hours}:${minutes} ${ampm}`;
  } catch {
    return isoString;
  }
}

function AppointmentItem({ appt }) {
  const statusColor = STATUS_COLORS[appt.confirm_status] ?? 'rgba(255,255,255,0.3)';
  const statusLabel = STATUS_LABELS[appt.confirm_status] ?? 'Pending';
  const dateStr = formatDate(appt.scheduled_at);

  return (
    <div className="receptionist-card__appt-card">
      <div className="receptionist-card__appt-top">
        <span className="receptionist-card__appt-title">{appt.title}</span>
        <div
          className="receptionist-card__appt-badge"
          style={{ backgroundColor: `${statusColor}20` }}
        >
          <span
            className="receptionist-card__appt-badge-text"
            style={{ color: statusColor }}
          >
            {statusLabel}
          </span>
        </div>
      </div>
      <p className="receptionist-card__appt-detail">
        {dateStr} &middot; {appt.duration_minutes} min
      </p>
      {appt.borrower_invite_sent && (
        <p className="receptionist-card__appt-detail">
          Invite sent to {appt.borrower_email}
        </p>
      )}
      {appt.lo_calendar_added && (
        <p className="receptionist-card__appt-detail">
          Added to your calendar
        </p>
      )}
    </div>
  );
}

export default function ReceptionistCard({ state }) {
  return (
    <div className="receptionist-card">
      {/* Header */}
      <div className="receptionist-card__header">
        <div className="receptionist-card__title-row">
          <div className="receptionist-card__dot" />
          <span className="receptionist-card__agent-name">Receptionist</span>
        </div>
        <div className="receptionist-card__tag-wrap">
          <span className="receptionist-card__tag-text">
            {state.appointments.length > 0
              ? `${state.appointments.length} Scheduled`
              : 'Ready'}
          </span>
        </div>
      </div>

      {/* Scheduled appointments */}
      {state.appointments.length === 0 ? (
        <div className="receptionist-card__waiting-wrap">
          <p className="receptionist-card__waiting-text">
            Listening for scheduling opportunities...
          </p>
          <p className="receptionist-card__waiting-hint">
            When you agree on a meeting time with the borrower, I'll send the invite automatically.
          </p>
        </div>
      ) : (
        state.appointments.map((appt) => (
          <AppointmentItem key={appt.id} appt={appt} />
        ))
      )}

      {/* Last action */}
      {state.last_action && (
        <div className="receptionist-card__action-row">
          <span className="receptionist-card__action-check">{'\u2713'}</span>
          <span className="receptionist-card__action-text">{state.last_action}</span>
        </div>
      )}

      {/* Stats */}
      {(state.emails_sent > 0 || state.calendar_events_created > 0) && (
        <div className="receptionist-card__stats-row">
          <div className="receptionist-card__stat">
            <span className="receptionist-card__stat-val">{state.emails_sent}</span>
            <span className="receptionist-card__stat-label">Emails Sent</span>
          </div>
          <div className="receptionist-card__stat-divider" />
          <div className="receptionist-card__stat">
            <span className="receptionist-card__stat-val">{state.calendar_events_created}</span>
            <span className="receptionist-card__stat-label">Cal Events</span>
          </div>
        </div>
      )}
    </div>
  );
}
