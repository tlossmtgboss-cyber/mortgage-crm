import React, { useState, useEffect, useRef, useCallback } from 'react';

/**
 * LiveRegion - Wrapper component for ARIA live regions that announces
 * dynamic content changes to screen readers.
 *
 * Features:
 * - Supports aria-live="polite" (default) and "assertive" modes
 * - Debounced updates to prevent announcement spam
 * - Clears previous content before announcing new content to ensure
 *   the screen reader detects the change
 * - Optional visual rendering or screen-reader-only mode
 *
 * Props:
 *   politeness   - "polite" (default) or "assertive"
 *   message      - The message to announce (when it changes, it's announced)
 *   debounceMs   - Debounce delay in milliseconds (default: 300)
 *   clearOnUnmount - Clear the region when the component unmounts (default: true)
 *   visible      - If true, render the content visually; if false, use sr-only style (default: false)
 *   as           - The HTML element to render (default: 'div')
 *   role         - ARIA role (default: 'status' for polite, 'alert' for assertive)
 *   atomic       - Whether to announce the entire region content (default: true)
 *   children     - If provided, renders children instead of message prop
 *   className    - Additional CSS class names
 */

const srOnlyStyle = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

const LiveRegion = React.forwardRef(function LiveRegion(
  {
    politeness = 'polite',
    message = '',
    debounceMs = 300,
    clearOnUnmount = true,
    visible = false,
    as: Component = 'div',
    role,
    atomic = true,
    children,
    className,
    style: customStyle,
    ...rest
  },
  ref
) {
  const [announcedMessage, setAnnouncedMessage] = useState('');
  const debounceTimerRef = useRef(null);
  const clearTimerRef = useRef(null);

  // Determine ARIA role based on politeness
  const ariaRole = role || (politeness === 'assertive' ? 'alert' : 'status');

  const announce = useCallback((msg) => {
    // Clear the region first to force screen readers to notice the change
    // even if the message is the same
    setAnnouncedMessage('');

    clearTimerRef.current = setTimeout(() => {
      setAnnouncedMessage(msg);
    }, 50); // Small delay to ensure the clear is processed
  }, []);

  useEffect(() => {
    // Debounce message updates
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    if (!message && !children) {
      setAnnouncedMessage('');
      return;
    }

    debounceTimerRef.current = setTimeout(() => {
      announce(message);
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (clearTimerRef.current) {
        clearTimeout(clearTimerRef.current);
      }
    };
  }, [message, debounceMs, announce, children]);

  // Clear on unmount
  useEffect(() => {
    return () => {
      if (clearOnUnmount) {
        setAnnouncedMessage('');
      }
    };
  }, [clearOnUnmount]);

  const computedStyle = visible
    ? customStyle || {}
    : { ...srOnlyStyle, ...(customStyle || {}) };

  return (
    <Component
      ref={ref}
      role={ariaRole}
      aria-live={politeness}
      aria-atomic={atomic}
      className={className}
      style={computedStyle}
      {...rest}
    >
      {children || announcedMessage}
    </Component>
  );
});

LiveRegion.displayName = 'LiveRegion';

export default LiveRegion;
