import React from 'react';

/**
 * StatusBadge - Colored badge for appointment status display.
 *
 * Colors:
 *   green   = confirmed
 *   blue    = booked
 *   yellow  = pending / reminded
 *   red     = cancelled / no_show
 *   gray    = completed
 *   purple  = checked_in
 *   orange  = rescheduled
 */

const STATUS_CONFIG = {
  booked:      { label: 'Booked',      bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
  confirmed:   { label: 'Confirmed',   bg: '#dcfce7', color: '#166534', border: '#86efac' },
  reminded:    { label: 'Reminded',    bg: '#fef9c3', color: '#854d0e', border: '#fde047' },
  checked_in:  { label: 'Checked In',  bg: '#f3e8ff', color: '#6b21a8', border: '#c084fc' },
  completed:   { label: 'Completed',   bg: '#f3f4f6', color: '#374151', border: '#d1d5db' },
  cancelled:   { label: 'Cancelled',   bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  no_show:     { label: 'No Show',     bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  rescheduled: { label: 'Rescheduled', bg: '#ffedd5', color: '#9a3412', border: '#fdba74' },
  tentative:   { label: 'Tentative',   bg: '#fef9c3', color: '#854d0e', border: '#fde047' },
  available:   { label: 'Available',   bg: '#f3f4f6', color: '#6b7280', border: '#d1d5db' },
};

const baseStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  fontWeight: 600,
  borderRadius: '9999px',
  borderWidth: '1px',
  borderStyle: 'solid',
  whiteSpace: 'nowrap',
  lineHeight: 1,
};

const sizeStyles = {
  sm: { fontSize: '11px', padding: '2px 8px', height: '20px' },
  md: { fontSize: '12px', padding: '3px 10px', height: '24px' },
  lg: { fontSize: '13px', padding: '4px 12px', height: '28px' },
};

function StatusBadge({ status, size = 'md', showDot = true }) {
  const normalized = (status || '').toLowerCase().replace(/\s+/g, '_');
  const config = STATUS_CONFIG[normalized] || STATUS_CONFIG.available;
  const sizing = sizeStyles[size] || sizeStyles.md;

  const style = {
    ...baseStyle,
    ...sizing,
    backgroundColor: config.bg,
    color: config.color,
    borderColor: config.border,
  };

  const dotStyle = {
    width: size === 'sm' ? '5px' : '6px',
    height: size === 'sm' ? '5px' : '6px',
    borderRadius: '50%',
    backgroundColor: config.color,
    flexShrink: 0,
  };

  return (
    <span style={style} role="status" aria-label={`Status: ${config.label}`}>
      {showDot && <span style={dotStyle} aria-hidden="true" />}
      {config.label}
    </span>
  );
}

export { STATUS_CONFIG };
export default StatusBadge;
