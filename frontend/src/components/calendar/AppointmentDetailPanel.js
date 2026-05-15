import React from 'react';
import { useNavigate } from 'react-router-dom';
import './AppointmentDetailPanel.css';

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${dayNames[d.getDay()]}, ${monthNames[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function formatDuration(start, end) {
  if (!start || !end) return '';
  const ms = new Date(end) - new Date(start);
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem ? `${hrs}h ${rem}m` : `${hrs}h`;
}

function getStatusLabel(status) {
  const map = {
    scheduled: 'Scheduled',
    confirmed: 'Confirmed',
    completed: 'Completed',
    cancelled: 'Cancelled',
    no_show: 'No Show',
    rescheduled: 'Rescheduled',
  };
  return map[status] || status || 'Scheduled';
}

function getStatusColor(status) {
  const map = {
    scheduled: '#1F3D2E',
    confirmed: '#2D7A52',
    completed: '#6b7280',
    cancelled: '#ef4444',
    no_show: '#f59e0b',
    rescheduled: '#B8924A',
  };
  return map[status] || '#1F3D2E';
}

function getModeLabel(mode) {
  const map = {
    VIDEO: 'Video Call',
    PHONE: 'Phone Call',
    IN_PERSON: 'In Person',
  };
  return map[(mode || '').toUpperCase()] || 'Calendar Event';
}

function getModeIcon(mode) {
  const m = (mode || '').toUpperCase();
  if (m === 'VIDEO') return '📹';
  if (m === 'PHONE') return '📞';
  if (m === 'IN_PERSON') return '🏢';
  return '📅';
}

function getTypeColor(event) {
  const type = (event.event_type || event.meeting_type || '').toLowerCase();
  if (type.includes('consultation') || type.includes('discovery')) return '#1F3D2E';
  if (type.includes('closing') || type.includes('review')) return '#ed8936';
  if (type.includes('application') || type.includes('walkthrough')) return '#48bb78';
  if (type.includes('rate') || type.includes('lock')) return '#e53e3e';
  if (type.includes('document') || type.includes('doc')) return '#9f7aea';
  return '#4299e1';
}

function AppointmentDetailPanel({ event, onEdit, onDelete, onClose }) {
  const navigate = useNavigate();

  if (!event) {
    return (
      <div className="appt-detail-panel appt-detail-panel--empty">
        <div className="appt-detail-empty">
          <div className="appt-detail-empty-icon">📋</div>
          <div className="appt-detail-empty-title">Select an appointment</div>
          <div className="appt-detail-empty-sub">Click on an appointment from the list to view its details</div>
        </div>
      </div>
    );
  }

  const title = event.title || 'Appointment';
  const status = event.status || 'scheduled';
  const statusLabel = getStatusLabel(status);
  const statusColor = getStatusColor(status);
  const modeLabel = getModeLabel(event.meeting_mode);
  const modeIcon = getModeIcon(event.meeting_mode);
  const typeColor = getTypeColor(event);
  const eventType = event.event_type || event.meeting_type || 'Appointment';
  const dateStr = formatDateTime(event.start_time);
  const startTime = formatTime(event.start_time);
  const endTime = formatTime(event.end_time);
  const duration = formatDuration(event.start_time, event.end_time);

  const handleNavigateToLead = () => {
    if (event.lead_id) navigate(`/leads/${event.lead_id}`);
  };

  return (
    <div className="appt-detail-panel">
      <div className="appt-detail-header">
        <div className="appt-detail-header-top">
          <div className="appt-detail-type-badge" style={{ backgroundColor: typeColor }}>
            {eventType}
          </div>
          <div className="appt-detail-status-badge" style={{ backgroundColor: statusColor }}>
            {statusLabel}
          </div>
        </div>
        <h2 className="appt-detail-title">{title}</h2>
        {event.attendee_name && (
          <div
            className={`appt-detail-attendee${event.lead_id ? ' appt-detail-attendee--link' : ''}`}
            onClick={event.lead_id ? handleNavigateToLead : undefined}
          >
            {event.attendee_name}
            {event.lead_id && <span className="appt-detail-attendee-arrow">&rarr;</span>}
          </div>
        )}
      </div>

      <div className="appt-detail-body">
        <div className="appt-detail-info-grid">
          <div className="appt-detail-info-item">
            <div className="appt-detail-info-label">Date</div>
            <div className="appt-detail-info-value">{dateStr}</div>
          </div>

          <div className="appt-detail-info-item">
            <div className="appt-detail-info-label">Time</div>
            <div className="appt-detail-info-value">
              {startTime}{endTime ? ` – ${endTime}` : ''}
              {duration && <span className="appt-detail-duration">({duration})</span>}
            </div>
          </div>

          <div className="appt-detail-info-item">
            <div className="appt-detail-info-label">Type</div>
            <div className="appt-detail-info-value">
              <span>{modeIcon}</span> {modeLabel}
            </div>
          </div>

          {event.location && (
            <div className="appt-detail-info-item">
              <div className="appt-detail-info-label">Location</div>
              <div className="appt-detail-info-value">{event.location}</div>
            </div>
          )}

          {event.attendee_email && (
            <div className="appt-detail-info-item">
              <div className="appt-detail-info-label">Email</div>
              <div className="appt-detail-info-value">{event.attendee_email}</div>
            </div>
          )}

          {event.attendee_phone && (
            <div className="appt-detail-info-item">
              <div className="appt-detail-info-label">Phone</div>
              <div className="appt-detail-info-value">{event.attendee_phone}</div>
            </div>
          )}

          {event.meeting_link && (
            <div className="appt-detail-info-item">
              <div className="appt-detail-info-label">Meeting Link</div>
              <div className="appt-detail-info-value">
                <a href={event.meeting_link} target="_blank" rel="noopener noreferrer" className="appt-detail-link">
                  Join Meeting
                </a>
              </div>
            </div>
          )}
        </div>

        {event.description && (
          <div className="appt-detail-section">
            <h3 className="appt-detail-section-title">Notes</h3>
            <div className="appt-detail-description">{event.description}</div>
          </div>
        )}

        {event.notes && event.notes !== event.description && (
          <div className="appt-detail-section">
            <h3 className="appt-detail-section-title">Additional Notes</h3>
            <div className="appt-detail-description">{event.notes}</div>
          </div>
        )}

        {event.reminder_minutes != null && (
          <div className="appt-detail-section">
            <h3 className="appt-detail-section-title">Reminder</h3>
            <div className="appt-detail-reminder">
              {event.reminder_minutes} minutes before
            </div>
          </div>
        )}
      </div>

      <div className="appt-detail-footer">
        {event.isAppointment && onEdit && (
          <button className="appt-detail-btn appt-detail-btn--primary" onClick={() => onEdit(event)}>
            Edit
          </button>
        )}
        {event.lead_id && (
          <button className="appt-detail-btn appt-detail-btn--secondary" onClick={handleNavigateToLead}>
            View Client
          </button>
        )}
        {event.isAppointment && onDelete && (
          <button className="appt-detail-btn appt-detail-btn--danger" onClick={() => onDelete(event)}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

export default React.memo(AppointmentDetailPanel);
