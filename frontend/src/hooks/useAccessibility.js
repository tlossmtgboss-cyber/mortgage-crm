import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  announceToScreenReader,
  setFocusTo,
  detectScreenReaderHeuristic,
} from '../utils/accessibility';

/**
 * useAccessibility - Comprehensive accessibility hook for Perennia AI components.
 *
 * Provides:
 * - announce(message, priority)  Announce dynamic changes via aria-live
 * - focusRef                     Ref to attach to an element for programmatic focus
 * - focus()                      Move VoiceOver / screen reader focus to focusRef
 * - reduceMotion                 Whether prefers-reduced-motion is enabled
 * - prefersLargeText             Whether iOS Dynamic Type / font scaling is >1.0
 * - isScreenReaderActive         Heuristic detection of screen reader usage
 *
 * Usage:
 *   const { announce, focusRef, focus, reduceMotion, prefersLargeText, isScreenReaderActive } = useAccessibility();
 *
 *   useEffect(() => {
 *     announce('Pipeline loaded: 12 active loans');
 *   }, [loans]);
 *
 *   return <h2 ref={focusRef}>Dashboard</h2>;
 */
export function useAccessibility() {
  // -----------------------------------------------------------------------
  // prefers-reduced-motion
  // -----------------------------------------------------------------------
  const [reduceMotion, setReduceMotion] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e) => setReduceMotion(e.matches);

    if (mq.addEventListener) {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
    // Safari < 14 fallback
    mq.addListener(handler);
    return () => mq.removeListener(handler);
  }, []);

  // -----------------------------------------------------------------------
  // prefersLargeText (iOS Dynamic Type / browser font scaling)
  // -----------------------------------------------------------------------
  const [prefersLargeText, setPrefersLargeText] = useState(() => {
    if (typeof window === 'undefined') return false;
    // Detect font scaling: compare a 1rem element to 16px baseline.
    // If the user has increased system font size, 1rem will be > 16px.
    try {
      const testEl = document.createElement('div');
      testEl.style.cssText = 'font-size:1rem;position:absolute;visibility:hidden;';
      document.body.appendChild(testEl);
      const computedSize = parseFloat(getComputedStyle(testEl).fontSize);
      document.body.removeChild(testEl);
      return computedSize > 16;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    // Re-check on resize since iOS Dynamic Type changes may trigger a
    // viewport or font recalculation.
    if (typeof window === 'undefined') return;

    const checkFontScale = () => {
      try {
        const testEl = document.createElement('div');
        testEl.style.cssText = 'font-size:1rem;position:absolute;visibility:hidden;';
        document.body.appendChild(testEl);
        const computedSize = parseFloat(getComputedStyle(testEl).fontSize);
        document.body.removeChild(testEl);
        setPrefersLargeText(computedSize > 16);
      } catch {
        // Silently fail
      }
    };

    window.addEventListener('resize', checkFontScale);
    return () => window.removeEventListener('resize', checkFontScale);
  }, []);

  // -----------------------------------------------------------------------
  // Screen reader heuristic detection
  // -----------------------------------------------------------------------
  const [isScreenReaderActive, setIsScreenReaderActive] = useState(() => {
    return detectScreenReaderHeuristic();
  });

  useEffect(() => {
    // Re-evaluate when reduced motion changes (a common VoiceOver signal)
    setIsScreenReaderActive(detectScreenReaderHeuristic());
  }, [reduceMotion]);

  // Also listen for focus-visible indicators that suggest keyboard/SR navigation
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleFocusIn = () => {
      // If the user is navigating via keyboard (Tab), screen reader may be active
      if (document.querySelector('[data-focus-visible-added]') || document.querySelector(':focus-visible')) {
        setIsScreenReaderActive(true);
      }
    };

    // Debounce: only check periodically, not on every focus event
    let timeout;
    const debouncedHandler = () => {
      clearTimeout(timeout);
      timeout = setTimeout(handleFocusIn, 500);
    };

    document.addEventListener('focusin', debouncedHandler);
    return () => {
      document.removeEventListener('focusin', debouncedHandler);
      clearTimeout(timeout);
    };
  }, []);

  // -----------------------------------------------------------------------
  // Announce helper (stable callback)
  // -----------------------------------------------------------------------
  const announce = useCallback(
    /**
     * @param {string} message
     * @param {'assertive'|'polite'} [priority='assertive']
     */
    (message, priority = 'assertive') => {
      announceToScreenReader(message, priority);
    },
    []
  );

  // -----------------------------------------------------------------------
  // Focus management
  // -----------------------------------------------------------------------
  const focusRef = useRef(null);

  const focus = useCallback(
    /** @param {{ preventScroll?: boolean }} [options] */
    (options) => {
      setFocusTo(focusRef, options);
    },
    []
  );

  // -----------------------------------------------------------------------
  // Return stable object
  // -----------------------------------------------------------------------
  return useMemo(
    () => ({
      announce,
      focusRef,
      focus,
      reduceMotion,
      prefersLargeText,
      isScreenReaderActive,
    }),
    [announce, focus, reduceMotion, prefersLargeText, isScreenReaderActive]
  );
}

export default useAccessibility;
