import React, { useEffect, useRef, useState } from 'react';

/**
 * NotificationBadge - Circular badge displaying unread notification count.
 *
 * Props:
 *   count    - Number of unread notifications
 *   max      - Maximum displayed count (default 99, shows "99+")
 *   variant  - "dot" (no number, just red dot) or "count" (number inside badge)
 */
const NotificationBadge = React.memo(function NotificationBadge({
  count = 0,
  max = 99,
  variant = 'count',
}) {
  const [pulse, setPulse] = useState(false);
  const prevCountRef = useRef(count);

  // Trigger pulse animation when count increases
  useEffect(() => {
    if (count > prevCountRef.current && count > 0) {
      setPulse(true);
      const timer = setTimeout(() => setPulse(false), 300);
      return () => clearTimeout(timer);
    }
    prevCountRef.current = count;
  }, [count]);

  if (count <= 0) return null;

  const displayCount = count > max ? `${max}+` : String(count);
  const label = `${count} unread notification${count !== 1 ? 's' : ''}`;

  if (variant === 'dot') {
    return (
      <span
        className={`notification-badge notification-badge-dot${pulse ? ' notification-badge-pulse' : ''}`}
        aria-label={label}
        role="status"
      />
    );
  }

  return (
    <span
      className={`notification-badge notification-badge-count${pulse ? ' notification-badge-pulse' : ''}`}
      aria-label={label}
      role="status"
    >
      {displayCount}
    </span>
  );
});

export default NotificationBadge;
