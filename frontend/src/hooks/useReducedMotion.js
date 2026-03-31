import { useState, useEffect, useCallback, useMemo } from 'react';

/**
 * useReducedMotion
 *
 * Reactive hook that tracks the OS / browser "prefers-reduced-motion"
 * media query. Returns the current preference plus convenience helpers
 * for conditionally applying animations, transitions, and durations.
 *
 * Usage:
 *   const { prefersReducedMotion, animate, transition, duration } = useReducedMotion();
 *
 *   <div style={{ animation: animate('fadeIn 300ms ease') }}>...</div>
 *   <div style={{ transition: transition('transform 200ms') }}>...</div>
 *   <div style={{ transitionDuration: `${duration(200)}ms` }}>...</div>
 */
export function useReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handler = (e) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  /** Return `animation` when motion is allowed, otherwise `fallback`. */
  const animate = useCallback(
    (animation, fallback = 'none') =>
      prefersReducedMotion ? fallback : animation,
    [prefersReducedMotion],
  );

  /** Return the CSS transition value or 'none'. */
  const transition = useCallback(
    (value) => (prefersReducedMotion ? 'none' : value),
    [prefersReducedMotion],
  );

  /** Return the duration in ms, or 0 when reduced motion is active. */
  const duration = useCallback(
    (ms) => (prefersReducedMotion ? 0 : ms),
    [prefersReducedMotion],
  );

  return useMemo(
    () => ({ prefersReducedMotion, animate, transition, duration }),
    [prefersReducedMotion, animate, transition, duration],
  );
}

export default useReducedMotion;
