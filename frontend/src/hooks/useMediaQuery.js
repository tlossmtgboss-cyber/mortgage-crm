import { useState, useEffect, useCallback } from 'react';

/**
 * useMediaQuery - Simple hook that tracks whether a CSS media query matches.
 *
 * Uses window.matchMedia for efficient, event-driven matching.
 * Returns a boolean indicating whether the query currently matches.
 *
 * @param {string} query - A CSS media query string, e.g. "(min-width: 768px)"
 * @returns {boolean} Whether the media query currently matches
 */
export function useMediaQuery(query) {
  const getMatches = useCallback(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  }, [query]);

  const [matches, setMatches] = useState(getMatches);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQueryList = window.matchMedia(query);

    // Set initial value (query may have changed)
    setMatches(mediaQueryList.matches);

    const handler = (event) => {
      setMatches(event.matches);
    };

    // Modern browsers support addEventListener on MediaQueryList
    if (mediaQueryList.addEventListener) {
      mediaQueryList.addEventListener('change', handler);
      return () => mediaQueryList.removeEventListener('change', handler);
    }

    // Fallback for older browsers (Safari < 14)
    mediaQueryList.addListener(handler);
    return () => mediaQueryList.removeListener(handler);
  }, [query]);

  return matches;
}

/**
 * useIsTablet - Detects tablet viewport (768px - 1024px).
 * @returns {boolean}
 */
export function useIsTablet() {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px)');
}

/**
 * useIsMobile - Detects mobile viewport (below 768px).
 * @returns {boolean}
 */
export function useIsMobile() {
  return useMediaQuery('(max-width: 767px)');
}

/**
 * useIsDesktop - Detects desktop viewport (above 1024px).
 * @returns {boolean}
 */
export function useIsDesktop() {
  return useMediaQuery('(min-width: 1025px)');
}

/**
 * useIsPortrait - Detects portrait orientation.
 * @returns {boolean}
 */
export function useIsPortrait() {
  return useMediaQuery('(orientation: portrait)');
}

/**
 * useIsLandscape - Detects landscape orientation.
 * @returns {boolean}
 */
export function useIsLandscape() {
  return useMediaQuery('(orientation: landscape)');
}

/**
 * useIsTabletPortrait - Detects tablet in portrait orientation.
 * @returns {boolean}
 */
export function useIsTabletPortrait() {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px) and (orientation: portrait)');
}

/**
 * useIsTabletLandscape - Detects tablet in landscape orientation.
 * @returns {boolean}
 */
export function useIsTabletLandscape() {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px) and (orientation: landscape)');
}

export default useMediaQuery;
