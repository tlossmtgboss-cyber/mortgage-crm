import React from 'react';

/**
 * TeamMemberColumn - Renders parts of a single LO's column in the team day view.
 *
 * This component supports two render modes since the parent uses a CSS Grid
 * where each row has [time-label, cell1, cell2, ...]:
 *
 * renderMode="header" - Renders the column header (avatar, name, capacity bar, status)
 * renderMode="cell"   - Renders a single time-slot cell with appointments
 *
 * Props (header mode):
 *   member            - { lo_id, lo_name, email }
 *   capacityPct       - Number 0-100
 *   renderMode        - "header"
 *
 * Props (cell mode):
 *   member            - { lo_id, lo_name }
 *   renderMode        - "cell"
 *   slotKey           - "HH:MM" string
 *   slotHour          - Number
 *   slotMinute        - Number (0 or 30)
 *   cellAppointments  - Array of appointment objects for this slot
 *   onDragOver        - Drag handler
 *   onDragLeave       - Drag handler
 *   onDrop            - (e, loId) => void
 *   onDragStart       - (e, appt, loId) => void
 *   onDragEnd         - Drag handler
 *   onSlotClick       - (loId, loName, hour, minute) => void
 *   onAppointmentHover - (e, appt) => void
 *   onAppointmentLeave - () => void
 *   getApptColorClass  - (appt) => string
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatHour = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

const capacityClass = (pct) => {
  if (pct < 50) return 'tc-capacity-green';
  if (pct < 80) return 'tc-capacity-yellow';
  return 'tc-capacity-red';
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AvailabilityIndicator({ pct }) {
  let label, statusClass;
  if (pct >= 95) {
    label = 'Fully booked';
    statusClass = 'tc-avail-status-off';
  } else if (pct >= 75) {
    label = 'Busy';
    statusClass = 'tc-avail-status-busy';
  } else {
    label = 'Available';
    statusClass = 'tc-avail-status-available';
  }

  return (
    <div className={`tc-avail-indicator ${statusClass}`}>
      <span className="tc-avail-dot" />
      <span>{label}</span>
    </div>
  );
}

function AppointmentBlock({
  appt,
  loId,
  onDragStart,
  onDragEnd,
  onMouseEnter,
  onMouseLeave,
  getApptColorClass,
}) {
  const durationMinutes = appt.duration_minutes || 30;
  // Scale height relative to the 48px min-height of a 30-min slot
  const heightSlots = durationMinutes / 30;
  const blockStyle = heightSlots > 1
    ? { minHeight: `${Math.round(heightSlots * 44)}px` }
    : {};

  return (
    <div
      className={`tc-appointment ${getApptColorClass(appt)}`}
      style={blockStyle}
      draggable
      onDragStart={(e) => onDragStart(e, appt, loId)}
      onDragEnd={onDragEnd}
      onMouseEnter={(e) => onMouseEnter(e, appt)}
      onMouseLeave={onMouseLeave}
      role="button"
      tabIndex={0}
      aria-label={`${appt.title || 'Appointment'}${appt.attendee_name ? ` with ${appt.attendee_name}` : ''}`}
    >
      <div className="tc-appointment-title">{appt.title}</div>
      {appt.scheduled_start && (
        <div className="tc-appointment-time">
          {new Date(appt.scheduled_start).toLocaleTimeString([], {
            hour: 'numeric',
            minute: '2-digit',
          })}
          {appt.scheduled_end &&
            ` - ${new Date(appt.scheduled_end).toLocaleTimeString([], {
              hour: 'numeric',
              minute: '2-digit',
            })}`}
        </div>
      )}
      {appt.attendee_name && (
        <div className="tc-appointment-attendee">{appt.attendee_name}</div>
      )}
      {appt.meeting_mode && (
        <div className="tc-appointment-mode">
          {appt.meeting_mode === 'VIDEO' && 'Video'}
          {appt.meeting_mode === 'PHONE' && 'Phone'}
          {appt.meeting_mode === 'IN_PERSON' && 'In Person'}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function TeamMemberColumn(props) {
  const { member, renderMode } = props;

  // ---- Header mode ----
  if (renderMode === 'header') {
    const { capacityPct = 0 } = props;
    return (
      <div className="tc-lo-col-header">
        <div className="tc-lo-avatar-row">
          <div className="tc-lo-avatar" aria-hidden="true">
            {(member.lo_name || '?')[0].toUpperCase()}
          </div>
          <div className="tc-lo-header-info">
            <div className="tc-lo-name" title={member.lo_name}>
              {member.lo_name}
            </div>
            {member.email && (
              <div className="tc-lo-email" title={member.email}>
                {member.email}
              </div>
            )}
          </div>
        </div>
        <div className="tc-capacity-bar-wrapper">
          <div className="tc-capacity-bar">
            <div
              className={`tc-capacity-bar-fill ${capacityClass(capacityPct)}`}
              style={{ width: `${Math.min(capacityPct, 100)}%` }}
            />
          </div>
          <span className={`tc-lo-capacity-badge ${capacityClass(capacityPct)}`}>
            {Math.round(capacityPct)}% booked
          </span>
        </div>
        <AvailabilityIndicator pct={capacityPct} />
      </div>
    );
  }

  // ---- Cell mode ----
  const {
    slotKey,
    slotHour,
    slotMinute,
    cellAppointments = [],
    onDragOver,
    onDragLeave,
    onDrop,
    onDragStart,
    onDragEnd,
    onSlotClick,
    onAppointmentHover,
    onAppointmentLeave,
    getApptColorClass,
  } = props;

  const handleCellClick = () => {
    if (cellAppointments.length === 0 && onSlotClick) {
      onSlotClick(member.lo_id, member.lo_name, slotHour, slotMinute);
    }
  };

  return (
    <div
      className={`tc-cell ${slotMinute === 30 ? 'tc-half-hour' : ''}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={(e) => onDrop(e, member.lo_id)}
      onClick={handleCellClick}
      role="gridcell"
      aria-label={`${member.lo_name}, ${formatHour(slotHour)}${slotMinute === 30 ? ':30' : ''}: ${cellAppointments.length ? cellAppointments.length + ' appointment(s)' : 'available'}`}
    >
      {cellAppointments.map((appt) => (
        <AppointmentBlock
          key={appt.id}
          appt={appt}
          loId={member.lo_id}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onMouseEnter={onAppointmentHover}
          onMouseLeave={onAppointmentLeave}
          getApptColorClass={getApptColorClass}
        />
      ))}
    </div>
  );
}

export default TeamMemberColumn;
