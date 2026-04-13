/**
 * SyncStatusBadge — Small numeric badge indicating pending offline mutations.
 *
 * Overlay this on nav items or buttons to show users that N changes are
 * waiting to sync. Renders nothing when count is 0.
 *
 * Usage:
 *   <div style={{ position: 'relative' }}>
 *     <NavIcon />
 *     <SyncStatusBadge count={pendingCount} />
 *   </div>
 */
import React from 'react';

const badgeStyle = {
  position: 'absolute',
  top: -4,
  right: -4,
  minWidth: 18,
  height: 18,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '0 5px',
  borderRadius: 9,
  backgroundColor: '#f59e0b',
  color: '#ffffff',
  fontSize: 11,
  fontWeight: 700,
  lineHeight: 1,
  boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
  pointerEvents: 'none',
  // Ensure badge doesn't shift layout of parent
  zIndex: 1,
};

export function SyncStatusBadge({ count }) {
  if (!count || count <= 0) return null;

  const display = count > 99 ? '99+' : String(count);

  return (
    <span style={badgeStyle} aria-label={`${count} pending sync`}>
      {display}
    </span>
  );
}

export default SyncStatusBadge;
